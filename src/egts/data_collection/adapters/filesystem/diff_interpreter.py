"""Unified diff interpreter that works with any diff type via duck-typing.

If the diff carries file-level detail (``created`` / ``deleted`` /
``modified`` / ``moved`` lists), those are used for richer intent inference.
Otherwise — e.g. ``_WorldStateDiff`` from benchmark worlds — the interpreter
falls back to classifying tool-call sequences.
"""

from typing import Any, List
import logging
from data_collection.adapters.base.diff_interpreter import (
    DiffInterpreter,
    IntentSpec,
    TaskCategory,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Heuristic tool-name classification (used when diff has no file detail)
# ---------------------------------------------------------------------------
_READ_PATTERNS = (
    "list_", "get_", "search_", "read_", "describe_", "explain_",
    "find_", "show_", "view_", "query", "select", "fetch_",
    "check_", "browse_", "cat_", "ls_", "dir_", "tree_",
    "stat_", "head_", "tail_", "grep_", "diff_",
)
_WRITE_PATTERNS = (
    "create_", "update_", "delete_", "remove_", "add_", "set_",
    "edit_", "modify_", "move_", "rename_", "copy_",
    "merge_", "close_", "resolve_", "lock_", "unlock_",
    "push_", "commit_", "upload_", "write_", "insert_",
    "drop_", "alter_", "grant_", "revoke_",
    "execute_", "run_", "apply_",
)
_MUTATION_CATEGORIES = {
    "create_": TaskCategory.STRUCTURE_CREATION,
    "delete_": TaskCategory.CLEANUP,
    "remove_": TaskCategory.CLEANUP,
    "update_": TaskCategory.CONTENT_PROCESSING,
    "edit_": TaskCategory.CONTENT_PROCESSING,
    "modify_": TaskCategory.CONTENT_PROCESSING,
    "move_": TaskCategory.FILE_ORGANIZATION,
    "rename_": TaskCategory.FILE_ORGANIZATION,
    "merge_": TaskCategory.CODE_MANAGEMENT,
    "insert_": TaskCategory.DATA_MANAGEMENT,
    "execute_": TaskCategory.DATA_MANAGEMENT,
    "drop_": TaskCategory.DATA_MANAGEMENT,
    "alter_": TaskCategory.DATA_MANAGEMENT,
}


def _looks_like_read(tool_name: str) -> bool:
    name_lower = tool_name.lower()
    for pat in _READ_PATTERNS:
        if name_lower.startswith(pat):
            return True
    return False


def _looks_like_write(tool_name: str) -> bool:
    name_lower = tool_name.lower()
    for pat in _WRITE_PATTERNS:
        if name_lower.startswith(pat):
            return True
    return False


# ---------------------------------------------------------------------------
# Unified Interpreter
# ---------------------------------------------------------------------------

class FilesystemDiffInterpreter(DiffInterpreter):
    """Interprets diffs with or without file-level detail.

    **Two code paths, selected automatically by duck-typing the diff:**

    *File-level path* — when the diff exposes ``created``, ``deleted``,
    ``modified``, ``moved`` as sequences (e.g. ``FilesystemDiff``).  Intent
    is inferred from the counts and types of file operations.

    *Tool-call path* — when the diff is hash-based (e.g. ``_WorldStateDiff``)
    and only tells us whether state changed.  Intent is inferred from the
    tool-call sequence via heuristic prefix matching.
    """

    DEFAULT_READ_CATEGORY = TaskCategory.INFORMATION_RETRIEVAL

    def interpret(
        self, diff: Any, tool_calls: List[Any], root_path: str
    ) -> IntentSpec:
        if self._has_file_detail(diff):
            return self._interpret_from_file_detail(diff, tool_calls)
        return self._interpret_from_tool_calls(diff, tool_calls)

    # ------------------------------------------------------------------
    # Path selection
    # ------------------------------------------------------------------

    @staticmethod
    def _has_file_detail(diff: Any) -> bool:
        """Return True if *diff* carries file-level operation lists."""
        if diff is None:
            return False
        for attr in ("created", "deleted", "modified", "moved"):
            val = getattr(diff, attr, None)
            if isinstance(val, (list, tuple)):
                return True
        return False

    # ------------------------------------------------------------------
    # File-level path (rich detail from e.g. FilesystemDiff)
    # ------------------------------------------------------------------

    def _interpret_from_file_detail(
        self, diff: Any, tool_calls: List[Any]
    ) -> IntentSpec:
        created_count = len(getattr(diff, "created", []) or [])
        deleted_count = len(getattr(diff, "deleted", []) or [])
        modified_count = len(getattr(diff, "modified", []) or [])
        moved_count = len(getattr(diff, "moved", []) or [])

        changes = {
            "created_count": created_count,
            "deleted_count": deleted_count,
            "modified_count": modified_count,
            "moved_count": moved_count,
        }

        total_changes = created_count + deleted_count + modified_count + moved_count

        if total_changes > 0:
            if created_count > 0 and moved_count > 0:
                category = TaskCategory.STRUCTURE_CREATION
            elif modified_count > 0:
                category = TaskCategory.CONTENT_PROCESSING
            else:
                category = TaskCategory.MIXED
        else:
            category = TaskCategory.MIXED

        return IntentSpec(
            primary_action="modify_filesystem",
            task_category=category,
            changes=changes,
            tools_used=[
                tc.tool_name
                for tc in tool_calls
                if hasattr(tc, "success") and tc.success
            ],
            tool_call_count=len(
                [tc for tc in tool_calls if hasattr(tc, "success") and tc.success]
            ),
            complexity_score=total_changes,
        )

    # ------------------------------------------------------------------
    # Tool-call path (hash-based diffs like _WorldStateDiff)
    # ------------------------------------------------------------------

    def _interpret_from_tool_calls(
        self, diff: Any, tool_calls: List[Any]
    ) -> IntentSpec:
        read_tools, write_tools = _classify_tool_calls(tool_calls)

        # Determine whether state changed
        changed = getattr(diff, "changed", None) if diff is not None else None
        if changed is None:
            changed = (
                not diff.is_empty()
                if hasattr(diff, "is_empty")
                else bool(write_tools)
            )

        # Determine primary action and category
        if changed and write_tools:
            primary_action = "mutate_state"
            category = _infer_mutation_category(write_tools)
        elif read_tools:
            primary_action = "inspect_state"
            category = self.DEFAULT_READ_CATEGORY
        else:
            primary_action = "unknown"
            category = TaskCategory.MIXED

        # Build changes dict
        raw_total = (
            getattr(diff, "total_changes", None) if diff is not None else None
        )
        total_changes = raw_total() if callable(raw_total) else raw_total
        changes: dict = {
            "state_changed": changed,
            "successful_write_calls": len(write_tools),
            "successful_read_calls": len(read_tools),
            "total_tool_calls": len(tool_calls),
            "write_tools_used": list(dict.fromkeys(write_tools)),
            "read_tools_used": list(dict.fromkeys(read_tools)),
        }
        if total_changes is not None:
            changes["total_changes"] = total_changes

        all_unique_tools = list(dict.fromkeys(read_tools + write_tools))

        return IntentSpec(
            primary_action=primary_action,
            task_category=category,
            changes=changes,
            tools_used=all_unique_tools,
            tool_call_count=len(
                [tc for tc in tool_calls if getattr(tc, "success", False)]
            ),
            complexity_score=max(1, len(write_tools)),
        )


# ---------------------------------------------------------------------------
# Helpers for the tool-call path
# ---------------------------------------------------------------------------

def _classify_tool_calls(
    tool_calls: List[Any],
) -> tuple:
    """Split tool calls into (read_names, write_names) for successful calls."""
    read_tools: List[str] = []
    write_tools: List[str] = []

    for tc in tool_calls:
        name = getattr(tc, "tool_name", "")
        ok = getattr(tc, "success", False)
        if not name:
            continue

        if _looks_like_write(name):
            if ok:
                write_tools.append(name)
        elif _looks_like_read(name):
            if ok:
                read_tools.append(name)
        else:
            # Unknown — conservatively treat as write
            if ok:
                write_tools.append(name)

    return read_tools, write_tools


def _infer_mutation_category(write_tools: List[str]) -> TaskCategory:
    """Pick the dominant ``TaskCategory`` from the set of write tools used."""
    counts: dict = {}
    for name in write_tools:
        name_lower = name.lower()
        for prefix, cat in _MUTATION_CATEGORIES.items():
            if name_lower.startswith(prefix):
                counts[cat] = counts.get(cat, 0) + 1
                break

    if not counts:
        return TaskCategory.MIXED
    return max(counts, key=lambda k: counts[k])  # type: ignore[no-any-return]
