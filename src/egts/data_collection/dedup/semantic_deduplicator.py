"""Semantic deduplication for problem text using embeddings.

Implements embedding-based near-duplicate detection with cluster-aware
K-variant retention (same problem, different trajectories).

Reference: AgentEvolver's deduplication/embedding.py using ChromaDB.
"""

import hashlib
import json
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

from .trajectory_signature import TrajectorySignature, compute_trajectory_similarity

logger = logging.getLogger(__name__)


@dataclass
class DedupDecision:
    """Result of a deduplication decision."""

    should_keep: bool
    reason: str
    cluster_id: Optional[str] = None
    similarity_score: Optional[float] = None
    variants_in_cluster: int = 0
    closest_match: Optional[str] = None  # Path or ID of closest existing sample


@dataclass
class ClusterEntry:
    """An entry in a problem cluster."""

    problem_hash: str
    trajectory_signature: TrajectorySignature
    sample_path: Path
    problem_text_preview: str
    added_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "problem_hash": self.problem_hash,
            "trajectory_signature": self.trajectory_signature.to_dict(),
            "sample_path": str(self.sample_path),
            "problem_text_preview": self.problem_text_preview[:100],
            "added_at": self.added_at,
        }


class EmbeddingProvider(ABC):
    """Abstract base for embedding providers."""

    @abstractmethod
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding vector for text."""
        pass

    @abstractmethod
    def batch_get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts."""
        pass


class OpenAICompatibleEmbedding(EmbeddingProvider):
    """Embedding provider using OpenAI-compatible API."""

    def __init__(self, base_url: str, api_key: str, model: str = "text-embedding-v4"):
        """Initialize embedding provider.

        Args:
            base_url: API base URL (e.g., https://api.openai.com/v1 or compatible)
            api_key: API key
            model: Model name for embeddings
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

        # Lazy import to avoid dependency issues
        self._client = None

    def _get_client(self):
        """Get or create OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "openai package required for embedding. "
                    "Install with: pip install openai"
                )
        return self._client

    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for single text."""
        client = self._get_client()

        # Truncate text if too long (typical limit ~8192 tokens)
        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars]

        response = client.embeddings.create(input=text, model=self.model)

        return response.data[0].embedding

    def batch_get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts."""
        client = self._get_client()

        # Truncate texts
        max_chars = 8000
        truncated = [t[:max_chars] if len(t) > max_chars else t for t in texts]

        response = client.embeddings.create(input=truncated, model=self.model)

        return [d.embedding for d in response.data]


