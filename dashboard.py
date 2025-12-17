#!/usr/bin/env python3
"""
fb_pillow_min.py  (ultra-basic)

- Reads framebuffer geometry from /dev/fb0 using sysfs:
    /sys/class/graphics/fb0/virtual_size
    /sys/class/graphics/fb0/bits_per_pixel
    /sys/class/graphics/fb0/stride
  (If stride is missing, falls back to xres * (bpp/8).)

- Renders a Pillow image (RGB) and blits to /dev/fb0.
- Supports only 16bpp RGB565 (most common). If your fb is 32bpp, it will tell you.

- Provides draw_box_text(text, ...) that draws a colored rectangle + text.

This is intentionally minimal and avoids ioctl/mmap edge cases: it uses a simple write().
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Tuple
from PIL import Image

from artist import *
from fb_driver import *
from colors import *

DISP_RES = 800, 480
FPS_CAP = 20


class FrameRateLimiter:
    def __init__(self, target_fps: int = 30):
        self.target_fps = target_fps
        self.frame_time = 1.0 / target_fps
        self.last_frame = time.perf_counter()

    def wait(self) -> None:
        """Sleep to maintain target framerate."""
        elapsed = time.perf_counter() - self.last_frame
        sleep_time = self.frame_time - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)
        self.last_frame = time.perf_counter()


class Dashboard:
    """Handles framebuffer drawing with a cached background."""

    def __init__(self, bg_color: Tuple[int, int, int] = (0, 0, 0), font_path: Path | None = None) -> None:
        # Hardcoded target hardware resolution
        self.xres, self.yres = DISP_RES

        self.font_path = font_path or DEFAULT_FONT
        self.background = self.create_background(bg_color)

    def create_background(self, bg_color: Tuple[int, int, int]) -> Image.Image:
        """Create a base background layer once."""
        return Image.new("RGB", (self.xres, self.yres), bg_color)


if __name__ == "__main__":
    hide_cursor()
    limiter = FrameRateLimiter(FPS_CAP)
    dashboard = Dashboard(bg_color=BLACK)
    heartbeat = 0
    try:
        while True:
            frame = dashboard.background.copy()

            simple_gauge(
                frame,
                label_str="COUNTER",
                data_str=str(heartbeat),
                box_xywh=(300, 100, 200, 150),
                box_color=DARK_GRAY,
                text_color=WHITE,
                label_font_path=DEFAULT_FONT,
                label_font_size=24,
                data_font_path=DEFAULT_FONT,
                data_font_size=96
            )

            blit(frame)

            heartbeat = (heartbeat + 1) % 100
            limiter.wait()
    finally:
        show_cursor()  # Restore cursor on exit
