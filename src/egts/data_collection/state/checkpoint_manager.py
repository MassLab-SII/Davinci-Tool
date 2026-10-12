from typing import Any, Optional
from pathlib import Path
import logging
import time
import copy
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Tuple

from data_collection.adapters.filesystem.snapshot_provider import (
    FilesystemSnapshotProvider,
)
from data_collection.adapters.base.interfaces import SnapshotProvider

logger = logging.getLogger(__name__)


class CheckpointType(str, Enum):
    """Types of checkpoints."""

    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"
    MANUAL = "manual"


@dataclass
class FailureEvent:
    """Record of a single failure during collection."""

    tool_name: str
    error_type: str
    error_message: str
    at_step: int
    at_checkpoint: int
    recovered: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "error_type": self.error_type,
            "error_message": self.error_message[:500],
            "at_step": self.at_step,
            "at_checkpoint": self.at_checkpoint,
            "recovered": self.recovered,
            "timestamp": self.timestamp,
        }


@dataclass
class Checkpoint:
    """A checkpoint capturing the state at a point in time."""

    checkpoint_id: int
    checkpoint_type: CheckpointType

    messages: List[Dict[str, Any]]
    num_successful_tool_calls: int
    num_steps: int
    tools_used: List[str]
    tool_calls_count: int = 0

    snapshot: Any = None

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    snapshot_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        snapshot_val = str(self.snapshot) if self.snapshot else None

        return {
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_type": self.checkpoint_type.value,
            "num_successful_tool_calls": self.num_successful_tool_calls,
            "num_steps": self.num_steps,
            "tools_used": self.tools_used,
            "tool_calls_count": self.tool_calls_count,
            "created_at": self.created_at,
            "snapshot_time_ms": self.snapshot_time_ms,
            "snapshot": snapshot_val,
        }


