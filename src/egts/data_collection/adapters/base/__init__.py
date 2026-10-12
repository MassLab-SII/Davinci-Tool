"""
Base Adapter Classes
====================

Exports base classes for MCP server adapters.
"""

from .state_manager import BaseStateManager
from .login_helper import BaseLoginHelper

__all__ = [
    "BaseStateManager",
    "BaseLoginHelper",
]
