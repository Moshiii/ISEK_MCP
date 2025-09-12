# ISEK MCP - Agent-to-Agent Protocol Demo

This project demonstrates an Agent-to-Agent (A2A) protocol implementation with multiple specialized AI agents that can be queried through a Model Context Protocol (MCP) server.

## Project Structure

- `openai_agent.py` - General-purpose OpenAI GPT-4 agent
- `trending_agent.py` - Agent for finding current trending topics
- `analyzer_agent.py` - Agent for analyzing trends with quantitative data
- `mcp_server.py` - REST API server with discoverability endpoints and MCP tools for backward compatibility
- `mcp_client.py` - REST API client for testing the server
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

# Terminal 4 - MCP Server (port 8080) - REST API mode (default)
python mcp_server.py --host 127.0.0.1 --port 8080

# Alternative: Run in MCP legacy mode
python mcp_server.py --host 127.0.0.1 --port 8080 --mode mcp --transport sse
```

2. Query the system:

```bash
# Using the REST API client
python mcp_client.py "Analyze the current AI trends"

# Or use curl directly:
curl -X GET http://localhost:8080/v1/agents
curl -X POST http://localhost:8080/v1/invoke \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "analyzer_agent", "agent_inputs": {"query": "Analyze AI trends"}}'
```

3. View API documentation:

```bash
# Interactive API docs
open http://localhost:8080/docs

# OpenAPI JSON spec
curl http://localhost:8080/openapi.json
```

## Agent Capabilities

- **OpenAI Agent**: General-purpose assistant using GPT-4
- **Trending Agent**: Searches for current trending topics on social media
- **Analyzer Agent**: Provides quantitative analysis and metrics for trends

## Architecture

The system uses:

- **A2A Protocol**: Agent-to-Agent communication protocol using the official [A2A Python SDK](https://github.com/a2aproject/a2a-python)
- **REST API**: Standard REST endpoints for discoverability and invocation (`/v1/agents`, `/v1/invoke`)
- **FastAPI**: Modern web framework for building REST APIs with automatic OpenAPI documentation
- **MCP**: Model Context Protocol tools for backward compatibility
- **Pydantic AI**: Framework for building AI agents
- **HTTPX**: Async HTTP client for agent communication
- **Uvicorn**: ASGI server for hosting agents

## API Endpoints

The server provides the following REST API endpoints:

### Core Endpoints

- `GET /v1/health` - Health check
- `GET /v1/ready` - Readiness check (verifies agents are reachable)
- `GET /v1/agents` - List all available agents with metadata
- `GET /v1/agents/{name}` - Get metadata for a specific agent
- `POST /v1/invoke` - Invoke an agent with inputs

### Documentation

- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /openapi.json` - OpenAPI specification

### Legacy MCP Mode

- `GET /sse` - MCP Server-Sent Events endpoint (when running in `--mode mcp`)

## Changelog (v1.0)

This project has been significantly refactored to implement a standard REST API for agent discoverability and invocation, replacing the previous custom MCP tool-based approach.

### Key Changes & Features

- **REST API Implementation**: The `mcp_server.py` now runs a FastAPI server, exposing a versioned (`/v1`) REST API.
- **Standardized Endpoints**:
  - `GET /v1/agents`: Discover all available agents and their detailed metadata.
  - `POST /v1/invoke`: A single endpoint to execute any agent.
- **API Best Practices**: Implemented a standard error model, request tracing, health endpoints (`/v1/health`, `/v1/ready`), and CORS.
- **Automatic API Documentation**: Interactive OpenAPI (Swagger) documentation is now available at `/docs`.
- **Updated Client**: The `mcp_client.py` has been rewritten to interact with the new REST API endpoints.
- **Improved Testing**: The `run_demo.sh` script is now a comprehensive API tester that validates all endpoints and error conditions.
- **Development Environment**: Added a `.vscode/terminals.json` configuration to bootstrap the entire ecosystem (server and all agents) automatically within VS Code.

### Bug Fixes

- **Resolved `404 Not Found` Errors**: Corrected the Uvicorn server startup method in `mcp_server.py` to use the recommended `"mcp_server:app"` string with `reload=True`. This ensures the FastAPI routes are always loaded correctly during development.
- **Accurate Test Script Reporting**: Fixed the `run_demo.sh` script to correctly detect and fail on non-2xx HTTP status codes, providing accurate test results.

## Troubleshooting

1. **OpenAI API errors**: Ensure your `OPENAI_API_KEY` is set in the `.env` file
2. **Port conflicts**: Agents run on ports 9999, 10020, 10021, and MCP server on 8080
3. **Agent startup**: Wait for agents to fully start (5+ seconds) before querying
4. **REST API errors**: Check `/v1/health` and `/v1/ready` endpoints for server status
5. **A2A SDK issues**: The project uses the official [A2A Python SDK](https://github.com/a2aproject/a2a-python) - ensure all dependencies are installed with `pip install -r requirements.txt`
6. **Agent not found**: Use `GET /v1/agents` to verify agents are registered and reachable
