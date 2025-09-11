# Rewritten client using the high-level FastMCP async API instead of the
# handcrafted SSE implementation.

"""Minimal CLI client for the local Agent-Cards MCP server.

Usage
-----
    python mcp_client.py "<query>"

The client
1. connects to the running MCP server (default: ``http://127.0.0.1:8080``),
2. lists available tools for demonstration purposes,
3. calls the ``find_agent`` tool with the provided natural-language query, and
4. prints the JSON result.

The implementation follows the FastMCP `Client` usage pattern:
https://pypi.org/project/fastmcp
"""

from __future__ import annotations

import asyncio
import sys
import json
from fastmcp import Client
from mcp.types import CallToolResult

SERVER_URL = "http://127.0.0.1:8080/sse"   # FastMCP SSE endpoint

async def main() -> None:
    """Connect to the MCP server and list the available tools."""

    async with Client(SERVER_URL) as client:
        # List available tools for demonstration purposes
        print("\nTools available on server:\n")
        for tool in await client.list_tools():
            print(f"\u2022 {tool.name}: {tool.description}")

        # If a query is provided via the CLI, call the `find_agent` tool and
        # pretty-print the resulting agent card (JSON).
        if len(sys.argv) > 1:
            query = sys.argv[1]
            print("\nTool Call: find_agent")
            print("\nQuery:", query)

            result = await client.call_tool("find_agent", {"query": query})

            agent_card = json.loads(result.data.result) 
            agent_url = agent_card.get("url", "<missing url>")
            print("\nTool Result:")
            print("\nAgent URL:", agent_url)

            print("\nTool Call: execute_task")
            print("\nQuery:\n", query)

            exec_call = await client.call_tool("execute_task", {"agent_url": agent_url, "query": query})
            print("\nTool Result:")
            print("\nExecution Result:\n", exec_call.data.result)

if __name__ == "__main__":
    asyncio.run(main()) 