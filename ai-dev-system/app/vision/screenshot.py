from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageGrab


class ScreenshotService:
    """Capture screenshots for evidence and visual fallback."""

    def capture(self, path: Path, region: tuple[int, int, int, int] | None = None) -> Path:
        image = ImageGrab.grab(bbox=region)
        image.save(path)
        return path

    def capture_image(self, region: tuple[int, int, int, int] | None = None) -> Image.Image:
        return ImageGrab.grab(bbox=region)
