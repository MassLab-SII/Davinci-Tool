"""
Server Registry for MCP Servers
================================

Centralized registry of all supported MCP servers with their configurations,
command templates, and adapter mappings.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class ServerDefinition:
    """Definition of an MCP server."""

    name: str
    type: str  # "stdio" or "sse"
    command_template: str
    config_schema: Dict[str, Any]
    adapters: Dict[str, str]  # Mapping of adapter type to class path
    description: str = ""


# Server definitions registry
SERVER_DEFINITIONS: Dict[str, ServerDefinition] = {
    "filesystem": ServerDefinition(
        name="filesystem",
        type="stdio",
        command_template="npx -y @modelcontextprotocol/server-filesystem {workspace_path}",
        config_schema={
            "required": ["workspace_path"],
            "optional": {},
        },
        adapters={
            "state_manager": "data_collection.adapters.filesystem.FilesystemStateManager",
            "init_generator": "data_collection.state.filesystem_init_generator.FilesystemInitGenerator",
            "snapshot_provider": "data_collection.adapters.filesystem.snapshot_provider.FilesystemSnapshotProvider",
            "diff_comparator": "data_collection.adapters.filesystem.diff_comparator.FilesystemDiffComparator",
        },
        description="Filesystem operations (read, write, list, search files)",
    ),

    "postgres": ServerDefinition(
        name="postgres",
        type="stdio",
        command_template="npx -y @modelcontextprotocol/server-postgres postgresql://{user}:{password}@{host}:{port}/{database}",
        config_schema={
            "required": ["database"],
            "optional": {
                "host": {"default": "localhost", "env": "POSTGRES_HOST"},
                "port": {"default": "5432", "env": "POSTGRES_PORT"},
                "user": {"default": "postgres", "env": "POSTGRES_USER"},
                "password": {"default": "postgres", "env": "POSTGRES_PASSWORD"},
            },
        },
        adapters={
            "state_manager": "data_collection.adapters.postgres.state_manager.PostgresStateManager",
            "init_generator": "data_collection.adapters.postgres.init_generator.PostgresInitGenerator",
            "snapshot_provider": "data_collection.adapters.postgres.snapshot_provider.PostgresSnapshotProvider",
            "diff_comparator": "data_collection.adapters.postgres.diff_comparator.PostgresDiffComparator",
        },
        description="PostgreSQL database operations (query, schema management, data manipulation)",
    ),

    "playwright": ServerDefinition(
        name="playwright",
        type="stdio",
        command_template="npx -y @modelcontextprotocol/server-playwright",
        config_schema={
            "required": [],
            "optional": {
                "browser": {"default": "chromium", "choices": ["chromium", "firefox", "webkit"]},
                "headless": {"default": True},
            },
        },
        adapters={
            "state_manager": "data_collection.adapters.playwright.state_manager.PlaywrightStateManager",
            "init_generator": "data_collection.adapters.playwright.init_generator.PlaywrightInitGenerator",
            "snapshot_provider": "data_collection.adapters.playwright.snapshot_provider.PlaywrightSnapshotProvider",
            "diff_comparator": "data_collection.adapters.playwright.diff_comparator.PlaywrightDiffComparator",
        },
        description="Browser automation (navigate, click, fill forms, screenshot)",
    ),
}


def get_server_definition(server_name: str) -> Optional[ServerDefinition]:
    """Get server definition by name.

    Args:
        server_name: Name of the server

    Returns:
        ServerDefinition or None if not found
    """
    return SERVER_DEFINITIONS.get(server_name)


def list_available_servers() -> List[str]:
    """List all available server names.

    Returns:
        List of server names
    """
    return list(SERVER_DEFINITIONS.keys())


def get_adapter_class_path(server_name: str, adapter_type: str) -> Optional[str]:
    """Get adapter class path for a server and adapter type.

    Args:
        server_name: Name of the server
        adapter_type: Type of adapter (state_manager, init_generator, etc.)

    Returns:
        Class path string or None if not found
    """
    definition = get_server_definition(server_name)
    if definition:
        return definition.adapters.get(adapter_type)
    return None


def register_server(definition: ServerDefinition) -> None:
    """Register a server definition at runtime.

    This allows config-driven server registration without modifying the
    static SERVER_DEFINITIONS dict at code level.

    Args:
        definition: ServerDefinition to register
    """
    SERVER_DEFINITIONS[definition.name] = definition


def register_http_server(
    name: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    description: str = "",
    adapters: Optional[Dict[str, str]] = None,
) -> None:
    """Convenience helper to register an HTTP MCP server.

    HTTP servers (benchmark worlds) typically have no adapters because
    they manage their own state via admin endpoints.

    Args:
        name: Server name (must match config key)
        url: HTTP MCP endpoint URL
        headers: Optional HTTP headers
        description: Human-readable description
        adapters: Optional adapter mappings (empty by default)
    """
    SERVER_DEFINITIONS[name] = ServerDefinition(
        name=name,
        type="http",
        command_template=url,  # Store URL in command_template for HTTP servers
        config_schema={
            "url": url,
            "headers": headers or {},
        },
        adapters=adapters or {},
        description=description or f"HTTP MCP server: {name}",
    )


def auto_register_from_config(config) -> None:
    """Auto-register servers declared in config that are not yet in the registry.

    Called by load_config() after parsing YAML. This ensures that HTTP and
    stdio servers declared in config are available in the registry for
    server_manager.get_adapters() and start_server().

    Args:
        config: Parsed Config object
    """
    # Register HTTP servers
    http_servers = getattr(config, "http_mcp_servers", {}) or {}
    for name, srv_cfg in http_servers.items():
        if name not in SERVER_DEFINITIONS:
            register_http_server(
                name=name,
                url=srv_cfg.url,
                headers=dict(srv_cfg.headers) if srv_cfg.headers else {},
                description=f"HTTP MCP server (from config): {name}",
            )

    # Register stdio servers not already in the static registry
    stdio_servers = getattr(config, "stdio_mcp_servers", {}) or {}
    for name, srv_cfg in stdio_servers.items():
        if name not in SERVER_DEFINITIONS:
            register_server(ServerDefinition(
                name=name,
                type="stdio",
                command_template=f"{srv_cfg.command} {' '.join(srv_cfg.args)}",
                config_schema={"required": [], "optional": {}},
                adapters={},
                description=f"Stdio MCP server (from config): {name}",
            ))
