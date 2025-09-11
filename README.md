# ISEK MCP - Agent-to-Agent Protocol Demo

This project demonstrates an Agent-to-Agent (A2A) protocol implementation with multiple specialized AI agents that can be queried through a Model Context Protocol (MCP) server.

## Project Structure

- `openai_agent.py` - General-purpose OpenAI GPT-4 agent
- `trending_agent.py` - Agent for finding current trending topics
- `analyzer_agent.py` - Agent for analyzing trends with quantitative data
- `mcp_server.py` - MCP server that routes queries to appropriate agents
- `mcp_client.py` - Client for testing the MCP server
- `common.py` - Shared utilities and logging functions
- `run_demo.sh` - Demo script that starts all agents and runs a test query

## Setup

### 1. Python Environment

Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
.\venv\Scripts\activate   # On Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

**Note:** The project uses the official [A2A Python SDK](https://github.com/a2aproject/a2a-python) for Agent-to-Agent protocol implementation. The `a2a-sdk[all]` package includes all necessary features including HTTP server, gRPC, telemetry, and database drivers.

### 3. Environment Variables

Create a `.env` file with necessary API keys:

```bash
# OpenAI API Key (required for AI agents)
OPENAI_API_KEY=your_openai_api_key_here

# Optional: Custom ports for agents
# PORT=10020  # for trending agent
# PORT=10021  # for analyzer agent
```

## Usage

### Quick Demo

Run the demo script to start all agents and test with a query:

```bash
./run_demo.sh "What's trending today?"
```

### Manual Usage

1. Start the agents individually:

```bash
# Terminal 1 - OpenAI Agent (port 9999)
python openai_agent.py

# Terminal 2 - Trending Agent (port 10020)
python trending_agent.py

# Terminal 3 - Analyzer Agent (port 10021)
python analyzer_agent.py

# Terminal 4 - MCP Server (port 8080)
python mcp_server.py --host 127.0.0.1 --port 8080 --transport sse
```

2. Query the system:

```bash
python mcp_client.py "Analyze the current AI trends"
```

## Agent Capabilities

- **OpenAI Agent**: General-purpose assistant using GPT-4
- **Trending Agent**: Searches for current trending topics on social media
- **Analyzer Agent**: Provides quantitative analysis and metrics for trends

## Architecture

The system uses:

- **A2A Protocol**: Agent-to-Agent communication protocol using the official [A2A Python SDK](https://github.com/a2aproject/a2a-python)
- **MCP**: Model Context Protocol for client-server communication
- **FastMCP**: Framework for building MCP servers
- **Pydantic AI**: Framework for building AI agents
- **HTTPX**: Async HTTP client for agent communication
- **Uvicorn**: ASGI server for hosting agents

## Troubleshooting

1. **OpenAI API errors**: Ensure your `OPENAI_API_KEY` is set in the `.env` file
2. **Port conflicts**: Agents run on ports 9999, 10020, 10021, and MCP server on 8080
3. **Agent startup**: Wait for agents to fully start (5+ seconds) before querying
4. **A2A SDK issues**: The project uses the official [A2A Python SDK](https://github.com/a2aproject/a2a-python) - ensure all dependencies are installed with `pip install -r requirements.txt`
