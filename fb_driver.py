#!/usr/bin/env python3

import sys
from pathlib import Path
from typing import Tuple
import numpy as np
from PIL import Image

FB0 = "/dev/fb0"
SYSFB = Path("/sys/class/graphics/fb0")


def hide_cursor() -> None:
    """Hide the blinking terminal cursor."""
    # requires root
    try:
        Path("/sys/class/graphics/fbcon/cursor_blink").write_text("0")
    except Exception:
        pass


def show_cursor() -> None:
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
    """Fast RGB565 conversion using NumPy."""
    if img.mode != "RGB":
        img = img.convert("RGB")
    
    # Convert to numpy array
    arr = np.array(img, dtype=np.uint8)
    h, w, _ = arr.shape
    
    # Extract RGB channels
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    
    # Pack into RGB565 (16-bit)
    rgb565 = ((r >> 3).astype(np.uint16) << 11) | \
             ((g >> 2).astype(np.uint16) << 5) | \
             (b >> 3).astype(np.uint16)
    
    # Convert to bytes (little-endian)
    out = bytearray(stride * h)
    for y in range(h):
        row_start = y * stride
        rgb565_row = rgb565[y, :w]
        # Pack as little-endian uint16
        out[row_start:row_start + w*2] = rgb565_row.tobytes()
    
    return bytes(out)


# Initialize framebuffer info once at module load
def _init_fb() -> int:
    """Initialize and validate framebuffer, return stride."""
    xres, yres, bpp, stride = get_fb0_info()
    print(f"fb0: {xres}x{yres} bpp={bpp} stride={stride}")
    
    if bpp != 16:
        raise RuntimeError(f"Unsupported fb bpp={bpp}. This script only supports 16bpp RGB565.")
    
    return stride

_STRIDE = _init_fb()

def blit(img: Image.Image) -> None:
    """Write image to framebuffer."""
    payload = rgb_to_rgb565_bytes(img, _STRIDE)
    
    with open(FB0, "wb", buffering=0) as fb:
        fb.write(payload)
