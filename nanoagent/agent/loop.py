"""Main agent loop with tool execution"""

import logging
from dataclasses import dataclass
from typing import Any, Callable

from ..config.config import Config
from ..providers.base import LLMProvider, LLMResponse, Message, ToolCall
from ..tools.base import ToolRegistry, ToolResult
from .context import ContextBuilder
from .session import SessionManager

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Response from the agent"""
    content: str
    tool_results: list[tuple[str, ToolResult]] = None  # (tool_name, result) pairs
    usage: dict[str, int] | None = None


class AgentLoop:
    """Main agent loop that processes messages and executes tools"""

    def __init__(
        self,
        provider: LLMProvider,
        tool_registry: ToolRegistry,
        session_manager: SessionManager,
        context_builder: ContextBuilder,
        config: Config,
    ):
        self.provider = provider
        self.tools = tool_registry
        self.sessions = session_manager
        self.context = context_builder
        self.config = config

        # Callbacks for UI updates
        self.on_tool_start: Callable[[str, dict], None] | None = None
        self.on_tool_end: Callable[[str, ToolResult], None] | None = None
        self.on_thinking: Callable[[], None] | None = None

    async def run(
        self,
        user_message: str,
        session_id: str = "default",
        model: str | None = None,
    ) -> AgentResponse:
        """
        Process a user message and return the agent's response.

        Args:
            user_message: The user's input
            session_id: Session identifier for conversation history
            model: Optional model override

        Returns:
            AgentResponse with the final content and any tool results
        """
        # Get model config
        model_config = self.config.get_model_config(model)
        max_iterations = self.config.agent.max_tool_iterations

        # Get or create session
        session = self.sessions.get(session_id)

        # Build system prompt
        tools_summary = self.context.get_tools_summary(self.tools.list_tools())
        system_prompt = self.context.build(tools_summary)

        # Add user message to session
        session.add_message("user", user_message)

        # Build messages for LLM
        messages = [Message(role="system", content=system_prompt)]
        messages.extend(session.get_history(self.config.agent.max_history_messages))

        # Get tool definitions
        tool_definitions = self.tools.to_definitions()

        # Track tool results for response
        all_tool_results: list[tuple[str, ToolResult]] = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        # Main loop
        iteration = 0
        while iteration < max_iterations:
            iteration += 1

            if self.on_thinking:
                self.on_thinking()

            # Call LLM
            logger.debug(f"Iteration {iteration}: calling LLM with {len(messages)} messages")

            response = await self.provider.chat(
                messages=messages,
                tools=tool_definitions if tool_definitions else None,
                model=model_config.model,
                max_tokens=model_config.max_tokens,
                temperature=model_config.temperature,
            )

            # Track usage
            if response.usage:
                total_usage["prompt_tokens"] += response.usage.prompt_tokens
                total_usage["completion_tokens"] += response.usage.completion_tokens
                total_usage["total_tokens"] += response.usage.total_tokens

            # No tool calls - we're done
            if not response.tool_calls:
                logger.debug(f"No tool calls, returning response")

                # Add assistant response to session
                session.add_message("assistant", response.content)
                self.sessions.save(session_id)

                return AgentResponse(
                    content=response.content,
                    tool_results=all_tool_results if all_tool_results else None,
                    usage=total_usage,
                )

            # Process tool calls
            logger.debug(f"Processing {len(response.tool_calls)} tool calls")

            # Add assistant message with tool calls to messages
            assistant_msg = Message(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls,
            )
            messages.append(assistant_msg)
            session.add_full_message(assistant_msg)

            # Execute each tool
            for tool_call in response.tool_calls:
                tool_name = tool_call.name
                tool_args = tool_call.arguments

                logger.debug(f"Executing tool: {tool_name} with args: {tool_args}")

                if self.on_tool_start:
                    self.on_tool_start(tool_name, tool_args)

                # Execute tool
                result = await self.tools.execute(tool_name, tool_args)
                all_tool_results.append((tool_name, result))

                if self.on_tool_end:
                    self.on_tool_end(tool_name, result)

                # Add tool result to messages
                tool_msg = Message(
                    role="tool",
                    content=result.content,
                    tool_call_id=tool_call.id,
                    name=tool_name,
                )
                messages.append(tool_msg)
                session.add_full_message(tool_msg)

        # Max iterations reached
        logger.warning(f"Max iterations ({max_iterations}) reached")
        final_content = response.content if response else "I reached my limit of tool iterations."

        session.add_message("assistant", final_content)
        self.sessions.save(session_id)

        return AgentResponse(
            content=final_content,
            tool_results=all_tool_results if all_tool_results else None,
            usage=total_usage,
        )

    async def chat(
        self,
        message: str,
        session_id: str = "default",
        model: str | None = None,
    ) -> str:
        """Simple interface that returns just the response text"""
        response = await self.run(message, session_id, model)
        return response.content


def create_provider(config: Config, model_name: str | None = None) -> LLMProvider:
    """Create an LLM provider from config"""
    from ..providers.anthropic import AnthropicProvider
    from ..providers.openai import OpenAIProvider
    from ..providers.openrouter import OpenRouterProvider

    model_config = config.get_model_config(model_name)
    provider_name = model_config.provider

    # Get API key (model override or provider default)
    api_key = model_config.api_key or config.get_api_key(model_name)
    api_base = model_config.api_base

    # Get provider-specific API base if not overridden
    if not api_base:
        provider_config = config.get_provider_config(provider_name)
        api_base = provider_config.api_base

    if provider_name == "anthropic":
        return AnthropicProvider(api_key=api_key, api_base=api_base)
    elif provider_name == "openai":
        return OpenAIProvider(api_key=api_key, api_base=api_base)
    elif provider_name == "openrouter":
        return OpenRouterProvider(
            api_key=api_key,
            api_base=api_base or "https://openrouter.ai/api/v1",
        )
    else:
        raise ValueError(f"Unknown provider: {provider_name}")


def create_agent(config: Config, model_name: str | None = None) -> AgentLoop:
    """Create a fully configured agent"""
    from ..tools.base import create_default_registry
    from .context import ContextBuilder, create_default_workspace_files
    from .session import SessionManager

    # Ensure workspace exists
    workspace = config.get_workspace_path()
    create_default_workspace_files(workspace)

    # Create components
    provider = create_provider(config, model_name)

    tool_registry = create_default_registry(
        workspace=str(workspace),
        restrict_to_workspace=config.tools.restrict_to_workspace,
        deny_patterns=config.tools.shell_deny_patterns,
    )

    session_manager = SessionManager(workspace / "sessions")
    context_builder = ContextBuilder(workspace)

    return AgentLoop(
        provider=provider,
        tool_registry=tool_registry,
        session_manager=session_manager,
        context_builder=context_builder,
        config=config,
    )
