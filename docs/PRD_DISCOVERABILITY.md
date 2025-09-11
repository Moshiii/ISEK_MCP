# PRD: MCP Server Discoverability API

**Version:** 1.0
**Status:** Proposed
**Author:** AI Assistant

## 1. Introduction & Context

This document outlines the requirements for implementing standardized discovery and invocation endpoints for our Model Context Protocol (MCP) server. The current implementation relies on custom tool definitions (`find_agent`, `execute_task`), which is not a standard pattern and makes it difficult for new clients and developers to interact with our agents.

To align with industry best practices and improve the developer experience, we will implement two primary endpoints:

- `GET /agents`: For discovering available agents and their capabilities.
- `POST /invoke`: A single, standardized endpoint for executing tasks on any agent.

This change will make our MCP server more predictable, easier to integrate with, and more aligned with user expectations for a modern API.

## 2. Requirements

### 2.1. Agent Discovery Endpoint

The server must provide a RESTful endpoint that returns a list of all available agents and their capabilities. This allows clients to dynamically discover what agents are available and how to interact with them.

- **Endpoint**: `GET /agents`
- **Method**: `GET`
- **Success Response (200 OK)**: A JSON array where each object represents an agent.

#### Agent Object Specification

Each object in the array must contain:

- `name` (string): A unique identifier for the agent (e.g., "trending_agent").
- `description` (string): A clear, concise description of what the agent does.
- `input_schema` (object): A valid JSON Schema object describing the expected input for the agent.

#### Example Response Body:

```json
[
  {
    "name": "trending_agent",
    "description": "Searches for and returns the top 3 current trending topics from social media.",
    "input_schema": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "A natural language query about the trends to find (e.g., 'What's trending today?')."
        }
      },
      "required": ["query"]
    }
  },
  {
    "name": "analyzer_agent",
    "description": "Performs a deep analysis of a given trend, providing quantitative data and metrics.",
    "input_schema": {
      "type": "object",
      "properties": {
        "trend_topic": {
          "type": "string",
          "description": "The specific trend to analyze (e.g., '#ClimateChange')."
        }
      },
      "required": ["trend_topic"]
    }
  }
]
```

#### Implementation Checklist:

- [ ] Create a `GET /agents` endpoint in `mcp_server.py`.
- [ ] The endpoint should dynamically fetch the `AgentCard` for each running agent.
- [ ] Transform the agent card data into the specified JSON structure (`name`, `description`, `input_schema`).
- [ ] Ensure the `input_schema` is a valid and descriptive JSON Schema.
- [ ] Implement error handling for cases where agents cannot be reached.

### 2.2. Standardized Invocation Endpoint

The server must provide a single, unified endpoint for executing any of its agents. This simplifies client logic by providing one consistent way to run tasks.

- **Endpoint**: `POST /invoke`
- **Method**: `POST`
- **Request Body**: A JSON object containing the agent to invoke and the inputs for it.
- **Success Response (200 OK)**: The JSON output directly from the invoked agent.

#### Request Body Specification

- `agent_name` (string): The name of the agent to invoke (must match a name from the `GET /agents` endpoint).
- `agent_inputs` (object): An object containing the inputs for the agent. This object **must** be valid according to the agent's `input_schema`.

#### Example Request Body:

```json
{
  "agent_name": "trending_agent",
  "agent_inputs": {
    "query": "What are people talking about on social media?"
  }
}
```

#### Error Responses

- **400 Bad Request**: If the request body is malformed, `agent_name` is missing, or `agent_inputs` do not validate against the agent's schema.
- **404 Not Found**: If the specified `agent_name` does not correspond to an available agent.
- **500 Internal Server Error**: If the agent fails during execution.

#### Implementation Checklist:

- [ ] Create a `POST /invoke` endpoint in `mcp_server.py`.
- [ ] The endpoint should parse `agent_name` and `agent_inputs` from the request body.
- [ ] Fetch the specified agent's `input_schema`.
- [ ] Validate the `agent_inputs` against the schema. Return a `400` error if validation fails.
- [ ] If valid, invoke the correct agent with the provided inputs.
- [ ] Return the agent's output directly as the success response.
- [ ] Implement standardized error responses (`400`, `404`, `500`) with clear error messages.

### 2.3. Standard Error Model

All error responses must follow a consistent JSON structure and include an actionable code and a trace identifier for troubleshooting.

- **Content-Type**: `application/json`
- **Schema**:

```json
{
  "error": {
    "code": "AGENT_NOT_FOUND | VALIDATION_FAILED | AGENT_UNAVAILABLE | EXECUTION_ERROR",
    "message": "Human-readable description",
    "details": {},
    "trace_id": "<uuid>"
  }
}
```

#### Status Code Mapping

