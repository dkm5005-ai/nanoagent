"""Main application entry point for NanoAgent"""

import argparse
import asyncio
import logging
import signal
import sys
import tempfile
import threading
from enum import Enum
from pathlib import Path
from typing import Callable

from .agent.loop import create_agent
from .config.config import Config, load_config
from .hardware.display import DisplayRenderer
from .hardware.whisplay import MockWhisplayDevice, WhisplayDevice
from .voice.synthesizer import Synthesizer
from .voice.transcriber import Transcriber

logger = logging.getLogger(__name__)


class State(Enum):
    """Voice assistant states"""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    THINKING = "thinking"
    SPEAKING = "speaking"


class VoiceAssistant:
    """Voice-enabled assistant with Whisplay HAT integration"""

    def __init__(
        self,
        config: Config,
        driver_path: str | Path | None = None,
        hardware_enabled: bool = True,
    ):
        self.config = config
        self.state = State.IDLE
        self._lock = threading.Lock()
        self._running = False

        # Initialize hardware
        if hardware_enabled and config.hardware.enabled:
            # Use driver_path from args, then config, then auto-detect
            effective_driver_path = driver_path or config.hardware.driver_path
            self.device = WhisplayDevice(
                driver_path=effective_driver_path,
                audio_card=config.hardware.audio_card,
                sample_rate=config.voice.sample_rate,
            )
        else:
            self.device = MockWhisplayDevice()

        self.renderer = DisplayRenderer(
            width=config.hardware.lcd_width,
            height=config.hardware.lcd_height,
        )

        # Initialize voice components (if enabled)
        self.transcriber: Transcriber | None = None
        self.synthesizer: Synthesizer | None = None

        if config.voice.enabled:
            openai_key = config.get_api_key("gpt4") if "gpt4" in [m.name for m in config.models] else ""
            if not openai_key:
                # Try to get from OpenAI provider
                openai_key = config.providers.get("openai", {})
                if hasattr(openai_key, "api_key"):
                    openai_key = openai_key.api_key
                else:
                    openai_key = ""

            if openai_key:
                self.transcriber = Transcriber(
                    api_key=openai_key,
                    model=config.voice.stt_model,
                )

                if config.voice.tts_enabled:
                    self.synthesizer = Synthesizer(
                        api_key=openai_key,
                        model=config.voice.tts_model,
                        voice=config.voice.tts_voice,
                        output_dir=Path(tempfile.gettempdir()) / "nanoagent",
                    )

        # Initialize agent
        self.agent = create_agent(config)

        # Recording state
        self._recording_path = Path(tempfile.gettempdir()) / "nanoagent" / "recording.wav"
        self._response_text = ""

        # Setup button callbacks
        self.device.on_button_press(self._on_button_press)
        self.device.on_button_release(self._on_button_release)

    def _set_state(self, new_state: State, update_display: bool = True) -> None:
        """Update state with LED and display feedback"""
        with self._lock:
            self.state = new_state

        hw = self.config.hardware

        if new_state == State.IDLE:
            self.device.led_breathing(*hw.led_idle_color)
            if update_display:
                pixels = self.renderer.render_status("Ready", bg_color=(20, 20, 40))
                self.device.draw_image(0, 0, 240, 280, pixels)

        elif new_state == State.LISTENING:
            self.device.set_led(*hw.led_listening_color)
            pixels = self.renderer.render_status("Listening...", bg_color=(40, 20, 20))
            self.device.draw_image(0, 0, 240, 280, pixels)

        elif new_state == State.PROCESSING:
            self.device.led_blink(*hw.led_thinking_color)
            pixels = self.renderer.render_status("Processing...", bg_color=(40, 40, 20))
            self.device.draw_image(0, 0, 240, 280, pixels)

        elif new_state == State.THINKING:
            self.device.led_blink(*hw.led_thinking_color)
            pixels = self.renderer.render_status("Thinking...", bg_color=(40, 40, 20))
            self.device.draw_image(0, 0, 240, 280, pixels)

        elif new_state == State.SPEAKING:
            self.device.set_led(*hw.led_speaking_color)
            # Display will be updated with response text

    def _on_button_press(self) -> None:
        """Handle button press - start recording"""
        with self._lock:
            if self.state != State.IDLE:
                return

        self._set_state(State.LISTENING)
        self.device.start_recording(self._recording_path)

    def _on_button_release(self) -> None:
        """Handle button release - stop recording and process"""
        with self._lock:
            if self.state != State.LISTENING:
                return

        self.device.stop_recording()
        self._set_state(State.PROCESSING)

        # Process in background thread
        threading.Thread(target=self._process_recording, daemon=True).start()

    def _process_recording(self) -> None:
        """Process recorded audio and generate response"""
        try:
            # Run async processing
            asyncio.run(self._async_process())
        except Exception as e:
            logger.error(f"Processing error: {e}")
            self._set_state(State.IDLE)

    async def _async_process(self) -> None:
        """Async processing of recording"""
        try:
            # Transcribe
            if self.transcriber and self._recording_path.exists():
                user_text = await self.transcriber.transcribe(self._recording_path)
                logger.info(f"User said: {user_text}")

                if not user_text.strip():
                    self._set_state(State.IDLE)
                    return

                # Think
                self._set_state(State.THINKING)

                # Get response from agent
                response = await self.agent.chat(user_text)
                self._response_text = response
                logger.info(f"Assistant: {response[:100]}...")

                # Speak response
                self._set_state(State.SPEAKING)

                # Update display with response
                logger.debug("Rendering conversation to display")
                pixels = self.renderer.render_conversation(user_text, response)
                logger.debug(f"Drawing {len(pixels)} bytes to display")
                self.device.draw_image(0, 0, 240, 280, pixels)

                # Synthesize and play audio
                if self.synthesizer:
                    audio_path = await self.synthesizer.synthesize(response, output_format="wav")
                    self.device.play_audio(audio_path, blocking=True)

            # Return to IDLE but keep conversation on screen
            self._set_state(State.IDLE, update_display=False)

        except Exception as e:
            logger.error(f"Async processing error: {e}")
            self._set_state(State.IDLE)

    def run(self) -> None:
        """Run the voice assistant main loop"""
        self._running = True

        # Setup mixer
        self.device.setup_mixer()

        # Set backlight brightness
        self.device.set_backlight(self.config.hardware.backlight_brightness)

        # Set initial state
        self._set_state(State.IDLE)

        logger.info("Voice assistant started. Press button to speak.")

        try:
            while self._running:
                asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.1))
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Clean shutdown"""
        self._running = False
        self.device.cleanup()
        logger.info("Voice assistant stopped.")


async def text_mode(config: Config, query: str | None = None) -> None:
    """Run in text-only mode (no hardware)"""
    agent = create_agent(config)

    if query:
        # One-shot query
        response = await agent.chat(query)
        print(response)
        return

    # Interactive mode
    print("NanoAgent - Text Mode")
    print("Type 'quit' or 'exit' to stop.\n")

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                break

            response = await agent.chat(user_input)
            print(f"\nAssistant: {response}\n")

        except KeyboardInterrupt:
            break
        except EOFError:
            break

    print("Goodbye!")


def main() -> None:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="NanoAgent - Lightweight AI Assistant"
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--text-only", "-t",
        action="store_true",
        help="Run in text-only mode (no hardware)",
    )
    parser.add_argument(
        "--query", "-q",
        help="One-shot query (exits after response)",
    )
    parser.add_argument(
        "--model", "-m",
        help="Model to use (overrides config default)",
    )
    parser.add_argument(
        "--driver-path", "-d",
        help="Path to Whisplay driver directory (only needed if not installed system-wide)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Suppress noisy asyncio event loop cleanup errors
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)

    # Load config
    try:
        config = load_config(args.config)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    # Override model if specified
    if args.model:
        config.default_model = args.model

    # Ensure workspace exists
    config.ensure_workspace()

    # Run in appropriate mode
    if args.text_only or args.query:
        asyncio.run(text_mode(config, args.query))
    else:
        # Voice mode with hardware
        assistant = VoiceAssistant(
            config=config,
            driver_path=args.driver_path,
            hardware_enabled=True,
        )

        # Handle signals
        def signal_handler(sig, frame):
            assistant.shutdown()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        assistant.run()


if __name__ == "__main__":
    main()
