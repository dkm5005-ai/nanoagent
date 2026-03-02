"""Shell execution tool for NanoAgent"""

import asyncio
import os
import shlex
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class ShellTool(Tool):
    """Tool for executing shell commands"""

    # Default dangerous patterns to block
    DEFAULT_DENY_PATTERNS = [
        "rm -rf /",
        "rm -rf /*",
        "rm -rf ~",
        "mkfs",
        "dd if=",
        ":(){:|:&};:",  # Fork bomb
        "chmod -R 777 /",
        "shutdown",
        "reboot",
        "init 0",
        "init 6",
        "> /dev/sd",
        "mv / ",
        "wget | sh",
        "curl | sh",
        "wget | bash",
        "curl | bash",
    ]

    def __init__(
        self,
        workspace: str | None = None,
        restrict: bool = True,
        deny_patterns: list[str] | None = None,
        timeout: int = 120,
    ):
        self.workspace = Path(workspace).expanduser().resolve() if workspace else Path.cwd()
        self.restrict = restrict
        self.deny_patterns = deny_patterns if deny_patterns is not None else self.DEFAULT_DENY_PATTERNS
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command. Use for running programs, scripts, "
            "or system commands. Commands run in the workspace directory."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Timeout in seconds (default: {self.timeout})",
                    "default": self.timeout,
                },
            },
            "required": ["command"],
        }

    def _check_command(self, command: str) -> str | None:
        """Check if command matches any deny patterns. Returns pattern if blocked."""
        command_lower = command.lower()
        for pattern in self.deny_patterns:
            if pattern.lower() in command_lower:
                return pattern
        return None

    async def execute(
        self,
        command: str,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        # Check for dangerous patterns
        blocked = self._check_command(command)
        if blocked:
            return ToolResult.error(
                f"Command blocked: matches dangerous pattern '{blocked}'"
            )

        timeout = timeout or self.timeout

        try:
            # Set working directory
            cwd = str(self.workspace) if self.restrict else None

            # Create subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env={**os.environ, "HOME": str(Path.home())},
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult.error(f"Command timed out after {timeout} seconds")

            # Decode output
            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            # Build result
            output_parts = []

            if stdout_text:
                output_parts.append(stdout_text)

            if stderr_text:
                output_parts.append(f"[stderr]\n{stderr_text}")

            if process.returncode != 0:
                output_parts.append(f"[exit code: {process.returncode}]")

            output = "\n\n".join(output_parts) if output_parts else "(no output)"

            # Truncate if too long
            max_length = 50000
            if len(output) > max_length:
                output = output[:max_length] + f"\n\n[... truncated, {len(output) - max_length} more chars]"

            # Return as error if non-zero exit code
            if process.returncode != 0:
                return ToolResult(content=output, is_error=True)

            return ToolResult.success(output)

        except Exception as e:
            return ToolResult.error(f"Failed to execute command: {e}")
