from pydantic import Field
from typing import Literal, Optional
from .base import BaseTaskConfig


class PostgresTaskConfig(BaseTaskConfig):
    """Configuration for postgres-based tasks."""

    task_type: Literal["postgres"] = "postgres"

    # Server configuration (set defaults for postgres)
    required_servers: list[str] = Field(
        default_factory=lambda: ["postgres"],
        description="List of MCP servers required (postgres only)",
    )

    primary_server: Optional[str] = Field(
        default="postgres",
        description="Primary server for state management",
    )

    # Postgres specific settings
    seed_base: Optional[int] = Field(
        default=None, description="Base seed for reproducibility (None = random)"
    )
    n_tools_min: int = Field(default=2, description="Minimum number of tools to sample")
    n_tools_max: int = Field(default=6, description="Maximum number of tools to sample")

    schema_complexity: str = Field(
        default="simple",
        description="Schema complexity: simple/medium/complex",
    )
    table_count_min: int = Field(default=2, description="Minimum number of tables")
    table_count_max: int = Field(default=4, description="Maximum number of tables")
    row_count_min: int = Field(default=10, description="Minimum rows per table")
    row_count_max: int = Field(default=50, description="Maximum rows per table")

    # Default tools for postgres task
    # @modelcontextprotocol/server-postgres only provides "query" (read-only SQL)
    read_only_tools: list[str] = Field(
        default_factory=lambda: [
            "query",
        ]
    )

    read_only_tools_priority: list[str] = Field(
        default_factory=lambda: [
            "query",
        ]
    )

    base_tools: list[str] = Field(
        default_factory=lambda: [
            "query",
        ],
        description="Base tools that are truly input-independent",
    )
