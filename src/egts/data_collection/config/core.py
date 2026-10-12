from pydantic import BaseModel, Field
from typing import Dict, Optional, List, Any


class SingleModelConfig(BaseModel):
    """Configuration for a single model."""

    model: str = Field(..., description="Model name")
    base_url: Optional[str] = Field(None, description="Base URL for this model's API")
    api_key: Optional[str] = Field(None, description="API key for this model")
    temperature: Optional[float] = Field(None, description="Temperature override")
    max_tokens: Optional[int] = Field(None, description="Max tokens override")
    thinking: Optional[str] = Field(
        None,
        description=(
            "Provider-specific thinking mode switch, e.g. 'enabled' or 'disabled' "
            "for DeepSeek V4-compatible APIs."
        ),
    )
    reasoning_effort: Optional[str] = Field(
        None,
        description="Optional reasoning effort hint for reasoning/thinking models.",
    )


class DefaultConfig(BaseModel):
    """Default MaaS configuration."""

    base_url: str = Field(..., description="Default base URL for MaaS API")
    api_key: str = Field(..., description="Default API key")
    temperature: float = Field(default=0.7, description="Default temperature")
    max_tokens: int = Field(default=4000, description="Default max tokens")


class ModelConfig(BaseModel):
    """Model configuration for different pipeline stages."""

    trajectory_collection: SingleModelConfig
    nl_rewrite: Optional[SingleModelConfig] = Field(
        default=None,
        description="Model for NL rewriting (uses trajectory_collection if not specified)",
    )
    judge: Optional[SingleModelConfig] = Field(
        default=None,
        description="Model for judging/quality scoring (uses trajectory_collection if not specified)",
    )


class MaaSConfig(BaseModel):
    """MaaS service configuration."""

    default: DefaultConfig
    models: ModelConfig


class StdioMCPServerConfig(BaseModel):
    """Configuration for a stdio-based MCP server."""

    command: str = Field(..., description="Command to start the server")
    args: list[str] = Field(default_factory=list, description="Command arguments")
    env: Dict[str, str] = Field(
        default_factory=dict, description="Environment variables"
    )
    timeout: int = Field(
        default=120, description="Timeout for server operations in seconds"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata describing tool traits, prompt domain, or output namespace",
    )


class HttpMCPServerConfig(BaseModel):
    """Configuration for an HTTP-based MCP server."""

    url: str = Field(..., description="Base URL for the HTTP MCP server")
    headers: Dict[str, str] = Field(default_factory=dict, description="HTTP headers")
    timeout: int = Field(default=30, description="Timeout for HTTP requests in seconds")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata describing tool traits, prompt domain, or output namespace",
    )


class PipelineConfig(BaseModel):
    """Pipeline execution settings."""

    exp_name: str = Field(
        default="", description="Experiment name for output organization"
    )
    num_iterations: int = Field(
        default=100, description="Total number of episodes to generate"
    )
    num_workers: int = Field(
        default=1, description="Number of concurrent workers (1 = single-threaded)"
    )
    output_dir: str = Field(default="./output", description="Output directory")
    save_failed: bool = Field(
        default=True, description="Save failed trajectories for debugging"
    )


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Logging level")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format",
    )
    file: Optional[str] = Field(default=None, description="Log file path")
    debug_log_path: Optional[str] = Field(
        default=None,
        description="Path for debug log (replaces _CURSOR_DEBUG_LOG_PATH hardcoding)",
    )


class DockerConfig(BaseModel):
    """Docker configuration for containerized environments."""

    base_image: str = Field(
        default="python:3.11-slim", description="Base image for Dockerfiles"
    )
    verify_image: str = Field(
        default="mcp-gen-verify:latest", description="Image for verification container"
    )
    cleanup_on_success: bool = Field(
        default=True, description="Remove containers after successful trajectories"
    )
    cleanup_on_failure: bool = Field(
        default=False, description="Remove containers after failed trajectories"
    )
    volume_driver: str = Field(default="local", description="Docker volume driver")


class LocalConfig(BaseModel):
    """Local mode configuration for running without Docker."""

    workspace_root: str = Field(
        default="./workspaces-async",
        description="Root directory for temporary workspaces",
    )
    cleanup_on_success: bool = Field(
        default=True, description="Clean up workspaces after successful runs"
    )
    cleanup_on_failure: bool = Field(
        default=False, description="Keep workspaces after failed runs for debugging"
    )
