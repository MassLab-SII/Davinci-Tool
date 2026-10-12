"""
Adapter Factory for MCP Services
=================================

Factory pattern for creating and managing service-specific adapters.
"""

import logging
from typing import Dict, Optional
from .base import BaseStateManager

logger = logging.getLogger(__name__)


class AdapterFactory:
    """Factory for creating and managing service adapters."""

    def __init__(self, config=None):
        """Initialize adapter factory.
        
        Args:
            config: Optional configuration object
        """
        self.config = config
        self._adapters: Dict[str, BaseStateManager] = {}

    def get_adapter(self, service_name: str) -> Optional[BaseStateManager]:
        """Get or create adapter for a service.
        
        Args:
            service_name: Name of the MCP service
            
        Returns:
            BaseStateManager instance or None if service not supported
        """
        if service_name not in self._adapters:
            self._adapters[service_name] = self._create_adapter(service_name)
        return self._adapters[service_name]

    def _create_adapter(self, service_name: str) -> Optional[BaseStateManager]:
        """Create adapter instance for a service.

        Known service names get their specialized adapter. Unknown service names
        fall back to FilesystemStateManager as a safe default.
        """
        try:
            lowered = service_name.lower()
            if lowered == "filesystem":
                from .filesystem import FilesystemStateManager
                adapter = FilesystemStateManager()
                logger.info(f"Created filesystem adapter")
                return adapter

            elif lowered in ("postgres", "pg"):
                from .postgres import PostgresStateManager
                adapter = PostgresStateManager()
                logger.info(f"Created postgres adapter")
                return adapter

            elif lowered in ("playwright", "browser"):
                from .playwright import PlaywrightStateManager
                adapter = PlaywrightStateManager()
                logger.info(f"Created playwright adapter")
                return adapter

            else:
                logger.info(
                    f"No specialized adapter for service '{service_name}', "
                    f"using filesystem fallback"
                )
                from .filesystem import FilesystemStateManager
                return FilesystemStateManager()
                
        except ImportError as e:
            logger.warning(f"Failed to import adapter for {service_name}: {e}")
            return None

    def cleanup_all(self) -> bool:
        """Clean up all active adapters.
        
        Returns:
            True if all cleanups successful, False otherwise
        """
        cleanup_success = True
        
        for service_name, adapter in self._adapters.items():
            try:
                if not adapter.cleanup():
                    logger.warning(f"Failed to cleanup {service_name} adapter")
                    cleanup_success = False
            except Exception as e:
                logger.error(f"Error cleaning up {service_name} adapter: {e}")
                cleanup_success = False
        
        return cleanup_success
