"""Base classes for LLM providers"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """Represents a tool call from the LLM"""
    id: str
    name: str
    arguments: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict) -> "ToolCall":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            arguments=data.get("arguments", {}),
        )


@dataclass
class ToolDefinition:
    """Definition of a tool for the LLM"""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema

    def to_anthropic_format(self) -> dict:
        """Convert to Anthropic tool format"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def to_openai_format(self) -> dict:
        """Convert to OpenAI function format"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class Message:
    """A message in the conversation"""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None  # For tool results
    name: str | None = None  # Tool name for tool results

    def to_anthropic_format(self) -> dict:
        """Convert to Anthropic message format"""
        if self.role == "system":
            # Anthropic handles system messages separately
            return {"role": "user", "content": f"[System]: {self.content}"}

        if self.role == "tool":
            return {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": self.tool_call_id,
                    "content": self.content,
                }],
            }

        if self.role == "assistant" and self.tool_calls:
            content = []
            if self.content:
                content.append({"type": "text", "text": self.content})
            for tc in self.tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                })
            return {"role": "assistant", "content": content}

        return {"role": self.role, "content": self.content}

    def to_openai_format(self) -> dict:
        """Convert to OpenAI message format"""
        msg: dict[str, Any] = {"role": self.role, "content": self.content}

        if self.role == "assistant" and self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": str(tc.arguments) if isinstance(tc.arguments, dict)
                        else tc.arguments,
                    },
                }
                for tc in self.tool_calls
            ]

        if self.role == "tool":
            msg["tool_call_id"] = self.tool_call_id
            msg["name"] = self.name

        return msg


@dataclass
class UsageInfo:
    """Token usage information"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """Response from an LLM provider"""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: UsageInfo | None = None
    raw_response: Any = None  # Original response for debugging


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Send a chat request to the LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of tool definitions
            model: Model identifier (provider-specific)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Returns:
            LLMResponse with content and optional tool calls
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name"""
        pass
