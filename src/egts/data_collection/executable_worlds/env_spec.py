from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Dict, Optional, Literal, Any


HealthcheckType = Literal["url", "command"]


class HealthcheckSpec(BaseModel):
    """How to determine that an environment is ready."""

    type: HealthcheckType = Field(..., description="Healthcheck type")
    value: str = Field(
        ..., description="URL to fetch (type=url) or shell command (type=command)"
    )
    timeout_s: int = Field(default=120, description="Max time to wait for healthy")
    interval_s: float = Field(default=2.0, description="Polling interval")


class ExecutableWorldEnvSpec(BaseModel):
    """Config-only spec for an external executable world.

    V1 target:
    - World lifecycle is managed via docker compose (up -d, exec reset, etc.)
    - Tools are exposed via an HTTP MCP endpoint (streamable HTTP transport)
    """

    name: str = Field(..., description="Environment name (unique id)")

    # Docker compose
    compose_file: str = Field(
        ..., description="Path to docker-compose.yml (relative or absolute)"
    )
    project_name: Optional[str] = Field(
        default=None,
        description=(
            "docker compose project name. If omitted, a name will be derived from env name"
        ),
    )

    # Lifecycle controls
    healthcheck: HealthcheckSpec = Field(..., description="Healthcheck definition")
    reset_command: Optional[str] = Field(
        default=None,
        description=(
            "Shell command to reset the environment between iterations. "
            "If omitted, no reset is performed."
        ),
    )

    # Tool endpoint used by trajs2data
    http_mcp_url: str = Field(
        ..., description="HTTP MCP endpoint URL (e.g., http://127.0.0.1:8005/mcp)"
    )
    http_mcp_headers: Dict[str, str] = Field(
        default_factory=dict, description="HTTP headers for MCP requests"
    )
    http_timeout_s: int = Field(
        default=30,
        description=(
            "Timeout for HTTP MCP requests and sibling admin endpoints. "
            "Heavy executable worlds may need a larger value for /admin/reset."
        ),
    )

    # Behavior knobs
    reuse_containers: bool = Field(
        default=True,
        description=(
            "If true, keep compose stack running across iterations and only reset."
        ),
    )
    prompt_domain: Optional[str] = Field(
        default=None,
        description="Optional prompt domain/profile override for this executable world",
    )
    output_namespace: Optional[str] = Field(
        default=None,
        description="Optional output namespace override for artifacts generated from this env",
    )
    tool_metadata: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional per-tool metadata keyed by tool name",
    )
    world_context: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Optional user-authored semantic context for this executable world. "
            "Merged into the unified exploration prompt and raw episode metadata."
        ),
    )


# Backward-compatible alias for older configs/imports.
BenchmarkEnvSpec = ExecutableWorldEnvSpec
