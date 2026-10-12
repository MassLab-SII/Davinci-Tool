from pydantic import Field
from typing import Literal, Optional
from .base import BaseTaskConfig


class PlaywrightTaskConfig(BaseTaskConfig):
    """Configuration for playwright-based tasks."""

    task_type: Literal["playwright"] = "playwright"

    # Server configuration (set defaults for playwright)
    required_servers: list[str] = Field(
        default_factory=lambda: ["playwright"],
        description="List of MCP servers required (playwright only)",
    )

    primary_server: Optional[str] = Field(
        default="playwright",
        description="Primary server for state management",
    )

    # Playwright specific settings
    seed_base: Optional[int] = Field(
        default=None, description="Base seed for reproducibility (None = random)"
    )
    n_tools_min: int = Field(default=2, description="Minimum number of tools to sample")
    n_tools_max: int = Field(default=6, description="Maximum number of tools to sample")

    browser: str = Field(
        default="chromium",
        description="Browser type: chromium/firefox/webkit",
    )
    headless: bool = Field(default=True, description="Run browser in headless mode")
    viewport_width: int = Field(default=1280, description="Browser viewport width")
    viewport_height: int = Field(default=720, description="Browser viewport height")
    starting_url: Optional[str] = Field(
        default="https://example.com",
        description="Starting URL for browser navigation",
    )
    init_complexity: str = Field(
        default="simple",
        description="Initialization complexity: simple/medium/complex",
    )

    # Default tools for playwright task
    # Actual tool names from @playwright/mcp use "browser_" prefix
    read_only_tools: list[str] = Field(
        default_factory=lambda: [
            "browser_take_screenshot",
            "browser_snapshot",
            "browser_evaluate",
            "browser_console_messages",
            "browser_network_requests",
        ]
    )

    read_only_tools_priority: list[str] = Field(
        default_factory=lambda: [
            "browser_evaluate",
            "browser_take_screenshot",
            "browser_snapshot",
        ]
    )

    base_tools: list[str] = Field(
        default_factory=lambda: [
            "browser_navigate",
            "browser_take_screenshot",
            "browser_snapshot",
        ],
        description="Base tools that are truly input-independent",
    )
