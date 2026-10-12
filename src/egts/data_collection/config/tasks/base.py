from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class BaseTaskConfig(BaseModel):
    """Base configuration for all task types."""

    model_config = {"extra": "allow"}

    task_type: str = Field(..., description="Discriminator field for task type")

    # Common settings for all tasks
    max_steps: int = Field(
        default=15, description="Maximum tool call steps per episode"
    )

    # Server configuration (NEW)
    required_servers: List[str] = Field(
        default_factory=list,
        description="List of MCP servers required for this task type",
    )

    primary_server: Optional[str] = Field(
        default=None,
        description="Primary server for state management (defaults to first in required_servers)",
    )

    # Lifecycle hooks (NEW)
    prepare_hook: Optional[str] = Field(
        default=None,
        description="Python function path for environment preparation (e.g., 'module.function')",
    )

    cleanup_hook: Optional[str] = Field(
        default=None,
        description="Python function path for environment cleanup (e.g., 'module.function')",
    )

    # Tool configuration
    read_only_tools: List[str] = Field(
        default_factory=list,
        description="List of tools considered read-only (no side effects)",
    )

    read_only_tools_priority: List[str] = Field(
        default_factory=list,
        description="Priority list of read-only tools for evidence selection",
    )

    # Optional task/world metadata for automation
    prompt_domain: Optional[str] = Field(
        default=None,
        description="Prompt domain/profile override for synthesis and self-questioning",
    )
    output_namespace: Optional[str] = Field(
        default=None,
        description="Namespace override for output artifacts and coverage tracking",
    )
    tool_metadata: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Optional per-tool metadata keyed by tool name. Supported keys include "
            "read_only, priority, base, anchor, and aliases."
        ),
    )

    # Multi-task-type world support (e.g. a unified world exposing several task families)
    enabled_task_types: Optional[List[str]] = Field(
        default=None,
        description="Task types to enable in a multi-type world (e.g. telecom, airline). None = use server default.",
    )
    task_type_selection: Optional[str] = Field(
        default=None,
        description="Task type selection strategy: auto_by_tool_count, uniform, manual. None = auto_by_tool_count.",
    )
    task_type_weights: Optional[Dict[str, float]] = Field(
        default=None,
        description="Explicit task type weights when task_type_selection=manual.",
    )
