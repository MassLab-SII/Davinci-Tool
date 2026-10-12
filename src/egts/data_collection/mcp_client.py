"""MCP client for connecting to and interacting with MCP servers."""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config.core import StdioMCPServerConfig

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for interacting with an MCP server."""

    def __init__(self, name: str, config: StdioMCPServerConfig):
        """Initialize MCP client.
        
        Args:
            name: Name of the MCP server
            config: Server configuration
        """
        self.name = name
        self.config = config
        self.session: Optional[ClientSession] = None
        self._stdio_context = None
        self._read = None
        self._write = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
        
    async def connect(self, id: int):
        """Connect to the MCP server."""
        logger.info(f"Connecting to MCP server: {self.name}")
        
        args = self.config.args.copy()

        # Only filesystem-like servers need a local workspace directory argument.
        self._ensure_working_directory(args)

        # Create server parameters
        server_params = StdioServerParameters(
            command=self.config.command,
            args=args,
            env=self.config.env or None
        )
        
        try:
            # Connect to server using stdio (it's a context manager)
            self._stdio_context = stdio_client(server_params)
            self._read, self._write = await self._stdio_context.__aenter__()

            # Create session
            self.session = ClientSession(self._read, self._write)

            # Initialize the session
            await self.session.__aenter__()

            # Initialize the connection
            await self.session.initialize()
        except Exception:
            await self._cleanup_partial_connection()
            raise
        
        logger.info(f"Successfully connected to {self.name}")
    
    def _ensure_working_directory(self, args: List[str]):
        """Ensure the working directory exists before starting the server.
        
        This is only applicable to filesystem server, where the last argument is
        a workspace directory path. It must not mutate args for other servers.
        """
        from pathlib import Path

        if self.name != "filesystem" or not args:
            return

        candidate = args[-1]
        if candidate.startswith("-") or "://" in candidate:
            return

        working_dir_path = Path(candidate)
        if not working_dir_path.exists():
            logger.info(f"Creating working directory for {self.name}: {candidate}")
            try:
                working_dir_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"✓ Working directory created: {candidate}")
            except Exception as e:
                logger.error(f"Failed to create working directory {candidate}: {e}")
                raise
        else:
            logger.debug(f"Working directory already exists: {candidate}")
        
    async def disconnect(self):
        """Disconnect from the MCP server."""
        if self.session:
            logger.info(f"Disconnecting from MCP server: {self.name}")
            try:
                await self.session.__aexit__(None, None, None)
            except asyncio.CancelledError as e:
                logger.warning(f"Session cleanup cancelled for {self.name}: {e}")
            except Exception as e:
                logger.warning(f"Session cleanup failed for {self.name}: {e}")
            self.session = None

        if self._stdio_context:
            try:
                await self._stdio_context.__aexit__(None, None, None)
            except asyncio.CancelledError as e:
                logger.warning(f"stdio cleanup cancelled for {self.name}: {e}")
            except Exception as e:
                logger.warning(f"stdio cleanup failed for {self.name}: {e}")
            self._stdio_context = None
            self._read = None
            self._write = None

    async def _cleanup_partial_connection(self):
        """Best-effort cleanup when connect() fails midway."""
        if self.session:
            try:
                await self.session.__aexit__(None, None, None)
            except Exception:
                pass
            self.session = None

        if self._stdio_context:
            try:
                await self._stdio_context.__aexit__(None, None, None)
            except Exception:
                pass
            self._stdio_context = None
            self._read = None
            self._write = None

            
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools from the MCP server.
        
        Returns:
            List of tool definitions with name, description, and input schema
        """
        if not self.session:
            raise RuntimeError("Not connected to MCP server")
            
        logger.info(f"Listing tools from {self.name}")
        
        # List tools using the MCP session
        response = await self.session.list_tools()
        
        tools = []
        for tool in response.tools:
            tool_def = {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema
            }
            tools.append(tool_def)
            logger.debug(f"Found tool: {tool.name}")
            
        logger.info(f"Found {len(tools)} tools from {self.name}")
        return tools
        
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the MCP server.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        if not self.session:
            raise RuntimeError("Not connected to MCP server")
            
        # This path is extremely hot (snapshots/checkpoints call many tools).
        # Keep per-call logging at DEBUG to avoid flooding collect logs.
        logger.debug(f"Calling tool {tool_name} with args: {arguments}")
        
        # Call the tool
        result = await self.session.call_tool(tool_name, arguments)
        
        logger.debug(f"Tool {tool_name} returned: {result}")
        return result


@asynccontextmanager
async def create_mcp_client(name: str, config: StdioMCPServerConfig, id: int):
    """Create and connect to an MCP client.

    Args:
        name: Name of the MCP server
        config: Server configuration

    Yields:
        Connected MCPClient instance
    """
    client = MCPClient(name, config)
    await client.connect(id)
    try:
        yield client
    finally:
        await client.disconnect()
