"""
Playwright Adapter for mcp-gen
================================

Exports playwright-specific state manager.
"""

from .state_manager import PlaywrightStateManager

__all__ = [
    "PlaywrightStateManager",
]
