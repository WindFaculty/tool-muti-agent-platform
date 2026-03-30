from __future__ import annotations

import asyncio
from contextlib import suppress
import json
from pathlib import Path
from typing import Any, Callable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class _UnityMcpAsyncClient:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._session: ClientSession | None = None
        self._stdio_ctx = None
        self._client_ctx = None

    async def connect(self) -> "_UnityMcpAsyncClient":
        if self._session is not None:
            return self

        server = StdioServerParameters(
            command=r"C:\Users\tranx\AppData\Local\Programs\Python\Python314\Scripts\uvx.exe",
            args=["-p", "3.14", "--from", "mcpforunityserver", "mcp-for-unity", "--transport", "stdio"],
            env={"SystemRoot": r"C:\Windows"},
            cwd=self._repo_root,
        )
        self._stdio_ctx = stdio_client(server)
        try:
            read, write = await self._stdio_ctx.__aenter__()
            self._client_ctx = ClientSession(read, write)
            self._session = await self._client_ctx.__aenter__()
            await self._session.initialize()
            return self
        except Exception as exc:
            await self.close(type(exc), exc, exc.__traceback__)
            raise

    async def close(self, exc_type=None, exc=None, tb=None) -> None:
        client_ctx = self._client_ctx
        stdio_ctx = self._stdio_ctx

        self._session = None
        self._client_ctx = None
        self._stdio_ctx = None

        if client_ctx is not None:
            with suppress(Exception):
                await client_ctx.__aexit__(exc_type, exc, tb)
        if stdio_ctx is not None:
            with suppress(Exception):
                await stdio_ctx.__aexit__(exc_type, exc, tb)

    async def reconnect(self) -> "_UnityMcpAsyncClient":
        await self.close()
        return await self.connect()

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("Unity MCP client is not connected.")
        return self._session

    async def list_tools(self) -> list[str]:
        result = await self.session.list_tools()
        return [tool.name for tool in result.tools]

    async def list_resources(self) -> list[str]:
        result = await self.session.list_resources()
        return [resource.name for resource in result.resources]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self.session.call_tool(name, arguments)
        return {
            "structured_content": getattr(result, "structuredContent", None),
            "content": [self._content_to_dict(item) for item in getattr(result, "content", [])],
            "is_error": getattr(result, "isError", False),
        }

    async def read_resource(self, uri: str) -> dict[str, Any]:
        result = await self.session.read_resource(uri)
        return {
            "uri": getattr(result, "uri", uri),
            "contents": [self._content_to_dict(item) for item in getattr(result, "contents", [])],
        }

    @staticmethod
    def _content_to_dict(item: Any) -> dict[str, Any]:
        payload = {"type": getattr(item, "type", item.__class__.__name__)}
        if hasattr(item, "text"):
            payload["text"] = item.text
        if hasattr(item, "data"):
            payload["data"] = item.data
        if hasattr(item, "mimeType"):
            payload["mimeType"] = item.mimeType
        if hasattr(item, "uri"):
            payload["uri"] = str(item.uri)
        return payload


class UnityMcpRuntime:
    """Synchronous wrapper used by the GUI-agent controller."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._runner: asyncio.Runner | None = None
        self._client: _UnityMcpAsyncClient | None = None
        self._tool_cache: list[str] = []
        self._resource_cache: list[str] = []

    def connect(self) -> None:
        if self._runner is not None and self._client is not None:
            return
        self._runner = asyncio.Runner()
        self._client = _UnityMcpAsyncClient(self._repo_root)
        self._runner.run(self._client.connect())
        self._tool_cache = self._runner.run(self._client.list_tools())
        self._resource_cache = self._runner.run(self._client.list_resources())

    def close(self) -> None:
        if self._runner is None or self._client is None:
            return
        try:
            self._runner.run(self._client.close())
        finally:
            self._runner.close()
            self._runner = None
            self._client = None
            self._tool_cache = []
            self._resource_cache = []

    def reconnect(self) -> None:
        self.close()
        self.connect()

    def list_tools(self) -> list[str]:
        self.connect()
        return list(self._tool_cache)

    def list_resources(self) -> list[str]:
        self.connect()
        return list(self._resource_cache)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            assert self._runner is not None and self._client is not None
            return self._runner.run(self._client.call_tool(name, arguments))

        return self._with_reconnect(_call)

    def read_resource(self, uri: str) -> dict[str, Any]:
        def _read() -> dict[str, Any]:
            assert self._runner is not None and self._client is not None
            return self._runner.run(self._client.read_resource(uri))

        return self._with_reconnect(_read)

    def read_text_resource(self, uri: str) -> str:
        payload = self.read_resource(uri)
        texts = [str(item.get("text", "")) for item in payload.get("contents", []) if item.get("text")]
        return "\n".join(texts)

    def read_json_resource(self, uri: str) -> dict[str, Any]:
        text = self.read_text_resource(uri).strip()
        return json.loads(text) if text else {}

    def capability_snapshot(self) -> dict[str, Any]:
        self.connect()
        return {
            "tools": self.list_tools(),
            "resources": self.list_resources(),
        }

    def _with_reconnect(self, operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        self.connect()
        try:
            return operation()
        except Exception as exc:
            if not self._is_retryable_transport_exception(exc):
                raise
            self.reconnect()
            return operation()

    @staticmethod
    def _is_retryable_transport_exception(exc: Exception) -> bool:
        message = str(exc).strip().lower()
        combined = f"{exc.__class__.__name__} {message}".lower()
        markers = (
            "connection closed",
            "stream closed",
            "closedresourceerror",
            "endofstream",
            "broken pipe",
            "connection reset",
            "pipe is being closed",
            "transport",
            "stdio",
            "stdiobridge",
            "reloading",
            "please retry",
            "hint='retry'",
            'hint="retry"',
            "eof",
        )
        return any(marker in combined for marker in markers)
