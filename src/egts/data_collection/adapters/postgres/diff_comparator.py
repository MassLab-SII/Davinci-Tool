"""Postgres diff comparator for mcp-trajs2data.

This module provides functionality to compare two postgres snapshots and identify changes.
"""

import logging
from typing import Set
from .snapshot_provider import (
    PostgresSnapshot,
    PostgresDiff,
    DiffEntry,
    ChangeType,
    TableInfo,
)

logger = logging.getLogger(__name__)


class PostgresDiffComparator:
    """Comparator for computing diffs between postgres snapshots."""

    def diff(self, snapshot_a: PostgresSnapshot, snapshot_b: PostgresSnapshot) -> PostgresDiff:
        """Compute diff between two snapshots.

        Args:
            snapshot_a: Earlier snapshot (S0)
            snapshot_b: Later snapshot (S1)

        Returns:
            PostgresDiff describing changes from A to B
        """
        changes = []

        # Get table names from both snapshots
        tables_a = snapshot_a.get_all_table_names()
        tables_b = snapshot_b.get_all_table_names()

        # Find created tables
        created_tables = tables_b - tables_a
        for table_name in created_tables:
            table_info = snapshot_b.tables[table_name]
            changes.append(
                DiffEntry(
                    change_type=ChangeType.TABLE_CREATED,
                    table=table_name,
                    details={
                        "columns": len(table_info.columns),
                        "rows": table_info.row_count,
                    },
                )
            )

        # Find dropped tables
        dropped_tables = tables_a - tables_b
        for table_name in dropped_tables:
            table_info = snapshot_a.tables[table_name]
            changes.append(
                DiffEntry(
                    change_type=ChangeType.TABLE_DROPPED,
                    table=table_name,
                    details={
                        "columns": len(table_info.columns),
                        "rows": table_info.row_count,
                    },
                )
            )

        # Find modified tables (tables that exist in both)
        common_tables = tables_a & tables_b
        for table_name in common_tables:
            table_changes = self._diff_table(
                snapshot_a.tables[table_name],
                snapshot_b.tables[table_name]
            )
            changes.extend(table_changes)

        diff = PostgresDiff(changes=changes)
        logger.info(f"Computed diff: {diff.get_change_summary()}")
        return diff

    def _diff_table(self, table_a: TableInfo, table_b: TableInfo) -> list[DiffEntry]:
        """Compare two versions of the same table.

        Args:
            table_a: Earlier version of table
            table_b: Later version of table

        Returns:
            List of DiffEntry objects describing changes
        """
        changes = []
        table_name = table_a.name

        # Compare columns
        columns_a = {col.name for col in table_a.columns}
        columns_b = {col.name for col in table_b.columns}

        # Find added columns
        added_columns = columns_b - columns_a
        for col_name in added_columns:
            changes.append(
                DiffEntry(
                    change_type=ChangeType.COLUMN_ADDED,
                    table=table_name,
                    details={"column": col_name},
                )
            )

        # Find removed columns
        removed_columns = columns_a - columns_b
        for col_name in removed_columns:
            changes.append(
                DiffEntry(
                    change_type=ChangeType.COLUMN_REMOVED,
                    table=table_name,
                    details={"column": col_name},
                )
            )

        # Compare row data using hashes
        rows_a = table_a.row_hashes
        rows_b = table_b.row_hashes

        # Find inserted rows
        inserted_rows = rows_b - rows_a
        if inserted_rows:
            changes.append(
                DiffEntry(
                    change_type=ChangeType.ROW_INSERTED,
                    table=table_name,
                    details={"count": len(inserted_rows)},
                )
            )

        # Find deleted rows
        deleted_rows = rows_a - rows_b
        if deleted_rows:
            changes.append(
                DiffEntry(
                    change_type=ChangeType.ROW_DELETED,
                    table=table_name,
                    details={"count": len(deleted_rows)},
                )
            )

        return changes
