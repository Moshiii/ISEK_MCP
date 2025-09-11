import json
from pathlib import Path
from openai import OpenAI
import asyncio
import httpx
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
from uuid import uuid4

import dotenv
dotenv.load_dotenv()

client = OpenAI()

logger = get_logger(__name__)
AGENT_CARDS_DIR = 'agent_cards'
MODEL = 'text-embedding-ada-002'
agent_urls = ['http://localhost:9999', # openai agent
              'http://localhost:10020', # trending agent
              'http://localhost:10021' # analyzer agent
            ]
AGENT_CARD_WELL_KNOWN_PATH = "/.well-known/agent.json"

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
                        
async def get_agents() -> list[dict]:
        """Fetch and cache agent cards from all configured agent URLs.

        The function uses a simple in-memory cache (``_agent_info_cache``) to avoid
        fetching the ­same agent card repeatedly.  If a card is not cached, it is
        retrieved from the agent’s “well-known” endpoint and stored in the cache.

        Returns:
            list[dict]: A list of ``AgentCard`` dictionaries – fully JSON-serialisable
            objects for interoperability with the rest of the MCP pipeline.
        """

        timeout_config = httpx.Timeout(10.0)  # seconds
        fetched_cards: list[dict] = []

        logger.info("[get_agents],Fetching agent cards from configured agent URLs …")

        async with httpx.AsyncClient(timeout=timeout_config) as httpx_client:
            for agent_url in agent_urls:
                logger.debug("[get_agents],Fetching agent card for %s", agent_url)
                response = await httpx_client.get(f"{agent_url}{AGENT_CARD_WELL_KNOWN_PATH}")
                response.raise_for_status()
                card_data = response.json()
                fetched_cards.append(card_data)

        logger.info("[get_agents],Successfully retrieved %d agent cards", len(fetched_cards))
        return fetched_cards
        
async def get_agent_card_by_url(agent_url: str) -> dict:
    """Fetch and cache agent cards from all configured agent URLs.

    The function uses a simple in-memory cache (``_agent_info_cache``) to avoid
    fetching the ­same agent card repeatedly.  If a card is not cached, it is
    retrieved from the agent’s “well-known” endpoint and stored in the cache.
    
    Args:
        agent_url: The URL of the agent to fetch the agent card from.

    Returns:
        dict: ``AgentCard`` fully JSON-serialisable object for interoperability with the rest of the MCP pipeline.
    """
    timeout_config = httpx.Timeout(10.0)  # seconds
    logger.debug("[get_agent_card_by_url],Fetching agent card for %s", agent_url)
    async with httpx.AsyncClient(timeout=timeout_config) as httpx_client:
        response = await httpx_client.get(f"{agent_url}{AGENT_CARD_WELL_KNOWN_PATH}")
        response.raise_for_status()
        card_data = response.json()
        return card_data

def serve(host, port, transport):  # noqa: PLR0915
    """Initializes and runs the Agent Cards MCP server.

    Args:
        host: The hostname or IP address to bind the server to.
        port: The port number to bind the server to.
        transport: The transport mechanism for the MCP server (e.g., 'stdio', 'sse').

    Raises:
        ValueError: If the 'GOOGLE_API_KEY' environment variable is not set.
    """
    logger.info('[serve],Starting Agent Cards MCP Server')
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
        logger.debug("[find_agent],Recruiting agent for query: %s", query)
        # Fetch agent cards asynchronously within the current event loop
        agent_cards = await get_agents()
        logger.debug("[find_agent],Candidate agent cards fetched: %s", agent_cards)
        agent_card = return_agent_card(agent_cards, query)
        agent_card = AgentCard(**agent_card)
        logger.info("[find_agent],Agent recruited for query %s -> %s", query, agent_card.name)
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

        logger.info("[execute_task],Executing task on agent %s with query: %s", agent_card.name, query)

        # Build request params
        msg_params = MessageSendParams(
            message=Message(
                role=Role.user,
                parts=[Part(TextPart(text=query))],
                message_id=uuid4().hex,
            )
        )

        logger.debug("[execute_task] Sending non-streaming request …")
        timeout_config = httpx.Timeout(10.0)
        async with httpx.AsyncClient(timeout=timeout_config) as httpx_client:
            client = A2AClient(httpx_client, agent_card=agent_card)
            response = await client.send_message(
                SendMessageRequest(id=str(uuid4().hex), params=msg_params)
            )
            
            message_content = response.root.result.status.message

            logger.info("[execute_task] Task result content: %s", message_content)
        
            return message_content

    mcp.run(transport=transport)


# -------------------------------
# Command-line Interface / Entry
# -------------------------------

def main() -> None:
    """Entry point for running the Agent Cards MCP server from the command line.

    Example:
        python -m mcp_server.mcp_server --host 0.0.0.0 --port 8000 --transport sse
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the Agent Cards MCP server"
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
        "--transport",
        default="sse",
        choices=["stdio", "sse"],
        help="Transport mechanism to use (stdio or sse).",
    )

    args = parser.parse_args()

    # Run the server
    serve(args.host, args.port, args.transport)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        logger.error("Unhandled exception in MCP server", exc_info=exc)
        raise