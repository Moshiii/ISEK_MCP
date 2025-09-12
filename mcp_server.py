import json
import asyncio
import httpx
import jsonschema
from typing import Dict, List, Optional, Any
from uuid import uuid4
from datetime import datetime
import time

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
import uvicorn

from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    Message,
    MessageSendParams,
    Part,
    Role,
    SendStreamingMessageRequest,
    SendMessageRequest,
    SendStreamingMessageSuccessResponse,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    TextPart,
    JSONRPCErrorResponse,
    Task,
    GetTaskRequest,
    TaskQueryParams,
)

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.logging import get_logger

import dotenv
dotenv.load_dotenv()

logger = get_logger(__name__)

# Configuration
AGENT_URLS = [
    'http://localhost:9999',   # openai agent
    'http://localhost:10020',  # trending agent
    'http://localhost:10021'   # analyzer agent
]
AGENT_CARD_WELL_KNOWN_PATH = "/.well-known/agent-card.json"
REQUEST_TIMEOUT = 30.0  # seconds

# Initialize FastAPI app
app = FastAPI(
    title="ISEK MCP Server",
    description="Model Context Protocol Server with Agent-to-Agent capabilities",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models
class ErrorResponse(BaseModel):
    error: Dict[str, Any] = Field(..., description="Error details")
    trace_id: str = Field(..., description="Request trace identifier")

class HealthResponse(BaseModel):
    status: str = Field(..., description="Health status")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

class AgentMetadata(BaseModel):
    name: str = Field(..., description="Unique agent identifier")
    description: str = Field(..., description="Agent description")
    version: str = Field(default="1.0", description="Agent version")
    tags: List[str] = Field(default_factory=list, description="Agent tags")
    capabilities: Dict[str, Any] = Field(default_factory=dict, description="Agent capabilities")
    url: str = Field(..., description="Agent base URL")
    input_schema: Dict[str, Any] = Field(..., description="JSON Schema for agent inputs")
    output_schema: Optional[Dict[str, Any]] = Field(None, description="JSON Schema for agent outputs")

class InvokeRequest(BaseModel):
    agent_name: str = Field(..., description="Name of the agent to invoke")
    agent_inputs: Dict[str, Any] = Field(..., description="Inputs for the agent")

class InvokeResponse(BaseModel):
    result: Any = Field(..., description="Agent execution result")
    trace_id: str = Field(..., description="Request trace identifier")

# Utility functions
def generate_trace_id() -> str:
    """Generate a unique trace identifier."""
    return str(uuid4())

def validate_json_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    """Validate data against JSON schema."""
    try:
        jsonschema.validate(instance=data, schema=schema)
        return True
    except jsonschema.ValidationError:
        return False

def create_error_response(code: str, message: str, trace_id: str, details: Optional[Dict] = None) -> ErrorResponse:
    """Create standardized error response."""
    error = {
        "code": code,
        "message": message,
    }
    if details:
        error["details"] = details

    return ErrorResponse(error=error, trace_id=trace_id)

# Request correlation middleware
@app.middleware("http")
async def add_request_correlation(request: Request, call_next):
    """Add request correlation and timing to all requests."""
    start_time = time.time()

    # Get or generate trace_id
    trace_id = request.headers.get("x-request-id") or request.headers.get("traceparent") or generate_trace_id()

    # Add trace_id to request state
    request.state.trace_id = trace_id

    # Add trace_id to response headers
    response = await call_next(request)

    response.headers["x-request-id"] = trace_id
    response.headers["x-trace-id"] = trace_id

    # Add timing
    process_time = time.time() - start_time
    response.headers["x-process-time"] = str(process_time)

    return response

from collections import Counter
import math
import re

def bm25_tokenize(text):
    # Simple whitespace and punctuation tokenizer
    return re.findall(r"\w+", text.lower())

def compute_bm25_scores(agent_cards, query, k1=1.5, b=0.75):
    # Prepare corpus
    documents = []
    print("[compute_bm25_scores],agent_cards count: ", len(agent_cards))
    for card in agent_cards:
        # Concatenate name, description, and all skill descriptions
        doc_parts = [card.get("name", ""), card.get("description", "")]
        for skill in card.get("skills", []):
            doc_parts.append(skill.get("description", ""))
        documents.append(" ".join(doc_parts))
    tokenized_docs = [bm25_tokenize(doc) for doc in documents]
    doc_lens = [len(doc) for doc in tokenized_docs]
    avgdl = sum(doc_lens) / len(doc_lens) if doc_lens else 1

    # Build document frequency for each term
    df = Counter()
    for doc in tokenized_docs:
        for term in set(doc):
            df[term] += 1

    N = len(tokenized_docs)
    query_terms = bm25_tokenize(query)
    scores = []
    for idx, doc in enumerate(tokenized_docs):
        score = 0.0
        doc_counter = Counter(doc)
        dl = len(doc)
        for term in query_terms:
            if df[term] == 0:
                continue
            idf = math.log(1 + (N - df[term] + 0.5) / (df[term] + 0.5))
            tf = doc_counter[term]
            denom = tf + k1 * (1 - b + b * dl / avgdl)
            score += idf * (tf * (k1 + 1)) / (denom + 1e-8)
        scores.append(score)
    return scores

def return_agent_card(agent_cards: list[dict], query: str) -> dict:
    """Returns the agent card deemed most relevant to the input query using BM25 similarity."""
    # Log the beginning of the agent selection process
    logger.debug(f"[return_agent_card],Selecting agent for query: {query!r}. Number of agent_cards available: {len(agent_cards)}")
    scores = compute_bm25_scores(agent_cards, query)
    logger.debug(f"[return_agent_card],BM25 scores computed for query {query!r}: {scores}")
    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    logger.info(
        "[return_agent_card],Agent selected for query %s -> index %d, name: %s",
        query,
        best_idx,
        agent_cards[best_idx].get("name", "unknown"),
    )
    return agent_cards[best_idx]

        
async def send_message_to_an_agent(
        self, agent_card: AgentCard, message: str
    ):
        """Send a message to a specific agent and yield the streaming response.

        Args:
            agent_card (AgentCard): The agent to send the message to.
            message (str): The message to send.

        Yields:
            str: The streaming response from the agent.
        """
        logger.info(
            "[send_message_to_an_agent], Initiating message send to agent %s with query: %s",
            getattr(agent_card, "name", "unknown"),
            message,
        )
        async with httpx.AsyncClient() as httpx_client:
            client = A2AClient(httpx_client, agent_card=agent_card)
            message = MessageSendParams(
                message=Message(
                    role=Role.user,
                    parts=[Part(TextPart(text=message))],
                    message_id=uuid4().hex,
                    task_id=uuid4().hex,
                )
            )

            streaming_request = SendStreamingMessageRequest(
                id=str(uuid4().hex), params=message
            )
            context_id, task_id = None, None
            task_completed = False
            message_chunks = []

            async for chunk in client.send_message_streaming(streaming_request):
                # 0. Ignore non-success response wrappers
                if not isinstance(chunk.root, SendStreamingMessageSuccessResponse):
                    continue
                event = chunk.root.result

                # Verbose event logging (type + truncated JSON payload)
                try:
                    logger.debug(
                        "[send_message_to_an_agent] Stream event type=%s payload=%s",
                        type(event).__name__,
                        (event.model_dump_json(exclude_none=True)[:300] if hasattr(event, "model_dump_json") else str(event)[:300]),
                    )
                except Exception:
                    pass

                # 1. Early error handling
                if isinstance(event, JSONRPCErrorResponse):
                    logger.error(f"[send_message_to_an_agent] Received JSONRPCErrorResponse: {event.error.message}")
                    break

                # 2. Capture context & task ids
                if isinstance(event, Task):
                    task_id = event.id
                    context_id = event.context_id
                elif isinstance(event, (TaskStatusUpdateEvent, TaskArtifactUpdateEvent)):
                    task_id = event.task_id
                    context_id = event.context_id

                # 3. Detect completed state
                if (
                    isinstance(event, TaskStatusUpdateEvent)
                    and event.status.state == 'completed'
                ):
                    task_completed = True

                # 4. Collect user-visible text
                if isinstance(event, Message):
                    message_chunks.append(event.parts[0].root.text)
                elif isinstance(event, TaskArtifactUpdateEvent):
                    message_chunks.append(event.artifact.parts[0].root.text)

            if task_id and not task_completed:
                logger.warning(f"[send_message_to_an_agent] Task {task_id} did not reach completed state, attempting to fetch final result.")
                try:
                    task_resp = await client.get_task(
                        GetTaskRequest(id=str(uuid4()), params=TaskQueryParams(id=task_id))
                    )
                    # pull final artefact/message and append to chunks
                    if task_resp.result and task_resp.result.artifact:
                        message_chunks.append(task_resp.result.artifact.parts[0].root.text)
                    elif task_resp.result and task_resp.result.message:
                        message_chunks.append(task_resp.result.message.parts[0].root.text)
                except Exception as e:
                    logger.error(f"[send_message_to_an_agent] Failed to fetch final task result for task {task_id}: {e}")

            for text in message_chunks:
                yield text

        logger.debug(
            "[send_message_to_an_agent] Finished streaming for agent=%s, total_chunks=%d, completed=%s",
            getattr(agent_card, "name", "unknown"),
            len(message_chunks),
            task_completed,
        )
                        
async def get_agents() -> List[Dict[str, Any]]:
    """Fetch agent cards from all configured agent URLs.

    Returns:
        List[Dict]: List of agent card dictionaries.
    """
    timeout_config = httpx.Timeout(REQUEST_TIMEOUT)
    fetched_cards: List[Dict[str, Any]] = []

    logger.info("Fetching agent cards from configured agent URLs...")

    async with httpx.AsyncClient(timeout=timeout_config) as httpx_client:
        for agent_url in AGENT_URLS:
            try:
                logger.debug("Fetching agent card for %s", agent_url)
                response = await httpx_client.get(f"{agent_url}{AGENT_CARD_WELL_KNOWN_PATH}")
                response.raise_for_status()
                card_data = response.json()
                fetched_cards.append(card_data)
                logger.debug("Successfully fetched agent card for %s", agent_url)
            except Exception as e:
                logger.warning("Failed to fetch agent card for %s: %s", agent_url, str(e))
                continue

    logger.info("Successfully retrieved %d agent cards", len(fetched_cards))
    return fetched_cards

async def get_agent_card_by_url(agent_url: str) -> Dict[str, Any]:
    """Fetch agent card from a specific URL.

    Args:
        agent_url: The URL of the agent to fetch the agent card from.

    Returns:
        Dict: Agent card data.
    """
    timeout_config = httpx.Timeout(REQUEST_TIMEOUT)
    logger.debug("Fetching agent card for %s", agent_url)
    async with httpx.AsyncClient(timeout=timeout_config) as httpx_client:
        response = await httpx_client.get(f"{agent_url}{AGENT_CARD_WELL_KNOWN_PATH}")
        response.raise_for_status()
        card_data = response.json()
        return card_data

def transform_agent_card_to_metadata(card_data: Dict[str, Any]) -> AgentMetadata:
    """Transform agent card data into AgentMetadata model."""
    # Extract tags from skills if available
    tags = []
    if "skills" in card_data:
        for skill in card_data["skills"]:
            if "tags" in skill:
                tags.extend(skill["tags"])

    # Determine capabilities
    capabilities = {
        "streaming": card_data.get("capabilities", {}).get("streaming", False),
        "tools": card_data.get("capabilities", {}).get("tools", False),
        "task_execution": True  # Assume all agents can execute tasks
    }

    # Create input schema from skills if not present
    input_schema = card_data.get("input_schema", {})
    if not input_schema and "skills" in card_data:
        # Generate schema from first skill
        skill = card_data["skills"][0]
        input_schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": f"Query for {skill.get('name', 'agent')}"
                }
            },
            "required": ["query"]
        }

    return AgentMetadata(
        name=card_data.get("name", "unknown"),
        description=card_data.get("description", ""),
        version=card_data.get("version", "1.0"),
        tags=tags,
        capabilities=capabilities,
        url=card_data.get("url", ""),
        input_schema=input_schema,
        output_schema=card_data.get("output_schema")
    )