- `400` – `VALIDATION_FAILED` (schema validation or malformed body)
- `404` – `AGENT_NOT_FOUND`
- `503` – `AGENT_UNAVAILABLE` (timeout/downstream unavailable)
- `500` – `EXECUTION_ERROR` (unexpected server error)

#### Implementation Checklist:

- [ ] Return the error envelope above for all non-2xx responses.
- [ ] Include a `trace_id` (UUID) in responses and logs; accept/propagate `traceparent` if present.
- [ ] Log errors with structured fields: `trace_id`, `path`, `method`, `status`, `agent_name`.

### 2.4. API Versioning & OpenAPI

Provide clear versioning and machine-readable API documentation.

- **Base Path**: `/v1` (e.g., `/v1/agents`, `/v1/invoke`)
- **OpenAPI Spec**: `GET /openapi.json`
- **Interactive Docs**: `GET /docs` (Swagger UI or ReDoc)

#### Implementation Checklist:

- [ ] Mount endpoints under `/v1`.
- [ ] Generate and serve an OpenAPI document covering `/agents` and `/invoke`.
- [ ] Include schemas for request/response and the error envelope.
- [ ] Document common headers: `X-Request-ID`, `traceparent`.

### 2.5. Health, Readiness, and Monitoring

Expose minimal health/readiness endpoints and basic observability.

- **Health**: `GET /health` → `{ "status": "ok" }`
- **Readiness**: `GET /ready` → checks downstream agent reachability (best-effort)
- **Metrics (optional)**: `GET /metrics` (Prometheus format)

#### Implementation Checklist:

- [ ] Implement `/health` (no dependencies) and `/ready` (lightweight downstream check).
- [ ] Add request logging with `method`, `path`, `status`, `duration_ms`, `trace_id`.
- [ ] If feasible, expose `/metrics` counters and latencies for `/agents` and `/invoke`.

### 2.6. Security Baseline

Initial version remains unauthenticated, but include safe defaults and a path to hardening.

#### Baseline (must-have)

- [ ] Validate and sanitize all inputs against JSON Schema.
- [ ] Enforce `Content-Type: application/json`; reject others with `415`.
- [ ] Set reasonable timeouts for downstream agent calls.
- [ ] CORS: default to a conservative allowlist (configurable); expose `GET /agents`, `POST /invoke`.

#### Future (recommended)

- [ ] Add Bearer token auth for `/invoke`.
- [ ] Support OAuth 2.0 Authorization Server Metadata at `/.well-known/oauth-authorization-server` with fallback endpoints (`/authorize`, `/token`, `/register`).
- [ ] Consider OAuth 2.0 Dynamic Client Registration when multi-tenant clients are required.

### 2.7. Agent Metadata & Catalog

Augment agent objects to improve discoverability and client ergonomics.

#### Agent Object (extended)

- `name` (string) – unique, stable identifier
- `description` (string)
- `version` (string) – semantic version of the agent
- `tags` (array<string>) – e.g., ["analysis", "trends"]
- `capabilities` (object) – e.g., `{ "streaming": true, "tools": false, "task_execution": true }`
- `url` (string) – base URL of the agent (if remotely invocable)
- `input_schema` (object) – JSON Schema for inputs (required)
- `output_schema` (object, optional) – JSON Schema for outputs

#### Additional Endpoints (optional)

- `GET /agents/{name}` – return a single agent object by `name`.
- Refresh: `GET /agents?refresh=true` to force re-fetch from upstreams.

#### Implementation Checklist:

- [ ] Include `version`, `tags`, `capabilities`, and `url` in `/agents` response when available.
- [ ] Keep `name` stable across deployments.
- [ ] Optionally implement `GET /agents/{name}` for direct lookup.

### 2.8. Consistency & Conventions

Provide predictable, consistent API surfaces.

- **Naming**: use kebab-case for paths (`/v1/agents`) and snake_case for JSON fields.
- **Headers**: support `Accept: application/json`; respond with `Content-Type: application/json`.
- **Correlation**: accept `X-Request-ID` and echo it back; generate one if missing.
- **Idempotency (optional)**: accept `Idempotency-Key` for `POST /invoke` to deduplicate retries.

#### Implementation Checklist:

- [ ] Enforce JSON field casing and path naming conventions.
- [ ] Echo `X-Request-ID` (or generate) on all responses.
- [ ] Document optional `Idempotency-Key` behavior (if implemented).

## 3. Out of Scope

- **Authentication/Authorization**: These endpoints will initially be unauthenticated. Security will be addressed in a separate effort.
- **Asynchronous Operations**: The `POST /invoke` endpoint will be synchronous for this version. Long-running tasks and callbacks are not in scope.
- **Dynamic Client Registration**: We will not be implementing OAuth 2.0 Dynamic Client Registration at this time.
