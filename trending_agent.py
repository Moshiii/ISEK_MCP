
import asyncio
from typing import Any, AsyncGenerator

from pydantic_ai import Agent
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState, AgentCard, AgentCapabilities, AgentSkill
from a2a.utils import new_agent_text_message, new_task

from common import (
    create_agent_a2a_server,
    run_server,
    google_search,
    log_agent_start,
    log_agent_activity,
    log_agent_request,
    log_agent_response,
    log_error,
    log_system_event,
    get_current_date_context,
)

import dotenv
dotenv.load_dotenv()

class TrendingAgent:
    """Agent for finding trending topics using Pydantic AI."""

    @staticmethod
    def get_system_instruction() -> str:
        """Generate system instruction with current date context."""
        date_context = get_current_date_context()
        return f"""{date_context}

You are a social media trends analyst. Your job is to search the web for current trending topics,
particularly from social platforms.

When asked about trends:
1. Search for "trending topics today" or similar queries
2. Extract the top 3 trending topics
3. Return them in a JSON format

Focus on current, real-time trends from the last 24 hours.

You MUST return your response in the following JSON format:
{{
    "trends": [
        {{"topic": "Topic name", "description": "Brief description (1-2 sentences)", "reason": "Why it's trending"}},
        {{"topic": "Topic name", "description": "Brief description (1-2 sentences)", "reason": "Why it's trending"}},
        {{"topic": "Topic name", "description": "Brief description (1-2 sentences)", "reason": "Why it's trending"}}
    ]
}}

Only return the JSON object, no additional text.
"""

    def __init__(self):
        system_prompt = self.get_system_instruction()
        self.agent = Agent(model="gpt-4", tools=[google_search], system_prompt=system_prompt)
        log_agent_activity("Trending Agent", "Initialized with GPT-4 model and current date context")

    async def stream(self, query: str, context_id: str) -> AsyncGenerator[dict[str, Any], None]:
        """Stream the agent response."""
        try:
            log_agent_request("Trending Agent", query, context_id)

            # Initial message
            log_agent_activity("Trending Agent", "Starting request processing")
            yield {
                "is_task_complete": False,
                "require_user_input": False,
                "content": "Searching for trending topics...",
            }

            # Get response
            log_agent_activity("Trending Agent", "Sending request to find trends")
            response = await self.agent.run(query)
            log_agent_activity("Trending Agent", "Received response")

            # Return final response
            log_agent_response("Trending Agent", "Task completed successfully", context_id)
            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": response.output,
            }

        except Exception as e:
            error_msg = f"Error during processing: {str(e)}"
            log_error(error_msg)
            yield {
                "is_task_complete": False,
                "require_user_input": True,
                "content": f"Error: {str(e)}",
            }


class TrendingAgentExecutor:
    """Executor for the Trending Agent."""

    def __init__(self):
        self.agent = TrendingAgent()
        log_agent_activity("Trending Agent Executor", "Initialized")

    async def execute(self, context, event_queue):
        """Execute the trending agent."""
        log_agent_activity("Trending Agent Executor", "Starting execution")
        query = context.get_user_input()
        log_agent_activity("Trending Agent Executor", f"Received execution request for context: {context.message.context_id}")
        log_agent_activity("Trending Agent Executor", f"Query: {query}")
        
        task = context.current_task or new_task(context.message)
        await event_queue.enqueue_event(task)
        log_agent_activity("Trending Agent Executor", f"Created new task: {task.id}")
        
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        log_agent_activity("Trending Agent Executor", "Created task updater")

        try:
            log_agent_activity("Trending Agent Executor", "Starting agent stream")
            async for item in self.agent.stream(query, task.context_id):
                log_agent_activity("Trending Agent Executor", f"Received stream item: {item}")
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]
                content = item["content"]

                message = new_agent_text_message(content, task.context_id, task.id)

                if is_task_complete:
                    log_agent_activity("Trending Agent Executor", f"Task {task.id} completed")
                    await updater.complete(message)
                elif require_user_input:
                    log_agent_activity("Trending Agent Executor", f"Task {task.id} requires user input")
                    await updater.update_status(TaskState.input_required, message, final=True)
                else:
                    log_agent_activity("Trending Agent Executor", f"Task {task.id} in progress")
                    await updater.update_status(TaskState.working, message)

        except Exception as e:
            from a2a.utils.errors import ServerError
            from a2a.types import InternalError
            log_error(f"Error in executor: {str(e)}")
            log_error(f"Error details: {type(e).__name__}")
            raise ServerError(error=InternalError()) from e

def create_agent():
    """Create and configure the Trending agent server."""
    log_system_event("Creating Trending Agent server")
    trending_agent_card = AgentCard(
        name="Trending Topics Agent",
        url="http://localhost:10020",
        description="Searches the web for current trending topics from social media",
        version="1.0",
        capabilities=AgentCapabilities(streaming=True),
        defaultInputModes=["text/plain"],
        defaultOutputModes=["application/json"],
        skills=[
            AgentSkill(
                id="find_trends",
                name="Find Trending Topics",
                description="Searches for current trending topics on social media",
                tags=["trends", "social media", "twitter", "current events"],
                examples=[
                    "What's trending today?",
                    "Show me current Twitter trends",
                    "What are people talking about on social media?",
                ],
            )
        ],
    )
    return create_agent_a2a_server(TrendingAgentExecutor(), trending_agent_card)

def main():
    """Run the Trending agent server."""
    import os
    port = int(os.getenv("PORT", 10020))
    log_agent_start("Trending Agent", port)
    asyncio.run(run_server(create_agent, port, "Trending Agent"))

if __name__ == "__main__":
    main()
