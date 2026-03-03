"""OpenRouter provider implementation (OpenAI-compatible)"""

import json
from typing import Any

import httpx

from .base import LLMProvider, LLMResponse, Message, ToolCall, ToolDefinition, UsageInfo


class OpenRouterProvider(LLMProvider):
    """Provider for OpenRouter (multi-model gateway)"""

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://openrouter.ai/api/v1",
    ):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")

    def _get_client(self) -> httpx.AsyncClient:
        """Create a fresh client for each request to avoid event loop issues"""
        return httpx.AsyncClient(
            base_url=self.api_base,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://github.com/nanoagent",
                "X-Title": "NanoAgent",
            },
            timeout=120.0,
        )

    @property
    def provider_name(self) -> str:
        return "openrouter"

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send chat request to OpenRouter API"""
        model = model or "anthropic/claude-sonnet-4"

        # Convert messages to OpenAI format (OpenRouter is OpenAI-compatible)
        openai_messages = [self._convert_message(msg) for msg in messages]

        # Build request body
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": openai_messages,
        }

        if tools:
            body["tools"] = [t.to_openai_format() for t in tools]

        # Make request with fresh client
        client = self._get_client()
        try:
            response = await client.post("/chat/completions", json=body)
            response.raise_for_status()
            data = response.json()
        finally:
            await client.aclose()

        # Parse response
        return self._parse_response(data)

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

    def _parse_response(self, data: dict) -> LLMResponse:
        """Parse OpenRouter response to LLMResponse"""
        choice = data["choices"][0]
        message = choice["message"]

        content = message.get("content", "") or ""
        tool_calls: list[ToolCall] = []

        if "tool_calls" in message and message["tool_calls"]:
            for tc in message["tool_calls"]:
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    args = {"raw": tc.get("function", {}).get("arguments", "")}

                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    name=tc["function"]["name"],
                    arguments=args,
                ))

        usage = None
        if "usage" in data:
            u = data["usage"]
            usage = UsageInfo(
                prompt_tokens=u.get("prompt_tokens", 0),
                completion_tokens=u.get("completion_tokens", 0),
                total_tokens=u.get("total_tokens", 0),
            )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=usage,
            raw_response=data,
        )

    async def close(self) -> None:
        """Close any resources (no-op since clients are created per-request)"""
        pass
