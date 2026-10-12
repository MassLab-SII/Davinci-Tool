"""Semantic deduplication module for mcp-trajs2data.

Provides embedding-based near-duplicate detection with K-variant retention
for improved data diversity while reducing redundancy.
"""

from .trajectory_signature import (
    TrajectorySignature,
    compute_trajectory_similarity,
)

from .semantic_deduplicator import (
    SemanticDeduplicator,
    DedupDecision,
    ClusterEntry,
    EmbeddingProvider,
    OpenAICompatibleEmbedding,
)

__all__ = [
    # Trajectory signature
    "TrajectorySignature",
    "compute_trajectory_similarity",
    # Semantic deduplicator
    "SemanticDeduplicator",
    "DedupDecision",
    "ClusterEntry",
    "EmbeddingProvider",
    "OpenAICompatibleEmbedding",
]
