"""Text-to-speech synthesis using OpenAI TTS API"""

import logging
import tempfile
import uuid
from pathlib import Path

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class Synthesizer:
    """Synthesizes speech from text using OpenAI TTS API"""

    # Available voices
    VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}

    # Available models
    MODELS = {"tts-1", "tts-1-hd"}

    # Output formats
    FORMATS = {"mp3", "opus", "aac", "flac", "wav", "pcm"}

    def __init__(
        self,
        api_key: str,
        model: str = "tts-1",
        voice: str = "alloy",
        output_dir: str | Path | None = None,
    ):
        """
        Initialize the synthesizer.

        Args:
            api_key: OpenAI API key
            model: TTS model (tts-1 or tts-1-hd)
            voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer)
            output_dir: Directory to save audio files (default: temp dir)
        """
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.voice = voice
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.gettempdir())

        # Validate
        if voice not in self.VOICES:
            raise ValueError(f"Invalid voice: {voice}. Available: {', '.join(self.VOICES)}")

        if model not in self.MODELS:
            raise ValueError(f"Invalid model: {model}. Available: {', '.join(self.MODELS)}")

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        output_format: str = "mp3",
        speed: float = 1.0,
    ) -> Path:
        """
        Synthesize text to speech.

        Args:
            text: Text to synthesize
            voice: Voice override (uses default if not specified)
            output_format: Audio format (mp3, opus, aac, flac, wav, pcm)
            speed: Speech speed (0.25 to 4.0)

        Returns:
            Path to the generated audio file
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")

        voice = voice or self.voice
        if voice not in self.VOICES:
            raise ValueError(f"Invalid voice: {voice}")

        if output_format not in self.FORMATS:
            raise ValueError(f"Invalid format: {output_format}")

        if not 0.25 <= speed <= 4.0:
            raise ValueError("Speed must be between 0.25 and 4.0")

        logger.debug(f"Synthesizing text ({len(text)} chars) with voice {voice}")

        # Generate unique filename
        filename = f"tts_{uuid.uuid4().hex[:8]}.{output_format}"
        output_path = self.output_dir / filename

        # Make API request
        response = await self.client.audio.speech.create(
            model=self.model,
            voice=voice,
            input=text,
            response_format=output_format,
            speed=speed,
        )

        # Save to file
        with open(output_path, "wb") as f:
            async for chunk in response.iter_bytes():
                f.write(chunk)

        logger.debug(f"Saved audio to: {output_path}")

        return output_path

    async def synthesize_to_bytes(
        self,
        text: str,
        voice: str | None = None,
        output_format: str = "mp3",
        speed: float = 1.0,
    ) -> bytes:
        """
        Synthesize text to speech and return as bytes.

        Args:
            text: Text to synthesize
            voice: Voice override
            output_format: Audio format
            speed: Speech speed

        Returns:
            Audio data as bytes
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")

        voice = voice or self.voice

        logger.debug(f"Synthesizing to bytes ({len(text)} chars)")

        response = await self.client.audio.speech.create(
            model=self.model,
            voice=voice,
            input=text,
            response_format=output_format,
            speed=speed,
        )

        # Collect all chunks
        chunks = []
        async for chunk in response.iter_bytes():
            chunks.append(chunk)

        return b"".join(chunks)

    def set_voice(self, voice: str) -> None:
        """Change the default voice"""
        if voice not in self.VOICES:
            raise ValueError(f"Invalid voice: {voice}")
        self.voice = voice

    def set_model(self, model: str) -> None:
        """Change the TTS model"""
        if model not in self.MODELS:
            raise ValueError(f"Invalid model: {model}")
        self.model = model
