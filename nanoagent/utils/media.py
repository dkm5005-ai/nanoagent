"""Media handling utilities"""

import os
import tempfile
import uuid
from pathlib import Path


# Supported audio formats
AUDIO_FORMATS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg", ".flac"}


def is_audio_file(path: str | Path) -> bool:
    """Check if a file is an audio file based on extension"""
    return Path(path).suffix.lower() in AUDIO_FORMATS


def get_temp_audio_path(extension: str = ".wav") -> Path:
    """Get a temporary file path for audio"""
    if not extension.startswith("."):
        extension = f".{extension}"

    temp_dir = Path(tempfile.gettempdir()) / "nanoagent"
    temp_dir.mkdir(parents=True, exist_ok=True)

    filename = f"audio_{uuid.uuid4().hex[:8]}{extension}"
    return temp_dir / filename


def save_audio(data: bytes, path: str | Path | None = None, extension: str = ".wav") -> Path:
    """Save audio data to a file"""
    if path is None:
        path = get_temp_audio_path(extension)
    else:
        path = Path(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def load_audio(path: str | Path) -> bytes:
    """Load audio data from a file"""
    return Path(path).read_bytes()


def cleanup_temp_audio() -> None:
    """Clean up temporary audio files"""
    temp_dir = Path(tempfile.gettempdir()) / "nanoagent"
    if temp_dir.exists():
        for f in temp_dir.glob("audio_*"):
            try:
                f.unlink()
            except Exception:
                pass
