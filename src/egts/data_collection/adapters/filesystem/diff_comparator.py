"""Filesystem diff comparator for mcp-trajs2data.

Bridges the generic adapter interface (`.diff`) to the existing
`diff_snapshots` implementation in `data_collection.state.filesystem_snapshot`.
"""

import logging
from data_collection.state.filesystem_snapshot import (
    FilesystemSnapshot,
    FilesystemDiff,
    diff_snapshots,
)

logger = logging.getLogger(__name__)


class FilesystemDiffComparator:
    """Comparator for computing diffs between filesystem snapshots."""

    def diff(
        self, snapshot_a: FilesystemSnapshot, snapshot_b: FilesystemSnapshot
    ) -> FilesystemDiff:
        """Compute diff between two snapshots."""
        diff = diff_snapshots(snapshot_a, snapshot_b)
        logger.info(f"Computed diff: {diff.get_change_summary()}")
        return diff

