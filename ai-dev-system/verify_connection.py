from __future__ import annotations

import asyncio
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent

for child in ("unity-interface",):
    sys.path.append(str(ROOT / child))

from mcp_client import UnityMcpClient


async def main() -> None:
    async with UnityMcpClient(REPO_ROOT) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        print(f"Connected to Unity MCP with {len(tools)} tools and {len(resources)} resources.")
        print("Sample tools:", ", ".join(tools[:10]))
        print("Sample resources:", ", ".join(resources[:10]))


if __name__ == "__main__":
    asyncio.run(main())
