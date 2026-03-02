"""Filesystem tools for NanoAgent"""

import os
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class BaseFilesystemTool(Tool):
    """Base class for filesystem tools with workspace restriction"""

    def __init__(self, workspace: str | None = None, restrict: bool = True):
        self.workspace = Path(workspace).expanduser().resolve() if workspace else None
        self.restrict = restrict

    def _resolve_path(self, path: str) -> Path:
        """Resolve path, optionally restricting to workspace"""
        resolved = Path(path).expanduser()

        # Make absolute
        if not resolved.is_absolute():
            if self.workspace:
                resolved = self.workspace / resolved
            else:
                resolved = Path.cwd() / resolved

        resolved = resolved.resolve()

        # Check workspace restriction
        if self.restrict and self.workspace:
            try:
                resolved.relative_to(self.workspace)
            except ValueError:
                raise PermissionError(
                    f"Access denied: path '{path}' is outside workspace"
                )

        return resolved


class ReadFileTool(BaseFilesystemTool):
    """Tool for reading file contents"""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file. Returns the file content as text."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (0-indexed)",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read",
                    "default": 1000,
                },
            },
            "required": ["path"],
        }

    async def execute(
        self,
        path: str,
        offset: int = 0,
        limit: int = 1000,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            resolved = self._resolve_path(path)

            if not resolved.exists():
                return ToolResult.error(f"File not found: {path}")

            if not resolved.is_file():
                return ToolResult.error(f"Not a file: {path}")

            content = resolved.read_text()
            lines = content.splitlines()

            # Apply offset and limit
            selected_lines = lines[offset:offset + limit]
            result = "\n".join(selected_lines)

            # Add info if truncated
            if len(lines) > offset + limit:
                result += f"\n\n[... {len(lines) - offset - limit} more lines]"

            return ToolResult.success(result)

        except PermissionError as e:
            return ToolResult.error(str(e))
        except Exception as e:
            return ToolResult.error(f"Failed to read file: {e}")


class WriteFileTool(BaseFilesystemTool):
    """Tool for writing file contents"""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file. Creates the file if it doesn't exist, overwrites if it does."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str, **kwargs: Any) -> ToolResult:
        try:
            resolved = self._resolve_path(path)

            # Create parent directories
            resolved.parent.mkdir(parents=True, exist_ok=True)

            resolved.write_text(content)

            return ToolResult.success(f"Successfully wrote {len(content)} bytes to {path}")

        except PermissionError as e:
            return ToolResult.error(str(e))
        except Exception as e:
            return ToolResult.error(f"Failed to write file: {e}")


class EditFileTool(BaseFilesystemTool):
    """Tool for editing files with search/replace"""

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Edit a file by replacing old_string with new_string. "
            "The old_string must match exactly (including whitespace)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact string to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The string to replace it with",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default: false, replaces first only)",
                    "default": False,
                },
            },
            "required": ["path", "old_string", "new_string"],
        }

    async def execute(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            resolved = self._resolve_path(path)

            if not resolved.exists():
                return ToolResult.error(f"File not found: {path}")

            content = resolved.read_text()

            if old_string not in content:
                return ToolResult.error(
                    f"String not found in file. Make sure the old_string matches exactly."
                )

            # Count occurrences
            count = content.count(old_string)

            if replace_all:
                new_content = content.replace(old_string, new_string)
                replaced_count = count
            else:
                new_content = content.replace(old_string, new_string, 1)
                replaced_count = 1

            resolved.write_text(new_content)

            return ToolResult.success(
                f"Replaced {replaced_count} occurrence(s) in {path}"
            )

        except PermissionError as e:
            return ToolResult.error(str(e))
        except Exception as e:
            return ToolResult.error(f"Failed to edit file: {e}")


class ListDirTool(BaseFilesystemTool):
    """Tool for listing directory contents"""

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "List the contents of a directory."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the directory to list",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "List recursively (default: false)",
                    "default": False,
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum depth for recursive listing",
                    "default": 3,
                },
            },
            "required": ["path"],
        }

    async def execute(
        self,
        path: str,
        recursive: bool = False,
        max_depth: int = 3,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            resolved = self._resolve_path(path)

            if not resolved.exists():
                return ToolResult.error(f"Directory not found: {path}")

            if not resolved.is_dir():
                return ToolResult.error(f"Not a directory: {path}")

            entries = []

            if recursive:
                self._list_recursive(resolved, entries, 0, max_depth, resolved)
            else:
                for entry in sorted(resolved.iterdir()):
                    suffix = "/" if entry.is_dir() else ""
                    entries.append(f"{entry.name}{suffix}")

            if not entries:
                return ToolResult.success("(empty directory)")

            return ToolResult.success("\n".join(entries))

        except PermissionError as e:
            return ToolResult.error(str(e))
        except Exception as e:
            return ToolResult.error(f"Failed to list directory: {e}")

    def _list_recursive(
        self,
        directory: Path,
        entries: list[str],
        depth: int,
        max_depth: int,
        base: Path,
    ) -> None:
        """Recursively list directory contents"""
        if depth >= max_depth:
            return

        try:
            for entry in sorted(directory.iterdir()):
                relative = entry.relative_to(base)
                indent = "  " * depth

                if entry.is_dir():
                    entries.append(f"{indent}{relative}/")
                    self._list_recursive(entry, entries, depth + 1, max_depth, base)
                else:
                    entries.append(f"{indent}{relative}")
        except PermissionError:
            entries.append(f"{'  ' * depth}(permission denied)")


class AppendFileTool(BaseFilesystemTool):
    """Tool for appending to files"""

    @property
    def name(self) -> str:
        return "append_file"

    @property
    def description(self) -> str:
        return "Append content to the end of a file. Creates the file if it doesn't exist."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to append to",
                },
                "content": {
                    "type": "string",
                    "description": "Content to append to the file",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str, **kwargs: Any) -> ToolResult:
        try:
            resolved = self._resolve_path(path)

            # Create parent directories
            resolved.parent.mkdir(parents=True, exist_ok=True)

            with open(resolved, "a") as f:
                f.write(content)

            return ToolResult.success(f"Appended {len(content)} bytes to {path}")

        except PermissionError as e:
            return ToolResult.error(str(e))
        except Exception as e:
            return ToolResult.error(f"Failed to append to file: {e}")
