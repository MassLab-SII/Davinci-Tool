from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class InitPlan:
    """Plan for initializing an environment."""

    root: str
    seed: int
    operations: List[Dict[str, Any]]

    def get_summary(self) -> Dict[str, Any]:
        return {"seed": self.seed, "total_operations": len(self.operations)}

    def to_operations(self) -> List[Dict[str, Any]]:
        """Convert plan to list of tool operations."""
        return self.operations


class EnvInitGenerator(ABC):
    """Abstract base class for environment initialization generators."""

    @abstractmethod
    def generate_init_plan(self, root: str, size_profile: str) -> InitPlan:
        """Generate an initialization plan."""
        pass


class SnapshotProvider(ABC):
    """Abstract base class for state snapshotting."""

    @abstractmethod
    async def create_snapshot(self, identifier: str) -> Any:
        """Create a snapshot of the current state.

        Args:
            identifier: Unique identifier for this snapshot (e.g. checkpoint ID)

        Returns:
            Snapshot object or path
        """
        pass

    @abstractmethod
    def restore_snapshot(self, snapshot: Any) -> None:
        """Restore state from a snapshot.

        Args:
            snapshot: The snapshot object returned by create_snapshot
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up snapshot resources."""
        pass


class DiffComparator(ABC):
    """Abstract base class for comparing states."""

    @abstractmethod
    def diff(self, state_a: Any, state_b: Any) -> Any:
        """Compute difference between two states."""
        pass

    @abstractmethod
    def get_change_summary(self, diff: Any) -> str:
        """Get human readable summary of changes."""
        pass
