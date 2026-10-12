"""Playwright diff comparator for mcp-trajs2data.

This module provides functionality to compare two playwright snapshots and identify changes.
"""

import logging
from .snapshot_provider import (
    PlaywrightSnapshot,
    PlaywrightDiff,
    DiffEntry,
    ChangeType,
    BrowserState,
)

logger = logging.getLogger(__name__)


class PlaywrightDiffComparator:
    """Comparator for computing diffs between playwright snapshots."""

    def diff(self, snapshot_a: PlaywrightSnapshot, snapshot_b: PlaywrightSnapshot) -> PlaywrightDiff:
        """Compute diff between two snapshots.

        Args:
            snapshot_a: Earlier snapshot (S0)
            snapshot_b: Later snapshot (S1)

        Returns:
            PlaywrightDiff describing changes from A to B
        """
        changes = []

        # Compare URLs (navigation)
        if snapshot_a.browser_state.url != snapshot_b.browser_state.url:
            changes.append(
                DiffEntry(
                    change_type=ChangeType.NAVIGATION,
                    details={
                        "from_url": snapshot_a.browser_state.url,
                        "to_url": snapshot_b.browser_state.url,
                    },
                )
            )

        # Compare DOM (if hashes are available)
        if snapshot_a.browser_state.dom_hash != snapshot_b.browser_state.dom_hash:
            if snapshot_a.browser_state.dom_hash is not None or snapshot_b.browser_state.dom_hash is not None:
                changes.append(
                    DiffEntry(
                        change_type=ChangeType.DOM_CHANGE,
                        details={
                            "from_hash": snapshot_a.browser_state.dom_hash,
                            "to_hash": snapshot_b.browser_state.dom_hash,
                        },
                    )
                )

        # Compare local storage
        storage_a = set(snapshot_a.browser_state.local_storage.keys())
        storage_b = set(snapshot_b.browser_state.local_storage.keys())

        if storage_a != storage_b or snapshot_a.browser_state.local_storage != snapshot_b.browser_state.local_storage:
            changes.append(
                DiffEntry(
                    change_type=ChangeType.STORAGE_CHANGE,
                    details={
                        "added_keys": list(storage_b - storage_a),
                        "removed_keys": list(storage_a - storage_b),
                    },
                )
            )

        # Compare cookies
        cookies_a = len(snapshot_a.browser_state.cookies)
        cookies_b = len(snapshot_b.browser_state.cookies)

        if cookies_a != cookies_b:
            changes.append(
                DiffEntry(
                    change_type=ChangeType.COOKIE_CHANGE,
                    details={
                        "from_count": cookies_a,
                        "to_count": cookies_b,
                    },
                )
            )

        diff = PlaywrightDiff(changes=changes)
        logger.info(f"Computed diff: {diff.get_change_summary()}")
        return diff
