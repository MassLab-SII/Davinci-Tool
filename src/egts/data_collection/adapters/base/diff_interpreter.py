from abc import ABC, abstractmethod
from typing import Any, Dict, List, Set, Optional
from dataclasses import dataclass, field
from enum import Enum


class TaskCategory(str, Enum):
    """Categories of tasks."""

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
    # New categories for other domains can be added here or extended


@dataclass
class IntentSpec:
    """Specification of the inferred task intent from trajectory."""

    # Core intent summary
    primary_action: str
    task_category: TaskCategory

    # Domain specific changes (flexible dict)
    changes: Dict[str, Any] = field(default_factory=dict)

    # Tool usage info
    tools_used: List[str] = field(default_factory=list)
    tool_call_count: int = 0

    # Complexity
    complexity_score: int = 1

    # Context samples
    sample_changes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary_action": self.primary_action,
            "task_category": self.task_category.value,
            "changes": self.changes,
            "tools_used": self.tools_used,
            "tool_call_count": self.tool_call_count,
            "complexity_score": self.complexity_score,
            "sample_changes": self.sample_changes,
        }


class DiffInterpreter(ABC):
    """Abstract base class for interpreting differences between states."""

    @abstractmethod
    def interpret(self, diff: Any, tool_calls: List[Any], root_path: str) -> IntentSpec:
        """Interpret a diff and tool calls to produce an intent specification.

        Args:
            diff: The difference object (domain specific)
            tool_calls: List of tool calls executed
            root_path: Root path or context identifier

        Returns:
            IntentSpec describing what happened
        """
        pass
