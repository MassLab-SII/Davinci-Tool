"""Playwright snapshot and diff utilities for mcp-trajs2data.

This module provides functionality to:
1. Take snapshots of browser state (DOM, URL, storage)
2. Compute diffs between snapshots to identify changes
"""

import logging
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Any
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ChangeType(str, Enum):
    """Types of browser changes."""

    NAVIGATION = "navigation"
    DOM_CHANGE = "dom_change"
    STORAGE_CHANGE = "storage_change"
    COOKIE_CHANGE = "cookie_change"


@dataclass
class BrowserState:
    """Information about browser state."""

    url: str
    title: str = ""
    dom_hash: Optional[str] = None  # Hash of DOM content
    cookies: List[Dict[str, Any]] = field(default_factory=list)
    local_storage: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BrowserState":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class PlaywrightSnapshot:
    """A snapshot of browser state at a point in time."""

    browser_state: BrowserState
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "browser_state": self.browser_state.to_dict(),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlaywrightSnapshot":
        """Create from dictionary."""
        browser_state = BrowserState.from_dict(data["browser_state"])
        return cls(
            browser_state=browser_state,
            timestamp=data.get("timestamp")
        )

    def get_url(self) -> str:
        """Get current URL."""
        return self.browser_state.url


@dataclass
class DiffEntry:
    """A single change in the browser diff."""

    change_type: ChangeType
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "change_type": self.change_type.value,
            "details": self.details,
        }


@dataclass
class PlaywrightDiff:
    """Diff between two playwright snapshots."""

    changes: List[DiffEntry] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Whether there are no observable browser-state changes."""
        return len(self.changes) == 0

    def total_changes(self) -> int:
        """Total number of change entries."""
        return len(self.changes)

    def get_change_summary(self) -> str:
        """Get a human-readable summary of changes."""
        if not self.changes:
            return "No changes"

        summary_parts = []
        change_counts = {}

        for entry in self.changes:
            change_type = entry.change_type.value
            change_counts[change_type] = change_counts.get(change_type, 0) + 1

        for change_type, count in sorted(change_counts.items()):
            summary_parts.append(f"{count} {change_type}")

        return ", ".join(summary_parts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "changes": [c.to_dict() for c in self.changes],
            "summary": self.get_change_summary(),
        }


class PlaywrightSnapshotProvider:
    """Provider for creating playwright browser snapshots."""

    async def create_snapshot(self, identifier: str) -> PlaywrightSnapshot:
        """Create a snapshot of the current browser state.

        Args:
            identifier: Identifier for the snapshot (not used for playwright, but kept for interface compatibility)

        Returns:
            PlaywrightSnapshot with current state
        """
        # For now, create a simple snapshot structure
        # In a real implementation, this would query the browser via MCP client
        browser_state = BrowserState(
            url="https://example.com",
            title="Example Domain",
            dom_hash=None,
            cookies=[],
            local_storage={},
        )

        snapshot = PlaywrightSnapshot(
            browser_state=browser_state,
            timestamp=datetime.now().isoformat(),
        )

        logger.info(f"Created playwright snapshot: {snapshot.get_url()}")
        return snapshot

    async def restore_snapshot(self, snapshot: PlaywrightSnapshot) -> bool:
        """Restore browser to a previous snapshot state.

        Args:
            snapshot: Snapshot to restore

        Returns:
            True if successful, False otherwise
        """
        # For now, this is a placeholder
        # In a real implementation, this would navigate to the URL and restore state
        logger.warning("Playwright snapshot restoration not yet implemented")
        return True

    def cleanup(self):
        """Clean up any resources used by the snapshot provider."""
        pass
