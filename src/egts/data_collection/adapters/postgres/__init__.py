"""
Postgres Adapter for mcp-gen
=============================

Exports postgres-specific state manager.
"""

from .state_manager import PostgresStateManager

__all__ = [
    "PostgresStateManager",
]
