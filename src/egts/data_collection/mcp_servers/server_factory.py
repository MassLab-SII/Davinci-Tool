"""
Server Factory for MCP Servers
==============================

Factory pattern for creating appropriate MCP server instances based on type.
"""

import asyncio
import logging
from pathlib import Path
from typing import Union, Optional
from contextlib import asynccontextmanager

from data_collection.utils.config import StdioMCPServerConfig, HttpMCPServerConfig
from .stdio_server import MCPStdioServer
from .http_server import MCPHttpServer

logger = logging.getLogger(__name__)

# Global semaphore to serialize MCP server connections.
# The anyio library used by mcp.client.stdio has task group issues when 
# multiple asyncio Tasks try to create concurrent stdio connections.
# This semaphore prevents "Attempted to exit cancel scope in a different task" errors.
_MCP_CONNECTION_SEMAPHORE: Optional[asyncio.Semaphore] = None
_MCP_MAX_CONCURRENT_CONNECTIONS = 1  # Serialize all connections to avoid anyio conflicts


def _get_connection_semaphore() -> asyncio.Semaphore:
    """Get or create the global connection semaphore."""
    global _MCP_CONNECTION_SEMAPHORE
    if _MCP_CONNECTION_SEMAPHORE is None:
        _MCP_CONNECTION_SEMAPHORE = asyncio.Semaphore(_MCP_MAX_CONCURRENT_CONNECTIONS)
    return _MCP_CONNECTION_SEMAPHORE


# def _ensure_working_directory(config: StdioMCPServerConfig, problem_id: int) -> Optional[str]:
#     """Ensure the working directory exists before starting the server.
    
#     For MCP servers that take a directory path as their last argument,
#     this method creates that directory if it doesn't exist to prevent server crashes.
    
#     Args:
#         config: Stdio server configuration
#         problem_id: Problem ID for directory naming
        
#     Returns:
#         The working directory path if applicable, None otherwise
#     """
#     # Check if the server has arguments and the last one looks like a path
#     if config.args:
#         # The last argument is typically the working directory
#         working_dir_base = config.args[-1]
        
#         # Check if it looks like a path (not a flag starting with -)
#         if not working_dir_base.startswith('-'):
#             working_dir = f"{working_dir_base}/problem_{problem_id:06}"
#             working_dir_path = Path(working_dir)
            
#             if not working_dir_path.exists():
#                 logger.info(f"Creating working directory: {working_dir}")
#                 try:
#                     working_dir_path.mkdir(parents=True, exist_ok=True)
#                     logger.info(f"✓ Working directory created: {working_dir}")
#                 except Exception as e:
#                     logger.error(f"Failed to create working directory {working_dir}: {e}")
#                     raise
#             else:
#                 logger.debug(f"Working directory already exists: {working_dir}")
            
#             return working_dir
    
#     return None


def create_stdio_server(config: StdioMCPServerConfig, problem_id: int, docker_volume_path: Optional[str] = None) -> MCPStdioServer:
    """Create a stdio-based MCP server.
    
    Args:
        config: Stdio server configuration
        problem_id: Problem ID for directory naming
        docker_volume_path: If provided, use this Docker volume path instead of creating local directory
        
    Returns:
        MCPStdioServer instance
    """
    # Update args with problem-specific path
    args = config.args.copy()
    
    if docker_volume_path:
        # Docker mode: use the volume path directly
        logger.info(f"Using Docker volume path: {docker_volume_path}")
        if args and not args[-1].startswith('-'):
            args[-1] = docker_volume_path
    else:
        # Non-Docker mode: use the path from config directly (already set in config.yaml)
        pass
    
    return MCPStdioServer(
        command=config.command,
        args=args,
        env=config.env or {},
        timeout=config.timeout
    )


def create_http_server(config: HttpMCPServerConfig) -> MCPHttpServer:
    """Create an HTTP-based MCP server.
    
    Args:
        config: HTTP server configuration
        
    Returns:
        MCPHttpServer instance
    """
    return MCPHttpServer(
        url=config.url,
        headers=config.headers or {},
        timeout=config.timeout
    )


@asynccontextmanager
async def create_mcp_server(
    name: str,
    server_type: str,
    config: Union[StdioMCPServerConfig, HttpMCPServerConfig],
    problem_id: int = 0,
    docker_volume_path: Optional[str] = None
):
    """Create and initialize an MCP server based on type.
    
    Args:
        name: Name of the MCP server
        server_type: Type of server ('stdio' or 'http')
        config: Server configuration
        problem_id: Problem ID for stdio servers (for directory naming)
        docker_volume_path: For Docker mode, the host path to container volume
        
    Yields:
        Initialized MCP server instance
        
    Raises:
        ValueError: If server_type is not 'stdio' or 'http'
    """
    logger.info(f"Creating MCP server '{name}' (type: {server_type})")
    
    if server_type == 'stdio':
        server = create_stdio_server(config, problem_id, docker_volume_path=docker_volume_path)
        
        # Use semaphore for stdio servers to prevent anyio task group conflicts
        # when multiple workers create concurrent connections
        semaphore = _get_connection_semaphore()
        logger.debug(f"Waiting for MCP connection semaphore for '{name}'...")
        async with semaphore:
            logger.debug(f"Acquired MCP connection semaphore for '{name}'")
            async with server as connected_server:
                logger.info(f"Successfully connected to MCP server '{name}'")
                yield connected_server
            logger.debug(f"Released MCP connection semaphore for '{name}'")
    elif server_type == 'http':
        server = create_http_server(config)
        async with server as connected_server:
            logger.info(f"Successfully connected to MCP server '{name}'")
            yield connected_server
    else:
        raise ValueError(f"Unknown server type: {server_type}. Must be 'stdio' or 'http'")
