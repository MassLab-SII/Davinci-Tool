"""Problem synthesizer for Traj→Problem pipeline.

This module converts trajectory diffs and tool calls into natural language problem descriptions.
Supports dual-mode synthesis:
- Mutation mode: When Diff > 0, synthesize problems based on filesystem changes
- Retrieval/QA mode: When Diff == 0, synthesize Q&A tasks based on tool inputs/outputs

Uses rule-based intent extraction + small model rewriting.
"""

import logging
import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Tuple
from pathlib import Path
from enum import Enum

from .state.filesystem_snapshot import FilesystemDiff, DiffEntry
from .trajs2data_collector import StrictTrajectory, ToolCallRecord
from .maas_client import MaaSClient
from .utils.config import MaaSConfig, ModelConfig, SelfQuestioningConfig
from prompts.synthesis import (
    PROBLEM_REWRITE_SYSTEM_PROMPT_ZH,
    PROBLEM_REWRITE_SYSTEM_PROMPT_EN,
    PROBLEM_REWRITE_USER_TEMPLATE_ZH,
    PROBLEM_REWRITE_USER_TEMPLATE_EN,
    RETRIEVAL_REWRITE_SYSTEM_PROMPT_ZH,
    RETRIEVAL_REWRITE_SYSTEM_PROMPT_EN,
    RETRIEVAL_REWRITE_USER_TEMPLATE_ZH,
    RETRIEVAL_REWRITE_USER_TEMPLATE_EN,
)
from prompts.hindsight import (
    HINDSIGHT_REWRITE_SYSTEM_PROMPT_ZH,
    HINDSIGHT_REWRITE_SYSTEM_PROMPT_EN,
    HINDSIGHT_REWRITE_USER_TEMPLATE_ZH,
    HINDSIGHT_REWRITE_USER_TEMPLATE_EN,
)

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Type of synthesized task based on trajectory effects."""

    MUTATION = "mutation"  # Diff > 0: filesystem was modified
    RETRIEVAL = "retrieval"  # Diff == 0: read-only information retrieval/QA


class TaskCategory(str, Enum):
    """Categories of filesystem tasks."""

    FILE_ORGANIZATION = "file_organization"
    CONTENT_PROCESSING = "content_processing"
    STRUCTURE_CREATION = "structure_creation"
    DATA_MANAGEMENT = "data_management"
    CODE_MANAGEMENT = "code_management"
    CLEANUP = "cleanup"
    INFORMATION_RETRIEVAL = "information_retrieval"
    FILE_SEARCH = "file_search"
    CONTENT_QUERY = "content_query"
    MIXED = "mixed"


@dataclass
class IntentSpec:
    """Specification of the inferred task intent from trajectory."""

    # Core intent summary
    primary_action: str  # e.g., "organize", "create", "edit", "move", "rename"
    task_category: TaskCategory

    # Change statistics
    files_created: int = 0
    files_deleted: int = 0
    files_modified: int = 0
    files_moved: int = 0
    directories_created: int = 0
    directories_deleted: int = 0

    # Affected paths info
    affected_directories: List[str] = field(default_factory=list)
    file_types_involved: Set[str] = field(default_factory=set)

    # Naming patterns detected
    naming_patterns: List[str] = field(
        default_factory=list
    )  # e.g., "date-based", "type-based"

    # Tool usage info
    tools_used: List[str] = field(default_factory=list)
    tool_call_count: int = 0

    # Inferred complexity
    complexity_score: int = 1  # 1-5 scale

    # Raw data for context
    sample_changes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "primary_action": self.primary_action,
            "task_category": self.task_category.value,
            "files_created": self.files_created,
            "files_deleted": self.files_deleted,
            "files_modified": self.files_modified,
            "files_moved": self.files_moved,
            "directories_created": self.directories_created,
            "directories_deleted": self.directories_deleted,
            "affected_directories": self.affected_directories,
            "file_types_involved": list(self.file_types_involved),
            "naming_patterns": self.naming_patterns,
            "tools_used": self.tools_used,
            "tool_call_count": self.tool_call_count,
            "complexity_score": self.complexity_score,
            "sample_changes": self.sample_changes,
        }

    def get_summary(self) -> str:
        """Get a brief summary of the intent."""
        total_changes = (
            self.files_created
            + self.files_deleted
            + self.files_modified
            + self.files_moved
            + self.directories_created
            + self.directories_deleted
        )
        return (
            f"{self.primary_action} ({self.task_category.value}): "
            f"{total_changes} changes, {self.tool_call_count} tool calls, "
            f"complexity={self.complexity_score}"
        )


@dataclass
class RetrievalSpec:
    """Specification for retrieval/QA task synthesis (when Diff == 0).

    Used when trajectory consists of read-only tool calls that don't
    modify the filesystem but retrieve information.
    """

    # Core retrieval info
    query_focus: str  # What was queried/searched for
    task_category: TaskCategory = TaskCategory.INFORMATION_RETRIEVAL

    # Evidence from tool calls
    evidence_tool: str = ""  # Primary tool used to get evidence
    evidence_arguments: Dict[str, Any] = field(default_factory=dict)
    evidence_snippet: str = ""  # Key part of tool output (truncated)

    # Answer info
    reference_answer: str = ""  # Answer derived from tool output
    answer_truncated: bool = False  # Whether answer was truncated

    # Tool usage info
    tools_used: List[str] = field(default_factory=list)
    tool_call_count: int = 0

    # All tool calls with their outputs (for context)
    tool_call_summaries: List[Dict[str, Any]] = field(default_factory=list)

    # Complexity
    complexity_score: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "query_focus": self.query_focus,
            "task_category": self.task_category.value,
            "evidence_tool": self.evidence_tool,
            "evidence_arguments": self.evidence_arguments,
            "evidence_snippet": self.evidence_snippet[:500]
            if self.evidence_snippet
            else "",
            "reference_answer": self.reference_answer,
            "answer_truncated": self.answer_truncated,
            "tools_used": self.tools_used,
            "tool_call_count": self.tool_call_count,
            "complexity_score": self.complexity_score,
        }

    def get_summary(self) -> str:
        """Get a brief summary of the retrieval spec."""
        return (
            f"retrieval ({self.task_category.value}): "
            f"query='{self.query_focus[:50]}...', "
            f"{self.tool_call_count} tool calls, "
            f"evidence_len={len(self.evidence_snippet)}"
        )


# Read-only tools default priority (fallback)
DEFAULT_READ_ONLY_TOOLS_PRIORITY = [
    "search_files",  # Highest: explicit search with query
    "read_file",  # High: reading specific file content
    "read_text_file",  # High: reading specific file content
    "read_multiple_files",  # High: reading multiple files
    "get_file_info",  # Medium: getting file metadata
    "directory_tree",  # Medium: exploring structure
    "list_directory",  # Lower: just listing
    "list_directory_with_sizes",
    "list_allowed_directories",  # Lowest: just listing allowed dirs
]


def _diff_is_empty(diff: Any) -> bool:
    """Best-effort check whether a diff object contains no changes."""
    if diff is None:
        return True

    # Primary contract used by FilesystemDiff/PlaywrightDiff/PostgresDiff
    if hasattr(diff, "is_empty") and callable(diff.is_empty):
        try:
            return bool(diff.is_empty())
        except Exception:
            pass

    # Common fallback contracts
    if hasattr(diff, "total_changes") and callable(diff.total_changes):
        try:
            return int(diff.total_changes()) == 0
        except Exception:
            pass
    if hasattr(diff, "changes"):
        try:
            return len(diff.changes) == 0
        except Exception:
            pass

    # Conservative fallback: assume not empty to avoid false retrieval labels
    return False


def _has_meaningful_output(result: Any, min_len: int) -> bool:
    """Return True when tool result has enough content for retrieval evidence."""
    if result is None:
        return False
    if isinstance(result, str):
        return len(result.strip()) >= min_len
    try:
        text = json.dumps(result, ensure_ascii=False)
        return len(text) >= min_len
    except Exception:
        return len(str(result)) >= min_len


# Keywords in tool names that indicate mutating (state-changing) operations
MUTATING_TOOL_KEYWORDS = {
    "update", "modify", "cancel", "book", "create", "delete", "remove",
    "set", "change", "add", "edit", "write", "move", "rename", "copy",
    "send", "transfer", "pay", "refund", "exchange", "return", "enable",
    "disable", "activate", "deactivate", "reset", "install", "uninstall",
    "connect", "disconnect", "lock", "unlock", "seat", "unseat",
}


def _infer_mutation_from_tools(
    tool_calls: List[ToolCallRecord],
    mutating_tools: Optional[List[str]] = None,
) -> bool:
    """Infer whether a trajectory contains mutating operations based on tool semantics.

    Args:
        tool_calls: List of tool calls from trajectory
        mutating_tools: Optional explicit list of tool names considered mutating

    Returns:
        True if any successful tool call is a mutating operation
    """
    explicit_set = set(mutating_tools) if mutating_tools else set()

    for tc in tool_calls:
        if not tc.success:
            continue
        name = tc.tool_name

        # Check explicit list first
        if name in explicit_set:
            return True

        # Heuristic: check if tool name contains mutating keywords
        name_lower = name.lower()
        if any(kw in name_lower for kw in MUTATING_TOOL_KEYWORDS):
            return True

    return False


def determine_task_type(
    diff: Any,
    tool_calls: List[ToolCallRecord],
    min_evidence_length: int = 20,
    read_only_tools_priority: Optional[List[str]] = None,
    mutating_tools: Optional[List[str]] = None,
) -> TaskType:
    """Determine whether this trajectory should produce mutation or retrieval data.

    Supports three determination modes:
    1. State diff available (filesystem/postgres/playwright): diff > 0 → mutation
    2. No diff but tool semantics available (benchmark worlds): mutating tool called → mutation
    3. Fallback: check read-only evidence for retrieval

    Args:
        diff: State diff between S0 and S1 (None for benchmark worlds)
        tool_calls: List of tool calls from trajectory
        min_evidence_length: Minimum output length to consider as valid evidence
        read_only_tools_priority: List of read-only tools to check for evidence
        mutating_tools: Optional explicit list of mutating tool names

    Returns:
        TaskType.MUTATION or TaskType.RETRIEVAL
    """
    # Mode 1: If there are observable state changes, it's a mutation task.
    if diff is not None and not _diff_is_empty(diff):
        return TaskType.MUTATION

    # Mode 2: No diff (benchmark world) — infer from tool semantics
    if diff is None and _infer_mutation_from_tools(tool_calls, mutating_tools):
        return TaskType.MUTATION

    priority_tools = read_only_tools_priority or DEFAULT_READ_ONLY_TOOLS_PRIORITY

    # Diff is empty or None: check if we have meaningful read-only tool outputs.
    for tc in tool_calls:
        if tc.success and tc.tool_name in priority_tools:
            if _has_meaningful_output(tc.result, min_evidence_length):
                return TaskType.RETRIEVAL

    # Fallback: empty diff with any successful tool call is still a retrieval-style
    # episode for non-mutating domains (e.g., browser observation/query tasks).
    if any(tc.success for tc in tool_calls):
        return TaskType.RETRIEVAL

    # No successful signals at all -> keep conservative mutation default.
    return TaskType.MUTATION


def build_retrieval_spec(
    tool_calls: List[ToolCallRecord],
    root: str,
    max_answer_length: int = 4000,
    language: str = "en",
    read_only_tools_priority: Optional[List[str]] = None,
) -> RetrievalSpec:
    """Build retrieval specification from read-only tool calls.

    Args:
        tool_calls: List of tool calls from trajectory
        root: Root directory path
        max_answer_length: Maximum length for reference answer
        language: Language for generated text ("en" or "zh")
        read_only_tools_priority: Priority list of read-only tools

    Returns:
        RetrievalSpec with inferred retrieval intent
    """
    spec = RetrievalSpec(
        query_focus="unknown", task_category=TaskCategory.INFORMATION_RETRIEVAL
    )

    # Analyze tool calls
    successful_calls = [tc for tc in tool_calls if tc.success]
    spec.tool_call_count = len(successful_calls)
    spec.tools_used = list(set(tc.tool_name for tc in successful_calls))

    # Build tool call summaries
    for tc in successful_calls:
        summary = {
            "tool": tc.tool_name,
            "arguments": tc.arguments,
            "output_length": len(tc.result or ""),
            "output_preview": (tc.result or "")[:200],
        }
        spec.tool_call_summaries.append(summary)

    # Find the best evidence tool call (by priority and output length)
    best_evidence = _select_best_evidence_call(
        successful_calls, read_only_tools_priority
    )

    if best_evidence:
        spec.evidence_tool = best_evidence.tool_name
        spec.evidence_arguments = best_evidence.arguments
        spec.evidence_snippet = best_evidence.result or ""

        # Build reference answer from evidence
        answer = best_evidence.result or ""
        if len(answer) > max_answer_length:
            spec.reference_answer = answer[:max_answer_length] + "\n... [truncated]"
            spec.answer_truncated = True
        else:
            spec.reference_answer = answer
            spec.answer_truncated = False

        # Infer query focus from tool and arguments
        spec.query_focus = _infer_query_focus(best_evidence, root, language)

        # Infer task category
        spec.task_category = _infer_retrieval_category(best_evidence)

    # Calculate complexity
    spec.complexity_score = min(5, max(1, spec.tool_call_count))

    logger.info(f"Built retrieval spec: {spec.get_summary()}")
    return spec


def _select_best_evidence_call(
    tool_calls: List[ToolCallRecord],
    read_only_tools_priority: Optional[List[str]] = None,
) -> Optional[ToolCallRecord]:
    """Select the best tool call to use as evidence for QA.

    Priority:
    1. Tools higher in priority list
    2. Among same priority, prefer longer outputs
    """
    if not tool_calls:
        return None

    priority_tools = read_only_tools_priority or DEFAULT_READ_ONLY_TOOLS_PRIORITY

    # Filter to read-only tools with meaningful output
    candidates = []
    for tc in tool_calls:
        if tc.tool_name in priority_tools and len(tc.result or "") > 20:
            try:
                priority = priority_tools.index(tc.tool_name)
            except ValueError:
                priority = 999  # Lowest priority if not in list
            candidates.append((priority, len(tc.result or ""), tc))

    if not candidates:
        # Fallback to any tool with output
        for tc in tool_calls:
            if len(tc.result or "") > 20:
                return tc
        return tool_calls[0] if tool_calls else None

    # Sort by priority (lower is better), then by output length (higher is better)
    candidates.sort(key=lambda x: (x[0], -x[1]))
    return candidates[0][2]


def _infer_query_focus(tc: ToolCallRecord, root: str, language: str = "en") -> str:
    """Infer what the user was trying to find/query based on tool call."""
    tool_name = tc.tool_name
    args = tc.arguments or {}

    def relativize(path: str) -> str:
        try:
            return str(Path(path).relative_to(root))
        except (ValueError, TypeError):
            return path

    if language == "en":
        if tool_name == "search_files":
            pattern = args.get("pattern", args.get("query", args.get("regex", "")))
            path = relativize(args.get("path", "."))
            return f"Search for '{pattern}' in {path}"

        elif tool_name in ["read_file", "read_text_file"]:
            path = relativize(args.get("path", ""))
            return f"Read the contents of {path}"

        elif tool_name == "read_multiple_files":
            paths = args.get("paths", [])
            if paths:
                rel_paths = [relativize(p) for p in paths[:3]]
                suffix = f" and {len(paths) - 3} more files" if len(paths) > 3 else ""
                return f"Read the contents of {', '.join(rel_paths)}{suffix}"
            return "Read the contents of multiple files"

        elif tool_name == "get_file_info":
            path = relativize(args.get("path", ""))
            return f"Get file information for {path}"

        elif tool_name == "directory_tree":
            path = relativize(args.get("path", "."))
            return f"View the directory structure of {path}"

        elif tool_name in ["list_directory", "list_directory_with_sizes"]:
            path = relativize(args.get("path", "."))
            return f"List the contents of {path}"

        elif tool_name == "list_allowed_directories":
            return "View accessible directories"

        else:
            return f"Query information using {tool_name}"
    else:
        if tool_name == "search_files":
            pattern = args.get("pattern", args.get("query", args.get("regex", "")))
            path = relativize(args.get("path", "."))
            return f"在 {path} 中搜索 '{pattern}'"

        elif tool_name in ["read_file", "read_text_file"]:
            path = relativize(args.get("path", ""))
            return f"查看文件 {path} 的内容"

        elif tool_name == "read_multiple_files":
            paths = args.get("paths", [])
            if paths:
                rel_paths = [relativize(p) for p in paths[:3]]
                suffix = f" 等{len(paths)}个文件" if len(paths) > 3 else ""
                return f"查看 {', '.join(rel_paths)}{suffix} 的内容"
            return "查看多个文件的内容"

        elif tool_name == "get_file_info":
            path = relativize(args.get("path", ""))
            return f"获取 {path} 的文件信息"

        elif tool_name == "directory_tree":
            path = relativize(args.get("path", "."))
            return f"查看 {path} 的目录结构"

        elif tool_name in ["list_directory", "list_directory_with_sizes"]:
            path = relativize(args.get("path", "."))
            return f"列出 {path} 目录下的内容"

        elif tool_name == "list_allowed_directories":
            return "查看可访问的目录"

        else:
            return f"使用 {tool_name} 查询信息"


def _infer_retrieval_category(tc: ToolCallRecord) -> TaskCategory:
    """Infer task category for retrieval task."""
    tool_name = tc.tool_name

    if tool_name == "search_files":
        return TaskCategory.FILE_SEARCH
    elif tool_name in ["read_file", "read_text_file", "read_multiple_files"]:
        return TaskCategory.CONTENT_QUERY
    elif tool_name in ["directory_tree", "list_directory", "list_directory_with_sizes"]:
        return TaskCategory.INFORMATION_RETRIEVAL
    else:
        return TaskCategory.INFORMATION_RETRIEVAL


def build_intent_spec(
    diff: FilesystemDiff, tool_calls: List[ToolCallRecord], root: str
) -> IntentSpec:
    """Build intent specification from trajectory diff and tool calls.

    Args:
        diff: Filesystem diff between S0 and S1
        tool_calls: List of tool calls from trajectory
        root: Root directory path

    Returns:
        IntentSpec with inferred task intent
    """
    spec = IntentSpec(primary_action="unknown", task_category=TaskCategory.MIXED)

    # Analyze diff
    _analyze_diff(spec, diff, root)

    # Analyze tool calls
    _analyze_tool_calls(spec, tool_calls)

    # Infer primary action
    _infer_primary_action(spec)

    # Infer task category
    _infer_task_category(spec)

    # Calculate complexity
    _calculate_complexity(spec)

    # Extract sample changes
    _extract_sample_changes(spec, diff, root)

    logger.info(f"Built intent spec: {spec.get_summary()}")
    return spec


def _analyze_diff(spec: IntentSpec, diff: FilesystemDiff, root: str):
    """Analyze filesystem diff to populate change statistics."""
    # Count files vs directories
    for entry in diff.created:
        if entry.new_info and entry.new_info.is_directory:
            spec.directories_created += 1
        else:
            spec.files_created += 1
            _add_file_type(spec, entry.path)

    for entry in diff.deleted:
        if entry.old_info and entry.old_info.is_directory:
            spec.directories_deleted += 1
        else:
            spec.files_deleted += 1
            _add_file_type(spec, entry.path)

    for entry in diff.modified:
        spec.files_modified += 1
        _add_file_type(spec, entry.path)

    for entry in diff.moved:
        spec.files_moved += 1
        _add_file_type(spec, entry.path)
        if entry.old_path:
            _add_file_type(spec, entry.old_path)

    # Collect affected directories
    affected_dirs = set()
    for entry in diff.created + diff.deleted + diff.modified + diff.moved:
        path = Path(entry.path)
        # Get parent directory relative to root
        try:
            rel_path = path.relative_to(root)
            if rel_path.parent != Path("."):
                affected_dirs.add(str(rel_path.parent))
            else:
                affected_dirs.add(".")
        except ValueError:
            affected_dirs.add(str(path.parent))

    spec.affected_directories = sorted(list(affected_dirs))

    # Detect naming patterns
    _detect_naming_patterns(spec, diff)


def _add_file_type(spec: IntentSpec, path: str):
    """Extract and add file type from path."""
    suffix = Path(path).suffix.lower()
    if suffix:
        spec.file_types_involved.add(suffix)


def _detect_naming_patterns(spec: IntentSpec, diff: FilesystemDiff):
    """Detect naming patterns from file changes."""
    patterns = set()

    all_paths = []
    for entry in diff.created + diff.modified:
        all_paths.append(entry.path)
    for entry in diff.moved:
        all_paths.append(entry.path)
        if entry.old_path:
            all_paths.append(entry.old_path)

    # Check for date patterns
    date_pattern = re.compile(r"\d{4}[-_]\d{2}[-_]\d{2}|\d{8}")
    if any(date_pattern.search(p) for p in all_paths):
        patterns.add("date-based")

    # Check for type/category based organization
    type_dirs = {"images", "documents", "data", "code", "scripts", "reports", "notes"}
    if any(any(d in p.lower() for d in type_dirs) for p in all_paths):
        patterns.add("type-based")

    # Check for numbering patterns
    number_pattern = re.compile(r"_\d+\.|_v\d+\.|_\(\d+\)")
    if any(number_pattern.search(p) for p in all_paths):
        patterns.add("numbered")

    # Check for standardization (similar naming across files)
    if diff.moved:
        old_names = [Path(e.old_path).stem for e in diff.moved if e.old_path]
        new_names = [Path(e.path).stem for e in diff.moved]
        if old_names and new_names:
            # Check if naming became more consistent
            old_styles = len(
                set(n.split("_")[0] if "_" in n else n[:3] for n in old_names)
            )
            new_styles = len(
                set(n.split("_")[0] if "_" in n else n[:3] for n in new_names)
            )
            if new_styles < old_styles:
                patterns.add("standardized")

    spec.naming_patterns = list(patterns)


def _analyze_tool_calls(spec: IntentSpec, tool_calls: List[ToolCallRecord]):
    """Analyze tool calls to understand operation patterns."""
    spec.tool_call_count = len(tool_calls)

    tool_names = [tc.tool_name for tc in tool_calls]
    spec.tools_used = list(set(tool_names))

    # Tool usage frequency for action inference
    tool_counts: Dict[str, int] = {}
    for name in tool_names:
        tool_counts[name] = tool_counts.get(name, 0) + 1


def _infer_primary_action(spec: IntentSpec):
    """Infer the primary action from change patterns."""
    # Priority based action inference
    if spec.files_moved > 0 and spec.files_moved >= spec.files_created:
        if spec.directories_created > 0:
            spec.primary_action = "organize"
        else:
            spec.primary_action = "reorganize"
    elif spec.files_modified > spec.files_created and spec.files_modified > 0:
        spec.primary_action = "process"
    elif spec.directories_created > 0 and spec.files_created > 0:
        spec.primary_action = "create_structure"
    elif spec.files_created > 0:
        spec.primary_action = "create"
    elif spec.files_deleted > spec.files_created:
        spec.primary_action = "cleanup"
    elif spec.files_moved > 0:
        spec.primary_action = "move"
    else:
        spec.primary_action = "modify"

    # Refine based on naming patterns
    if "standardized" in spec.naming_patterns:
        spec.primary_action = "standardize"
    elif "date-based" in spec.naming_patterns and spec.files_moved > 0:
        spec.primary_action = "organize_by_date"
    elif "type-based" in spec.naming_patterns and spec.files_moved > 0:
        spec.primary_action = "organize_by_type"


def _infer_task_category(spec: IntentSpec):
    """Infer task category from changes and file types."""
    # Check file types
    code_types = {".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp", ".h"}
    data_types = {".csv", ".json", ".yaml", ".yml", ".xml", ".sql"}
    doc_types = {".txt", ".md", ".doc", ".pdf", ".docx"}

    is_code = bool(spec.file_types_involved & code_types)
    is_data = bool(spec.file_types_involved & data_types)
    is_doc = bool(spec.file_types_involved & doc_types)

    # Determine category
    if spec.primary_action in [
        "organize",
        "reorganize",
        "move",
        "organize_by_date",
        "organize_by_type",
    ]:
        spec.task_category = TaskCategory.FILE_ORGANIZATION
    elif spec.primary_action == "cleanup":
        spec.task_category = TaskCategory.CLEANUP
    elif spec.primary_action == "create_structure":
        spec.task_category = TaskCategory.STRUCTURE_CREATION
    elif spec.files_modified > 0:
        if is_code:
            spec.task_category = TaskCategory.CODE_MANAGEMENT
        elif is_data:
            spec.task_category = TaskCategory.DATA_MANAGEMENT
        else:
            spec.task_category = TaskCategory.CONTENT_PROCESSING
    elif is_code:
        spec.task_category = TaskCategory.CODE_MANAGEMENT
    elif is_data:
        spec.task_category = TaskCategory.DATA_MANAGEMENT
    else:
        spec.task_category = TaskCategory.MIXED


def _calculate_complexity(spec: IntentSpec):
    """Calculate complexity score (1-5)."""
    score = 1

    total_changes = (
        spec.files_created
        + spec.files_deleted
        + spec.files_modified
        + spec.files_moved
        + spec.directories_created
        + spec.directories_deleted
    )

    # Scale by number of changes
    if total_changes > 20:
        score += 2
    elif total_changes > 10:
        score += 1

    # Scale by directory depth/spread
    if len(spec.affected_directories) > 5:
        score += 1

    # Scale by operation variety
    operation_types = sum(
        [
            1 if spec.files_created > 0 else 0,
            1 if spec.files_deleted > 0 else 0,
            1 if spec.files_modified > 0 else 0,
            1 if spec.files_moved > 0 else 0,
            1 if spec.directories_created > 0 else 0,
        ]
    )
    if operation_types >= 3:
        score += 1

    spec.complexity_score = min(5, max(1, score))


def _extract_sample_changes(
    spec: IntentSpec, diff: FilesystemDiff, root: str, max_samples: int = 5
):
    """Extract sample changes for context."""
    samples = []

    def relativize(path: str) -> str:
        try:
            return str(Path(path).relative_to(root))
        except ValueError:
            return path

    # Add samples from each change type
    for entry in diff.created[:max_samples]:
        samples.append(
            {
                "type": "created",
                "path": relativize(entry.path),
                "is_directory": entry.new_info.is_directory
                if entry.new_info
                else False,
            }
        )

    for entry in diff.moved[:max_samples]:
        samples.append(
            {
                "type": "moved",
                "from": relativize(entry.old_path) if entry.old_path else None,
                "to": relativize(entry.path),
            }
        )

    for entry in diff.modified[:max_samples]:
        samples.append({"type": "modified", "path": relativize(entry.path)})

    for entry in diff.deleted[:max_samples]:
        samples.append({"type": "deleted", "path": relativize(entry.path)})

    spec.sample_changes = samples[: max_samples * 2]


# ============================================================
# Natural Language Problem Generation (Small Model Rewriting)
# ============================================================

# Step-by-step patterns to reject (hard filter)
STEP_PATTERNS = [
    r"第[一二三四五六七八九十\d]+步",  # Chinese: 第一步, 第二步, etc.
    r"Step\s*\d+",  # English: Step 1, Step 2
    r"步骤\s*\d+",  # Chinese: 步骤1, 步骤2
    r"^\s*\d+\.\s+",  # Numbered list: 1. xxx, 2. xxx
    r"首先.*然后.*最后",  # Chinese: 首先...然后...最后
    r"First.*then.*finally",  # English sequence
    r"Execute the following",  # Imperative instructions
    r"执行以下",  # Chinese: execute following
    r"按照以下步骤",  # Chinese: follow these steps
    r"依次执行",  # Chinese: execute in order
]

# Mutation Problem Rewrite Prompts (Now imported from prompts.synthesis)


# ============================================================
# Retrieval/QA Problem Generation Prompts
# ============================================================

# Retrieval/QA Problem Generation Prompts (Now imported from prompts.synthesis)


def _check_step_patterns(text: str) -> bool:
    """Check if text contains step-by-step patterns.

    Args:
        text: Text to check

    Returns:
        True if step patterns detected (should reject), False otherwise
    """
    for pattern in STEP_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            logger.debug(f"Step pattern detected: {pattern}")
            return True
    return False


async def rewrite_to_problem_json(
    intent_spec: IntentSpec,
    tools_subset: List[Dict[str, Any]],
    init_ops: List[Dict[str, Any]],
    mcp_server: str,
    maas_client: MaaSClient,
    model_config: ModelConfig,
    root: str,
    language: str = "zh",
    max_retries: int = 2,
    self_questioning_config=None,
    novelty_selector=None,
    embedding_provider=None,
    prompt_domain: Optional[str] = None,
) -> Dict[str, Any]:
    """Rewrite intent spec to natural language problem.json using small model.

    If self_questioning_config is provided and enabled, generates multiple
    candidates and selects the most novel one.

    Args:
        intent_spec: The extracted intent specification
        tools_subset: Tools that were sampled for this episode
        init_ops: Initialization operations for problem.json
        mcp_server: MCP server name
        maas_client: MaaS client for LLM calls
        model_config: Model configuration for the small rewrite model
        root: Root directory path
        language: Output language: 'zh' (Chinese) or 'en' (English)
        max_retries: Maximum retries if step patterns detected
        self_questioning_config: Optional SelfQuestioningConfig for candidate generation
        novelty_selector: Optional NoveltySelector for persisting novelity state
        embedding_provider: Optional EmbeddingProvider for creating new NoveltySelector if needed

    Returns:
        Complete problem.json dict
    """

    # Self-Questioning path
    if self_questioning_config and self_questioning_config.enabled:
        from .self_questioning import CandidateGenerator, NoveltySelector

        generator = CandidateGenerator(
            maas_client=maas_client,
            model_config=model_config,
            num_candidates=self_questioning_config.num_candidates,
            language=language,
            mcp_server=prompt_domain or mcp_server,
        )

        candidates = await generator.generate_candidates(
            intent_spec=intent_spec,
            tools_used=intent_spec.tools_used,
            sample_changes=intent_spec.sample_changes,
        )

        if novelty_selector is None:
            novelty_selector = NoveltySelector(
                novelty_weight=self_questioning_config.novelty_weight,
                coverage_weight=self_questioning_config.coverage_weight,
                embedding_provider=embedding_provider,
            )

        selected, reason = novelty_selector.select_best(
            candidates, intent_spec.tools_used
        )

        logger.info(f"Self-Questioning: selected candidate ({reason})")

        # Add selected to existing for future novelty computation
        novelty_selector.add_to_existing(selected.problem)

        nl_problem = {
            "problem": selected.problem,
            "context": selected.context,
            "expected_outcome": selected.expected_outcome,
            "candidates": [candidate.to_dict() for candidate in candidates],
            "selection_reason": reason,
        }
    else:
        # Original LLM-based problem generation path
        # Build prompt from intent spec with enriched sample changes
        sample_changes_enriched = _enrich_sample_changes(
            intent_spec.sample_changes, root
        )

        try:
            from prompts import PromptLoader

            loader = PromptLoader(prompt_domain or mcp_server)
            system_prompt = loader.get_mutation_rewrite_system(language=language)
            user_prompt = loader.get_mutation_rewrite_user(
                language=language,
                primary_action=intent_spec.primary_action,
                task_category=intent_spec.task_category.value,
                files_created=intent_spec.files_created,
                files_modified=intent_spec.files_modified,
                files_moved=intent_spec.files_moved,
                files_deleted=intent_spec.files_deleted,
                directories_created=intent_spec.directories_created,
                directories_deleted=intent_spec.directories_deleted,
                affected_directories=", ".join(intent_spec.affected_directories[:5])
                or "root",
                file_types=", ".join(intent_spec.file_types_involved) or "various",
                naming_patterns=", ".join(intent_spec.naming_patterns)
                or "none detected",
                sample_changes=json.dumps(
                    sample_changes_enriched, indent=2, ensure_ascii=False
                ),
                tools_used=", ".join(intent_spec.tools_used),
                # Cross-domain compatibility fields for prompt templates.
                navigations_count=intent_spec.tool_call_count,
                clicks_count=0,
                fills_count=0,
                screenshots_count=0,
                evaluations_count=0,
                visited_urls="unknown",
                url_categories="unknown",
                interacted_elements="unknown",
                sample_operations=json.dumps(
                    sample_changes_enriched, indent=2, ensure_ascii=False
                ),
                queries_executed=intent_spec.tool_call_count,
                tables_queried=max(1, len(intent_spec.affected_directories)),
                affected_tables=", ".join(intent_spec.affected_directories[:5])
                or "unknown",
                database_theme="unknown",
                column_types=", ".join(intent_spec.file_types_involved) or "unknown",
                sql_patterns="unknown",
            )
        except (ImportError, FileNotFoundError):
            # Fallback to inline prompts
            if language == "en":
                system_prompt = PROBLEM_REWRITE_SYSTEM_PROMPT_EN
                user_template = PROBLEM_REWRITE_USER_TEMPLATE_EN
            else:
                system_prompt = PROBLEM_REWRITE_SYSTEM_PROMPT_ZH
                user_template = PROBLEM_REWRITE_USER_TEMPLATE_ZH

            user_prompt = user_template.format(
                primary_action=intent_spec.primary_action,
                task_category=intent_spec.task_category.value,
                files_created=intent_spec.files_created,
                files_modified=intent_spec.files_modified,
                files_moved=intent_spec.files_moved,
                files_deleted=intent_spec.files_deleted,
                directories_created=intent_spec.directories_created,
                directories_deleted=intent_spec.directories_deleted,
                affected_directories=", ".join(intent_spec.affected_directories[:5])
                or "root",
                file_types=", ".join(intent_spec.file_types_involved) or "various",
                naming_patterns=", ".join(intent_spec.naming_patterns)
                or "none detected",
                sample_changes=json.dumps(
                    sample_changes_enriched, indent=2, ensure_ascii=False
                ),
                tools_used=", ".join(intent_spec.tools_used),
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        nl_problem = None

        for attempt in range(max_retries + 1):
            try:
                response = await maas_client.generate_completion(
                    messages=messages,
                    model_config=model_config,
                    tools=None,  # No tools for this call
                )

                content = response.get("content", "{}")

                # Parse JSON from response
                nl_problem = _parse_json_response(content)

                # Check for step patterns in the problem description
                problem_text = nl_problem.get("problem", "")
                if _check_step_patterns(problem_text):
                    logger.warning(
                        f"Step patterns detected in attempt {attempt + 1}, retrying..."
                    )
                    if attempt < max_retries:
                        # Add feedback to encourage non-step format
                        if language == "zh":
                            messages.append({"role": "assistant", "content": content})
                            messages.append(
                                {
                                    "role": "user",
                                    "content": "你的回答包含了步骤式描述。请重新撰写，用自然的口语表达任务目标，不要使用'第一步'、'然后'等顺序词。",
                                }
                            )
                        else:
                            messages.append({"role": "assistant", "content": content})
                            messages.append(
                                {
                                    "role": "user",
                                    "content": "Your response contains step-by-step instructions. Please rewrite using natural conversational language describing the goal, not using 'Step 1', 'then', etc.",
                                }
                            )
                        continue
                    else:
                        # All retries exhausted, use fallback
                        logger.warning("Max retries exhausted, using fallback")
                        nl_problem = _generate_fallback_problem(intent_spec, language)
                else:
                    # No step patterns, accept the response
                    break

            except Exception as e:
                logger.warning(
                    f"Failed to generate NL problem (attempt {attempt + 1}): {e}"
                )
                if attempt >= max_retries:
                    nl_problem = _generate_fallback_problem(intent_spec, language)

        if nl_problem is None:
            nl_problem = _generate_fallback_problem(intent_spec, language)

    # For mutation tasks, reference_answer is typically not applicable
    # It may be present in nl_problem if generated by LLM
    reference_answer = nl_problem.get("reference_answer", "")

    # Build complete problem.json
    problem_json = {
        "problem": nl_problem.get(
            "problem", _generate_fallback_problem(intent_spec, language)["problem"]
        ),
        "context": nl_problem.get("context", ""),
        "expected_outcome": nl_problem.get("expected_outcome", ""),
        "mcp_server": mcp_server,
        "target_tools": [
            t.get("name") or t.get("function", {}).get("name") for t in tools_subset
        ],
        "tools": tools_subset,
        "initialization": init_ops,
        "difficulty_bucket": _get_difficulty_bucket(intent_spec.tool_call_count),
        "intent_spec": intent_spec.to_dict(),
        "filesystem_root": root,
        "language": language,
    }

    # Add self-questioning metadata if enabled
    if (
        self_questioning_config
        and self_questioning_config.enabled
        and "nl_problem" in locals()
        and nl_problem
    ):
        problem_json["self_questioning"] = {
            "num_candidates": len(nl_problem.get("candidates", [])),
            "selection_reason": nl_problem.get("selection_reason", ""),
        }
        problem_json["problem_candidates"] = nl_problem.get("candidates", [])

    logger.info(
        f"Generated problem.json (mutation): {problem_json['problem'][:100]}..."
    )
    return problem_json


async def rewrite_retrieval_to_problem_json(
    retrieval_spec: RetrievalSpec,
    tools_subset: List[Dict[str, Any]],
    init_ops: List[Dict[str, Any]],
    mcp_server: str,
    maas_client: MaaSClient,
    model_config: ModelConfig,
    root: str,
    language: str = "zh",
    max_retries: int = 2,
    prompt_domain: Optional[str] = None,
) -> Dict[str, Any]:
    """Rewrite retrieval spec to natural language Q&A problem.json using small model.

    Args:
        retrieval_spec: The extracted retrieval specification
        tools_subset: Tools that were sampled for this episode
        init_ops: Initialization operations for problem.json
        mcp_server: MCP server name
        maas_client: MaaS client for LLM calls
        model_config: Model configuration for the small rewrite model
        root: Root directory path
        language: Output language: 'zh' (Chinese) or 'en' (English)
        max_retries: Maximum retries if generation fails

    Returns:
        Complete problem.json dict with reference_answer
    """
    # Truncate evidence snippet for prompt (keep full in spec)
    evidence_for_prompt = retrieval_spec.evidence_snippet[:2000]
    if len(retrieval_spec.evidence_snippet) > 2000:
        evidence_for_prompt += "\n... [truncated for prompt]"

    # Try to load prompts from file, fallback to inline
    try:
        from prompts import PromptLoader

        loader = PromptLoader(prompt_domain or mcp_server)
        system_prompt = loader.get_retrieval_rewrite_system(language=language)
        user_prompt = loader.get_retrieval_rewrite_user(
            language=language,
            query_focus=retrieval_spec.query_focus,
            evidence_tool=retrieval_spec.evidence_tool,
            evidence_arguments=json.dumps(
                retrieval_spec.evidence_arguments, ensure_ascii=False
            ),
            evidence_snippet=evidence_for_prompt,
            tool_call_summaries=json.dumps(
                retrieval_spec.tool_call_summaries[:5], indent=2, ensure_ascii=False
            ),
        )
    except (ImportError, FileNotFoundError):
        # Fallback to inline prompts
        if language == "en":
            system_prompt = RETRIEVAL_REWRITE_SYSTEM_PROMPT_EN
            user_template = RETRIEVAL_REWRITE_USER_TEMPLATE_EN
        else:
            system_prompt = RETRIEVAL_REWRITE_SYSTEM_PROMPT_ZH
            user_template = RETRIEVAL_REWRITE_USER_TEMPLATE_ZH

        user_prompt = user_template.format(
            query_focus=retrieval_spec.query_focus,
            evidence_tool=retrieval_spec.evidence_tool,
            evidence_arguments=json.dumps(
                retrieval_spec.evidence_arguments, ensure_ascii=False
            ),
            evidence_snippet=evidence_for_prompt,
            tool_call_summaries=json.dumps(
                retrieval_spec.tool_call_summaries[:5], indent=2, ensure_ascii=False
            ),
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    nl_problem = None

    for attempt in range(max_retries + 1):
        try:
            response = await maas_client.generate_completion(
                messages=messages, model_config=model_config, tools=None
            )

            content = response.get("content", "{}")
            nl_problem = _parse_json_response(content)

            # Check for step patterns
            problem_text = nl_problem.get("problem", "")
            if _check_step_patterns(problem_text):
                logger.warning(
                    f"Step patterns detected in retrieval attempt {attempt + 1}, retrying..."
                )
                if attempt < max_retries:
                    messages.append({"role": "assistant", "content": content})
                    messages.append(
                        {
                            "role": "user",
                            "content": "你的回答包含了步骤式描述或工具名称。请重新撰写，用自然的口语表达问题，不要提及具体工具。"
                            if language == "zh"
                            else "Your response contains step-by-step instructions or tool names. Please rewrite using natural language without mentioning specific tools.",
                        }
                    )
                    continue
                else:
                    nl_problem = _generate_fallback_retrieval_problem(
                        retrieval_spec, language
                    )
            else:
                break

        except Exception as e:
            logger.warning(
                f"Failed to generate retrieval problem (attempt {attempt + 1}): {e}"
            )
            if attempt >= max_retries:
                nl_problem = _generate_fallback_retrieval_problem(
                    retrieval_spec, language
                )

    if nl_problem is None:
        nl_problem = _generate_fallback_retrieval_problem(retrieval_spec, language)

    # Use LLM-generated answer if available, otherwise fall back to spec's reference_answer
    if nl_problem is None:
        # Use problem from self-questioning if available, else use existing nl_problem
        final_nl_problem = nl_problem
    else:
        # nl_problem was generated from self-questioning, already has the right format
        final_nl_problem = nl_problem

    reference_answer = nl_problem.get(
        "reference_answer", retrieval_spec.reference_answer
    )

    # Build complete problem.json for retrieval
    problem_json = {
        "problem": nl_problem.get(
            "problem",
            _generate_fallback_retrieval_problem(retrieval_spec, language)["problem"],
        ),
        "reference_answer": reference_answer,
        "context": nl_problem.get("context", ""),
        "expected_outcome": nl_problem.get(
            "expected_outcome",
            "提供准确的信息" if language == "zh" else "Provide accurate information",
        ),
        "task_type": TaskType.RETRIEVAL.value,
        "mcp_server": mcp_server,
        "target_tools": [
            t.get("name") or t.get("function", {}).get("name") for t in tools_subset
        ],
        "tools": tools_subset,
        "initialization": init_ops,
        "difficulty_bucket": _get_difficulty_bucket(retrieval_spec.tool_call_count),
        "retrieval_spec": retrieval_spec.to_dict(),
        "filesystem_root": root,
        "language": language,
        "answer_truncated": retrieval_spec.answer_truncated,
    }

    logger.info(
        f"Generated problem.json (retrieval): {problem_json['problem'][:100]}..."
    )
    return problem_json


def _generate_fallback_retrieval_problem(
    spec: RetrievalSpec, language: str = "zh"
) -> Dict[str, Any]:
    """Generate a fallback retrieval problem description when LLM fails."""

    if language == "zh":
        category_templates = {
            TaskCategory.FILE_SEARCH: "帮我在工作区里找一下相关的文件。",
            TaskCategory.CONTENT_QUERY: "帮我看看这个文件里有什么内容。",
            TaskCategory.INFORMATION_RETRIEVAL: "帮我查看一下目录结构。",
        }
        default = "帮我查询一下相关信息。"
        answer_prefix = "根据查询结果："
    else:
        category_templates = {
            TaskCategory.FILE_SEARCH: "Help me find relevant files in the workspace.",
            TaskCategory.CONTENT_QUERY: "Help me see what's in this file.",
            TaskCategory.INFORMATION_RETRIEVAL: "Help me check the directory structure.",
        }
        default = "Help me query the relevant information."
        answer_prefix = "Based on the query result:"

    problem = category_templates.get(spec.task_category, default)

    # Use reference answer from spec, truncated if needed
    ref_answer = spec.reference_answer
    if len(ref_answer) > 1000:
        ref_answer = ref_answer[:1000] + "..."

    return {
        "problem": problem,
        "reference_answer": f"{answer_prefix}\n{ref_answer}",
        "context": spec.query_focus,
    }


def _enrich_sample_changes(
    sample_changes: List[Dict[str, Any]], root: str
) -> List[Dict[str, Any]]:
    """Enrich sample changes with additional context without revealing steps.

    Args:
        sample_changes: Original sample changes
        root: Root directory path

    Returns:
        Enriched sample changes (limited to 3 representative examples)
    """
    enriched = []

    for change in sample_changes[:3]:  # Limit to 3 examples
        enriched_change = change.copy()

        # Make paths relative and more readable
        if "path" in enriched_change:
            try:
                rel_path = Path(enriched_change["path"]).relative_to(root)
                enriched_change["path"] = str(rel_path)
            except (ValueError, TypeError):
                pass

        if "from" in enriched_change:
            try:
                rel_from = Path(enriched_change["from"]).relative_to(root)
                enriched_change["from"] = str(rel_from)
            except (ValueError, TypeError):
                pass

        if "to" in enriched_change:
            try:
                rel_to = Path(enriched_change["to"]).relative_to(root)
                enriched_change["to"] = str(rel_to)
            except (ValueError, TypeError):
                pass

        enriched.append(enriched_change)

    return enriched


def _parse_json_response(content: str) -> Any:
    """Parse JSON (object or array) from LLM response, handling code fences."""
    content = content.strip()

    # Remove markdown code blocks
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first and last lines (```json and ```)
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # Try to find JSON object in content
    json_match = re.search(r"\{.*\}", content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Try direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def _generate_fallback_problem(
    intent_spec: IntentSpec, language: str = "zh"
) -> Dict[str, Any]:
    """Generate a fallback problem description when LLM fails."""

    if language == "zh":
        action_templates = {
            "organize": "帮我按{pattern}整理一下工作区里的文件。",
            "organize_by_date": "把文件按日期分类整理到对应的文件夹里。",
            "organize_by_type": "把文件按类型分类整理一下。",
            "create": "创建需要的文件和目录。",
            "create_structure": "搭建一下项目的目录结构。",
            "cleanup": "清理一下不需要的文件和文件夹。",
            "process": "处理并更新这些文件的内容。",
            "move": "把文件移动到合适的位置。",
            "modify": "对文件做一些必要的修改。",
            "standardize": "统一规范一下文件的命名。",
            "reorganize": "重新整理一下文件结构。",
        }
        pattern = "类别" if intent_spec.naming_patterns else "内容"
        default_template = f"对文件系统执行{intent_spec.primary_action}操作。"
        context = f"涉及{len(intent_spec.file_types_involved)}种文件类型。"
        outcome = f"文件应该被正确{intent_spec.primary_action}。"
    else:
        action_templates = {
            "organize": "Organize the files in the workspace by {pattern}.",
            "organize_by_date": "Organize the files into date-based folders.",
            "organize_by_type": "Organize the files into type-based folders.",
            "create": "Create new files and directories as needed.",
            "create_structure": "Set up a folder structure for the project.",
            "cleanup": "Clean up unnecessary files and folders.",
            "process": "Process and update the content of files.",
            "move": "Move files to their appropriate locations.",
            "modify": "Make necessary modifications to the files.",
            "standardize": "Standardize the naming of files.",
            "reorganize": "Reorganize the file structure.",
        }
        pattern = "category" if intent_spec.naming_patterns else "content"
        default_template = (
            f"Perform {intent_spec.primary_action} operations on the filesystem."
        )
        context = f"Working with {len(intent_spec.file_types_involved)} file types."
        outcome = f"Files should be properly {intent_spec.primary_action}d."

    problem = action_templates.get(intent_spec.primary_action, default_template).format(
        pattern=pattern
    )

    return {"problem": problem, "context": context, "expected_outcome": outcome}


def _get_difficulty_bucket(tool_call_count: int) -> str:
    """Map successful tool call count (PRD's n) to difficulty bucket.

    Based on PRD:
    - n=1 (入门/感知): easy
    - n=3~5 (中等): medium
    - n>5 (困难): hard/expert
    """
    if tool_call_count <= 1:
        return "easy"
    elif tool_call_count <= 5:
        return "medium"
    elif tool_call_count <= 10:
        return "hard"
    else:
        return "expert"


# ============================================================
# Quality Filters
# ============================================================


@dataclass
class FilterResult:
    """Result of applying quality filters."""

    passed: bool
    reason: Optional[str] = None


def _is_mcpmark_playwright_trajectory(trajectory: StrictTrajectory) -> bool:
    """Return whether trajectory belongs to the MCPMark Playwright world."""
    for message in trajectory.messages or []:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and "MCPMark Playwright executable world" in content:
            return True
    return False


def _has_successful_nonblank_browser_navigation(trajectory: StrictTrajectory) -> bool:
    """Return whether a browser trajectory reached a concrete non-blank page."""
    for call in trajectory.tool_calls or []:
        if not call.success:
            continue
        if call.tool_name == "browser_navigate":
            url = str((call.arguments or {}).get("url") or "").strip()
            if url and url != "about:blank":
                return True
        result_text = call.result or ""
        if re.search(r'"url"\s*:\s*"https?://', result_text):
            return True
    return False


def apply_hard_filters(trajectory: StrictTrajectory) -> FilterResult:
    """Apply hard filters (abort conditions).

    Hard filters cause immediate episode abort.
    """
    assistant_call_ids: List[str] = []
    tool_output_ids: List[str] = []
    for msg in trajectory.messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []) or []:
                if isinstance(tc, dict):
                    call_id = tc.get("id")
                    if call_id:
                        assistant_call_ids.append(str(call_id))
        elif msg.get("role") == "tool":
            call_id = msg.get("tool_call_id")
            if call_id:
                tool_output_ids.append(str(call_id))

    if len(set(assistant_call_ids)) != len(assistant_call_ids):
        return FilterResult(
            passed=False,
            reason="Trajectory invalid: duplicate assistant tool_call ids",
        )
    if len(set(tool_output_ids)) != len(tool_output_ids):
        return FilterResult(
            passed=False,
            reason="Trajectory invalid: duplicate tool message tool_call_id",
        )
    if len(assistant_call_ids) != len(tool_output_ids):
        return FilterResult(
            passed=False,
            reason=(
                "Trajectory invalid: assistant/tool message count mismatch "
                f"({len(assistant_call_ids)} vs {len(tool_output_ids)})"
            ),
        )
    if set(assistant_call_ids) != set(tool_output_ids):
        return FilterResult(
            passed=False,
            reason="Trajectory invalid: assistant/tool id sets mismatch",
        )

    trajectory_call_ids = [str(tc.call_id) for tc in trajectory.tool_calls if tc.call_id]
    # Detect ToolCallRecords with missing call_id — these indicate a data integrity issue
    # and would cause silent count mismatches if ignored.
    n_missing_call_id = sum(1 for tc in trajectory.tool_calls if not tc.call_id)
    if n_missing_call_id > 0:
        return FilterResult(
            passed=False,
            reason=(
                f"Trajectory invalid: {n_missing_call_id} tool_call record(s) "
                "have empty or None call_id"
            ),
        )
    if len(trajectory_call_ids) != len(tool_output_ids):
        return FilterResult(
            passed=False,
            reason=(
                "Trajectory invalid: tool_calls list and tool messages count mismatch "
                f"({len(trajectory_call_ids)} vs {len(tool_output_ids)})"
            ),
        )
    if set(trajectory_call_ids) != set(tool_output_ids):
        return FilterResult(
            passed=False,
            reason="Trajectory invalid: tool_calls ids and tool message ids mismatch",
        )

    successful_calls = sum(1 for tc in trajectory.tool_calls if tc.success)
    if successful_calls != trajectory.num_successful_tool_calls:
        return FilterResult(
            passed=False,
            reason=(
                "Trajectory invalid: num_successful_tool_calls inconsistent "
                f"(field={trajectory.num_successful_tool_calls}, actual={successful_calls})"
            ),
        )

    # Already handled by StrictTrajectory status
    if not trajectory.is_valid():
        return FilterResult(
            passed=False,
            reason=f"Trajectory invalid: {trajectory.status.value} - {trajectory.abort_reason}",
        )

    # Check minimum successful tool calls
    if trajectory.num_successful_tool_calls < 1:
        return FilterResult(
            passed=False,
            reason=f"No successful tool calls: {trajectory.num_successful_tool_calls}",
        )

    if trajectory.target_n > 0 and trajectory.num_successful_tool_calls < trajectory.target_n:
        return FilterResult(
            passed=False,
            reason=(
                "Target n not reached: "
                f"{trajectory.num_successful_tool_calls} < {trajectory.target_n}"
            ),
        )

    if _is_mcpmark_playwright_trajectory(
        trajectory
    ) and not _has_successful_nonblank_browser_navigation(trajectory):
        return FilterResult(
            passed=False,
            reason="MCPMark Playwright trajectory never reached a non-blank browser page",
        )

    return FilterResult(passed=True)


def apply_soft_filters(
    trajectory: StrictTrajectory,
    diff: FilesystemDiff,
    min_steps: int = 2,
    min_changes: int = 1,
    max_changes: int = 100,
    max_failure_rate: float = 0.5,
    task_type: Optional[TaskType] = None,
    retrieval_spec: Optional[RetrievalSpec] = None,
) -> FilterResult:
    """Apply soft filters (quality checks) with dual-mode support.

    Soft filters determine if the trajectory is worth keeping.
    Supports both mutation (diff > 0) and retrieval (diff == 0) modes.

    Args:
        trajectory: The collected trajectory
        diff: Filesystem diff
        min_steps: Minimum number of successful tool calls (PRD's n)
        min_changes: Minimum number of filesystem changes (mutation mode)
        max_changes: Maximum number of filesystem changes (mutation mode)
        max_failure_rate: Maximum failed_calls / total_calls ratio (soft filter)
        task_type: Explicit task type (if None, will be auto-determined)
        retrieval_spec: Retrieval spec for retrieval mode validation
    """
    # Check minimum successful tool calls (using PRD's n semantics)
    actual_n = trajectory.num_successful_tool_calls
    if actual_n < min_steps:
        return FilterResult(
            passed=False,
            reason=f"Too few successful tool calls: {actual_n} < {min_steps}",
        )

    # Filter high-failure trajectories:
    # failed calls cannot exceed 50% of all tool calls by default.
    failure_ratio_limit = max(0.0, min(1.0, float(max_failure_rate)))
    total_calls = len(trajectory.tool_calls)
    failed_calls = sum(1 for tc in trajectory.tool_calls if not tc.success)
    if total_calls > 0:
        failure_rate = failed_calls / total_calls
        if failure_rate > failure_ratio_limit:
            return FilterResult(
                passed=False,
                reason=(
                    "Failure ratio too high: "
                    f"{failed_calls}/{total_calls}={failure_rate:.2%} > {failure_ratio_limit:.2%}"
                ),
            )

    # Auto-determine task type if not provided
    if task_type is None:
        task_type = determine_task_type(diff, trajectory.tool_calls)

    # Apply mode-specific filters
    if task_type == TaskType.MUTATION:
        # Mutation mode: require filesystem changes
        if diff is None or diff.is_empty():
            return FilterResult(
                passed=False,
                reason="Empty diff - no filesystem changes (mutation mode requires changes)",
            )

        total_changes = diff.total_changes()

        # Check minimum changes
        if total_changes < min_changes:
            return FilterResult(
                passed=False, reason=f"Too few changes: {total_changes} < {min_changes}"
            )

        # Check maximum changes (prevent explosion)
        if total_changes > max_changes:
            return FilterResult(
                passed=False,
                reason=f"Too many changes: {total_changes} > {max_changes}",
            )

    else:  # TaskType.RETRIEVAL
        # Retrieval mode: require meaningful tool output (evidence)
        if retrieval_spec is None:
            # Build spec to validate
            retrieval_spec = build_retrieval_spec(trajectory.tool_calls, "")

        # Check we have evidence
        if (
            not retrieval_spec.evidence_snippet
            or len(retrieval_spec.evidence_snippet) < 20
        ):
            return FilterResult(
                passed=False,
                reason="No meaningful evidence from tool calls (retrieval mode requires output)",
            )

        # Check we have a reference answer
        if (
            not retrieval_spec.reference_answer
            or len(retrieval_spec.reference_answer) < 10
        ):
            return FilterResult(
                passed=False,
                reason="No reference answer could be generated from tool output",
            )

    return FilterResult(passed=True)


def apply_soft_filters_mutation(
    trajectory: StrictTrajectory,
    diff: FilesystemDiff,
    min_steps: int = 2,
    min_changes: int = 1,
    max_changes: int = 100,
    max_failure_rate: float = 0.5,
) -> FilterResult:
    """Apply soft filters for mutation mode only (backward compatible).

    This is a convenience wrapper for mutation-only filtering.
    """
    return apply_soft_filters(
        trajectory=trajectory,
        diff=diff,
        min_steps=min_steps,
        min_changes=min_changes,
        max_changes=max_changes,
        max_failure_rate=max_failure_rate,
        task_type=TaskType.MUTATION,
    )


def apply_soft_filters_retrieval(
    trajectory: StrictTrajectory,
    retrieval_spec: RetrievalSpec,
    min_steps: int = 1,
    max_failure_rate: float = 0.5,
) -> FilterResult:
    """Apply soft filters for retrieval mode only.

    This is a convenience wrapper for retrieval-only filtering.
    """
    # Create a dummy empty diff for retrieval mode
    from .state.filesystem_snapshot import FilesystemDiff

    empty_diff = FilesystemDiff()

    return apply_soft_filters(
        trajectory=trajectory,
        diff=empty_diff,
        min_steps=min_steps,
        min_changes=0,  # Not used in retrieval mode
        max_changes=0,  # Not used in retrieval mode
        max_failure_rate=max_failure_rate,
        task_type=TaskType.RETRIEVAL,
        retrieval_spec=retrieval_spec,
    )


# ============================================================
# Hindsight Reasoning (PRD 4.2 Step 3)
# ============================================================

# Hindsight Rewrite Prompts (Now imported from prompts.hindsight)


async def rewrite_trajectory_thoughts(
    trajectory: StrictTrajectory,
    problem: Dict[str, Any],
    maas_client: MaaSClient,
    model_config: ModelConfig,
    language: str = "en",
) -> StrictTrajectory:
    """Rewrite trajectory thoughts with hindsight reasoning (PRD 4.2 Step 3).

    Uses the synthesized problem and actual successful actions to create
    "God mode" chain-of-thought that removes exploration artifacts.

    Args:
        trajectory: The trajectory to rewrite
        problem: The synthesized problem dict
        maas_client: MaaS client for LLM calls
        model_config: Model configuration
        language: Output language: 'zh' (Chinese) or 'en' (English)

    Returns:
        The trajectory with rewritten thoughts (modified in-place)
    """
    if not trajectory.tool_calls:
        logger.debug("No tool calls to rewrite thoughts for")
        return trajectory

    # Build tool calls summary
    successful_calls = [tc for tc in trajectory.tool_calls if tc.success]
    if not successful_calls:
        logger.debug("No successful tool calls to rewrite")
        return trajectory

    tool_calls_summary = []
    for i, tc in enumerate(successful_calls, 1):
        summary = {
            "step": i,
            "tool": tc.tool_name,
            "arguments": tc.arguments,
            "original_thought": _extract_thought_from_messages(
                trajectory.messages, tc.tool_name
            ),
        }
        tool_calls_summary.append(summary)

    # Select prompts based on language
    if language == "zh":
        system_prompt = HINDSIGHT_REWRITE_SYSTEM_PROMPT_ZH
        user_template = HINDSIGHT_REWRITE_USER_TEMPLATE_ZH
    else:
        system_prompt = HINDSIGHT_REWRITE_SYSTEM_PROMPT_EN
        user_template = HINDSIGHT_REWRITE_USER_TEMPLATE_EN

    user_prompt = user_template.format(
        problem=problem.get("problem", ""),
        tool_calls_summary=json.dumps(tool_calls_summary, indent=2, ensure_ascii=False),
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = await maas_client.generate_completion(
            messages=messages, model_config=model_config, tools=None
        )

        content = response.get("content", "[]")
        rewrite_payload = _parse_json_response(content)
        rewritten_thoughts: List[Dict[str, Any]] = []
        final_response = ""

        if isinstance(rewrite_payload, dict):
            steps = rewrite_payload.get("steps", [])
            if isinstance(steps, list):
                rewritten_thoughts = steps
            final_response = str(rewrite_payload.get("final_response", "") or "").strip()
        elif isinstance(rewrite_payload, list):
            rewritten_thoughts = rewrite_payload

        if isinstance(rewritten_thoughts, list) and rewritten_thoughts:
            # Apply rewritten thoughts to trajectory messages
            _apply_rewritten_thoughts(trajectory, rewritten_thoughts)
            final_text = _build_hindsight_final_response(
                problem=problem,
                provided_response=final_response,
            )
            if final_text:
                _apply_hindsight_final_response(trajectory, final_text)
            logger.info(
                f"Hindsight reasoning: rewrote {len(rewritten_thoughts)} thoughts"
            )
        else:
            logger.warning("Hindsight reasoning: unexpected response format")

    except Exception as e:
        logger.warning(f"Hindsight reasoning failed: {e}")

    return trajectory


def _extract_thought_from_messages(
    messages: List[Dict[str, Any]], tool_name: str
) -> str:
    """Extract the original thought/reasoning for a tool call from messages."""
    for msg in messages:
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            # Check if this message contains the tool call
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                tc_name = (
                    tc.get("function", {}).get("name", "")
                    if isinstance(tc, dict)
                    else ""
                )
                if tc_name == tool_name:
                    # Return the assistant content as the thought
                    return content[:500] if content else ""
    return ""


def _apply_rewritten_thoughts(
    trajectory: StrictTrajectory, rewritten_thoughts: List[Dict[str, Any]]
):
    """Apply rewritten thoughts to trajectory messages.

    Updates the assistant message content before each tool call with the rewritten thought.
    """
    # Create a mapping from step to new thought
    thought_map = {}
    for item in rewritten_thoughts:
        if isinstance(item, dict):
            step = item.get("step", 0)
            thought = item.get("thought", "")
            tool = item.get("tool", "")
            if step and thought:
                thought_map[(step, tool)] = thought

    # Track which step we're on for each tool
    tool_step_counts = {}

    for i, msg in enumerate(trajectory.messages):
        if msg.get("role") == "assistant":
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                if isinstance(tc, dict):
                    tc_name = tc.get("function", {}).get("name", "")
                    if tc_name:
                        # Increment step count for this tool
                        if tc_name not in tool_step_counts:
                            tool_step_counts[tc_name] = 0
                        tool_step_counts[tc_name] += 1

                        # Find matching rewritten thought
                        total_step = sum(tool_step_counts.values())
                        key = (total_step, tc_name)
                        if key in thought_map:
                            # Update message content with rewritten thought
                            trajectory.messages[i]["content"] = thought_map[key]
                            trajectory.messages[i]["hindsight_rewritten"] = True


def _build_hindsight_final_response(
    problem: Dict[str, Any], provided_response: str
) -> str:
    """Build a final completion/answer text for hindsight rewrite output."""
    text = (provided_response or "").strip()
    if text:
        return text

    task_type = str(problem.get("task_type", TaskType.MUTATION.value) or "").lower()
    if task_type == TaskType.RETRIEVAL.value:
        reference_answer = str(problem.get("reference_answer", "") or "").strip()
        if reference_answer:
            if len(reference_answer) > 4000:
                reference_answer = reference_answer[:4000] + "\n... [truncated]"
            return (
                "Based on the observed tool outputs, here is the retrieval answer:\n"
                f"{reference_answer}"
            )
        return (
            "I have completed the retrieval task and provided the answer "
            "based on the observed evidence."
        )

    return (
        "I have completed the requested filesystem operations based on the "
        "observed tool outputs."
    )


def _apply_hindsight_final_response(
    trajectory: StrictTrajectory, final_response: str
) -> None:
    """Place final assistant response after the last tool-use turn."""
    if not final_response:
        return

    last_tool_turn_idx = -1
    for idx, msg in enumerate(trajectory.messages):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            last_tool_turn_idx = idx

    for idx in range(len(trajectory.messages) - 1, -1, -1):
        msg = trajectory.messages[idx]
        if (
            msg.get("role") == "assistant"
            and not msg.get("tool_calls")
            and idx > last_tool_turn_idx
        ):
            trajectory.messages[idx]["content"] = final_response
            trajectory.messages[idx]["hindsight_rewritten"] = True
            return

    trajectory.messages.append(
        {
            "role": "assistant",
            "content": final_response,
            "hindsight_rewritten": True,
        }
    )
