
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


class AnalyzerAgent:
    """Agent for analyzing trends using Pydantic AI."""

    @staticmethod
    def get_system_instruction() -> str:
        """Generate system instruction with current date context."""
        date_context = get_current_date_context()
        return f"""{date_context}

You are a data analyst specializing in trend analysis. When given a trending topic,
perform deep research to find quantitative data and insights.

For each trend you analyze:
1. Search for statistics, numbers, and metrics related to the trend
2. Look for:
   - Engagement metrics (views, shares, mentions)
   - Growth rates and timeline
   - Geographic distribution
   - Related hashtags or keywords
3. Provide concrete numbers and data points

Keep it somehow concise

Always prioritize quantitative information over qualitative descriptions.
"""

    def __init__(self):
        system_prompt = self.get_system_instruction()
        self.agent = Agent(model="gpt-4", tools=[google_search], system_prompt=system_prompt)
        log_agent_activity("Analyzer Agent", "Initialized with GPT-4 model and current date context")

    async def stream(self, query: str, context_id: str) -> AsyncGenerator[dict[str, Any], None]:
        """Stream the agent response."""
        try:
            log_agent_request("Analyzer Agent", query, context_id)

            # Initial message
            log_agent_activity("Analyzer Agent", "Starting request processing")
            yield {
                "is_task_complete": False,
                "require_user_input": False,
                "content": "Analyzing trend data...",
            }

            # Get response
            log_agent_activity("Analyzer Agent", "Sending request for analysis")
            response = await self.agent.run(query)
            log_agent_activity("Analyzer Agent", "Received response")

            # Return final response
            log_agent_response("Analyzer Agent", "Task completed successfully", context_id)
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


class AnalyzerAgentExecutor:
    """Executor for the Analyzer Agent."""

    def __init__(self):
        self.agent = AnalyzerAgent()
        log_agent_activity("Analyzer Agent Executor", "Initialized")

    async def execute(self, context, event_queue):
        """Execute the analyzer agent."""
        log_agent_activity("Analyzer Agent Executor", "Starting execution")
        query = context.get_user_input()
        log_agent_activity("Analyzer Agent Executor", f"Received execution request for context: {context.message.context_id}")
        log_agent_activity("Analyzer Agent Executor", f"Query: {query}")
        
        task = context.current_task or new_task(context.message)
        await event_queue.enqueue_event(task)
        log_agent_activity("Analyzer Agent Executor", f"Created new task: {task.id}")
        
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        log_agent_activity("Analyzer Agent Executor", "Created task updater")

        try:
            log_agent_activity("Analyzer Agent Executor", "Starting agent stream")
            async for item in self.agent.stream(query, task.context_id):
                log_agent_activity("Analyzer Agent Executor", f"Received stream item: {item}")
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]
                content = item["content"]

                message = new_agent_text_message(content, task.context_id, task.id)

                if is_task_complete:
                    log_agent_activity("Analyzer Agent Executor", f"Task {task.id} completed")
                    await updater.complete(message)
                elif require_user_input:
                    log_agent_activity("Analyzer Agent Executor", f"Task {task.id} requires user input")
                    await updater.update_status(TaskState.input_required, message, final=True)
                else:
                    log_agent_activity("Analyzer Agent Executor", f"Task {task.id} in progress")
                    await updater.update_status(TaskState.working, message)

        except Exception as e:
            from a2a.utils.errors import ServerError
            from a2a.types import InternalError
            log_error(f"Error in executor: {str(e)}")
            log_error(f"Error details: {type(e).__name__}")
            raise ServerError(error=InternalError()) from e

def create_agent():
    """Create and configure the Analyzer agent server."""
    log_system_event("Creating Analyzer Agent server")
    analyzer_agent_card = AgentCard(
        name="Trend Analyzer Agent",
        url="http://localhost:10021",
        description="Performs deep analysis of trends with quantitative data",
        version="1.0",
        capabilities=AgentCapabilities(streaming=True),
        defaultInputModes=["text/plain"],
        defaultOutputModes=["application/json"],
        skills=[
            AgentSkill(
                id="analyze_trend",
                name="Analyze Trend",
                description="Provides quantitative analysis of a specific trend",
                tags=["analysis", "data", "metrics", "statistics"],
                examples=[
                    "Analyze the #ClimateChange trend",
                    "Get metrics for the Taylor Swift trend",
                    "Provide data analysis for AI adoption trend",
                ],
            )
        ],
    )
    return create_agent_a2a_server(AnalyzerAgentExecutor(), analyzer_agent_card)

def main():
    """Run the Analyzer agent server."""
    import os
    port = int(os.getenv("PORT", 10021))
    log_agent_start("Analyzer Agent", port)
    asyncio.run(run_server(create_agent, port, "Analyzer Agent"))

if __name__ == "__main__":
    main()
