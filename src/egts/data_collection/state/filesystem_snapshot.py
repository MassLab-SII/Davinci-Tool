"""Filesystem snapshot and diff utilities for mcp-trajs2data.

This module provides functionality to:
1. Take snapshots of filesystem state (S0, S1)
2. Compute diffs between snapshots to identify changes
"""

import logging
import hashlib
import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Any, Tuple
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)

# Debug logging - configurable via environment variable
_DEBUG_LOG_ENABLED = os.environ.get("TRAJS2DATA_DEBUG", "").lower() in (
    "1",
    "true",
    "yes",
)
_DEBUG_LOG_PATH = Path(
    os.environ.get("TRAJS2DATA_DEBUG_PATH", "/tmp/trajs2data_debug.log")
)


def _dbg(
    hypothesis_id: str,
    location: str,
    message: str,
    data: Dict[str, Any],
    run_id: str = "pre-fix",
) -> None:
    """Debug logging helper - only writes when enabled via environment."""
    if not _DEBUG_LOG_ENABLED:
        return
    try:
        payload = {
            "sessionId": "debug-session",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


class ChangeType(str, Enum):
    """Types of filesystem changes."""

    CREATED = "created"
    DELETED = "deleted"
    MODIFIED = "modified"
    MOVED = "moved"
    RENAMED = "renamed"


@dataclass
class FileInfo:
    """Information about a single file or directory."""

    path: str
    is_directory: bool
    size: int = 0
    content_hash: Optional[str] = None  # MD5 hash of content for files
    children: List[str] = field(default_factory=list)  # For directories

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileInfo":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class FilesystemSnapshot:
    """A snapshot of filesystem state at a point in time."""

    root: str
    files: Dict[str, FileInfo] = field(default_factory=dict)  # path -> FileInfo
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "root": self.root,
            "files": {k: v.to_dict() for k, v in self.files.items()},
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FilesystemSnapshot":
        """Create from dictionary."""
        files = {k: FileInfo.from_dict(v) for k, v in data.get("files", {}).items()}
        return cls(root=data["root"], files=files, timestamp=data.get("timestamp"))

    def get_all_paths(self) -> Set[str]:
        """Get all paths in this snapshot."""
        return set(self.files.keys())

    def get_file_paths(self) -> Set[str]:
        """Get paths of files only (not directories)."""
        return {p for p, info in self.files.items() if not info.is_directory}

    def get_directory_paths(self) -> Set[str]:
        """Get paths of directories only."""
        return {p for p, info in self.files.items() if info.is_directory}


@dataclass
class DiffEntry:
    """A single change in the filesystem diff."""

    change_type: ChangeType
    path: str
    old_path: Optional[str] = None  # For moves/renames
    old_info: Optional[FileInfo] = None
    new_info: Optional[FileInfo] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "change_type": self.change_type.value,
            "path": self.path,
            "old_path": self.old_path,
            "old_info": self.old_info.to_dict() if self.old_info else None,
            "new_info": self.new_info.to_dict() if self.new_info else None,
        }


