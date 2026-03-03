"""OpenAI provider implementation"""

import json
from typing import Any

from openai import AsyncOpenAI

from .base import LLMProvider, LLMResponse, Message, ToolCall, ToolDefinition, UsageInfo


class OpenAIProvider(LLMProvider):
    """Provider for OpenAI GPT models"""

    def __init__(self, api_key: str, api_base: str | None = None):
        self.api_key = api_key
        self.api_base = api_base

    def _get_client(self) -> AsyncOpenAI:
        """Create a fresh client for each request to avoid event loop issues"""
        return AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base,
        )

    @property
    def provider_name(self) -> str:
        return "openai"

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send chat request to OpenAI API"""
        model = model or "gpt-4o"

        # Convert messages to OpenAI format
        openai_messages = [self._convert_message(msg) for msg in messages]

        # Build request
        request_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": openai_messages,
        }

        if tools:
            request_kwargs["tools"] = [t.to_openai_format() for t in tools]

        # Make request
        client = self._get_client()
        response = await client.chat.completions.create(**request_kwargs)

        # Parse response
        return self._parse_response(response)

    def _convert_message(self, msg: Message) -> dict:
        """Convert Message to OpenAI format"""
        result: dict[str, Any] = {
            "role": msg.role,
            "content": msg.content,
        }

        if msg.role == "assistant" and msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments)
                        if isinstance(tc.arguments, dict) else tc.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]

        if msg.role == "tool":
            result["tool_call_id"] = msg.tool_call_id
            if msg.name:
                result["name"] = msg.name

        return result

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse OpenAI response to LLMResponse"""
        choice = response.choices[0]
        message = choice.message

        content = message.content or ""
        tool_calls: list[ToolCall] = []

        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {"raw": tc.function.arguments}

                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        usage = None
        if response.usage:
            usage = UsageInfo(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            raw_response=response,
        )
