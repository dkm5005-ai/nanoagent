"""Session management for conversation history"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..providers.base import Message, ToolCall


@dataclass
class SessionMessage:
    """A message in a session with metadata"""
    role: str
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    timestamp: float = field(default_factory=time.time)

    def to_message(self) -> Message:
        """Convert to provider Message"""
        tool_calls = None
        if self.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.get("id", ""),
                    name=tc.get("name", ""),
                    arguments=tc.get("arguments", {}),
                )
                for tc in self.tool_calls
            ]

        return Message(
            role=self.role,
            content=self.content,
            tool_calls=tool_calls,
            tool_call_id=self.tool_call_id,
            name=self.name,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "role": self.role,
            "content": self.content,
            "tool_calls": self.tool_calls,
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionMessage":
        """Create from dictionary"""
        return cls(
            role=data["role"],
            content=data["content"],
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
            name=data.get("name"),
            timestamp=data.get("timestamp", time.time()),
        )

    @classmethod
    def from_message(cls, msg: Message) -> "SessionMessage":
        """Create from provider Message"""
        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                }
                for tc in msg.tool_calls
            ]

        return cls(
            role=msg.role,
            content=msg.content,
            tool_calls=tool_calls,
            tool_call_id=msg.tool_call_id,
            name=msg.name,
        )


@dataclass
class Session:
    """A conversation session"""
    id: str
    messages: list[SessionMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str) -> None:
        """Add a simple text message"""
        self.messages.append(SessionMessage(role=role, content=content))
        self.updated_at = time.time()

    def add_full_message(self, message: Message) -> None:
        """Add a full message with tool calls etc."""
        self.messages.append(SessionMessage.from_message(message))
        self.updated_at = time.time()

    def get_history(self, max_messages: int | None = None) -> list[Message]:
        """Get message history as provider Messages"""
        messages = self.messages
        if max_messages:
            messages = messages[-max_messages:]
        return [m.to_message() for m in messages]

    def truncate(self, keep_last: int) -> None:
        """Keep only the last N messages"""
        if len(self.messages) > keep_last:
            self.messages = self.messages[-keep_last:]
            self.updated_at = time.time()

    def clear(self) -> None:
        """Clear all messages"""
        self.messages = []
        self.updated_at = time.time()

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """Create from dictionary"""
        return cls(
            id=data["id"],
            messages=[SessionMessage.from_dict(m) for m in data.get("messages", [])],
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            metadata=data.get("metadata", {}),
        )


class SessionManager:
    """Manages conversation sessions with persistence"""

    def __init__(self, storage_path: Path | str | None = None):
        self.storage_path = Path(storage_path) if storage_path else None
        self._sessions: dict[str, Session] = {}

        # Create storage directory
        if self.storage_path:
            self.storage_path.mkdir(parents=True, exist_ok=True)

    def get(self, session_id: str) -> Session:
        """Get or create a session"""
        if session_id not in self._sessions:
            # Try to load from disk
            session = self._load(session_id)
            if session:
                self._sessions[session_id] = session
            else:
                self._sessions[session_id] = Session(id=session_id)

        return self._sessions[session_id]

    def save(self, session_id: str) -> None:
        """Save a session to disk"""
        if not self.storage_path:
            return

        session = self._sessions.get(session_id)
        if not session:
            return

        file_path = self.storage_path / f"{session_id}.json"

        # Atomic write
        temp_path = file_path.with_suffix(".tmp")
        with open(temp_path, "w") as f:
            json.dump(session.to_dict(), f, indent=2)
        temp_path.rename(file_path)

    def _load(self, session_id: str) -> Session | None:
        """Load a session from disk"""
        if not self.storage_path:
            return None

        file_path = self.storage_path / f"{session_id}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path) as f:
                data = json.load(f)
            return Session.from_dict(data)
        except Exception:
            return None

    def delete(self, session_id: str) -> None:
        """Delete a session"""
        if session_id in self._sessions:
            del self._sessions[session_id]

        if self.storage_path:
            file_path = self.storage_path / f"{session_id}.json"
            if file_path.exists():
                file_path.unlink()

    def list_sessions(self) -> list[str]:
        """List all session IDs"""
        session_ids = set(self._sessions.keys())

        if self.storage_path:
            for f in self.storage_path.glob("*.json"):
                session_ids.add(f.stem)

        return sorted(session_ids)