@dataclass
class FilesystemDiff:
    """Diff between two filesystem snapshots."""

    created: List[DiffEntry] = field(default_factory=list)
    deleted: List[DiffEntry] = field(default_factory=list)
    modified: List[DiffEntry] = field(default_factory=list)
    moved: List[DiffEntry] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "created": [e.to_dict() for e in self.created],
            "deleted": [e.to_dict() for e in self.deleted],
            "modified": [e.to_dict() for e in self.modified],
            "moved": [e.to_dict() for e in self.moved],
        }

    def is_empty(self) -> bool:
        """Check if the diff has no changes."""
        return not (self.created or self.deleted or self.modified or self.moved)

    def total_changes(self) -> int:
        """Get total number of changes."""
        return (
            len(self.created) + len(self.deleted) + len(self.modified) + len(self.moved)
        )

    def get_change_summary(self) -> Dict[str, int]:
        """Get summary of changes by type."""
        return {
            "created": len(self.created),
            "deleted": len(self.deleted),
            "modified": len(self.modified),
            "moved": len(self.moved),
            "total": self.total_changes(),
        }

    def get_affected_paths(self) -> Set[str]:
        """Get all paths affected by changes."""
        paths = set()
        for entry in self.created + self.deleted + self.modified + self.moved:
            paths.add(entry.path)
            if entry.old_path:
                paths.add(entry.old_path)
        return paths

    def get_action_types(self) -> Set[str]:
        """Get types of actions performed (for intent spec)."""
        actions = set()
        if self.created:
            # Distinguish between file and directory creation
            for entry in self.created:
                if entry.new_info and entry.new_info.is_directory:
                    actions.add("create_directory")
                else:
                    actions.add("create_file")
        if self.deleted:
            actions.add("delete")
        if self.modified:
            actions.add("edit")
        if self.moved:
            # Check if it's a rename (same directory) or move
            for entry in self.moved:
                if entry.old_path:
                    old_dir = str(Path(entry.old_path).parent)
                    new_dir = str(Path(entry.path).parent)
                    if old_dir == new_dir:
                        actions.add("rename")
                    else:
                        actions.add("move")
        return actions


def _compute_content_hash(content: str) -> str:
    """Compute MD5 hash of content."""
    return hashlib.md5(content.encode("utf-8")).hexdigest()


async def snapshot_filesystem(
    mcp_client, root: str, include_content_hash: bool = True, max_depth: int = 10
) -> FilesystemSnapshot:
    """Take a snapshot of the filesystem state using MCP tools.

    Args:
        mcp_client: MCP client for calling filesystem tools
        root: Root directory to snapshot
        include_content_hash: Whether to compute content hashes for files
        max_depth: Maximum depth to traverse

    Returns:
        FilesystemSnapshot containing all files and directories
    """
    from datetime import datetime

    snapshot = FilesystemSnapshot(root=root, timestamp=datetime.now().isoformat())

    _dbg(
        "H3",
        "filesystem_snapshot.py:snapshot_filesystem:entry",
        "snapshot start",
        {
            "root": root,
            "include_content_hash": include_content_hash,
            "max_depth": max_depth,
        },
    )

    async def traverse_directory(path: str, depth: int = 0):
        """Recursively traverse directory and collect file info."""
        if depth > max_depth:
            logger.warning(f"Max depth reached at {path}")
            return

        try:
            # Use directory_tree if available, otherwise list_directory
            result = await mcp_client.call_tool(
                "directory_tree", {"path": path, "depth": 1}
            )

            # Parse the result
            result_text = _extract_tool_result_text(result)
            _dbg(
                "H3",
                "filesystem_snapshot.py:traverse_directory:directory_tree",
                "directory_tree result",
                {"path": path, "depth": depth, "result_preview_400": result_text[:400]},
            )
            entries = _parse_directory_listing(result_text, path)
            _dbg(
                "H3",
                "filesystem_snapshot.py:traverse_directory:parsed_entries",
                "parsed entries",
                {
                    "path": path,
                    "depth": depth,
                    "entries_count": len(entries),
                    "sample": entries[:10],
                },
            )

            for entry_path, is_dir in entries:
                # Normalize path
                normalized_path = str(Path(entry_path))

                if is_dir:
                    # Add directory entry
                    snapshot.files[normalized_path] = FileInfo(
                        path=normalized_path, is_directory=True, size=0
                    )
                    # Recursively traverse
                    await traverse_directory(normalized_path, depth + 1)
                else:
                    # Get file info
                    file_info = FileInfo(
                        path=normalized_path, is_directory=False, size=0
                    )

                    # Try to get file info (size)
                    try:
                        info_result = await mcp_client.call_tool(
                            "get_file_info", {"path": normalized_path}
                        )
                        info_text = _extract_tool_result_text(info_result)
                        file_info.size = _parse_file_size(info_text)
                    except Exception as e:
                        logger.debug(
                            f"Could not get file info for {normalized_path}: {e}"
                        )

                    # Compute content hash if requested
                    if include_content_hash:
                        try:
                            content_result = await mcp_client.call_tool(
                                "read_file", {"path": normalized_path}
                            )
                            content = _extract_tool_result_text(content_result)
                            file_info.content_hash = _compute_content_hash(content)
                        except Exception as e:
                            logger.debug(
                                f"Could not read file for hash {normalized_path}: {e}"
                            )

                    snapshot.files[normalized_path] = file_info

        except Exception as e:
            logger.warning(f"Error traversing {path}: {e}")
            # Try simpler list_directory as fallback
            try:
                result = await mcp_client.call_tool("list_directory", {"path": path})
                result_text = _extract_tool_result_text(result)
                _dbg(
                    "H3",
                    "filesystem_snapshot.py:traverse_directory:list_directory",
                    "list_directory result (fallback)",
                    {
                        "path": path,
                        "depth": depth,
                        "result_preview_400": result_text[:400],
                        "error": str(e),
                    },
                )
                entries = _parse_simple_listing(result_text, path)
                _dbg(
                    "H3",
                    "filesystem_snapshot.py:traverse_directory:parsed_entries_fallback",
                    "parsed entries (fallback)",
                    {
                        "path": path,
                        "depth": depth,
                        "entries_count": len(entries),
                        "sample": entries[:10],
                    },
                )

                for entry_path, is_dir in entries:
                    normalized_path = str(Path(entry_path))

                    if is_dir:
                        snapshot.files[normalized_path] = FileInfo(
                            path=normalized_path, is_directory=True, size=0
                        )
                        await traverse_directory(normalized_path, depth + 1)
                    else:
                        snapshot.files[normalized_path] = FileInfo(
                            path=normalized_path, is_directory=False, size=0
                        )
            except Exception as e2:
                logger.error(f"Failed to list directory {path}: {e2}")

    # Add root directory
    snapshot.files[root] = FileInfo(path=root, is_directory=True, size=0)

    # Start traversal
    await traverse_directory(root)

    # High-frequency path in recoverable mode; keep this at DEBUG to avoid log spam.
    logger.debug(f"Snapshot captured: {len(snapshot.files)} entries (root={root})")
    return snapshot


