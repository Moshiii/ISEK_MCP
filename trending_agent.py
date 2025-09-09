
import asyncio
from typing import Any, AsyncGenerator

from pydantic_ai import Agent
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState, AgentCard, AgentCapabilities, AgentSkill
from a2a.utils import new_agent_text_message, new_task

from common import (
    log_a2a_protocol,
    log_a2a_function_call,
    log_error,
    google_search,
    create_agent_a2a_server,
    run_server,
)

import dotenv
dotenv.load_dotenv()

class TrendingAgent:
    """Agent for finding trending topics using Pydantic AI."""

    SYSTEM_INSTRUCTION = """
    You are a social media trends analyst. Your job is to search the web for current trending topics,
    particularly from social platforms.

    When asked about trends:
    1. Search for "trending topics today" or similar queries
    2. Extract the top 3 trending topics
    3. Return them in a JSON format

    Focus on current, real-time trends from the last 24 hours.

    You MUST return your response in the following JSON format:
    {
        "trends": [
            {"topic": "Topic name", "description": "Brief description (1-2 sentences)", "reason": "Why it's trending"},
            {"topic": "Topic name", "description": "Brief description (1-2 sentences)", "reason": "Why it's trending"},
            {"topic": "Topic name", "description": "Brief description (1-2 sentences)", "reason": "Why it's trending"}
        ]
    }

    Only return the JSON object, no additional text.
    """

    def __init__(self):
        self.agent = Agent(model="gpt-4", tools=[google_search], system_prompt=self.SYSTEM_INSTRUCTION)

    async def stream(self, query: str, context_id: str) -> AsyncGenerator[dict[str, Any], None]:
        """Stream the agent response."""
        log_a2a_protocol(
            f"TrendingAgent.stream() called with query: '{query[:50]}{'...' if len(query) > 50 else ''}', context_id: {context_id}",
            "←",
            "User",
            "TrendingAgent",
        )

        try:
            yield {
                "is_task_complete": False,
                "require_user_input": False,
                "content": "Searching for trending topics...",
            }
            log_a2a_protocol(
                "TrendingAgent.stream() yielding status update - searching for trends", "→", "TrendingAgent", "A2A_System"
            )

            response = await self.agent.run(query)
            log_a2a_function_call(
                "self.agent.run()", f"query_length: {len(query)}, response_length: {len(response.output)}"
            )

            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": response.output,
            }
            log_a2a_protocol(
                f"TrendingAgent.stream() yielding final response - task complete, content_length: {len(response.output)}",
                "→",
                "TrendingAgent",
                "A2A_System",
            )

        except Exception as e:
            log_error(f"TrendingAgent.stream() error: {str(e)} - query: '{query[:30]}...', context_id: {context_id}")
            yield {
                "is_task_complete": False,
                "require_user_input": True,
                "content": f"Error processing request: {str(e)}",
            }
            log_a2a_protocol(
                f"TrendingAgent.stream() yielding error response - require_user_input: True", "→", "TrendingAgent", "A2A_System"
            )


class TrendingAgentExecutor:
    """Executor for the Trending Agent."""

    def __init__(self):
        self.agent = TrendingAgent()

    async def execute(self, context, event_queue):
        """Execute the trending agent."""
        from a2a.server.agent_execution import RequestContext
        from a2a.server.events import EventQueue
        from a2a.types import Part, TextPart

        log_a2a_function_call(
            "TrendingAgentExecutor.execute()", f"context_id: {context.context_id}, context_type: {type(context).__name__}"
        )

        query = context.get_user_input()
        log_a2a_function_call(
            "context.get_user_input()", f"query: '{query[:50]}{'...' if len(query) > 50 else ''}', context_id: {context.context_id}"
        )

        task = context.current_task
        if not task:
            task = new_task(context.message)
            log_a2a_function_call("new_task()", f"message_id: {context.message.message_id}, task_id: {task.id}")
            await event_queue.enqueue_event(task)
            log_a2a_function_call("event_queue.enqueue_event()", f"task_id: {task.id}, event_type: {type(task).__name__}")
        else:
            log_a2a_function_call(
                "Using existing task", f"task_id: {task.id}, task_state: {getattr(task, 'state', 'unknown')}"
            )

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        log_a2a_function_call("TaskUpdater()", f"task_id: {task.id}, context_id: {task.context_id}")

        try:
            async for item in self.agent.stream(query, task.context_id):
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]
                content = item["content"]

                log_a2a_function_call(
                    "Processing stream item",
                    f"is_complete: {is_task_complete}, require_input: {require_user_input}, content_length: {len(content)}",
                )

                if not is_task_complete and not require_user_input:
                    message = new_agent_text_message(content, task.context_id, task.id)
                    log_a2a_function_call(
                        "new_agent_text_message()",
                        f"content_length: {len(content)}, context_id: {task.context_id}, task_id: {task.id}",
                    )

                    await updater.update_status(TaskState.working, message)
                    log_a2a_function_call(
                        "TaskUpdater.update_status()", f"state: working, task_id: {task.id}, message_id: {message.message_id}"
                    )
                elif require_user_input:
                    message = new_agent_text_message(content, task.context_id, task.id)
                    log_a2a_function_call(
                        "new_agent_text_message()",
                        f"content_length: {len(content)}, context_id: {task.context_id}, task_id: {task.id}",
                    )

                    await updater.update_status(TaskState.input_required, message, final=True)
                    log_a2a_function_call(
                        "TaskUpdater.update_status()",
                        f"state: input_required, task_id: {task.id}, final: True, message_id: {message.message_id}",
                    )
                    break
                else:
                    parts = [Part(root=TextPart(text=content))]
                    log_a2a_function_call(
                        "Creating artifact parts", f"parts_count: {len(parts)}, content_length: {len(content)}"
                    )

                    await updater.add_artifact(parts, name="trending_results")
                    log_a2a_function_call(
                        "TaskUpdater.add_artifact()", f"name: trending_results, task_id: {task.id}, parts_count: {len(parts)}"
                    )

                    await updater.complete()
                    log_a2a_function_call("TaskUpdater.complete()", f"task_id: {task.id}")
                    break

        except Exception as e:
            log_error(
                f"TrendingAgentExecutor.execute() error: {str(e)} - context_id: {context.context_id}, task_id: {task.id if task else 'None'}"
            )
            from a2a.utils.errors import ServerError
            from a2a.types import InternalError

            raise ServerError(error=InternalError()) from e

def main():
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

    def create_agent():
        return create_agent_a2a_server(TrendingAgentExecutor(), trending_agent_card)

    import os
    port = int(os.getenv("PORT", 10020))
    asyncio.run(run_server(create_agent, port, "Trending Agent"))

if __name__ == "__main__":
    main()
