"""Display rendering helpers for Whisplay LCD"""

import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

# Default dimensions
LCD_WIDTH = 240
LCD_HEIGHT = 280


def rgb_to_rgb565(r: int, g: int, b: int) -> int:
    """Convert RGB888 to RGB565"""
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def rgb565_to_bytes(color: int) -> bytes:
    """Convert RGB565 color to 2 bytes (big-endian)"""
    return bytes([(color >> 8) & 0xFF, color & 0xFF])


class DisplayRenderer:
    """Renders content to Whisplay LCD display"""

    # Default font paths to try
    FONT_PATHS = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",  # macOS
    ]

    def __init__(
        self,
        width: int = LCD_WIDTH,
        height: int = LCD_HEIGHT,
        font_path: str | None = None,
    ):
        self.width = width
        self.height = height
        self._font_path = font_path
        self._pil_available = False

        # Try to import PIL
        try:
            from PIL import Image, ImageDraw, ImageFont
            self._pil_available = True
            self._Image = Image
            self._ImageDraw = ImageDraw
            self._ImageFont = ImageFont
        except ImportError:
            logger.warning("PIL not available, display rendering will be limited")

    def _get_font(self, size: int):
        """Get a font at the specified size"""
        if not self._pil_available:
            return None

        # Try custom font path first
        if self._font_path:
            try:
                return self._ImageFont.truetype(self._font_path, size)
            except Exception:
                pass

        # Try default font paths
        for path in self.FONT_PATHS:
            try:
                if Path(path).exists():
                    return self._ImageFont.truetype(path, size)
            except Exception:
                continue

        # Fall back to default font
        try:
            return self._ImageFont.load_default()
        except Exception:
            return None

    def render_text(
        self,
        text: str,
        subtext: str = "",
        bg_color: Tuple[int, int, int] = (0, 0, 0),
        text_color: Tuple[int, int, int] = (255, 255, 255),
        font_size: int = 24,
        subtext_size: int = 16,
    ) -> bytes:
        """
        Render text to RGB565 pixel data.

        Args:
            text: Main text to display
            subtext: Optional smaller text below main text
            bg_color: Background color (R, G, B)
            text_color: Text color (R, G, B)
            font_size: Main text font size
            subtext_size: Subtext font size

        Returns:
            RGB565 pixel data as bytes
        """
        if not self._pil_available:
            # Return solid color if PIL not available
            return self._solid_color_pixels(rgb_to_rgb565(*bg_color))

        # Create image
        img = self._Image.new("RGB", (self.width, self.height), bg_color)
        draw = self._ImageDraw.Draw(img)

        # Get fonts
        main_font = self._get_font(font_size)
        sub_font = self._get_font(subtext_size) if subtext else None

        # Calculate text positions (centered)
        if main_font:
            bbox = draw.textbbox((0, 0), text, font=main_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        else:
            tw, th = len(text) * 10, 20

        x = (self.width - tw) // 2
        y = (self.height - th) // 2

        if subtext:
            y -= 15  # Move main text up if there's subtext

        # Draw main text
        draw.text((x, y), text, fill=text_color, font=main_font)

        # Draw subtext
        if subtext and sub_font:
            bbox = draw.textbbox((0, 0), subtext, font=sub_font)
            stw = bbox[2] - bbox[0]
            sx = (self.width - stw) // 2
            sy = y + th + 10
            draw.text((sx, sy), subtext, fill=text_color, font=sub_font)

        return self._image_to_rgb565(img)

    def render_status(
        self,
        status: str,
        icon: str | None = None,
        bg_color: Tuple[int, int, int] = (0, 0, 0),
    ) -> bytes:
        """
        Render a status screen.

        Args:
            status: Status text (e.g., "Listening...", "Thinking...")
            icon: Optional icon character
            bg_color: Background color

        Returns:
            RGB565 pixel data as bytes
        """
        return self.render_text(
            text=status,
            subtext=icon or "",
            bg_color=bg_color,
            text_color=(255, 255, 255),
            font_size=28,
        )

    def render_conversation(
        self,
        user_text: str,
        assistant_text: str,
        bg_color: Tuple[int, int, int] = (20, 20, 30),
    ) -> bytes:
        """
        Render conversation display with user and assistant text.

        Args:
            user_text: User's message
            assistant_text: Assistant's response
            bg_color: Background color

        Returns:
            RGB565 pixel data as bytes
        """
        logger.debug(f"render_conversation: PIL available={self._pil_available}")
        logger.debug(f"render_conversation: user='{user_text[:50]}...', assistant='{assistant_text[:50]}...'")

        if not self._pil_available:
            logger.warning("PIL not available, returning solid color")
            return self._solid_color_pixels(rgb_to_rgb565(*bg_color))

        img = self._Image.new("RGB", (self.width, self.height), bg_color)
        draw = self._ImageDraw.Draw(img)

        font = self._get_font(14)
        small_font = self._get_font(12)

        padding = 10
        y = padding

        # User section
        draw.text((padding, y), "You:", fill=(100, 200, 255), font=small_font)
        y += 18

        # Wrap and draw user text
        user_lines = self._wrap_text(user_text, font, self.width - 2 * padding)
        for line in user_lines[:3]:  # Max 3 lines
            draw.text((padding, y), line, fill=(200, 200, 200), font=font)
            y += 18

        y += 10

        # Assistant section
        draw.text((padding, y), "Assistant:", fill=(100, 255, 100), font=small_font)
        y += 18

        # Wrap and draw assistant text
        remaining_height = self.height - y - padding
        max_lines = remaining_height // 18
        assistant_lines = self._wrap_text(assistant_text, font, self.width - 2 * padding)

        for line in assistant_lines[:max_lines]:
            draw.text((padding, y), line, fill=(255, 255, 255), font=font)
            y += 18

        pixels = self._image_to_rgb565(img)
        logger.debug(f"render_conversation: generated {len(pixels)} bytes")
        return pixels

    def load_image(self, image_path: str | Path) -> bytes:
        """
        Load and convert an image file to RGB565.

        Args:
            image_path: Path to image file

        Returns:
            RGB565 pixel data as bytes
        """
        if not self._pil_available:
            raise RuntimeError("PIL is required for image loading")

        img = self._Image.open(image_path).convert("RGB")

        # Resize to fit screen
        img = self._resize_and_crop(img)

        return self._image_to_rgb565(img)

    def _resize_and_crop(self, img) -> "Image":
        """Resize and center-crop image to screen dimensions"""
        # Calculate aspect ratios
        img_ratio = img.width / img.height
        screen_ratio = self.width / self.height

        if img_ratio > screen_ratio:
            # Image is wider - fit to height
            new_height = self.height
            new_width = int(new_height * img_ratio)
        else:
            # Image is taller - fit to width
            new_width = self.width
            new_height = int(new_width / img_ratio)

        img = img.resize((new_width, new_height), self._Image.Resampling.LANCZOS)

        # Center crop
        left = (new_width - self.width) // 2
        top = (new_height - self.height) // 2
        img = img.crop((left, top, left + self.width, top + self.height))

        return img

    def _image_to_rgb565(self, img) -> list:
        """Convert PIL Image to RGB565 list (for Whisplay driver compatibility)"""
        pixels = []

        for y in range(self.height):
            for x in range(self.width):
                r, g, b = img.getpixel((x, y))
                rgb565 = rgb_to_rgb565(r, g, b)
                pixels.extend([(rgb565 >> 8) & 0xFF, rgb565 & 0xFF])

        return pixels

    def _solid_color_pixels(self, color: int) -> list:
        """Generate solid color pixel data"""
        high = (color >> 8) & 0xFF
        low = color & 0xFF
        return [high, low] * (self.width * self.height)

    def _wrap_text(self, text: str, font, max_width: int) -> list[str]:
        """Wrap text to fit within max_width"""
        if not self._pil_available or not font:
            # Simple character-based wrapping
            chars_per_line = max_width // 8
            words = text.split()
            lines = []
            current = ""
            for word in words:
                if len(current) + len(word) + 1 <= chars_per_line:
                    current = f"{current} {word}" if current else word
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
            return lines

        # PIL-based wrapping
        img = self._Image.new("RGB", (1, 1))
        draw = self._ImageDraw.Draw(img)

        words = text.split()
        lines = []
        current = ""

        for word in words:
            test = f"{current} {word}" if current else word
            bbox = draw.textbbox((0, 0), test, font=font)
            width = bbox[2] - bbox[0]

            if width <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word

        if current:
            lines.append(current)

        return lines
