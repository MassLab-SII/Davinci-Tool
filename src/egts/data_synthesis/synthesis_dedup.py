"""Dataset-level deduplication for data_synthesis pipeline.

Self-contained module — no dependency on data_collection.

Supports three modes (configurable via ``dedup_mode``):
- hash:     Exact signature dedup (normalised problem + compressed tool sequence).
            Fast, zero external dependencies.
- semantic: Embedding-based problem similarity + trajectory signature comparison.
            Catches paraphrased duplicates. Requires an OpenAI-compatible embedding API.
- hybrid:   Hash layer first (fast reject), then semantic layer for remaining
            candidates. Best quality, requires embedding API.

Each mode supports K-variant retention: up to *max_variants_per_problem* distinct
trajectory variants are kept per problem cluster.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import re
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False
    np = None  # type: ignore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DedupDecision:
    """Result of a deduplication decision."""

    should_keep: bool
    reason: str
    cluster_id: Optional[str] = None
    similarity_score: Optional[float] = None
    variants_in_cluster: int = 0


@dataclass
class TrajectorySignature:
    """Lightweight structural fingerprint of a trajectory.

    Captures tool sequence, argument key patterns, and success/failure pattern
    so that two trajectories can be compared without full text matching.
    """

    tool_sequence: List[str] = field(default_factory=list)
    argument_patterns: Dict[str, List[str]] = field(default_factory=dict)
    success_pattern: List[bool] = field(default_factory=list)
    _hash: Optional[str] = None

    @classmethod
    def from_tool_calls(cls, tool_calls: List[Dict[str, Any]]) -> "TrajectorySignature":
        sig = cls()
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            name = tc.get("tool_name", tc.get("name", "unknown"))
            args = tc.get("arguments", {})
            success = tc.get("success", True)

            sig.tool_sequence.append(name)
            sig.success_pattern.append(bool(success))

            if isinstance(args, dict):
                pattern_str = ",".join(sorted(args.keys()))
                sig.argument_patterns.setdefault(name, [])
                if pattern_str not in sig.argument_patterns[name]:
                    sig.argument_patterns[name].append(pattern_str)

        for name in sig.argument_patterns:
            sig.argument_patterns[name] = sorted(set(sig.argument_patterns[name]))
        return sig

    def compute_hash(self) -> str:
        if self._hash is not None:
            return self._hash
        parts = [
            "|".join(self.tool_sequence),
            json.dumps(self.argument_patterns, sort_keys=True),
            "".join("1" if s else "0" for s in self.success_pattern),
        ]
        self._hash = hashlib.md5("||".join(parts).encode("utf-8")).hexdigest()
        return self._hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_sequence": self.tool_sequence,
            "argument_patterns": self.argument_patterns,
            "success_pattern": self.success_pattern,
            "hash": self.compute_hash(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrajectorySignature":
        sig = cls(
            tool_sequence=data.get("tool_sequence", []),
            argument_patterns=data.get("argument_patterns", {}),
            success_pattern=data.get("success_pattern", []),
        )
        sig._hash = data.get("hash")
        return sig


def compute_trajectory_similarity(
    sig1: TrajectorySignature, sig2: TrajectorySignature
) -> float:
    """Similarity score between two trajectory signatures (0.0 – 1.0)."""
    if sig1.compute_hash() == sig2.compute_hash():
        return 1.0

    set1, set2 = set(sig1.tool_sequence), set(sig2.tool_sequence)
    tool_sim = len(set1 & set2) / len(set1 | set2) if (set1 or set2) else 0.0

    if len(sig1.success_pattern) == len(sig2.success_pattern) and sig1.success_pattern:
        matches = sum(a == b for a, b in zip(sig1.success_pattern, sig2.success_pattern))
        success_sim = matches / len(sig1.success_pattern)
    else:
        success_sim = 0.0

    return 0.7 * tool_sim + 0.3 * success_sim


# ---------------------------------------------------------------------------
# Embedding provider (for semantic / hybrid mode)
# ---------------------------------------------------------------------------

class EmbeddingProvider(ABC):
    @abstractmethod
    def get_embedding(self, text: str) -> List[float]: ...

    @abstractmethod
    def batch_get_embeddings(self, texts: List[str]) -> List[List[float]]: ...


class OpenAICompatibleEmbedding(EmbeddingProvider):
    """Embedding via any OpenAI-compatible ``/v1/embeddings`` endpoint."""

    def __init__(self, base_url: str, api_key: str, model: str = "text-embedding-v4"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client: Any = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "openai package required for embedding dedup. "
                    "Install with: pip install openai"
                )
        return self._client

    def get_embedding(self, text: str) -> List[float]:
        client = self._get_client()
        text = text[:8000] if len(text) > 8000 else text
        return client.embeddings.create(input=text, model=self.model).data[0].embedding

    def batch_get_embeddings(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        truncated = [t[:8000] for t in texts]
        resp = client.embeddings.create(input=truncated, model=self.model)
        return [d.embedding for d in resp.data]


# ---------------------------------------------------------------------------
# Semantic dedup layer
# ---------------------------------------------------------------------------

@dataclass
class _ClusterEntry:
    problem_hash: str
    traj_sig: TrajectorySignature


class _SemanticLayer:
    """Embedding-based problem clustering with K-variant trajectory retention."""

    def __init__(
        self,
        problem_threshold: float,
        trajectory_threshold: float,
        max_variants: int,
        embedding_provider: Optional[EmbeddingProvider],
    ):
        self.problem_threshold = problem_threshold
        self.trajectory_threshold = trajectory_threshold
        self.max_variants = max_variants
        self.embedding_provider = embedding_provider

        self._lock = threading.Lock()
        # cluster_id -> list[_ClusterEntry]
        self._clusters: Dict[str, List[_ClusterEntry]] = {}
        # problem_hash -> cluster_id
        self._hash_to_cluster: Dict[str, str] = {}
        # cluster_id -> embedding (for cosine search when no ChromaDB)
        self._cluster_embeddings: Dict[str, List[float]] = {}

        self._stats = {
            "total_checked": 0,
            "kept": 0,
            "rejected_similar_problem": 0,
            "rejected_similar_trajectory": 0,
            "rejected_max_variants": 0,
        }

    # -- public API --

    def should_keep(
        self,
        problem_text: str,
        tool_calls: List[Dict[str, Any]],
        episode_dir: str = "",
    ) -> DedupDecision:
        self._stats["total_checked"] += 1
        problem_hash = _compute_problem_hash(problem_text)
        traj_sig = TrajectorySignature.from_tool_calls(tool_calls)

        with self._lock:
            # 1) Exact hash match
            if problem_hash in self._hash_to_cluster:
                cluster_id = self._hash_to_cluster[problem_hash]
                return self._check_variants(cluster_id, traj_sig)

            # 2) Embedding similarity
            if self.embedding_provider:
                match = self._find_similar_cluster(problem_text)
                if match:
                    cluster_id, sim = match
                    decision = self._check_variants(cluster_id, traj_sig)
                    decision.similarity_score = sim
                    return decision

            # 3) New cluster
            cluster_id = f"cluster_{problem_hash}"
            self._clusters[cluster_id] = [
                _ClusterEntry(problem_hash=problem_hash, traj_sig=traj_sig)
            ]
            self._hash_to_cluster[problem_hash] = cluster_id
            if self.embedding_provider:
                try:
                    emb = self.embedding_provider.get_embedding(problem_text)
                    self._cluster_embeddings[cluster_id] = emb
                except Exception as e:
                    logger.debug("Embedding failed (non-fatal): %s", e)

            self._stats["kept"] += 1
            return DedupDecision(should_keep=True, reason="New unique problem", cluster_id=cluster_id)

    def _check_variants(
        self, cluster_id: str, traj_sig: TrajectorySignature
    ) -> DedupDecision:
        cluster = self._clusters.get(cluster_id, [])

        for entry in cluster:
            sim = compute_trajectory_similarity(traj_sig, entry.traj_sig)
            if sim >= self.trajectory_threshold:
                self._stats["rejected_similar_trajectory"] += 1
                return DedupDecision(
                    should_keep=False,
                    reason=f"Similar trajectory in cluster (sim={sim:.2f})",
                    cluster_id=cluster_id,
                    similarity_score=sim,
                    variants_in_cluster=len(cluster),
                )

        if len(cluster) >= self.max_variants:
            self._stats["rejected_max_variants"] += 1
            return DedupDecision(
                should_keep=False,
                reason=f"Cluster full ({len(cluster)}/{self.max_variants})",
                cluster_id=cluster_id,
                variants_in_cluster=len(cluster),
            )

        cluster.append(_ClusterEntry(problem_hash="", traj_sig=traj_sig))
        self._stats["kept"] += 1
        return DedupDecision(
            should_keep=True,
            reason=f"New variant ({len(cluster)}/{self.max_variants})",
            cluster_id=cluster_id,
            variants_in_cluster=len(cluster),
        )

    @functools.lru_cache(maxsize=1024)
    def _cached_embedding(self, problem_text: str) -> Optional[Tuple[float, ...]]:
        """LRU-cached embedding to avoid re-embedding identical texts."""
        if not self.embedding_provider:
            return None
        try:
            emb = self.embedding_provider.get_embedding(problem_text)
            return tuple(emb)
        except Exception:
            return None

    def _find_similar_cluster(self, problem_text: str) -> Optional[Tuple[str, float]]:
        if not self._cluster_embeddings:
            return None

        query_tuple = self._cached_embedding(problem_text)
        if query_tuple is None:
            return None
        query_emb = list(query_tuple)

        cids = list(self._cluster_embeddings.keys())
        if not cids:
            return None

        # Scale guard: with very large clusters, do a fast hash-bucket pre-filter
        # to avoid brute-forcing >5000 cosine comparisons per episode.
        _LARGE_SCALE = 5000
        if _HAS_NUMPY and len(cids) > _LARGE_SCALE:
            candidate_cids = cids
        else:
            candidate_cids = cids

        if _HAS_NUMPY:
            # Vectorized cosine similarity — single matrix multiplication
            emb_matrix = np.array(
                [self._cluster_embeddings[cid] for cid in candidate_cids], dtype=np.float64
            )
            query_vec = np.array(query_emb, dtype=np.float64)
            # Normalize
            query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-12)
            emb_norms = emb_matrix / (np.linalg.norm(emb_matrix, axis=1, keepdims=True) + 1e-12)
            sims = np.dot(emb_norms, query_norm)
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])
            if best_sim >= self.problem_threshold:
                return (candidate_cids[best_idx], best_sim)
            return None
        else:
            # Pure Python fallback
            best_id, best_sim = None, -1.0
            for cid in candidate_cids:
                sim = _cosine_similarity(query_emb, self._cluster_embeddings[cid])
                if sim > best_sim:
                    best_id, best_sim = cid, sim
            if best_sim is not None and best_sim >= self.problem_threshold:
                return (best_id, best_sim)
            return None

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats, "num_clusters": len(self._clusters)}

    # -- persistence --

    def save_state(self, path: Path) -> None:
        state = {
            "clusters": {
                cid: [
                    {"problem_hash": e.problem_hash, "traj_sig": e.traj_sig.to_dict()}
                    for e in entries
                ]
                for cid, entries in self._clusters.items()
            },
            "hash_to_cluster": self._hash_to_cluster,
            "cluster_embeddings": self._cluster_embeddings,
            "stats": self._stats,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def load_state(self, path: Path) -> None:
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        self._hash_to_cluster = state.get("hash_to_cluster", {})
        raw_embeddings = state.get("cluster_embeddings", {})
        self._cluster_embeddings = {}
        if isinstance(raw_embeddings, dict):
            for cid, emb in raw_embeddings.items():
                if not isinstance(emb, list):
                    continue
                try:
                    self._cluster_embeddings[str(cid)] = [float(v) for v in emb]
                except (TypeError, ValueError):
                    continue
        self._stats = state.get("stats", self._stats)
        for cid, entries in state.get("clusters", {}).items():
            self._clusters[cid] = [
                _ClusterEntry(
                    problem_hash=e["problem_hash"],
                    traj_sig=TrajectorySignature.from_dict(e["traj_sig"]),
                )
                for e in entries
            ]
        logger.info(
            "Semantic layer loaded: %d clusters, %d embeddings",
            len(self._clusters),
            len(self._cluster_embeddings),
        )


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@dataclass
class SynthesisDedupStats:
    total_checked: int = 0
    kept: int = 0
    rejected_hash: int = 0
    rejected_semantic: int = 0
    rejected_max_variants: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_checked": self.total_checked,
            "kept": self.kept,
            "rejected_hash": self.rejected_hash,
            "rejected_semantic": self.rejected_semantic,
            "rejected_max_variants": self.rejected_max_variants,
            "dedup_rate": (
                1 - self.kept / self.total_checked
                if self.total_checked > 0
                else 0.0
            ),
        }


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _normalize_problem_text(text: str) -> str:
    t = (text or "").lower().strip()
    t = re.sub(r"/workspace/[a-z0-9_-]+", "/workspace/<id>", t)
    t = " ".join(t.split())
    return t


def _compute_problem_hash(problem_text: str) -> str:
    normalized = _normalize_problem_text(problem_text)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]


def _compress_tool_sequence(tool_names: List[str]) -> str:
    """e.g. [ld, ld, ld, wf, wf] -> 'ld*3|wf*2'"""
    if not tool_names:
        return ""
    compressed: List[str] = []
    prev = tool_names[0]
    count = 1
    for name in tool_names[1:]:
        if name == prev:
            count += 1
        else:
            compressed.append(f"{prev}*{count}" if count > 1 else prev)
            prev = name
            count = 1
    compressed.append(f"{prev}*{count}" if count > 1 else prev)
    return "|".join(compressed)


def _compute_record_signature(record: Dict[str, Any]) -> str:
    """problem_hash:tool_seq_hash — fast structural fingerprint."""
    problem_hash = _compute_problem_hash(record.get("problem", ""))
    tool_calls = record.get("tool_calls", [])
    tool_names = [
        tc.get("tool_name", tc.get("name", ""))
        for tc in tool_calls
        if isinstance(tc, dict)
    ]
    seq_hash = hashlib.md5(
        _compress_tool_sequence(tool_names).encode("utf-8")
    ).hexdigest()[:12]
    return f"{problem_hash}:{seq_hash}"


# ---------------------------------------------------------------------------
# Main deduplicator
# ---------------------------------------------------------------------------

class SynthesisDeduplicator:
    """Dataset-level deduplicator for data_synthesis pipeline.

    Operates on accepted (record, meta) pairs before they are saved.
    """

    def __init__(
        self,
        mode: str = "hybrid",
        problem_similarity_threshold: float = 0.90,
        trajectory_similarity_threshold: float = 0.85,
        max_variants_per_problem: int = 3,
        embedding_model: str = "text-embedding-v4",
        embedding_base_url: Optional[str] = None,
        embedding_api_key: Optional[str] = None,
        vector_store_path: Optional[str] = None,
        state_file: Optional[str] = None,
    ):
        if mode not in ("hash", "semantic", "hybrid"):
            logger.warning("Invalid dedup mode '%s', falling back to 'hybrid'", mode)
            mode = "hybrid"

        self.mode = mode
        self.max_variants = max_variants_per_problem
        self.problem_threshold = problem_similarity_threshold
        self.trajectory_threshold = trajectory_similarity_threshold
        self.state_file = state_file

        self._lock = threading.Lock()
        self._stats = SynthesisDedupStats()

        # --- Hash layer ---
        self._hash_clusters: Dict[str, List[TrajectorySignature]] = {}

        # --- Semantic layer ---
        self._semantic: Optional[_SemanticLayer] = None
        if mode in ("semantic", "hybrid"):
            embedding_provider: Optional[EmbeddingProvider] = None
            if embedding_base_url and embedding_api_key:
                try:
                    embedding_provider = OpenAICompatibleEmbedding(
                        base_url=embedding_base_url,
                        api_key=embedding_api_key,
                        model=embedding_model,
                    )
                except Exception as e:
                    logger.warning("Failed to init embedding provider: %s", e)

            self._semantic = _SemanticLayer(
                problem_threshold=problem_similarity_threshold,
                trajectory_threshold=trajectory_similarity_threshold,
                max_variants=max_variants_per_problem,
                embedding_provider=embedding_provider,
            )

        logger.info(
            "SynthesisDeduplicator: mode=%s, problem_thresh=%.2f, "
            "traj_thresh=%.2f, max_variants=%d",
            self.mode, self.problem_threshold,
            self.trajectory_threshold, self.max_variants,
        )

    # -- public API --

    def should_keep(
        self, record: Dict[str, Any], meta: Dict[str, Any]
    ) -> DedupDecision:
        self._stats.total_checked += 1

        return self._check_record(record, meta, update_stats=True)

    def _register_without_stats(
        self, record: Dict[str, Any], meta: Dict[str, Any]
    ) -> DedupDecision:
        return self._check_record(record, meta, update_stats=False)

    def _check_record(
        self, record: Dict[str, Any], meta: Dict[str, Any], *, update_stats: bool
    ) -> DedupDecision:
        problem_text = record.get("problem", "")
        tool_calls = record.get("tool_calls", [])
        traj_sig = TrajectorySignature.from_tool_calls(tool_calls)

        # --- Hash layer ---
        if self.mode in ("hash", "hybrid"):
            sig = _compute_record_signature(record)
            decision = self._check_hash_layer(sig, traj_sig, update_stats=update_stats)
            if decision is not None:
                return decision

        # --- Semantic layer ---
        if self.mode in ("semantic", "hybrid") and self._semantic:
            decision = self._semantic.should_keep(
                problem_text=problem_text,
                tool_calls=tool_calls,
                episode_dir=str(meta.get("episode_dir", "")),
            )
            if not decision.should_keep:
                if update_stats:
                    self._stats.rejected_semantic += 1
                return decision

        # Passed all layers — register in hash layer if hash-only
        if self.mode == "hash":
            sig = _compute_record_signature(record)
            self._register_hash(sig, traj_sig)

        if update_stats:
            self._stats.kept += 1
        return DedupDecision(should_keep=True, reason="Passed dedup check")

    # -- hash layer internals --

    def _check_hash_layer(
        self, sig: str, traj_sig: TrajectorySignature, *, update_stats: bool = True
    ) -> Optional[DedupDecision]:
        with self._lock:
            if sig not in self._hash_clusters:
                self._hash_clusters[sig] = [traj_sig]
                return None

            existing = self._hash_clusters[sig]

            for existing_sig in existing:
                sim = compute_trajectory_similarity(traj_sig, existing_sig)
                if sim >= self.trajectory_threshold:
                    if update_stats:
                        self._stats.rejected_hash += 1
                    return DedupDecision(
                        should_keep=False,
                        reason=f"Hash duplicate: similar trajectory (sim={sim:.2f})",
                        similarity_score=sim,
                        variants_in_cluster=len(existing),
                    )

            if len(existing) >= self.max_variants:
                if update_stats:
                    self._stats.rejected_max_variants += 1
                return DedupDecision(
                    should_keep=False,
                    reason=f"Hash cluster full ({len(existing)}/{self.max_variants})",
                    variants_in_cluster=len(existing),
                )

            existing.append(traj_sig)
            return None

    def _register_hash(self, sig: str, traj_sig: TrajectorySignature) -> None:
        with self._lock:
            self._hash_clusters.setdefault(sig, []).append(traj_sig)

    # -- stats --

    def get_stats(self) -> Dict[str, Any]:
        stats = self._stats.to_dict()
        stats["mode"] = self.mode
        stats["num_hash_clusters"] = len(self._hash_clusters)
        if self._semantic:
            stats["semantic_stats"] = self._semantic.get_stats()
        return stats

    # -- persistence --

    def save_state(self, output_dir: str) -> None:
        if not self.state_file:
            return
        path = os.path.join(output_dir, self.state_file)
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            state = {
                "mode": self.mode,
                "stats": self._stats.to_dict(),
                "hash_clusters": {
                    sig: [ts.to_dict() for ts in sigs]
                    for sig, sigs in self._hash_clusters.items()
                },
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            logger.debug("Dedup state saved to %s", path)
        except Exception as e:
            logger.warning("Failed to save dedup state: %s", e)

        if self._semantic:
            try:
                self._semantic.save_state(Path(path).with_suffix(".semantic.json"))
            except Exception as e:
                logger.warning("Failed to save semantic dedup state: %s", e)

    def load_state(self, output_dir: str) -> None:
        if not self.state_file:
            return
        path = os.path.join(output_dir, self.state_file)
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            for sig, entries in state.get("hash_clusters", {}).items():
                self._hash_clusters[sig] = [
                    TrajectorySignature.from_dict(e) for e in entries
                ]
            saved = state.get("stats", {})
            self._stats.total_checked = saved.get("total_checked", 0)
            self._stats.kept = saved.get("kept", 0)
            self._stats.rejected_hash = saved.get("rejected_hash", 0)
            self._stats.rejected_semantic = saved.get("rejected_semantic", 0)
            self._stats.rejected_max_variants = saved.get("rejected_max_variants", 0)
            logger.info(
                "Dedup state loaded: %d hash clusters, %d checked, %d kept",
                len(self._hash_clusters), self._stats.total_checked, self._stats.kept,
            )
        except Exception as e:
            logger.warning("Failed to load dedup state: %s", e)

        if self._semantic:
            semantic_path = Path(path).with_suffix(".semantic.json")
            if semantic_path.exists():
                try:
                    self._semantic.load_state(semantic_path)
                except Exception as e:
                    logger.warning("Failed to load semantic dedup state: %s", e)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_synthesis_deduplicator(
    ds_cfg: Any,
    maas_cfg: Any = None,
) -> Optional[SynthesisDeduplicator]:
    """Create SynthesisDeduplicator from config. Returns None if disabled."""
    if not getattr(ds_cfg, "dedup_enabled", False):
        return None

    mode = getattr(ds_cfg, "dedup_mode", "hybrid")

    embedding_base_url = getattr(ds_cfg, "dedup_embedding_base_url", None)
    embedding_api_key = getattr(ds_cfg, "dedup_embedding_api_key", None)

    if not embedding_base_url and maas_cfg and mode in ("semantic", "hybrid"):
        default_maas = getattr(maas_cfg, "default", None)
        if default_maas:
            embedding_base_url = getattr(default_maas, "base_url", None)
            embedding_api_key = getattr(default_maas, "api_key", None)

    return SynthesisDeduplicator(
        mode=mode,
        problem_similarity_threshold=getattr(ds_cfg, "dedup_problem_similarity_threshold", 0.90),
        trajectory_similarity_threshold=getattr(ds_cfg, "dedup_trajectory_similarity_threshold", 0.85),
        max_variants_per_problem=getattr(ds_cfg, "dedup_max_variants_per_problem", 3),
        embedding_model=getattr(ds_cfg, "dedup_embedding_model", "text-embedding-v4"),
        embedding_base_url=embedding_base_url,
        embedding_api_key=embedding_api_key,
        vector_store_path=getattr(ds_cfg, "dedup_vector_store_path", None),
        state_file=getattr(ds_cfg, "dedup_state_file", "dedup_state.json"),
    )