class SemanticDeduplicator:
    """Semantic deduplication with embedding-based similarity and K-variant retention.

    Features:
    - Problem text embedding similarity (near-duplicate detection)
    - Cluster-aware storage: group similar problems together
    - K-variant retention: keep up to K different trajectories per problem cluster
    - Trajectory signature comparison to distinguish "different" trajectories
    """

    def __init__(
        self,
        problem_similarity_threshold: float = 0.90,
        trajectory_similarity_threshold: float = 0.85,
        max_trajectories_per_problem: int = 3,
        embedding_provider: Optional[EmbeddingProvider] = None,
        vector_store_path: Optional[Path] = None,
        use_chroma: bool = True,
    ):
        """Initialize semantic deduplicator.

        Args:
            problem_similarity_threshold: Cosine similarity threshold for "same problem"
            trajectory_similarity_threshold: Threshold for "same trajectory" (using signatures)
            max_trajectories_per_problem: Max variants to keep per problem cluster
            embedding_provider: Provider for text embeddings (optional)
            vector_store_path: Path for persistent vector storage
            use_chroma: Whether to use ChromaDB (requires chromadb package)
        """
        self.problem_threshold = problem_similarity_threshold
        self.trajectory_threshold = trajectory_similarity_threshold
        self.max_trajectories = max_trajectories_per_problem
        self.embedding_provider = embedding_provider
        self.vector_store_path = vector_store_path
        self.use_chroma = use_chroma and self._check_chroma_available()

        # Thread safety
        self._lock = threading.Lock()

        # In-memory cluster storage (fallback if no ChromaDB)
        # cluster_id -> list of ClusterEntry
        self._clusters: Dict[str, List[ClusterEntry]] = {}

        # Problem text hash -> cluster_id mapping
        self._hash_to_cluster: Dict[str, str] = {}

        # ChromaDB collection (if available)
        self._chroma_client = None
        self._chroma_collection = None

        if self.use_chroma:
            self._init_chroma()

        # Statistics
        self._stats = {
            "total_checked": 0,
            "kept": 0,
            "deduplicated_exact": 0,
            "deduplicated_similar_problem": 0,
            "deduplicated_max_variants": 0,
        }

        logger.info(
            f"SemanticDeduplicator initialized: "
            f"problem_threshold={problem_similarity_threshold}, "
            f"trajectory_threshold={trajectory_similarity_threshold}, "
            f"max_variants={max_trajectories_per_problem}, "
            f"use_chroma={self.use_chroma}"
        )

    def _check_chroma_available(self) -> bool:
        """Check if ChromaDB is available."""
        try:
            import chromadb

            return True
        except ImportError:
            logger.warning("chromadb not installed, using in-memory deduplication")
            return False

    def _init_chroma(self):
        """Initialize ChromaDB collection."""
        try:
            import chromadb
            from chromadb.config import Settings

            if self.vector_store_path:
                # Persistent storage
                self.vector_store_path.mkdir(parents=True, exist_ok=True)
                self._chroma_client = chromadb.PersistentClient(
                    path=str(self.vector_store_path),
                    settings=Settings(anonymized_telemetry=False),
                )
            else:
                # In-memory
                self._chroma_client = chromadb.Client(
                    settings=Settings(anonymized_telemetry=False)
                )

            self._chroma_collection = self._chroma_client.get_or_create_collection(
                name="problem_embeddings", metadata={"hnsw:space": "cosine"}
            )

            logger.info(
                f"ChromaDB initialized with {self._chroma_collection.count()} entries"
            )

        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            self.use_chroma = False

    def _compute_problem_hash(self, problem_text: str) -> str:
        """Compute hash of normalized problem text."""
        normalized = " ".join(problem_text.lower().strip().split())
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]

    def should_keep(
        self,
        problem_text: str,
        trajectory: Dict[str, Any],
        diff: Optional[Dict[str, Any]] = None,
        sample_path: Optional[Path] = None,
    ) -> DedupDecision:
        """Decide whether to keep this sample.

        Args:
            problem_text: The synthesized problem text
            trajectory: The trajectory data
            diff: Optional filesystem diff
            sample_path: Path where sample will be saved

        Returns:
            DedupDecision indicating whether to keep and why
        """
        self._stats["total_checked"] += 1

        problem_hash = self._compute_problem_hash(problem_text)
        traj_sig = TrajectorySignature.from_trajectory(trajectory, diff)

        with self._lock:
            # Check for exact hash match first (fast path)
            if problem_hash in self._hash_to_cluster:
                cluster_id = self._hash_to_cluster[problem_hash]
                return self._check_cluster_variants(
                    cluster_id, traj_sig, problem_text, sample_path
                )

            # Check for semantic similarity (if embeddings available)
            if self.use_chroma and self.embedding_provider and self._chroma_collection:
                similar_result = self._find_similar_problem(problem_text)
                if similar_result:
                    cluster_id, similarity = similar_result
                    decision = self._check_cluster_variants(
                        cluster_id, traj_sig, problem_text, sample_path
                    )
                    decision.similarity_score = similarity
                    return decision

            # No match found - create new cluster
            cluster_id = self._create_cluster(
                problem_hash, problem_text, traj_sig, sample_path
            )

            self._stats["kept"] += 1

            return DedupDecision(
                should_keep=True,
                reason="New unique problem",
                cluster_id=cluster_id,
                variants_in_cluster=1,
            )

    def _find_similar_problem(self, problem_text: str) -> Optional[Tuple[str, float]]:
        """Find semantically similar problem in vector store.

        Returns:
            (cluster_id, similarity_score) if found, None otherwise
        """
        if not self.embedding_provider or not self._chroma_collection:
            return None

        try:
            # Get embedding for this problem
            embedding = self.embedding_provider.get_embedding(problem_text)

            # Query ChromaDB
            results = self._chroma_collection.query(
                query_embeddings=[embedding],
                n_results=1,
                include=["metadatas", "distances"],
            )

            if not results["ids"] or not results["ids"][0]:
                return None

            # ChromaDB returns distance, convert to similarity
            distance = results["distances"][0][0]
            similarity = 1 - distance  # For cosine distance

            if similarity >= self.problem_threshold:
                metadata = results["metadatas"][0][0]
                cluster_id = metadata.get("cluster_id")
                return (cluster_id, similarity)

            return None

        except Exception as e:
            logger.warning(f"Error querying vector store: {e}")
            return None

    def _check_cluster_variants(
        self,
        cluster_id: str,
        traj_sig: TrajectorySignature,
        problem_text: str,
        sample_path: Optional[Path],
    ) -> DedupDecision:
        """Check if we should add another variant to an existing cluster.

        Args:
            cluster_id: ID of the existing cluster
            traj_sig: Trajectory signature of new sample
            problem_text: Problem text
            sample_path: Path for new sample

        Returns:
            DedupDecision
        """
        cluster = self._clusters.get(cluster_id, [])

        # Check if trajectory is similar to any existing variant
        for entry in cluster:
            similarity = compute_trajectory_similarity(
                traj_sig, entry.trajectory_signature
            )

            if similarity >= self.trajectory_threshold:
                self._stats["deduplicated_exact"] += 1
                return DedupDecision(
                    should_keep=False,
                    reason=f"Similar trajectory exists in cluster (sim={similarity:.2f})",
                    cluster_id=cluster_id,
                    similarity_score=similarity,
                    variants_in_cluster=len(cluster),
                    closest_match=str(entry.sample_path),
                )

        # Check if cluster is full
        if len(cluster) >= self.max_trajectories:
            self._stats["deduplicated_max_variants"] += 1
            return DedupDecision(
                should_keep=False,
                reason=f"Cluster full ({len(cluster)}/{self.max_trajectories} variants)",
                cluster_id=cluster_id,
                variants_in_cluster=len(cluster),
            )

        # Add new variant to cluster
        self._add_to_cluster(cluster_id, problem_text, traj_sig, sample_path)
        self._stats["kept"] += 1

        return DedupDecision(
            should_keep=True,
            reason=f"New trajectory variant ({len(cluster) + 1}/{self.max_trajectories})",
            cluster_id=cluster_id,
            variants_in_cluster=len(cluster) + 1,
        )

    def _create_cluster(
        self,
        problem_hash: str,
        problem_text: str,
        traj_sig: TrajectorySignature,
        sample_path: Optional[Path],
    ) -> str:
        """Create a new problem cluster.

        Returns:
            The new cluster ID
        """
        cluster_id = f"cluster_{problem_hash}"

        # Create cluster with first entry
        entry = ClusterEntry(
            problem_hash=problem_hash,
            trajectory_signature=traj_sig,
            sample_path=sample_path or Path("unknown"),
            problem_text_preview=problem_text[:100],
        )

        self._clusters[cluster_id] = [entry]
        self._hash_to_cluster[problem_hash] = cluster_id

        if self.use_chroma and self.embedding_provider and self._chroma_collection:
            try:
                embedding = self.embedding_provider.get_embedding(problem_text)
                self._chroma_collection.add(
                    embeddings=[embedding],
                    ids=[cluster_id],
                    metadatas=[
                        {"cluster_id": cluster_id, "problem_hash": problem_hash}
                    ],
                    documents=[problem_text[:1000]],
                )
            except Exception as e:
                error_str = str(e)
                if "502" in error_str or "504" in error_str:
                    logger.debug(f"Failed to add to vector store (transient): {e}")
                else:
                    logger.warning(f"Failed to add to vector store: {e}")

        return cluster_id

    def _add_to_cluster(
        self,
        cluster_id: str,
        problem_text: str,
        traj_sig: TrajectorySignature,
        sample_path: Optional[Path],
    ):
        """Add a new entry to an existing cluster."""
        problem_hash = self._compute_problem_hash(problem_text)

        entry = ClusterEntry(
            problem_hash=problem_hash,
            trajectory_signature=traj_sig,
            sample_path=sample_path or Path("unknown"),
            problem_text_preview=problem_text[:100],
        )

        if cluster_id not in self._clusters:
            self._clusters[cluster_id] = []

        self._clusters[cluster_id].append(entry)

    def get_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        with self._lock:
            return {
                **self._stats,
                "num_clusters": len(self._clusters),
                "total_variants": sum(len(c) for c in self._clusters.values()),
                "avg_variants_per_cluster": (
                    sum(len(c) for c in self._clusters.values()) / len(self._clusters)
                    if self._clusters
                    else 0.0
                ),
                "dedup_rate": (
                    1 - self._stats["kept"] / self._stats["total_checked"]
                    if self._stats["total_checked"] > 0
                    else 0.0
                ),
            }

    def get_report(self) -> Dict[str, Any]:
        """Get detailed deduplication report."""
        stats = self.get_stats()

        # Get cluster size distribution
        cluster_sizes = [len(c) for c in self._clusters.values()]
        size_distribution = {}
        for size in cluster_sizes:
            size_distribution[size] = size_distribution.get(size, 0) + 1

        return {
            "summary": stats,
            "cluster_size_distribution": size_distribution,
            "sample_clusters": [
                {
                    "cluster_id": cid,
                    "num_variants": len(entries),
                    "preview": entries[0].problem_text_preview if entries else "",
                }
                for cid, entries in list(self._clusters.items())[:10]
            ],
            "settings": {
                "problem_similarity_threshold": self.problem_threshold,
                "trajectory_similarity_threshold": self.trajectory_threshold,
                "max_trajectories_per_problem": self.max_trajectories,
                "use_chroma": self.use_chroma,
            },
        }

    def save_state(self, path: Path):
        """Save deduplicator state to disk."""
        state = {
            "clusters": {
                cid: [e.to_dict() for e in entries]
                for cid, entries in self._clusters.items()
            },
            "hash_to_cluster": self._hash_to_cluster,
            "stats": self._stats,
            "settings": {
                "problem_threshold": self.problem_threshold,
                "trajectory_threshold": self.trajectory_threshold,
                "max_trajectories": self.max_trajectories,
            },
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

        logger.info(f"Dedup state saved to {path}")

    def load_state(self, path: Path):
        """Load deduplicator state from disk."""
        if not path.exists():
            logger.warning(f"Dedup state file not found: {path}")
            return

        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)

        self._hash_to_cluster = state.get("hash_to_cluster", {})
        self._stats = state.get("stats", self._stats)

        # Reconstruct clusters
        for cid, entries in state.get("clusters", {}).items():
            self._clusters[cid] = [
                ClusterEntry(
                    problem_hash=e["problem_hash"],
                    trajectory_signature=TrajectorySignature.from_dict(
                        e["trajectory_signature"]
                    ),
                    sample_path=Path(e["sample_path"]),
                    problem_text_preview=e["problem_text_preview"],
                    added_at=e.get("added_at", ""),
                )
                for e in entries
            ]

        logger.info(f"Dedup state loaded: {len(self._clusters)} clusters")
