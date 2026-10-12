"""
Minimal MCP HTTP Server Implementation  
=======================================

Provides HTTP-based MCP server communication for services like GitHub.
"""

import asyncio
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

class MCPHttpServer:
    """
    HTTP-based MCP client using the official MCP Python SDK
    (Streamable HTTP transport).
    """

    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
    ):
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout

        self._stack: Optional[AsyncExitStack] = None
        self.session: Optional[ClientSession] = None
        self._tools_cache: Optional[List[Dict[str, Any]]] = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    async def start(self):
        """Open Streamable HTTP transport and initialize MCP session."""
        self._stack = AsyncExitStack()

        read_stream, write_stream, _ = await self._stack.enter_async_context(
            streamablehttp_client(self.url, headers=self.headers)
        )

        self.session = await self._stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await asyncio.wait_for(self.session.initialize(), timeout=self.timeout)

    async def stop(self):
        """Close the session/transport cleanly."""
        if self._stack:
            try:
                await self._stack.aclose()
            except BaseException:
                # CancelledError / cancel-scope mismatches during session
                # termination are non-fatal; the transport is torn down anyway.
                pass
        self._stack = None
        self.session = None
        self._tools_cache = None

    async def disconnect(self):
        await self.stop()

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Return tool definitions (cached)."""
        if self._tools_cache is not None:
            return self._tools_cache
        if not self.session:
            raise RuntimeError("MCP HTTP client not started")

        resp = await asyncio.wait_for(self.session.list_tools(), timeout=self.timeout)
        self._tools_cache = [t.model_dump() for t in resp.tools]
        return self._tools_cache

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Invoke a remote tool and return the structured result."""
        if not self.session:
            raise RuntimeError("MCP HTTP client not started")

        result = await asyncio.wait_for(self.session.call_tool(name, arguments), timeout=self.timeout)
        return result.model_dump()

    async def admin_request(
        self, path: str, method: str = "GET", body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Call an admin HTTP endpoint on the server (not an MCP tool call).

        Admin endpoints like /admin/reset, /admin/state, /admin/status are
        regular HTTP endpoints exposed alongside the MCP transport.

        Args:
            path: Admin endpoint path (e.g. "/admin/state")
            method: HTTP method (GET or POST)
            body: Optional JSON body for POST requests

        Returns:
            Parsed JSON response dict
        """
        import httpx

        base = self.url.rsplit("/mcp", 1)[0] if "/mcp" in self.url else self.url.rstrip("/")
        url = f"{base}{path}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if method.upper() == "POST":
                resp = await client.post(url, json=body or {}, headers=self.headers)
            else:
                resp = await client.get(url, headers=self.headers)
            if resp.status_code >= 400:
                detail = (resp.text or "(empty body)")[:500]
                raise httpx.HTTPStatusError(
                    f"Server error '{resp.status_code}' for url '{url}': {detail}",
                    request=resp.request,
                    response=resp,
                )
            return resp.json()
