"""Postgres snapshot and diff utilities for mcp-trajs2data.

This module provides functionality to:
1. Take snapshots of postgres database state (schema + data)
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
    """Types of database changes."""

    TABLE_CREATED = "table_created"
    TABLE_DROPPED = "table_dropped"
    COLUMN_ADDED = "column_added"
    COLUMN_REMOVED = "column_removed"
    ROW_INSERTED = "row_inserted"
    ROW_DELETED = "row_deleted"
    ROW_UPDATED = "row_updated"


@dataclass
class ColumnInfo:
    """Information about a database column."""

    name: str
    type: str
    nullable: bool = True
    default: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ColumnInfo":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class TableInfo:
    """Information about a database table."""

    name: str
    columns: List[ColumnInfo] = field(default_factory=list)
    row_count: int = 0
    row_hashes: Set[str] = field(default_factory=set)  # Hash of each row for comparison

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "columns": [c.to_dict() for c in self.columns],
            "row_count": self.row_count,
            "row_hashes": list(self.row_hashes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TableInfo":
        """Create from dictionary."""
        columns = [ColumnInfo.from_dict(c) for c in data.get("columns", [])]
        return cls(
            name=data["name"],
            columns=columns,
            row_count=data.get("row_count", 0),
            row_hashes=set(data.get("row_hashes", [])),
        )


@dataclass
class PostgresSnapshot:
    """A snapshot of postgres database state at a point in time."""

    database: str
    tables: Dict[str, TableInfo] = field(default_factory=dict)  # table_name -> TableInfo
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "database": self.database,
            "tables": {k: v.to_dict() for k, v in self.tables.items()},
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PostgresSnapshot":
        """Create from dictionary."""
        tables = {k: TableInfo.from_dict(v) for k, v in data.get("tables", {}).items()}
        return cls(
            database=data["database"],
            tables=tables,
            timestamp=data.get("timestamp")
        )

    def get_all_table_names(self) -> Set[str]:
        """Get all table names in this snapshot."""
        return set(self.tables.keys())

    def get_total_rows(self) -> int:
        """Get total number of rows across all tables."""
        return sum(t.row_count for t in self.tables.values())


@dataclass
class DiffEntry:
    """A single change in the database diff."""

    change_type: ChangeType
    table: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "change_type": self.change_type.value,
            "table": self.table,
            "details": self.details,
        }


@dataclass
class PostgresDiff:
    """Diff between two postgres snapshots."""

    changes: List[DiffEntry] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Whether there are no observable database-state changes."""
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


class PostgresSnapshotProvider:
    """Provider for creating postgres database snapshots."""

    async def create_snapshot(self, database: str) -> PostgresSnapshot:
        """Create a snapshot of the current database state.

        Args:
            database: Database identifier (not used for postgres, but kept for interface compatibility)

        Returns:
            PostgresSnapshot with current state
        """
        # For now, create a simple snapshot structure
        # In a real implementation, this would query the database via MCP client
        snapshot = PostgresSnapshot(
            database=database,
            tables={},
            timestamp=datetime.now().isoformat(),
        )

        logger.info(f"Created postgres snapshot: {len(snapshot.tables)} tables")
        return snapshot

    async def restore_snapshot(self, snapshot: PostgresSnapshot) -> bool:
        """Restore database to a previous snapshot state.

        Args:
            snapshot: Snapshot to restore

        Returns:
            True if successful, False otherwise
        """
        # For now, this is a placeholder
        # In a real implementation, this would drop all tables and recreate from snapshot
        logger.warning("Postgres snapshot restoration not yet implemented")
        return True

    def cleanup(self):
        """Clean up any resources used by the snapshot provider."""
        pass
