from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class UnityMcpClient:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._session: ClientSession | None = None
        self._stdio_ctx = None
        self._client_ctx = None

    async def __aenter__(self) -> "UnityMcpClient":
        await self.connect()
        return self

    async def connect(self) -> "UnityMcpClient":
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

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close(exc_type, exc, tb)

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

    async def reconnect(self) -> "UnityMcpClient":
        await self.close()
        return await self.connect()

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("UnityMcpClient is not connected.")
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

    async def batch_execute(self, commands: list[dict[str, Any]], *, fail_fast: bool = True) -> dict[str, Any]:
        return await self.call_tool(
            "batch_execute",
            {
                "commands": commands,
                "fail_fast": fail_fast,
                "parallel": False,
            },
        )

    async def create_script(self, path: str, contents: str) -> dict[str, Any]:
        return await self.call_tool("create_script", {"path": path, "contents": contents})

    async def update_script(self, path: str, contents: str) -> dict[str, Any]:
        delete_result = await self.delete_script(path)
        if not self._delete_succeeded(delete_result):
            return delete_result
        return await self.create_script(path, contents)

    async def delete_script(self, path: str) -> dict[str, Any]:
        name, directory = self._split_script_path(path)
        return await self.call_tool(
            "manage_script",
            {
                "action": "delete",
                "name": name,
                "path": directory,
            },
        )

    async def create_scene(self, name: str, path: str, template: str = "3d_basic") -> dict[str, Any]:
        return await self.call_tool("manage_scene", {"action": "create", "name": name, "path": path, "template": template})

    async def load_scene(self, path: str) -> dict[str, Any]:
        return await self.call_tool("manage_scene", {"action": "load", "path": path})

    async def get_active_scene(self) -> dict[str, Any]:
        return await self.call_tool("manage_scene", {"action": "get_active"})

    async def get_scene_hierarchy(self, *, page_size: int = 50, include_transform: bool = True) -> dict[str, Any]:
        return await self.call_tool(
            "manage_scene",
            {
                "action": "get_hierarchy",
                "page_size": page_size,
                "include_transform": include_transform,
            },
        )

    async def get_project_info(self) -> dict[str, Any]:
        return await self.session.read_resource("mcpforunity://project/info")

    async def get_editor_state(self) -> dict[str, Any]:
        return await self.session.read_resource("mcpforunity://editor/state")

    async def find_gameobjects(self, search_term: str, search_method: str = "by_name") -> dict[str, Any]:
        return await self.call_tool("find_gameobjects", {"search_term": search_term, "search_method": search_method})

    async def read_console(self, *, types: list[str] | None = None, count: int = 50, format_name: str = "json") -> dict[str, Any]:
        return await self.call_tool(
            "read_console",
            {
                "action": "get",
                "types": types or ["error", "warning", "log"],
                "count": count,
                "format": format_name,
                "include_stacktrace": True,
            },
        )

    async def play(self) -> dict[str, Any]:
        return await self.call_tool("manage_editor", {"action": "play"})

    async def stop(self) -> dict[str, Any]:
        return await self.call_tool("manage_editor", {"action": "stop"})

    @staticmethod
    def _content_to_dict(item: Any) -> dict[str, Any]:
        payload = {"type": getattr(item, "type", item.__class__.__name__)}
        if hasattr(item, "text"):
            payload["text"] = item.text
        if hasattr(item, "data"):
            payload["data"] = item.data
        if hasattr(item, "mimeType"):
            payload["mimeType"] = item.mimeType
        return payload

    @staticmethod
    def _split_script_path(path: str) -> tuple[str, str]:
        script_path = Path(path.replace("\\", "/"))
        return script_path.stem, script_path.parent.as_posix()

    @staticmethod
    def _delete_succeeded(result: dict[str, Any] | None) -> bool:
        if not result or result.get("is_error"):
            return False
        structured = result.get("structured_content") or {}
        return bool(structured.get("success"))
