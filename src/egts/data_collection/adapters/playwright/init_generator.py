"""Playwright initialization generator for mcp-trajs2data.

Generates realistic initial browser automation scenarios with seed-based reproducibility.
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


# URL categories for diverse initialization scenarios
URL_CATEGORIES = {
    "documentation": [
        "https://developer.mozilla.org/en-US/docs/Web",
        "https://docs.python.org/3/",
        "https://nodejs.org/docs/latest/api/",
        "https://react.dev/learn",
    ],
    "interactive_demos": [
        "https://www.w3schools.com/html/",
        "https://jsfiddle.net/",
        "https://codepen.io/",
    ],
    "form_heavy": [
        "https://www.wikipedia.org/",
        "https://duckduckgo.com/",
        "https://archive.org/",
    ],
    "content_rich": [
        "https://news.ycombinator.com/",
        "https://stackoverflow.com/",
        "https://dev.to/",
    ],
    "simple_static": [
        "https://example.com/",
        "https://example.org/",
        "https://httpbin.org/",
    ],
}


class NavigationType(str, Enum):
    """Types of navigation actions."""

    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SCREENSHOT = "screenshot"


@dataclass
class NavigationSpec:
    """Specification for a navigation action."""

    action: NavigationType
    target: str  # URL for navigate, selector for click/fill
    value: Optional[str] = None  # Value for fill actions

    def to_init_operation(self) -> Dict[str, Any]:
        """Convert to initialization operation format."""
        if self.action == NavigationType.NAVIGATE:
            return {
                "tool": "browser_navigate",
                "arguments": {"url": self.target}
            }
        elif self.action == NavigationType.CLICK:
            return {
                "tool": "browser_click",
                "arguments": {"ref": self.target}
            }
        elif self.action == NavigationType.FILL:
            return {
                "tool": "browser_type",
                "arguments": {"ref": self.target, "text": self.value}
            }
        elif self.action == NavigationType.SCREENSHOT:
            return {
                "tool": "browser_take_screenshot",
                "arguments": {"type": "page"}
            }
        return


@dataclass
class InitPlan:
    """Plan for initializing a playwright browser environment."""

    starting_url: str
    actions: List[NavigationSpec] = field(default_factory=list)
    seed: int = 0

    def to_operations(self) -> List[Dict[str, Any]]:
        """Convert to list of initialization operations."""
        operations = []

        # Start with navigation to starting URL
        operations.append({
            "tool": "browser_navigate",
            "arguments": {"url": self.starting_url}
        })

        # Add other actions
        for action_spec in self.actions:
            operations.append(action_spec.to_init_operation())

        return operations

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of the init plan."""
        return {
            "starting_url": self.starting_url,
            "seed": self.seed,
            "num_actions": len(self.actions),
            "total_operations": 1 + len(self.actions),
        }


class PlaywrightInitGenerator:
    """Generator for playwright browser initialization plans."""

    def __init__(self, seed: Optional[int] = None):
        """Initialize generator with optional seed.

        Args:
            seed: Random seed for reproducibility. If None, uses random seed.
        """
        self.seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        self.rng = random.Random(self.seed)

    def generate_init_plan(
        self, starting_url: str, complexity: str = "simple"
    ) -> InitPlan:
        """Generate an initialization plan for a playwright browser session.

        Args:
            starting_url: Starting URL for the browser (if None or default, select randomly)
            complexity: Complexity level (simple/medium/complex)

        Returns:
            InitPlan with navigation actions
        """
        # Step 1: Determine starting URL
        selected_category = None
        if starting_url and starting_url != "https://example.com":
            # Use configured URL (config override)
            selected_url = starting_url
            logger.info(f"Using configured starting_url: {selected_url}")
        else:
            # Random selection based on seed
            selected_category = self.rng.choice(list(URL_CATEGORIES.keys()))
            selected_url = self.rng.choice(URL_CATEGORIES[selected_category])
            logger.info(f"Selected random URL from category '{selected_category}': {selected_url}")

        # Step 2: Generate actions based on complexity
        actions = []
        complexity_config = self._get_complexity_config(complexity)

        # Always take initial screenshot
        actions.append(
            NavigationSpec(
                action=NavigationType.SCREENSHOT,
                target=""
            )
        )

        # Add complexity-specific actions
        if complexity in ["medium", "complex"]:
            # Add additional screenshots based on complexity
            num_additional = self.rng.randint(
                complexity_config["min_actions"] - 1,
                complexity_config["max_actions"] - 1
            )
            for _ in range(num_additional):
                actions.append(
                    NavigationSpec(
                        action=NavigationType.SCREENSHOT,
                        target=""
                    )
                )

        plan = InitPlan(
            starting_url=selected_url,
            actions=actions,
            seed=self.seed,
        )

        summary = plan.get_summary()
        if selected_category:
            summary["url_category"] = selected_category
        logger.info(f"Generated init plan: {summary}")
        return plan

    def _get_complexity_config(self, complexity: str) -> Dict[str, Any]:
        """Get configuration for a complexity level.

        Args:
            complexity: Complexity level (simple/medium/complex)

        Returns:
            Configuration dictionary with min/max actions and interaction settings
        """
        configs = {
            "simple": {
                "min_actions": 1,
                "max_actions": 1,
                "interaction_probability": 0.0,
                "multi_page": False,
            },
            "medium": {
                "min_actions": 1,
                "max_actions": 2,
                "interaction_probability": 0.5,
                "multi_page": False,
            },
            "complex": {
                "min_actions": 2,
                "max_actions": 4,
                "interaction_probability": 0.8,
                "multi_page": True,
            },
        }
        return configs.get(complexity, configs["simple"])


# Utility functions for pipeline compatibility
async def execute_init_plan(plan: InitPlan, mcp_client) -> List[Dict[str, Any]]:
    """Execute an initialization plan using MCP client.

    Args:
        plan: InitPlan to execute
        mcp_client: MCP client for executing operations

    Returns:
        List of execution results
    """
    operations = plan.to_operations()
    results = []

    for op in operations:
        try:
            result = await mcp_client.call_tool(op["tool"], op["arguments"])
            results.append({"success": True, "operation": op, "result": result})
        except Exception as e:
            logger.error(f"Failed to execute operation {op}: {e}")
            results.append({"success": False, "operation": op, "error": str(e)})

    return results


def init_plan_to_operations(plan: InitPlan) -> List[Dict[str, Any]]:
    """Convert InitPlan to list of operations for metadata.

    Args:
        plan: InitPlan to convert

    Returns:
        List of operation dictionaries
    """
    return plan.to_operations()