# REST API Endpoints

@app.get("/v1/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="ok")

@app.get("/v1/ready", response_model=HealthResponse)
async def readiness_check():
    """Readiness check endpoint - checks if agents are reachable."""
    try:
        # Quick check if we can reach at least one agent
        agent_cards = await get_agents()
        if len(agent_cards) == 0:
            raise HTTPException(status_code=503, detail="No agents available")

        return HealthResponse(status="ok")
    except Exception as e:
        logger.error("Readiness check failed: %s", str(e))
        raise HTTPException(status_code=503, detail="Service not ready")

@app.get("/v1/agents", response_model=List[AgentMetadata])
async def list_agents(request: Request):
    """List all available agents with their metadata."""
    try:
        trace_id = getattr(request.state, 'trace_id', generate_trace_id())
        logger.info("Listing agents", extra={"trace_id": trace_id})

        agent_cards = await get_agents()

        if not agent_cards:
            raise HTTPException(
                status_code=503,
                detail="No agents available"
            )

        agents = []
        for card_data in agent_cards:
            try:
                agent_metadata = transform_agent_card_to_metadata(card_data)
                agents.append(agent_metadata)
            except Exception as e:
                logger.warning("Failed to transform agent card: %s", str(e))
                continue

        logger.info("Successfully returned %d agents", len(agents), extra={"trace_id": trace_id})
        return agents

    except HTTPException:
        raise
    except Exception as e:
        trace_id = getattr(request.state, 'trace_id', generate_trace_id())
        logger.error("Error listing agents: %s", str(e), extra={"trace_id": trace_id})
        error_response = create_error_response(
            "EXECUTION_ERROR",
            "Failed to list agents",
            trace_id,
            {"error": str(e)}
        )
        raise HTTPException(status_code=500, detail=error_response.model_dump())

@app.get("/v1/agents/{name}", response_model=AgentMetadata)
async def get_agent(name: str, request: Request):
    """Get metadata for a specific agent."""
    try:
        trace_id = getattr(request.state, 'trace_id', generate_trace_id())
        logger.info("Getting agent metadata for %s", name, extra={"trace_id": trace_id})

        agent_cards = await get_agents()

        for card_data in agent_cards:
            if card_data.get("name") == name:
                agent_metadata = transform_agent_card_to_metadata(card_data)
                logger.info("Successfully returned agent %s", name, extra={"trace_id": trace_id})
                return agent_metadata

        # Agent not found
        error_response = create_error_response(
            "AGENT_NOT_FOUND",
            f"Agent '{name}' not found",
            trace_id
        )
        raise HTTPException(status_code=404, detail=error_response.model_dump())

    except HTTPException:
        raise
    except Exception as e:
        trace_id = getattr(request.state, 'trace_id', generate_trace_id())
        logger.error("Error getting agent %s: %s", name, str(e), extra={"trace_id": trace_id})
        error_response = create_error_response(
            "EXECUTION_ERROR",
            f"Failed to get agent {name}",
            trace_id,
            {"error": str(e)}
        )
        raise HTTPException(status_code=500, detail=error_response.model_dump())

@app.post("/v1/invoke", response_model=InvokeResponse)
async def invoke_agent(request_data: InvokeRequest, request: Request):
    """Invoke an agent with the provided inputs."""
    trace_id = getattr(request.state, 'trace_id', generate_trace_id())

    try:
        logger.info(
            "Invoking agent %s with inputs: %s",
            request_data.agent_name,
            request_data.agent_inputs,
            extra={"trace_id": trace_id},
        )

        # Get all agents to find the requested one
        agent_cards = await get_agents()

        # Find the requested agent
        agent_card_data = None
        for card in agent_cards:
            if card.get("name") == request_data.agent_name:
                agent_card_data = card
                break

        if not agent_card_data:
            error_response = create_error_response(
                "AGENT_NOT_FOUND",
                f"Agent '{request_data.agent_name}' not found",
                trace_id
            )
            raise HTTPException(status_code=404, detail=error_response.model_dump())

        # Transform to AgentMetadata to get input schema
        agent_metadata = transform_agent_card_to_metadata(agent_card_data)

        # Validate inputs against schema
        if not validate_json_schema(request_data.agent_inputs, agent_metadata.input_schema):
            error_response = create_error_response(
                "VALIDATION_FAILED",
                "Input validation failed",
                trace_id,
                {"schema": agent_metadata.input_schema}
            )
            raise HTTPException(status_code=400, detail=error_response.model_dump())

        # Create A2A client and invoke agent
        timeout_config = httpx.Timeout(REQUEST_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout_config) as httpx_client:
            agent_card = AgentCard(**agent_card_data)
            client = A2AClient(httpx_client, agent_card=agent_card)

            # Prepare the message
            query_text = json.dumps(request_data.agent_inputs) if isinstance(request_data.agent_inputs, dict) else str(request_data.agent_inputs)

            msg_params = MessageSendParams(
                message=Message(
                    role=Role.user,
                    parts=[Part(TextPart(text=query_text))],
                    message_id=uuid4().hex,
                )
            )

            # Send the request
            response = await client.send_message(
                SendMessageRequest(id=str(uuid4().hex), params=msg_params)
            )

            result = response.root.result.status.message

            logger.info(
                "Successfully invoked agent %s with reply: %s",
                request_data.agent_name,
                result,
                extra={"trace_id": trace_id},
            )

            return InvokeResponse(result=result, trace_id=trace_id)

    except HTTPException:
        raise
    except ValidationError as e:
        logger.warning(
            "Validation error for agent %s: %s",
            request_data.agent_name,
            str(e),
            extra={"trace_id": trace_id}
        )
        error_response = create_error_response(
            "VALIDATION_FAILED",
            "Request validation failed",
            trace_id,
            {"errors": e.errors()}
        )
        raise HTTPException(status_code=400, detail=error_response.model_dump())
    except Exception as e:
        logger.error(
            "Error invoking agent %s: %s",
            request_data.agent_name,
            str(e),
            extra={"trace_id": trace_id}
        )
        error_response = create_error_response(
            "EXECUTION_ERROR",
            f"Failed to invoke agent {request_data.agent_name}",
            trace_id,
            {"error": str(e)}
        )
        raise HTTPException(status_code=500, detail=error_response.model_dump())

# Legacy MCP Tools (for backward compatibility)
def serve(host, port, transport):  # noqa: PLR0915
    """Initializes and runs the Agent Cards MCP server.

    Args:
        host: The hostname or IP address to bind the server to.
        port: The port number to bind the server to.
        transport: The transport mechanism for the MCP server (e.g., 'stdio', 'sse').

    Raises:
        ValueError: If the 'GOOGLE_API_KEY' environment variable is not set.
    """
    logger.info('Starting Agent Cards MCP Server')
    mcp = FastMCP('agent-cards', host=host, port=port)

    @mcp.tool(
        name='find_agent',
        description='Finds the most relevant agent card based on a natural language query string.',
    )
    async def find_agent(query: str) -> str:
        """Recruits an agent to execute a task.

        Args:
            query: The natural language query string used to search for a
                   relevant agent.

        Returns:
            The json representing the agent card deemed most relevant
            to the input query based on embedding similarity.
        """
        logger.debug("Recruiting agent for query: %s", query)
        # Fetch agent cards asynchronously within the current event loop
        agent_cards = await get_agents()
        logger.debug("Candidate agent cards fetched: %s", agent_cards)
        agent_card = return_agent_card(agent_cards, query)
        agent_card = AgentCard(**agent_card)
        logger.info("Agent recruited for query %s -> %s", query, agent_card.name)
        return json.dumps(agent_card.model_dump())

    @mcp.tool(
        name='execute_task',
        description='Executes a task on a remote agent using the A2A protocol.',
    )
    async def execute_task(agent_url: str, query: str) -> str:  # noqa: D401 – fastapi tool signature
        """Execute a task on a remote agent and return the aggregated response."""

        # Fetch the agent-card data and build a proper ``AgentCard`` instance.
        agent_card_data = await get_agent_card_by_url(agent_url)
        agent_card = AgentCard(**agent_card_data)

        logger.info("Executing task on agent %s with query: %s", agent_card.name, query)

        # Build request params
        msg_params = MessageSendParams(
            message=Message(
                role=Role.user,
                parts=[Part(TextPart(text=query))],
                message_id=uuid4().hex,
            )
        )

        logger.debug("Sending non-streaming request …")
        timeout_config = httpx.Timeout(REQUEST_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout_config) as httpx_client:
            client = A2AClient(httpx_client, agent_card=agent_card)
            response = await client.send_message(
                SendMessageRequest(id=str(uuid4().hex), params=msg_params)
            )

            message_content = response.root.result.status.message

            logger.info("Agent %s task result: %s", agent_card.name, message_content)

            return message_content

    mcp.run(transport=transport)


# -------------------------------
# Command-line Interface / Entry
# -------------------------------

def main() -> None:
    """Entry point for running the ISEK MCP server from the command line.

    Example:
        python mcp_server.py --host 0.0.0.0 --port 8080
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the ISEK MCP server with REST API and MCP tools"
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Hostname or IP address to bind."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port number to bind the server to.",
    )
    parser.add_argument(
        "--mode",
        default="rest",
        choices=["rest", "mcp"],
        help="Server mode: 'rest' for REST API, 'mcp' for MCP tools only.",
    )
    parser.add_argument(
        "--transport",
        default="sse",
        choices=["stdio", "sse"],
        help="Transport mechanism for MCP mode (ignored in REST mode).",
    )

    args = parser.parse_args()

    if args.mode == "mcp":
        # Run legacy MCP server for backward compatibility
        logger.info("Starting MCP server in legacy mode")
        serve(args.host, args.port, args.transport)
    else:
        # Run FastAPI REST server
        logger.info("Starting REST API server on %s:%d", args.host, args.port)
        uvicorn.run(
            "mcp_server:app",
            host=args.host,
            port=args.port,
            log_level="info",
            reload=True
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        logger.error("Unhandled exception in MCP server", exc_info=exc)
        raise