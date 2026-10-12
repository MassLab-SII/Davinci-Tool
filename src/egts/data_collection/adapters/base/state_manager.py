"""
Base State Manager for MCP Server Adapters
==========================================

Simplified version of mcpmark's BaseStateManager adapted for mcp-gen's
problem generation context.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class BaseStateManager(ABC):
    """
    Base class for MCP service state management in mcp-gen.
    
    This provides essential functionality for environment setup and cleanup
    while allowing service-specific implementations.
    """

    def __init__(self, service_name: str):
        """Initialize state manager.
        
        Args:
            service_name: Name of the MCP service (e.g., 'filesystem', 'postgres')
        """
        self.service_name = service_name
        self.tracked_resources: List[Dict[str, Any]] = []

    @abstractmethod
    def initialize(self, **kwargs) -> bool:
        """Initialize service connection/authentication.
        
        Returns:
            True if initialization successful, False otherwise
        """
        pass

    @abstractmethod
    def setup_environment(self, problem_context: Dict[str, Any]) -> Dict[str, Any]:
        """Set up environment for a specific problem.
        
        Args:
            problem_context: Context about the problem being generated
                - iteration: Current iteration number
                - mcp_server: MCP server name
                - category: Optional problem category
                
        Returns:
            Dictionary with environment configuration for MCP server
        """
        pass

    @abstractmethod
    def cleanup(self) -> bool:
        """Clean up resources after data collection.
        
        Returns:
            True if cleanup successful, False otherwise
        """
        pass

    def get_server_config(self) -> Dict[str, Any]:
        """Get MCP server configuration.
        
        Returns:
            Dictionary with server-specific configuration
        """
        return {}

    def track_resource(
        self,
        resource_type: str,
        identifier: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Track a resource for later cleanup.
        
        Args:
            resource_type: Type of resource (e.g., 'directory', 'database')
            identifier: Unique identifier for the resource
            metadata: Additional metadata about the resource
        """
        resource = {
            "type": resource_type,
            "id": identifier,
            "metadata": metadata or {},
        }
        self.tracked_resources.append(resource)
        logger.debug(f"Tracked {resource_type} resource: {identifier}")

    def _cleanup_tracked_resources(self) -> bool:
        """Clean up all tracked resources.
        
        Returns:
            True if all cleanups successful, False otherwise
        """
        cleanup_success = True

        for resource in self.tracked_resources:
            try:
                if not self._cleanup_single_resource(resource):
                    cleanup_success = False
            except Exception as e:
                logger.error(f"Failed to cleanup resource {resource}: {e}")
                cleanup_success = False

        # Clear resources after cleanup attempt
        self.tracked_resources.clear()
        return cleanup_success

    @abstractmethod
    def _cleanup_single_resource(self, resource: Dict[str, Any]) -> bool:
        """Clean up a single tracked resource.
        
        Args:
            resource: Resource dictionary with type, id, and metadata
            
        Returns:
            True if cleanup successful, False otherwise
        """
        pass

    async def execute_init_operations(
        self,
        mcp_client,
        operations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Execute LLM-generated initialization operations using MCP tools.
        
        This method executes a list of MCP tool calls to set up the initial
        environment (e.g., create files, directories, database tables).
        
        Args:
            mcp_client: MCP client for executing tool calls
            operations: List of operations, each with:
                - tool: Tool name to call
                - arguments: Arguments for the tool
                
        Returns:
            List of execution results with success status
        """
        results = []
        
        for i, operation in enumerate(operations):
            tool_name = operation.get("tool")
            arguments = operation.get("arguments", {})
            
            logger.debug(f"Init [{i+1}/{len(operations)}]: {tool_name}")
            
            try:
                result = await mcp_client.call_tool(tool_name, arguments)
                results.append({
                    "tool": tool_name,
                    "arguments": arguments,
                    "success": True,
                    "result": self._format_tool_result(result)
                })
                logger.debug(f"✓ Init {i+1} succeeded: {tool_name}")
            except Exception as e:
                logger.warning(f"✗ Init {i+1} failed: {tool_name} - {e}")
                results.append({
                    "tool": tool_name,
                    "arguments": arguments,
                    "success": False,
                    "error": str(e)
                })
                
        return results

    def _format_tool_result(self, result) -> str:
        """Format tool execution result to string.
        
        Args:
            result: Tool execution result from MCP
            
        Returns:
            Formatted result string
        """
        if hasattr(result, 'content'):
            if isinstance(result.content, list):
                formatted = []
                for item in result.content:
                    if hasattr(item, 'text'):
                        formatted.append(item.text)
                    else:
                        formatted.append(str(item))
                return "\n".join(formatted)
            else:
                return str(result.content)
        else:
            import json
            return json.dumps(result, indent=2)

