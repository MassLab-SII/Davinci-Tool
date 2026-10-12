from pydantic import Field
from typing import Literal, Optional
from .base import BaseTaskConfig


class FilesystemTaskConfig(BaseTaskConfig):
    """Configuration for filesystem-based tasks."""

    task_type: Literal["filesystem"] = "filesystem"

    # Server configuration (set defaults for filesystem)
    required_servers: list[str] = Field(
        default_factory=lambda: ["filesystem"],
        description="List of MCP servers required (filesystem only)",
    )

    primary_server: Optional[str] = Field(
        default="filesystem",
        description="Primary server for state management",
    )

    # Filesystem specific settings
    seed_base: Optional[int] = Field(
        default=None, description="Base seed for reproducibility (None = random)"
    )
    n_tools_min: int = Field(default=2, description="Minimum number of tools to sample")
    n_tools_max: int = Field(default=6, description="Maximum number of tools to sample")
    size_profile: str = Field(
        default="small",
        description="Size profile for init env: tiny/small/medium/large",
    )
    init_mode: Literal["random", "benchmark", "hybrid"] = Field(
        default="random",
        description="Filesystem init mode: random (legacy), benchmark, or hybrid",
    )
    benchmark_ratio: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="When init_mode=hybrid, probability of using benchmark init",
    )
    benchmark_source: str = Field(
        default="all",
        description="Benchmark source selector, default 'all' (all discovered sources)",
    )
    benchmark_roots: list[str] = Field(
        default_factory=lambda: ["../eval"],
        description="Roots to scan for benchmark environments",
    )
    benchmark_cache_subdir: str = Field(
        default="benchmark_envs/filesystem",
        description="Cache subdir under workspace_root for deployed benchmark envs",
    )
    benchmark_deploy_all: bool = Field(
        default=True,
        description="Deploy all discovered benchmark environments at startup",
    )
    benchmark_include_local_dirs: bool = Field(
        default=True,
        description="Also include local filesystem benchmark directories if discovered",
    )
    benchmark_download_timeout_sec: int = Field(
        default=900,
        ge=10,
        description="Timeout for downloading one benchmark environment archive",
    )
    benchmark_max_environments: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional cap on discovered benchmark environments",
    )

    # Default tools for filesystem task (override base defaults)
    read_only_tools: list[str] = Field(
        default_factory=lambda: [
            "list_directory",
            "read_file",
            "read_text_file",
            "read_multiple_files",
            "get_file_info",
            "directory_tree",
            "search_files",
            "list_allowed_directories",
        ]
    )

    read_only_tools_priority: list[str] = Field(
        default_factory=lambda: [
            "search_files",
            "read_file",
            "read_text_file",
            "read_multiple_files",
            "get_file_info",
            "directory_tree",
            "list_directory",
            "list_directory_with_sizes",
            "list_allowed_directories",
        ]
    )

    base_tools: list[str] = Field(
        default_factory=lambda: [
            "list_allowed_directories",
            "list_directory",
            "directory_tree",
            "create_directory",
            "write_file",
        ],
        description="Base tools that are truly input-independent",
    )
