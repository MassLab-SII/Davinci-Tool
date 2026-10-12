"""
Base Login Helper for MCP Server Adapters
=========================================

Direct copy from mcpmark for authentication support.
"""

from abc import ABC, abstractmethod


class BaseLoginHelper(ABC):
    """Abstract base class for login helpers."""

    def __init__(self):
        pass

    @abstractmethod
    def login(self, **kwargs):
        """Perform login/authentication for the service.
        
        Args:
            **kwargs: Service-specific login parameters
            
        Returns:
            Authentication credentials or session object
        """
        pass
