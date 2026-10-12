"""State management module for mcp-trajs2data."""

from .filesystem_snapshot import (
    FilesystemSnapshot,
    FilesystemDiff,
    FileInfo,
    DiffEntry,
    ChangeType,
    snapshot_filesystem,
    diff_snapshots,
)

from .filesystem_init_generator import (
    FilesystemInitGenerator,
    InitPlan,
    FileSpec,
    DirectorySpec,
    SizeProfile,
    generate_seed_env,
    init_plan_to_operations,
    execute_init_plan,
)

from .checkpoint_manager import (
    CheckpointManager,
    CheckpointType,
    Checkpoint,
    FailureEvent,
)

__all__ = [
    # Snapshot & Diff
    "FilesystemSnapshot",
    "FilesystemDiff",
    "FileInfo",
    "DiffEntry",
    "ChangeType",
    "snapshot_filesystem",
    "diff_snapshots",
    # Init Generator
    "FilesystemInitGenerator",
    "InitPlan",
    "FileSpec",
    "DirectorySpec",
    "SizeProfile",
    "generate_seed_env",
    "init_plan_to_operations",
    "execute_init_plan",
    # Checkpoint Manager (for recoverable collection)
    "CheckpointManager",
    "CheckpointType",
    "Checkpoint",
    "FailureEvent",
]
