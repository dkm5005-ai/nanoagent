"""Speech-to-text transcription using OpenAI Whisper API"""

import logging
from pathlib import Path

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class Transcriber:
    """Transcribes audio to text using OpenAI Whisper API"""

    # Supported audio formats
    SUPPORTED_FORMATS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}

    def __init__(
        self,
        api_key: str,
        model: str = "whisper-1",
        language: str | None = None,
    ):
        """
        Initialize the transcriber.

        Args:
            api_key: OpenAI API key
            model: Whisper model to use (default: whisper-1)
            language: Optional language code (e.g., "en", "es", "ja")
        """
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.language = language

    async def transcribe(
        self,
        audio_path: str | Path,
        prompt: str | None = None,
    ) -> str:
        """
        Transcribe an audio file to text.

        Args:
            audio_path: Path to the audio file
            prompt: Optional prompt to guide transcription

        Returns:
            Transcribed text
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        suffix = audio_path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported audio format: {suffix}. "
                f"Supported: {', '.join(self.SUPPORTED_FORMATS)}"
            )

        logger.debug(f"Transcribing audio file: {audio_path}")

        with open(audio_path, "rb") as audio_file:
            kwargs = {
                "model": self.model,
                "file": audio_file,
            }

            if self.language:
                kwargs["language"] = self.language

            if prompt:
                kwargs["prompt"] = prompt

            response = await self.client.audio.transcriptions.create(**kwargs)

        text = response.text.strip()
        logger.debug(f"Transcription result: {text[:100]}...")

        return text

    async def transcribe_with_timestamps(
        self,
        audio_path: str | Path,
        prompt: str | None = None,
    ) -> dict:
        """
        Transcribe audio with word-level timestamps.

        Args:
            audio_path: Path to the audio file
            prompt: Optional prompt to guide transcription

        Returns:
            Dictionary with text and segments
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        logger.debug(f"Transcribing with timestamps: {audio_path}")

        with open(audio_path, "rb") as audio_file:
            kwargs = {
                "model": self.model,
                "file": audio_file,
                "response_format": "verbose_json",
                "timestamp_granularities": ["word", "segment"],
            }

            if self.language:
                kwargs["language"] = self.language

            if prompt:
                kwargs["prompt"] = prompt

            response = await self.client.audio.transcriptions.create(**kwargs)

        return {
            "text": response.text,
            "language": getattr(response, "language", None),
            "duration": getattr(response, "duration", None),
            "segments": getattr(response, "segments", []),
            "words": getattr(response, "words", []),
        }
