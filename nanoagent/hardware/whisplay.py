"""Whisplay HAT integration wrapper"""

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class WhisplayDevice:
    """
    High-level wrapper for Whisplay HAT hardware.

    Provides interface for:
    - Button input (press/release callbacks)
    - RGB LED control
    - LCD display
    - Audio recording/playback via WM8960 codec

    Note: The actual WhisPlayBoard driver is imported dynamically
    to allow the module to be imported on non-Pi systems.
    """

    # Screen dimensions
    LCD_WIDTH = 240
    LCD_HEIGHT = 280

    # RGB565 color constants
    COLOR_BLACK = 0x0000
    COLOR_WHITE = 0xFFFF
    COLOR_RED = 0xF800
    COLOR_GREEN = 0x07E0
    COLOR_BLUE = 0x001F
    COLOR_YELLOW = 0xFFE0
    COLOR_CYAN = 0x07FF
    COLOR_MAGENTA = 0xF81F

    def __init__(
        self,
        driver_path: str | Path | None = None,
        audio_card: str = "wm8960soundcard",
        sample_rate: int = 48000,
    ):
        """
        Initialize Whisplay device.

        Args:
            driver_path: Path to Whisplay driver directory
            audio_card: ALSA sound card name
            sample_rate: Audio sample rate (48000 for Radxa, 44100 for Pi)
        """
        self.audio_card = audio_card
        self.sample_rate = sample_rate
        self._card_index: int | None = None

        self._board = None
        self._available = False
        self._record_proc: subprocess.Popen | None = None
        self._play_proc: subprocess.Popen | None = None

        # LED animation state
        self._led_thread: threading.Thread | None = None
        self._led_running = False

        # Try to import and initialize the board
        self._init_board(driver_path)

    # Common locations to search for WhisPlay driver
    DRIVER_SEARCH_PATHS = [
        # User-specified or relative to nanoagent
        "~/Whisplay/Driver",
        "~/whisplay/Driver",
        "/opt/Whisplay/Driver",
        "/opt/whisplay/Driver",
        # Relative to home
        "~/pisugar/Whisplay/Driver",
        # System-wide
        "/usr/local/lib/whisplay",
        "/usr/share/whisplay",
        # Development paths
        "../Whisplay/Driver",
        "../../Whisplay/Driver",
    ]

    def _init_board(self, driver_path: str | Path | None) -> None:
        """Initialize the WhisPlayBoard"""
        # First, try direct import (if installed as package)
        try:
            from WhisPlay import WhisPlayBoard
            self._board = WhisPlayBoard()
            self._available = True
            logger.info("Whisplay HAT initialized (driver already in path)")
            return
        except ImportError:
            pass  # Not installed as package, search for it
        except Exception as e:
            logger.warning(f"Failed to initialize Whisplay HAT: {e}")
            self._available = False
            return

        # Build list of paths to search
        search_paths = []

        # User-specified path first
        if driver_path:
            search_paths.append(Path(driver_path).expanduser().resolve())

        # Environment variable
        env_path = os.environ.get("WHISPLAY_DRIVER_PATH")
        if env_path:
            search_paths.append(Path(env_path).expanduser().resolve())

        # Common locations
        for p in self.DRIVER_SEARCH_PATHS:
            search_paths.append(Path(p).expanduser().resolve())

        # Search for driver
        for path in search_paths:
            if path.exists() and (path / "WhisPlay.py").exists():
                if str(path) not in sys.path:
                    sys.path.insert(0, str(path))
                    logger.debug(f"Added {path} to sys.path")

                try:
                    from WhisPlay import WhisPlayBoard
                    self._board = WhisPlayBoard()
                    self._available = True
                    logger.info(f"Whisplay HAT initialized (driver found at {path})")
                    return
                except Exception as e:
                    logger.warning(f"Failed to initialize from {path}: {e}")
                    continue

        logger.warning(
            "Whisplay driver not found. Searched: " +
            ", ".join(str(p) for p in search_paths[:5]) +
            "... Set WHISPLAY_DRIVER_PATH or use --driver-path"
        )
        self._available = False

    @property
    def available(self) -> bool:
        """Check if hardware is available"""
        return self._available

    # ==================== Button ====================

    def on_button_press(self, callback: Callable[[], None]) -> None:
        """Register callback for button press"""
        if self._board:
            self._board.on_button_press(callback)

    def on_button_release(self, callback: Callable[[], None]) -> None:
        """Register callback for button release"""
        if self._board:
            self._board.on_button_release(callback)

    def button_pressed(self) -> bool:
        """Check if button is currently pressed"""
        if self._board:
            return self._board.button_pressed()
        return False

    # ==================== LED ====================

    def set_led(self, r: int, g: int, b: int) -> None:
        """Set RGB LED color (0-255 each)"""
        self._stop_led_animation()
        if self._board:
            self._board.set_rgb(r, g, b)

    def led_off(self) -> None:
        """Turn off LED"""
        self.set_led(0, 0, 0)

    def led_breathing(self, r: int, g: int, b: int) -> None:
        """Start breathing LED animation"""
        self._stop_led_animation()
        self._led_running = True
        self._led_thread = threading.Thread(
            target=self._led_breath_loop,
            args=(r, g, b),
            daemon=True,
        )
        self._led_thread.start()

    def led_blink(self, r: int, g: int, b: int, interval: float = 0.4) -> None:
        """Start blinking LED animation"""
        self._stop_led_animation()
        self._led_running = True
        self._led_thread = threading.Thread(
            target=self._led_blink_loop,
            args=(r, g, b, interval),
            daemon=True,
        )
        self._led_thread.start()

    def _stop_led_animation(self) -> None:
        """Stop any running LED animation"""
        self._led_running = False
        if self._led_thread and self._led_thread.is_alive():
            self._led_thread.join(timeout=1.0)
        self._led_thread = None

    def _led_breath_loop(self, r: int, g: int, b: int) -> None:
        """Breathing LED animation loop"""
        while self._led_running and self._board:
            # Fade in
            for i in range(0, 101, 5):
                if not self._led_running:
                    return
                f = i / 100.0
                self._board.set_rgb(int(r * f), int(g * f), int(b * f))
                time.sleep(0.03)
            # Fade out
            for i in range(100, -1, -5):
                if not self._led_running:
                    return
                f = i / 100.0
                self._board.set_rgb(int(r * f), int(g * f), int(b * f))
                time.sleep(0.03)

    def _led_blink_loop(self, r: int, g: int, b: int, interval: float) -> None:
        """Blinking LED animation loop"""
        while self._led_running and self._board:
            self._board.set_rgb(r, g, b)
            time.sleep(interval)
            if not self._led_running:
                return
            self._board.set_rgb(0, 0, 0)
            time.sleep(interval)

    # ==================== Display ====================

    def fill_screen(self, color: int) -> None:
        """Fill screen with solid color (RGB565)"""
        if self._board:
            self._board.fill_screen(color)

    def draw_image(self, x: int, y: int, width: int, height: int, pixels: bytes | list) -> None:
        """Draw image at position (pixels in RGB565 format)"""
        if self._board:
            self._board.draw_image(x, y, width, height, pixels)

    def set_backlight(self, brightness: int) -> None:
        """Set backlight brightness (0-100, 0=bright, 100=off for PWM)"""
        if self._board:
            self._board.set_backlight(brightness)

    # ==================== Audio ====================

    def _find_card_index(self) -> int:
        """Find WM8960 sound card index"""
        if self._card_index is not None:
            return self._card_index

        try:
            with open("/proc/asound/cards") as f:
                for line in f:
                    if "wm8960" in line.lower():
                        self._card_index = int(line.strip().split()[0])
                        return self._card_index
        except Exception:
            pass

        self._card_index = 1  # Default fallback
        return self._card_index

    def setup_mixer(self) -> None:
        """Configure ALSA mixer for optimal recording/playback"""
        card = str(self._find_card_index())

        commands = [
            # Output routing
            ["amixer", "-c", card, "sset", "Left Output Mixer PCM", "on"],
            ["amixer", "-c", card, "sset", "Right Output Mixer PCM", "on"],
            ["amixer", "-c", card, "sset", "Speaker", "121"],
            ["amixer", "-c", card, "sset", "Playback", "230"],
            # Input routing
            ["amixer", "-c", card, "sset", "Left Input Mixer Boost", "on"],
            ["amixer", "-c", card, "sset", "Right Input Mixer Boost", "on"],
            ["amixer", "-c", card, "sset", "Capture", "45"],
            # Mic gain
            ["amixer", "-c", card, "sset", "Left Input Boost Mixer LINPUT1", "2"],
            ["amixer", "-c", card, "sset", "Right Input Boost Mixer RINPUT1", "2"],
        ]

        for cmd in commands:
            try:
                subprocess.run(cmd, capture_output=True, timeout=5)
            except Exception as e:
                logger.debug(f"Mixer command failed: {e}")

    def start_recording(self, output_path: str | Path) -> None:
        """Start recording audio to file"""
        if self._record_proc:
            self.stop_recording()

        card_index = self._find_card_index()
        hw_device = f"hw:{card_index},0"

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self._record_proc = subprocess.Popen(
            [
                "arecord",
                "-D", hw_device,
                "-f", "S16_LE",
                "-r", str(self.sample_rate),
                "-c", "2",
                "-t", "wav",
                str(output_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logger.debug(f"Started recording to {output_path}")

    def stop_recording(self) -> None:
        """Stop recording"""
        if self._record_proc:
            self._record_proc.terminate()
            try:
                self._record_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._record_proc.kill()
            self._record_proc = None
            logger.debug("Stopped recording")

    def play_audio(self, audio_path: str | Path, blocking: bool = True) -> None:
        """Play audio file through speaker"""
        if self._play_proc:
            self.stop_playback()

        card_index = self._find_card_index()
        # Use plughw for automatic format conversion (sample rate, channels)
        hw_device = f"plughw:{card_index},0"

        self._play_proc = subprocess.Popen(
            ["aplay", "-D", hw_device, str(audio_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if blocking:
            self._play_proc.wait()
            self._play_proc = None
        else:
            logger.debug(f"Started playing {audio_path}")

    def stop_playback(self) -> None:
        """Stop audio playback"""
        if self._play_proc:
            self._play_proc.terminate()
            try:
                self._play_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._play_proc.kill()
            self._play_proc = None
            logger.debug("Stopped playback")

    def is_playing(self) -> bool:
        """Check if audio is currently playing"""
        if self._play_proc:
            return self._play_proc.poll() is None
        return False

    # ==================== Cleanup ====================

    def cleanup(self) -> None:
        """Clean up resources"""
        self._stop_led_animation()
        self.stop_recording()
        self.stop_playback()
        self.led_off()

        if self._board:
            try:
                self._board.cleanup()
            except Exception:
                pass


class MockWhisplayDevice:
    """Mock device for testing without hardware"""

    LCD_WIDTH = 240
    LCD_HEIGHT = 280

    def __init__(self, *args, **kwargs):
        self._button_press_cb = None
        self._button_release_cb = None
        logger.info("Using mock Whisplay device")

    @property
    def available(self) -> bool:
        return False

    def on_button_press(self, callback: Callable[[], None]) -> None:
        self._button_press_cb = callback

    def on_button_release(self, callback: Callable[[], None]) -> None:
        self._button_release_cb = callback

    def button_pressed(self) -> bool:
        return False

    def set_led(self, r: int, g: int, b: int) -> None:
        logger.debug(f"LED: RGB({r}, {g}, {b})")

    def led_off(self) -> None:
        logger.debug("LED: off")

    def led_breathing(self, r: int, g: int, b: int) -> None:
        logger.debug(f"LED breathing: RGB({r}, {g}, {b})")

    def led_blink(self, r: int, g: int, b: int, interval: float = 0.4) -> None:
        logger.debug(f"LED blink: RGB({r}, {g}, {b})")

    def fill_screen(self, color: int) -> None:
        logger.debug(f"Screen fill: 0x{color:04X}")

    def draw_image(self, x: int, y: int, width: int, height: int, pixels: bytes | list) -> None:
        logger.debug(f"Draw image: {x},{y} {width}x{height}")

    def set_backlight(self, brightness: int) -> None:
        logger.debug(f"Backlight: {brightness}")

    def setup_mixer(self) -> None:
        logger.debug("Mixer setup (mock)")

    def start_recording(self, output_path: str | Path) -> None:
        logger.debug(f"Start recording: {output_path}")

    def stop_recording(self) -> None:
        logger.debug("Stop recording")

    def play_audio(self, audio_path: str | Path, blocking: bool = True) -> None:
        logger.debug(f"Play audio: {audio_path}")

    def stop_playback(self) -> None:
        logger.debug("Stop playback")

    def is_playing(self) -> bool:
        return False

    def cleanup(self) -> None:
        logger.debug("Cleanup (mock)")

    # For testing - simulate button press
    def simulate_button_press(self) -> None:
        if self._button_press_cb:
            self._button_press_cb()

    def simulate_button_release(self) -> None:
        if self._button_release_cb:
            self._button_release_cb()
