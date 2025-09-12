"""REST API client for the ISEK MCP server.

Usage
-----
    python mcp_client.py "<query>"

The client
1. connects to the running MCP server (default: ``http://127.0.0.1:8080``),
2. lists available agents using GET /v1/agents,
3. finds the most relevant agent for the query,
4. invokes the agent using POST /v1/invoke, and
5. prints the JSON result.

This client uses the REST API endpoints instead of MCP protocol.
"""

from __future__ import annotations

import asyncio
import sys
import json
import httpx
from typing import List, Dict, Any

SERVER_URL = "http://127.0.0.1:8080"  # REST API base URL

class MCPRestClient:
    """REST API client for ISEK MCP server."""

    def __init__(self, base_url: str = SERVER_URL):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def list_agents(self) -> List[Dict[str, Any]]:
        """List all available agents."""
        response = await self.client.get(f"{self.base_url}/v1/agents")
        response.raise_for_status()
        return response.json()

    async def get_agent(self, name: str) -> Dict[str, Any]:
        """Get metadata for a specific agent."""
        response = await self.client.get(f"{self.base_url}/v1/agents/{name}")
        response.raise_for_status()
        return response.json()

    async def invoke_agent(self, agent_name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke an agent with the provided inputs."""
        request_data = {
            "agent_name": agent_name,
            "agent_inputs": inputs
        }
        response = await self.client.post(
            f"{self.base_url}/v1/invoke",
            json=request_data,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()

    def find_best_agent(self, agents: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """Simple agent selection based on query keywords."""
        # This is a simplified version - in production you'd use the BM25 algorithm
        # like in the server, but for the client we'll just pick the first agent
        if agents:
            return agents[0]
        raise ValueError("No agents available")

async def main() -> None:
    """Connect to the MCP server and interact with agents via REST API."""

    if len(sys.argv) < 2:
        print("Usage: python mcp_client.py \"<your query>\"")
        sys.exit(1)

    query = sys.argv[1]

    async with MCPRestClient() as client:
        try:
            # List available agents
            print("\nAvailable agents:\n")
            agents = await client.list_agents()
            for agent in agents:
                print(f"• {agent['name']}: {agent['description']}")
                print(f"  Tags: {', '.join(agent.get('tags', []))}")
                print(f"  URL: {agent.get('url', 'N/A')}")
                print()

            if not agents:
                print("No agents available!")
                return

            # Invoke all agents
            for agent in agents:
                agent_inputs = {"query": query}
                print(f"\nInvoking agent '{agent['name']}' with query: {query}")
                result = await client.invoke_agent(agent['name'], agent_inputs)

                print("\nAgent Response:")
                print("=" * 50)
                print(result.get('result', 'No result returned'))
                print("=" * 50)
                print(f"Trace ID: {result.get('trace_id', 'N/A')}")

        except httpx.HTTPStatusError as e:
            print(f"HTTP Error: {e.response.status_code}")
            try:
                error_data = e.response.json()
                print(f"Error: {error_data}")
            except:
                print(f"Response: {e.response.text}")
        except Exception as e:
            print(f"Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 