def _extract_tool_result_text(result) -> str:
    """Extract text content from MCP tool result."""
    # Dict-style results (some MCP client implementations)
    if isinstance(result, dict):
        # Prefer structuredContent if present
        sc = result.get("structuredContent")
        if isinstance(sc, dict):
            sc_content = sc.get("content")
            if isinstance(sc_content, str):
                return sc_content
        # Fallback: join text items from content[]
        content = result.get("content")
        if isinstance(content, list):
            texts: List[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    texts.append(item["text"])
                else:
                    texts.append(str(item))
            return "\n".join(texts)
        return str(result)

    if hasattr(result, "content"):
        if isinstance(result.content, list):
            texts = []
            for item in result.content:
                if hasattr(item, "text"):
                    texts.append(item.text)
                else:
                    texts.append(str(item))
            return "\n".join(texts)
        return str(result.content)
    return str(result)


def _parse_directory_listing(
    result_text: str, parent_path: str
) -> List[Tuple[str, bool]]:
    """Parse directory_tree output to extract entries.

    Returns list of (path, is_directory) tuples.
    """
    import re
    import json

    entries: List[Tuple[str, bool]] = []
    parent_path_norm = str(Path(parent_path))
    parent_name = Path(parent_path).name

    # Newer filesystem servers may return JSON (list of nodes with name/type/children)
    rt = (result_text or "").strip()
    if rt.startswith("[") or rt.startswith("{"):
        try:
            data = json.loads(rt)
        except Exception:
            data = None

        def _iter_nodes(obj: Any) -> List[Dict[str, Any]]:
            if isinstance(obj, list):
                return [x for x in obj if isinstance(x, dict)]
            if isinstance(obj, dict):
                # sometimes wrapped
                if isinstance(obj.get("children"), list):
                    return [obj]
                if isinstance(obj.get("content"), list):
                    return [x for x in obj["content"] if isinstance(x, dict)]
                return [obj]
            return []

        nodes = _iter_nodes(data)
        # If nodes look like directory entries, extract first-level children
        if nodes and any("name" in n and "type" in n for n in nodes):
            for node in nodes:
                name = node.get("name")
                typ = node.get("type")
                if not isinstance(name, str) or not isinstance(typ, str):
                    continue
                is_dir = typ.lower() == "directory"
                # skip hidden
                if name.startswith("."):
                    continue
                full_path = str(Path(parent_path) / name)
                entries.append((full_path, is_dir))
            return entries

    lines = (result_text or "").splitlines()

    for raw_line in lines:
        line = (raw_line or "").rstrip("\n")
        if not line.strip():
            continue

        stripped = line.strip()

        # Skip common header / metadata lines
        lower = stripped.lower()
        if (
            lower.startswith("directory tree")
            or lower.startswith("tree view")
            or lower.startswith("path:")
        ):
            continue

        # Extract the entry name from common tree formats
        name_part = stripped
        if "──" in name_part:
            # e.g. "├── file.txt" or "└── dir/"
            name_part = name_part.split("──")[-1].strip()
        else:
            # e.g. "- dir/" or "  - file.txt"
            name_part = re.sub(r"^[\s│├└─]+", "", name_part)
            name_part = re.sub(r"^[\-\*•]\s*", "", name_part)

        # Detect directory marker BEFORE stripping
        is_dir = ("[DIR]" in stripped) or name_part.endswith("/")

        # Remove markers and normalize
        name_part = name_part.replace("[DIR]", "").replace("[FILE]", "").strip()
        if not name_part:
            continue

        candidate = name_part.rstrip("/").strip().strip("`\"'")

        # Skip the root directory itself (some servers print only basename)
        if candidate == parent_path_norm.rstrip("/") or candidate == parent_name:
            continue

        # Skip hidden files/directories for cleaner snapshots (Deterministic Filter)
        if candidate.startswith(".") or candidate == "__pycache__":
            continue

        # Build full path
        if candidate.startswith(parent_path_norm):
            full_path = str(Path(candidate))
        elif candidate.startswith("/"):
            full_path = str(Path(candidate))
        else:
            full_path = str(Path(parent_path) / candidate)

        entries.append((full_path, is_dir))

    return entries


def _parse_simple_listing(result_text: str, parent_path: str) -> List[Tuple[str, bool]]:
    """Parse simple list_directory output."""
    import re

    entries: List[Tuple[str, bool]] = []
    parent_path_norm = str(Path(parent_path))
    parent_name = Path(parent_path).name

    lines = (result_text or "").splitlines()

    for raw_line in lines:
        line = (raw_line or "").strip()
        if not line:
            continue

        # Detect directory marker BEFORE stripping
        is_dir = ("[DIR]" in line) or line.endswith("/")

        # Remove bullet prefixes like "- " or "* "
        clean = re.sub(r"^[\-\*•]\s*", "", line)

        # Remove markers and normalize
        name = clean.replace("[DIR]", "").replace("[FILE]", "").strip()
        name = name.rstrip("/").strip().strip("`\"'")

        if not name:
            continue
        if name == parent_path_norm.rstrip("/") or name == parent_name:
            continue
        if name.startswith("."):
            continue

        if name.startswith(parent_path_norm):
            full_path = str(Path(name))
        elif name.startswith("/"):
            full_path = str(Path(name))
        else:
            full_path = str(Path(parent_path) / name)

        entries.append((full_path, is_dir))

    return entries


def _parse_file_size(info_text: str) -> int:
    """Parse file size from get_file_info output."""
    # Look for size: <number> or Size: <number>
    import re

    match = re.search(r"[Ss]ize:\s*(\d+)", info_text)
    if match:
        return int(match.group(1))
    return 0


def diff_snapshots(
    snapshot_before: FilesystemSnapshot,
    snapshot_after: FilesystemSnapshot,
    detect_moves: bool = True,
) -> FilesystemDiff:
    """Compute diff between two filesystem snapshots.

    Args:
        snapshot_before: The S0 (initial) snapshot
        snapshot_after: The S1 (final) snapshot
        detect_moves: Whether to detect file moves (by content hash)

    Returns:
        FilesystemDiff with all changes
    """
    diff = FilesystemDiff()

    paths_before = snapshot_before.get_all_paths()
    paths_after = snapshot_after.get_all_paths()

    # Find created and deleted paths
    created_paths = paths_after - paths_before
    deleted_paths = paths_before - paths_after
    common_paths = paths_before & paths_after

    # Track which deleted files were actually moved
    moved_deleted_paths: Set[str] = set()

    # Detect moves by matching content hashes
    if detect_moves:
        deleted_files_with_hash: Dict[str, str] = {}  # hash -> path
        for path in deleted_paths:
            info = snapshot_before.files[path]
            if not info.is_directory and info.content_hash:
                deleted_files_with_hash[info.content_hash] = path

        for path in list(created_paths):
            info = snapshot_after.files[path]
            if not info.is_directory and info.content_hash:
                if info.content_hash in deleted_files_with_hash:
                    old_path = deleted_files_with_hash[info.content_hash]
                    # This is a move/rename
                    diff.moved.append(
                        DiffEntry(
                            change_type=ChangeType.MOVED,
                            path=path,
                            old_path=old_path,
                            old_info=snapshot_before.files[old_path],
                            new_info=info,
                        )
                    )
                    created_paths.discard(path)
                    moved_deleted_paths.add(old_path)

    # Record created entries (excluding moves)
    for path in created_paths:
        info = snapshot_after.files[path]
        diff.created.append(
            DiffEntry(change_type=ChangeType.CREATED, path=path, new_info=info)
        )

    # Record deleted entries (excluding moves)
    for path in deleted_paths:
        if path not in moved_deleted_paths:
            info = snapshot_before.files[path]
            diff.deleted.append(
                DiffEntry(change_type=ChangeType.DELETED, path=path, old_info=info)
            )

    # Check for modifications in common paths
    for path in common_paths:
        info_before = snapshot_before.files[path]
        info_after = snapshot_after.files[path]

        # Skip directories
        if info_before.is_directory or info_after.is_directory:
            continue

        # Check if content changed (by hash or size)
        content_changed = False
        if info_before.content_hash and info_after.content_hash:
            content_changed = info_before.content_hash != info_after.content_hash
        elif info_before.size != info_after.size:
            # If no hash available, use size but tolerate tiny differences (metadata overhead)
            # Only flag if size diff > 4KB (block size) or strictly different for small files
            size_diff = abs(info_before.size - info_after.size)
            if size_diff > 4096 or (info_before.size < 4096 and size_diff > 0):
                content_changed = True

        if content_changed:
            diff.modified.append(
                DiffEntry(
                    change_type=ChangeType.MODIFIED,
                    path=path,
                    old_info=info_before,
                    new_info=info_after,
                )
            )

    # Sort lists to ensure deterministic output order
    diff.created.sort(key=lambda x: x.path)
    diff.deleted.sort(key=lambda x: x.path)
    diff.modified.sort(key=lambda x: x.path)
    diff.moved.sort(key=lambda x: x.path)

    logger.info(f"Diff computed: {diff.get_change_summary()}")
    return diff


def snapshot_to_json(snapshot: FilesystemSnapshot) -> str:
    """Serialize snapshot to JSON string."""
    return json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False)


def diff_to_json(diff: FilesystemDiff) -> str:
    """Serialize diff to JSON string."""
    return json.dumps(diff.to_dict(), indent=2, ensure_ascii=False)
