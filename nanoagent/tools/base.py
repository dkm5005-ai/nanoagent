"""Base classes for the tool system"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..providers.base import ToolDefinition


@dataclass
class ToolResult:
    """Result from executing a tool"""
    content: str  # Content for the LLM
    for_user: str | None = None  # Optional content for direct user display
    is_error: bool = False

    @classmethod
    def success(cls, content: str, for_user: str | None = None) -> "ToolResult":
        """Create a successful result"""
        return cls(content=content, for_user=for_user, is_error=False)

    @classmethod
    def error(cls, message: str) -> "ToolResult":
        """Create an error result"""
        return cls(content=f"Error: {message}", is_error=True)


class Tool(ABC):
    """Abstract base class for tools"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the tool name (used in function calls)"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a description of what the tool does"""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """Return JSON Schema for the tool parameters"""
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the given arguments"""
        pass

    def to_definition(self) -> ToolDefinition:
        """Convert to ToolDefinition for LLM"""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )


@dataclass
class ToolRegistry:
    """Registry for managing available tools"""
    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        """Register a tool"""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool by name"""
        if name in self._tools:
            del self._tools[name]

    def get(self, name: str) -> Tool | None:
        """Get a tool by name"""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names"""
        return sorted(self._tools.keys())

    def to_definitions(self) -> list[ToolDefinition]:
        """Convert all tools to definitions for LLM"""
        # Sort by name for deterministic ordering (helps with LLM caching)
        return [
            self._tools[name].to_definition()
            for name in sorted(self._tools.keys())
        ]

    async def execute(self, name: str, args: dict[str, Any]) -> ToolResult:
        """Execute a tool by name with arguments"""
        tool = self.get(name)
        if not tool:
            return ToolResult.error(f"Unknown tool: {name}")

        try:
            return await tool.execute(**args)
        except Exception as e:
            return ToolResult.error(f"Tool execution failed: {e}")


def create_default_registry(
    workspace: str | None = None,
    restrict_to_workspace: bool = True,
    deny_patterns: list[str] | None = None,
) -> ToolRegistry:
    """Create a registry with default tools"""
    from .filesystem import (
        ReadFileTool, WriteFileTool, EditFileTool,
        ListDirTool, AppendFileTool,
    )
    from .shell import ShellTool
    from .web import WebSearchTool, WebFetchTool

    registry = ToolRegistry()

    # Filesystem tools
    registry.register(ReadFileTool(workspace=workspace, restrict=restrict_to_workspace))
    registry.register(WriteFileTool(workspace=workspace, restrict=restrict_to_workspace))
    registry.register(EditFileTool(workspace=workspace, restrict=restrict_to_workspace))
    registry.register(ListDirTool(workspace=workspace, restrict=restrict_to_workspace))
    registry.register(AppendFileTool(workspace=workspace, restrict=restrict_to_workspace))

    # Shell tool
    registry.register(ShellTool(
        workspace=workspace,
        restrict=restrict_to_workspace,
        deny_patterns=deny_patterns or [],
    ))

    # Web tools
    registry.register(WebSearchTool())
    registry.register(WebFetchTool())

    return registry