class CheckpointManager:
    """Manages checkpoints using adapter pattern for snapshot storage."""

    def __init__(
        self,
        workspace_path: Path,
        mcp_client: Optional[Any] = None,
        snapshot_provider: Optional[SnapshotProvider] = None,
        max_failures: int = 3,
        max_failures_per_tool: int = 2,
        enable_filesystem_snapshots: bool = True,
        snapshot_strategy: str = "incremental",
    ):
        self.workspace_path = Path(workspace_path)

        if snapshot_provider:
            self.snapshot_provider = snapshot_provider
        else:
            self.snapshot_provider = FilesystemSnapshotProvider(
                mcp_client, str(workspace_path)
            )

        self.max_failures = max_failures
        self.max_failures_per_tool = max_failures_per_tool
        self.enable_snapshots = enable_filesystem_snapshots

        self._checkpoints: List[Checkpoint] = []
        self._failure_events: List[FailureEvent] = []
        self._current_checkpoint_id = 0
        self._total_failures = 0
        self._failures_by_tool: Dict[str, int] = {}

        self._total_snapshot_time_ms = 0.0
        self._total_restore_time_ms = 0.0

    @property
    def total_failures(self) -> int:
        """Total number of failures recorded."""
        return self._total_failures

    @property
    def should_salvage(self) -> bool:
        """Check if we should salvage (max failures reached)."""
        return self._total_failures >= self.max_failures

    @property
    def failure_events(self) -> List[FailureEvent]:
        """Get all recorded failure events."""
        return self._failure_events.copy()

    def get_tool_failure_count(self, tool_name: str) -> int:
        """Get failure count for a specific tool."""
        return self._failures_by_tool.get(tool_name, 0)

    def should_skip_tool(self, tool_name: str) -> bool:
        """Check if a tool should be skipped due to too many failures."""
        return self.get_tool_failure_count(tool_name) >= self.max_failures_per_tool

    async def create_checkpoint(
        self,
        messages: List[Dict[str, Any]],
        num_successful_tool_calls: int,
        num_steps: int,
        tools_used: List[str],
        tool_calls_count: int = 0,
        checkpoint_type: CheckpointType = CheckpointType.PRE_TOOL_CALL,
    ) -> Checkpoint:
        """Create a new checkpoint."""
        checkpoint_id = self._current_checkpoint_id
        self._current_checkpoint_id += 1

        snapshot = None
        snapshot_time_ms = 0.0

        if self.enable_snapshots:
            start_time = time.time()
            try:
                snapshot = await self.snapshot_provider.create_snapshot(
                    str(checkpoint_id)
                )
            except Exception as e:
                logger.warning(f"Failed to create snapshot via provider: {e}")

            snapshot_time_ms = (time.time() - start_time) * 1000
            self._total_snapshot_time_ms += snapshot_time_ms

        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            checkpoint_type=checkpoint_type,
            messages=copy.deepcopy(messages),
            num_successful_tool_calls=num_successful_tool_calls,
            num_steps=num_steps,
            tools_used=tools_used.copy(),
            tool_calls_count=tool_calls_count,
            snapshot=snapshot,
            snapshot_time_ms=snapshot_time_ms,
        )

        self._checkpoints.append(checkpoint)
        logger.debug(
            f"Created checkpoint {checkpoint_id} (snapshot: {snapshot_time_ms:.1f}ms)"
        )
        return checkpoint

    def record_failure(
        self, tool_name: str, error_type: str, error_message: str, at_step: int
    ) -> FailureEvent:
        """Record a failure event."""
        self._total_failures += 1

        if tool_name and tool_name != "none":
            self._failures_by_tool[tool_name] = (
                self._failures_by_tool.get(tool_name, 0) + 1
            )

        event = FailureEvent(
            tool_name=tool_name,
            error_type=error_type,
            error_message=error_message,
            at_step=at_step,
            at_checkpoint=self._current_checkpoint_id - 1,
            recovered=False,
        )

        self._failure_events.append(event)
        logger.info(
            f"Recorded failure #{self._total_failures}: {tool_name} - {error_type}"
        )
        return event

    def rollback_to_checkpoint(
        self, checkpoint_id: Optional[int] = None
    ) -> Optional[Checkpoint]:
        """Rollback to a checkpoint."""
        if not self._checkpoints:
            logger.warning("No checkpoints available for rollback")
            return None

        if checkpoint_id is None:
            checkpoint = self._checkpoints[-1]
        else:
            checkpoint = next(
                (cp for cp in self._checkpoints if cp.checkpoint_id == checkpoint_id),
                None,
            )
            if checkpoint is None:
                logger.warning(f"Checkpoint {checkpoint_id} not found")
                return None

        if checkpoint.snapshot:
            start_time = time.time()
            try:
                self.snapshot_provider.restore_snapshot(checkpoint.snapshot)
                restore_time_ms = (time.time() - start_time) * 1000
                self._total_restore_time_ms += restore_time_ms
                logger.debug(
                    f"State restored from checkpoint {checkpoint.checkpoint_id} ({restore_time_ms:.1f}ms)"
                )
            except Exception as e:
                logger.error(f"Failed to restore snapshot: {e}")

        if self._failure_events:
            self._failure_events[-1].recovered = True

        self._checkpoints = [
            cp
            for cp in self._checkpoints
            if cp.checkpoint_id <= checkpoint.checkpoint_id
        ]

        logger.info(f"Rolled back to checkpoint {checkpoint.checkpoint_id}")
        return checkpoint

    def get_latest_valid_state(
        self, min_tools: int = 1, required_anchors: Optional[List[str]] = None
    ) -> Optional[Checkpoint]:
        """Get the latest checkpoint that meets minimum viability criteria."""
        for cp in reversed(self._checkpoints):
            if cp.num_successful_tool_calls < min_tools:
                continue

            if required_anchors:
                has_anchor = any(t in required_anchors for t in cp.tools_used)
                if not has_anchor:
                    continue

            return cp
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get checkpoint manager statistics."""
        return {
            "total_checkpoints": len(self._checkpoints),
            "total_failures": self._total_failures,
            "failures_by_tool": dict(self._failures_by_tool),
            "failure_events": [e.to_dict() for e in self._failure_events],
            "total_snapshot_time_ms": self._total_snapshot_time_ms,
            "total_restore_time_ms": self._total_restore_time_ms,
            "avg_snapshot_time_ms": (
                self._total_snapshot_time_ms / len(self._checkpoints)
                if self._checkpoints
                else 0.0
            ),
            "rollback_count": sum(1 for e in self._failure_events if e.recovered),
        }

    def cleanup(self):
        """Clean up checkpoint storage."""
        if self.snapshot_provider:
            self.snapshot_provider.cleanup()
