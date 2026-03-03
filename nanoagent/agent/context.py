"""Context builder for system prompts"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any


class ContextBuilder:
    """Builds system prompts from workspace files and runtime context"""

    # Files to include in system prompt (in order)
    CONTEXT_FILES = [
        "IDENTITY.md",
        "USER.md",
        "TOOLS.md",
    ]

    # Memory file for persistent facts
    MEMORY_FILE = "memory/MEMORY.md"

    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace).expanduser().resolve()
        self._cache: dict[str, tuple[float, str]] = {}  # path -> (mtime, content)

    def build(self, tools_summary: str | None = None) -> str:
        """Build the complete system prompt"""
        parts = []

        # Add identity and context files
        for filename in self.CONTEXT_FILES:
            content = self._load_file(filename)
            if content:
                parts.append(content)

        # Add memory
        memory = self._load_file(self.MEMORY_FILE)
        if memory:
            parts.append(f"## Memory\n\n{memory}")

        # Add tools summary
        if tools_summary:
            parts.append(f"## Available Tools\n\n{tools_summary}")

        # Add runtime context
        parts.append(self._build_runtime_context())

        return "\n\n---\n\n".join(parts)

    def _load_file(self, filename: str) -> str | None:
        """Load a file from workspace with caching"""
        file_path = self.workspace / filename

        if not file_path.exists():
            return None

        # Check cache
        mtime = file_path.stat().st_mtime
        if filename in self._cache:
            cached_mtime, cached_content = self._cache[filename]
            if cached_mtime == mtime:
                return cached_content

        # Load and cache
        try:
            content = file_path.read_text().strip()
            self._cache[filename] = (mtime, content)
            return content
        except Exception:
            return None

    def _build_runtime_context(self) -> str:
        """Build runtime context (time, system info, etc.)"""
        now = datetime.now()

        lines = [
            "## Runtime Context",
            "",
            f"- Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- Timezone: {now.astimezone().tzname()}",
            f"- Workspace: {self.workspace}",
        ]

        # Add platform info if available
        try:
            import platform
            lines.append(f"- Platform: {platform.system()} {platform.release()}")
            lines.append(f"- Python: {platform.python_version()}")
        except Exception:
            pass

        return "\n".join(lines)

    def invalidate_cache(self) -> None:
        """Clear the file cache"""
        self._cache.clear()

    def get_tools_summary(self, tool_names: list[str]) -> str:
        """Generate a summary of available tools"""
        if not tool_names:
            return "No tools available."

        return "You have access to the following tools:\n- " + "\n- ".join(sorted(tool_names))


def create_default_workspace_files(workspace: Path) -> None:
    """Create default workspace files if they don't exist"""
    workspace = Path(workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "sessions").mkdir(exist_ok=True)
    (workspace / "memory").mkdir(exist_ok=True)

    # IDENTITY.md
    identity_file = workspace / "IDENTITY.md"
    if not identity_file.exists():
        identity_file.write_text("""# NanoAgent

You are NanoAgent, a voice assistant on a tiny Raspberry Pi with a small LCD screen.

## CRITICAL: Response Length

- Keep ALL responses to 1-2 sentences maximum
- You speak responses aloud - long responses are tedious to listen to
- The LCD screen is only 240x280 pixels - text must be brief
- Never use bullet points, lists, or multiple paragraphs
- Get straight to the point

## Capabilities

- Read, write, edit files
- Execute shell commands
- Search web and fetch pages

## Guidelines

- Be direct and concise - no filler words
- One short answer, then stop
- If you don't know, say "I don't know" and stop
""")

    # USER.md
    user_file = workspace / "USER.md"
    if not user_file.exists():
        user_file.write_text("""# User Preferences

- Responses must be extremely brief (1-2 sentences max)
- No explanations unless explicitly asked
- Just answer the question directly
""")

    # MEMORY.md
    memory_file = workspace / "memory" / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text("""# Memory

This file stores persistent facts and information.

(Add important facts to remember here)
""")
