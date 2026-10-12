"""Experience data model and storage for Experience Manager (PRD 4.7).

Provides lightweight file-based experience storage with optional embedding support.
"""

import json
import logging
import random
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class Experience:
    """Represents an extracted experience from a successful trajectory.

    An experience captures a reusable pattern of tool usage that achieved
    a specific goal, allowing it to be retrieved and suggested for
    similar future tasks.
    """

    experience_id: str
    description: str
    tool_sequence: List[str]
    context_summary: str
    action_sequence: Optional[str] = None
    confidence: float = 1.0
    success_count: int = 1
    source_namespace: Optional[str] = None
    retrieval_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert experience to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Experience":
        """Create experience from dictionary."""
        # Backward compatibility: map old 'skill_id' key to 'experience_id'
        if "skill_id" in data and "experience_id" not in data:
            skill_id_value = data.pop("skill_id")
            data = {**data, "experience_id": skill_id_value}
        return cls(**data)

    def get_signature(self) -> str:
        """Get a unique signature for this experience based on tool sequence."""
        seq_str = ",".join(self.tool_sequence)
        return hashlib.md5(seq_str.encode()).hexdigest()[:12]


class ExperienceStore:
    """Lightweight file-based experience storage with deduplication.

    Stores experiences as JSON, with similarity-based deduplication
    to avoid storing redundant experiences.
    """

    def __init__(
        self,
        store_path: Path,
        max_experiences: int = 100,
        similarity_threshold: float = 0.85,
    ):
        """Initialize experience store.

        Args:
            store_path: Path to JSON file for experience storage
            max_experiences: Maximum number of experiences to retain
            similarity_threshold: Threshold for considering experiences as duplicates
        """
        self.store_path = Path(store_path)
        self.max_experiences = max_experiences
        self.similarity_threshold = similarity_threshold

        self._experiences: Dict[str, Experience] = {}
        self._lock = threading.Lock()

        self.load()

    def load(self):
        """Load experiences from disk."""
        try:
            if self.store_path.exists():
                with open(self.store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for exp_data in data.get("experiences", data.get("skills", [])):
                        exp = Experience.from_dict(exp_data)
                        self._experiences[exp.experience_id] = exp
                    logger.info(
                        f"Loaded {len(self._experiences)} experiences from {self.store_path}"
                    )
        except Exception as e:
            logger.warning(f"Failed to load experiences: {e}")
            self._experiences = {}

    def save(self):
        """Persist experiences to disk."""
        with self._lock:
            experiences_list = [e.to_dict() for e in self._experiences.values()]

        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "last_updated": datetime.now().isoformat(),
                "experience_count": len(experiences_list),
                "experiences": experiences_list,
            }

            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(
                f"Saved {len(experiences_list)} experiences to {self.store_path}"
            )
        except Exception as e:
            logger.error(f"Failed to save experiences: {e}")

    def add_experience(self, experience: Experience) -> bool:
        """Add an experience, deduplicate by similarity.

        Args:
            experience: The experience to add

        Returns:
            True if experience was added (not a duplicate), False otherwise
        """
        with self._lock:
            # Check for duplicates by signature
            new_sig = experience.get_signature()

            for existing in self._experiences.values():
                if existing.get_signature() == new_sig:
                    # Same tool sequence, increment success count
                    existing.success_count += 1
                    existing.last_used = datetime.now().isoformat()
                    logger.debug(
                        f"Merged duplicate experience, count now {existing.success_count}"
                    )
                    return False

                # Check text similarity if signatures differ
                if self._is_similar(experience.description, existing.description):
                    existing.success_count += 1
                    existing.last_used = datetime.now().isoformat()
                    logger.debug(
                        f"Merged similar experience, count now {existing.success_count}"
                    )
                    return False

            # New experience - add it
            self._experiences[experience.experience_id] = experience
            logger.info(f"Added new experience: {experience.experience_id}")

            # Evict oldest if over limit
            if len(self._experiences) > self.max_experiences:
                self._evict_oldest()

            return True

    def update_experience(self, experience: Experience):
        """Update an existing experience in the store."""
        with self._lock:
            if experience.experience_id in self._experiences:
                self._experiences[experience.experience_id] = experience
                logger.debug(f"Updated experience: {experience.experience_id}")
            else:
                logger.warning(
                    f"Attempted to update non-existent experience: {experience.experience_id}"
                )

    def _is_similar(self, text1: str, text2: str) -> bool:
        """Check if two texts are similar using simple token overlap."""
        if not text1 or not text2:
            return False

        tokens1 = set(text1.lower().split())
        tokens2 = set(text2.lower().split())

        if not tokens1 or not tokens2:
            return False

        intersection = tokens1 & tokens2
        union = tokens1 | tokens2

        similarity = len(intersection) / len(union) if union else 0
        return similarity >= self.similarity_threshold

    def _evict_oldest(self):
        """Evict the oldest/least used experiences to stay under limit."""
        if len(self._experiences) <= self.max_experiences:
            return

        # Sort by success_count (lower = evict first) then by created_at (older = evict first)
        sorted_experiences = sorted(
            self._experiences.values(), key=lambda e: (e.success_count, e.created_at)
        )

        # Remove oldest until under limit
        while len(self._experiences) > self.max_experiences:
            oldest = sorted_experiences.pop(0)
            del self._experiences[oldest.experience_id]
            logger.debug(f"Evicted experience: {oldest.experience_id}")

    def retrieve_experiences(
        self,
        query: str,
        top_k: int = 3,
        required_tools: Optional[List[str]] = None,
        boost_tools: Optional[List[str]] = None,
        source_namespace: Optional[str] = None,
        namespace_scoping_enabled: bool = False,
        increment_retrieval_count: bool = True,
    ) -> List[Experience]:
        """Retrieve relevant experiences using inverse-frequency weighted random sampling.

        Args:
            query: Query string (retained for signature compatibility; unused)
            top_k: Maximum number of experiences to return
            required_tools: Optional filter for experiences whose tool sequence
                is a subset of the available tools
            boost_tools: Optional list of tools that double the weight
            source_namespace: Only return experiences from this namespace
                when namespace_scoping_enabled is True
            namespace_scoping_enabled: Enable hard namespace filtering
            increment_retrieval_count: Whether to increment retrieval_count
                on selected experiences (set False for internal/evolution calls)

        Returns:
            List of relevant experiences selected via weighted random sampling
        """
        with self._lock:
            candidates = list(self._experiences.values())

        if not candidates:
            return []

        # Hard filter by source namespace
        if namespace_scoping_enabled and source_namespace:
            candidates = [
                e for e in candidates
                if e.source_namespace and e.source_namespace == source_namespace
            ]

        # Hard filter by available tools
        if required_tools:
            available_set = set(required_tools)
            candidates = [
                e
                for e in candidates
                if set(e.tool_sequence).issubset(available_set)
            ]

        if not candidates:
            return []

        boost_set = set(boost_tools) if boost_tools else set()

        # Compute inverse-frequency weights
        weights = []
        for exp in candidates:
            # Inverse frequency: higher retrieval_count → lower weight
            w = 1.0 / (1.0 + exp.retrieval_count)
            # Boost if experience uses preferred tools
            if boost_set and (boost_set & set(exp.tool_sequence)):
                w *= 2.0
            weights.append(w)

        # Weighted random sampling without replacement
        k = min(top_k, len(candidates))
        selected = _weighted_sample_without_replacement(candidates, weights, k)

        # Increment retrieval count for selected experiences
        if increment_retrieval_count:
            with self._lock:
                for exp in selected:
                    exp.retrieval_count += 1

        return selected

    def get_experience(self, experience_id: str) -> Optional[Experience]:
        """Get an experience by ID."""
        with self._lock:
            return self._experiences.get(experience_id)

    def get_all_experiences(self) -> List[Experience]:
        """Get all stored experiences."""
        with self._lock:
            return list(self._experiences.values())

    def get_stats(self) -> Dict[str, Any]:
        """Get experience store statistics."""
        with self._lock:
            experiences = list(self._experiences.values())

        if not experiences:
            return {
                "total_experiences": 0,
                "total_uses": 0,
                "avg_success_count": 0,
            }

        return {
            "total_experiences": len(experiences),
            "total_uses": sum(e.success_count for e in experiences),
            "avg_success_count": sum(e.success_count for e in experiences)
            / len(experiences),
            "tool_distribution": self._get_tool_distribution(experiences),
        }

    def _get_tool_distribution(
        self, experiences: List[Experience]
    ) -> Dict[str, int]:
        """Get distribution of tools across experiences."""
        dist: Dict[str, int] = {}
        for exp in experiences:
            for tool in exp.tool_sequence:
                dist[tool] = dist.get(tool, 0) + 1
        return dist


def _weighted_sample_without_replacement(
    candidates: List[Experience],
    weights: List[float],
    k: int,
) -> List[Experience]:
    """Sample k items from candidates using weighted random sampling without replacement.

    Items are selected one at a time with probability proportional to their
    weight, then removed from the pool. Weights are re-normalized after each
    selection. When all weights are zero, falls back to uniform random sampling.

    Args:
        candidates: List of candidate experiences.
        weights: Non-negative weight for each candidate (same length).
        k: Number of items to sample.

    Returns:
        Sampled experiences in selection order.
    """
    if k <= 0 or not candidates:
        return []

    pool = list(zip(range(len(candidates)), candidates, weights))
    selected: List[Experience] = []

    for _ in range(k):
        total_w = sum(w for _, _, w in pool)
        if total_w <= 0:
            # All zero weights — uniform random
            idx = random.randrange(len(pool))
        else:
            r = random.random() * total_w
            cumulative = 0.0
            idx = 0
            for i, (_, _, w) in enumerate(pool):
                cumulative += w
                if cumulative >= r:
                    idx = i
                    break

        selected.append(pool[idx][1])
        pool.pop(idx)

    return selected
