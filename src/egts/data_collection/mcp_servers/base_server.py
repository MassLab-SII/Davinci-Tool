"""
Base Server Interface for MCP Servers
=====================================

Defines the common interface that all MCP server implementations must follow.
"""

from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class MCPServerProtocol(Protocol):
    """Protocol defining the interface for MCP servers.
    
    Both stdio and HTTP server implementations must conform to this protocol.
    """
    
    async def __aenter__(self):
        """Enter async context manager."""
        ...
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        ...
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools from the MCP server.
        
        Returns:
            List of tool definitions as dictionaries with:
            - name: Tool name
            - description: Tool description
            - inputSchema: Tool input schema
        """
        ...
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the MCP server.
        
        Args:
            name: Tool name
            arguments: Tool arguments
            
        Returns:
            Tool execution result as a dictionary
        """
        ...
