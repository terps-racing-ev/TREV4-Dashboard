#!/usr/bin/env python3

import sys
from pathlib import Path
from typing import Tuple
from PIL import Image

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
        raise RuntimeError(f"Unsupported fb bpp={bpp}. This script only supports 16bpp RGB565.")

    if img.size != (xres, yres):
        img = img.resize((xres, yres), Image.NEAREST)

    payload = rgb_to_rgb565_bytes(img, stride)

    # Simple write (no mmap). Requires correct size.
    with open(FB0, "wb", buffering=0) as fb:
        fb.write(payload)
