"""
Server Manager for MCP Servers
================================

Orchestrates the lifecycle of multiple MCP servers, managing their startup,
adapter access, and cleanup.
"""

import asyncio
import logging
import importlib
from typing import Dict, Any, Optional, Protocol
from pathlib import Path
from copy import deepcopy

from .server_registry import get_server_definition, ServerDefinition
from ..mcp_client import MCPClient
from .http_server import MCPHttpServer
from ..config.core import StdioMCPServerConfig

logger = logging.getLogger(__name__)


class _Disconnectable(Protocol):
    async def disconnect(self) -> Any: ...


class MCPServerManager:
    """Manager for orchestrating multiple MCP servers."""

    def __init__(self, config=None):
        """Initialize the server manager.

        Args:
            config: Optional global configuration object
        """
        self.config = config
        self.active_servers: Dict[str, Any] = {}
        self.adapter_cache: Dict[str, Dict[str, Any]] = {}
        # Serialize server startups to avoid npx/npm cache conflicts
        self._startup_lock = asyncio.Lock()

    @staticmethod
    def _instance_key(server_name: str, iteration: int) -> str:
        """Build an iteration-scoped key for active server instances."""
        return f"{server_name}::iter::{int(iteration)}"

    async def start_server(
        self, server_name: str, iteration: int, **kwargs
    ):
        """Start an MCP server (stdio or HTTP) and return the client.

        For stdio servers: starts a subprocess via MCPClient.
        For HTTP servers: connects via MCPHttpServer.

        Args:
            server_name: Name of the server to start
            iteration: Iteration number for workspace isolation
            **kwargs: Additional configuration parameters

        Returns:
            Connected client instance (MCPClient for stdio, MCPHttpServer for HTTP)

        Raises:
            ValueError: If server definition not found
            RuntimeError: If server fails to start
        """
        instance_key = self._instance_key(server_name, iteration)

        # Check if this iteration-scoped server instance is already running and connected.
        if instance_key in self.active_servers:
            existing_client = self.active_servers[instance_key]
            if getattr(existing_client, "session", None) is not None:
                logger.warning(
                    f"Server {server_name} (key={instance_key}) is already running, returning existing client"
                )
                return existing_client

            logger.warning(
                f"Server {server_name} (key={instance_key}) has stale disconnected client in cache; restarting"
            )
            self.active_servers.pop(instance_key, None)

        # Get server definition
        definition = get_server_definition(server_name)
        if not definition:
            raise ValueError(f"Unknown server: {server_name}")

        # HTTP servers: connect via MCPHttpServer
        if definition.type == "http":
            url = kwargs.get("url") or definition.config_schema.get("url", definition.command_template)
            headers = kwargs.get("headers") or definition.config_schema.get("headers", {})
            timeout = kwargs.get("timeout", definition.config_schema.get("timeout", 30))
            client = MCPHttpServer(url=url, headers=headers, timeout=timeout)
            await client.start()
            self.active_servers[instance_key] = client
            logger.info(f"✓ HTTP server {server_name} connected ({url})")
            return client

        # Stdio servers: start subprocess
        logger.info(f"Starting MCP server: {server_name} (iteration {iteration})")

        # Build server configuration (prefer explicit YAML config if present)
        server_config = self._resolve_server_config(server_name, definition, iteration, **kwargs)

        # Serialize subprocess startup to avoid npx/npm cache conflicts
        # when multiple workers start servers concurrently.
        async with self._startup_lock:
            client = MCPClient(server_name, server_config)
            await client.connect(iteration)

        # Store active client (iteration-scoped, prevents cross-worker sharing).
        self.active_servers[instance_key] = client

        logger.info(f"✓ Server {server_name} started successfully")
        return client

    async def start_http_client(
        self,
        *,
        server_name: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        iteration: int,
    ) -> MCPHttpServer:
        """Start (or reuse) an HTTP MCP client.

        This bypasses the server registry and is intended for external benchmark
        environments that expose tools via MCP over HTTP.
        """
        instance_key = self._instance_key(server_name, iteration)
        existing = self.active_servers.get(instance_key)
        if isinstance(existing, MCPHttpServer) and existing.session is not None:
            return existing

        client = MCPHttpServer(url=url, headers=headers or {}, timeout=timeout)
        await client.start()
        self.active_servers[instance_key] = client
        return client

    def unregister_server(self, server_name: str, iteration: int) -> None:
        """Remove an iteration-scoped server instance from active cache."""
        instance_key = self._instance_key(server_name, iteration)
        self.active_servers.pop(instance_key, None)

    def _resolve_server_config(
        self, server_name: str, definition: ServerDefinition, iteration: int, **kwargs
    ) -> StdioMCPServerConfig:
        """Resolve runtime server config with precedence:
        1) User config YAML (stdio_mcp_servers)
        2) Server registry template fallback
        """
        if self.config is not None:
            stdio_cfg = getattr(self.config, "stdio_mcp_servers", None) or {}
            if server_name in stdio_cfg:
                user_cfg = deepcopy(stdio_cfg[server_name])
                args = list(user_cfg.args)

                # Allow filesystem workspace override from runtime kwargs.
                # For non-filesystem servers (e.g. playwright/postgres), do not rewrite args.
                if server_name == "filesystem" and kwargs.get("workspace_path"):
                    workspace_path = str(kwargs["workspace_path"])
                    replaced = False
                    for idx, arg in enumerate(args):
                        if "{workspace_path}" in arg:
                            args[idx] = arg.replace("{workspace_path}", workspace_path)
                            replaced = True
                    if not replaced and args:
                        last = args[-1]
                        if not last.startswith("-") and "://" not in last:
                            args[-1] = workspace_path

                return StdioMCPServerConfig(
                    command=user_cfg.command,
                    args=args,
                    env=user_cfg.env or {},
                    timeout=user_cfg.timeout,
                )

        return self._build_server_config(definition, iteration, **kwargs)

    def _build_server_config(
        self, definition: ServerDefinition, iteration: int, **kwargs
    ) -> StdioMCPServerConfig:
        """Build server configuration from definition and parameters.

        Args:
            definition: Server definition
            iteration: Iteration number
            **kwargs: Configuration parameters

        Returns:
            StdioMCPServerConfig instance
        """
        # Parse command template
        command_parts = definition.command_template.split()
        command = command_parts[0]
        args = command_parts[1:]

        # Substitute placeholders in args
        substituted_args = []
        for arg in args:
            # Handle template variables like {workspace_path}, {database}, etc.
            if "{" in arg and "}" in arg:
                # Extract all template variables
                import re
                template_vars = re.findall(r'\{(\w+)\}', arg)

                # Substitute each variable
                substituted_arg = arg
                for var in template_vars:
                    if var in kwargs:
                        substituted_arg = substituted_arg.replace(f"{{{var}}}", str(kwargs[var]))
                    elif var in definition.config_schema.get("optional", {}):
                        # Use default value
                        default = definition.config_schema["optional"][var].get("default")
                        if default is not None:
                            substituted_arg = substituted_arg.replace(f"{{{var}}}", str(default))

                substituted_args.append(substituted_arg)
            else:
                substituted_args.append(arg)

        # Build environment variables
        env = {}
        for param, spec in definition.config_schema.get("optional", {}).items():
            if "env" in spec and param in kwargs:
                env[spec["env"]] = str(kwargs[param])

        return StdioMCPServerConfig(
            command=command,
            args=substituted_args,
            env=env
        )

    def get_adapters(self, server_name: str) -> Dict[str, Any]:
        """Get all adapters for a server.

        Args:
            server_name: Name of the server

        Returns:
            Dictionary mapping adapter type to adapter class.
            Returns an empty dict for servers not in the static registry
            (e.g. HTTP benchmark worlds that manage their own state).
        """
        # Check cache first
        if server_name in self.adapter_cache:
            return self.adapter_cache[server_name]

        # Get server definition
        definition = get_server_definition(server_name)
        if not definition:
            logger.info(
                f"No static server definition for '{server_name}'; "
                f"returning empty adapters (benchmark world manages its own state)"
            )
            self.adapter_cache[server_name] = {}
            return {}

        # Load adapter classes
        adapters = {}
        for adapter_type, class_path in definition.adapters.items():
            try:
                adapter_class = self._import_class(class_path)
                adapters[adapter_type] = adapter_class
                logger.debug(f"Loaded {adapter_type} for {server_name}: {class_path}")
            except Exception as e:
                logger.warning(f"Failed to load {adapter_type} for {server_name}: {e}")

        # Cache the adapters
        self.adapter_cache[server_name] = adapters

        return adapters

    def _import_class(self, class_path: str) -> type:
        """Import a class from a module path.

        Args:
            class_path: Full path to class (e.g., "module.submodule.ClassName")

        Returns:
            The imported class

        Raises:
            ImportError: If module or class cannot be imported
        """
        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    async def cleanup_all(self) -> bool:
        """Clean up all active servers.

        Returns:
            True if all cleanups successful, False otherwise
        """
        cleanup_success = True

        for instance_key, client in list(self.active_servers.items()):
            try:
                logger.info(f"Cleaning up server: {instance_key}")
                if hasattr(client, "disconnect"):
                    await client.disconnect()
                elif hasattr(client, "stop"):
                    await client.stop()
                else:
                    raise TypeError(
                        f"Server client for {instance_key} does not support cleanup"
                    )
                logger.info(f"✓ Server {instance_key} cleaned up")
            except Exception as e:
                logger.error(f"✗ Failed to cleanup {instance_key}: {e}")
                cleanup_success = False

        # Clear active servers
        self.active_servers.clear()

        return cleanup_success

    def get_active_servers(self) -> Dict[str, MCPClient]:
        """Get all active server clients.

        Returns:
            Dictionary mapping server name to MCPClient
        """
        return self.active_servers.copy()
