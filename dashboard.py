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

import os
import sys
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont


FB0 = "/dev/fb0"
SYSFB = Path("/sys/class/graphics/fb0")


def hide_cursor() -> None:
    """Hide the blinking terminal cursor."""
    # Method 1: ANSI escape code
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()
    
    # Method 2: Disable cursor blink via sysfs (requires root)
    try:
        Path("/sys/class/graphics/fbcon/cursor_blink").write_text("0")
    except Exception:
        pass  # Ignore if we don't have permission


def show_cursor() -> None:
    """Show the terminal cursor again."""
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()
    
    try:
        Path("/sys/class/graphics/fbcon/cursor_blink").write_text("1")
    except Exception:
        pass


def _read_text(p: Path) -> str:
    return p.read_text().strip()


def get_fb0_info() -> Tuple[int, int, int, int]:
    """
    Returns (xres, yres, bpp, stride_bytes).
    """
    xres_str, yres_str = _read_text(SYSFB / "virtual_size").split(",")
    xres, yres = int(xres_str), int(yres_str)

    bpp = int(_read_text(SYSFB / "bits_per_pixel"))

    stride_path = SYSFB / "stride"
    if stride_path.exists():
        stride = int(_read_text(stride_path))
    else:
        stride = xres * (bpp // 8)

    return xres, yres, bpp, stride


def rgb_to_rgb565_bytes(img: Image.Image, stride: int) -> bytes:
    """
    Convert an RGB Pillow image to packed RGB565 with per-row stride padding.
    Minimal (not optimized) but simple and reliable.
    """
    if img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    px = img.load()

    out = bytearray(stride * h)
    for y in range(h):
        row = y * stride
        for x in range(w):
            r, g, b = px[x, y]
            rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            off = row + x * 2
            out[off] = rgb565 & 0xFF
            out[off + 1] = (rgb565 >> 8) & 0xFF
    return bytes(out)


def blit(img: Image.Image) -> None:
    xres, yres, bpp, stride = get_fb0_info()
    print(f"fb0: {xres}x{yres} bpp={bpp} stride={stride}")

    if bpp != 16:
        raise RuntimeError(f"Unsupported fb bpp={bpp}. This minimal script only supports 16bpp RGB565.")

    if img.size != (xres, yres):
        img = img.resize((xres, yres), Image.NEAREST)

    payload = rgb_to_rgb565_bytes(img, stride)

    # Simple write (no mmap). Requires correct size.
    with open(FB0, "wb", buffering=0) as fb:
        fb.write(payload)


def draw_box_text(
    text: str,
    box_xywh: Tuple[int, int, int, int] = (50, 50, 500, 200),
    box_color: Tuple[int, int, int] = (0, 200, 0),
    text_color: Tuple[int, int, int] = (0, 0, 0),
    bg_color: Tuple[int, int, int] = (40, 0, 0),
    font_size: int = 48,
) -> None:
    xres, yres, _, _ = get_fb0_info()

    img = Image.new("RGB", (xres, yres), bg_color)
    d = ImageDraw.Draw(img)

    x, y, w, h = box_xywh
    d.rectangle([x, y, x + w, y + h], fill=box_color)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    # Center text in the box
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = x + (w - tw) // 2
    ty = y + (h - th) // 2
    d.text((tx, ty), text, font=font, fill=text_color)

    blit(img)


if __name__ == "__main__":
    hide_cursor()
    try:
        draw_box_text("HELLO", box_xywh=(100, 100, 700, 300), box_color=(16, 35, 92), font_size=500)
    finally:
        show_cursor()  # Restore cursor on exit
