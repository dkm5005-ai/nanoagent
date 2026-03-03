"""Anthropic Claude provider implementation"""

import json
from typing import Any

from anthropic import AsyncAnthropic

from .base import LLMProvider, LLMResponse, Message, ToolCall, ToolDefinition, UsageInfo


class AnthropicProvider(LLMProvider):
    """Provider for Anthropic Claude models"""

    def __init__(self, api_key: str, api_base: str | None = None):
        self.api_key = api_key
        self.api_base = api_base

    def _get_client(self) -> AsyncAnthropic:
        """Create a fresh client for each request to avoid event loop issues"""
        return AsyncAnthropic(
            api_key=self.api_key,
            base_url=self.api_base,
        )

    @property
    def provider_name(self) -> str:
        return "anthropic"

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send chat request to Anthropic API"""
        model = model or "claude-sonnet-4-20250514"

        # Extract system message
        system_content = ""
        chat_messages = []

        for msg in messages:
            if msg.role == "system":
                system_content += msg.content + "\n"
            else:
                chat_messages.append(self._convert_message(msg))

        # Build request
        request_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_messages,
        }

        if system_content:
            request_kwargs["system"] = system_content.strip()

        if tools:
            request_kwargs["tools"] = [t.to_anthropic_format() for t in tools]

        # Make request
        client = self._get_client()
        response = await client.messages.create(**request_kwargs)

        # Parse response
        return self._parse_response(response)

    def _convert_message(self, msg: Message) -> dict:
        """Convert Message to Anthropic format"""
        if msg.role == "tool":
            return {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": msg.content,
                }],
            }

        if msg.role == "assistant" and msg.tool_calls:
            content: list[dict[str, Any]] = []
            if msg.content:
                content.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                })
            return {"role": "assistant", "content": content}

        return {"role": msg.role, "content": msg.content}

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse Anthropic response to LLMResponse"""
        content = ""
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else json.loads(block.input),
                ))

        usage = None
        if hasattr(response, "usage"):
            usage = UsageInfo(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason or "stop",
            usage=usage,
            raw_response=response,
        )
