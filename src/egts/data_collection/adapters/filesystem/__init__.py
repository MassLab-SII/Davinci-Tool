"""
Filesystem Adapter for mcp-gen
===============================

Exports filesystem-specific state manager.
"""

from .state_manager import FilesystemStateManager

__all__ = [
    "FilesystemStateManager",
]
