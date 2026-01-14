#!/usr/bin/env python3

import sys
import platform
from pathlib import Path
from typing import Tuple
import numpy as np
from PIL import Image

FB0 = "/dev/fb0"
SYSFB = Path("/sys/class/graphics/fb0")

# Platform detection
IS_WINDOWS = platform.system() == "Windows"

# Windows simulator components
if IS_WINDOWS:
    import tkinter as tk
    from PIL import ImageTk
    
    _tk_root = None
    _tk_label = None
    _tk_photo = None


def hide_cursor() -> None:
    """Hide the blinking terminal cursor."""
    if IS_WINDOWS:
        return  # No-op on Windows
    # requires root
    try:
        Path("/sys/class/graphics/fbcon/cursor_blink").write_text("0")
    except Exception:
        pass


def show_cursor() -> None:
    if IS_WINDOWS:
        return  # No-op on Windows
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
    if IS_WINDOWS:
        print("Windows simulator mode - using tkinter display")
        return 0  # Stride not needed on Windows
    
    xres, yres, bpp, stride = get_fb0_info()
    print(f"fb0: {xres}x{yres} bpp={bpp} stride={stride}")
    
    if bpp != 16:
        raise RuntimeError(f"Unsupported fb bpp={bpp}. This script only supports 16bpp RGB565.")
    
    return stride

_STRIDE = _init_fb()


def _init_tk_window(width: int = 800, height: int = 480):
    """Initialize tkinter window for Windows simulator."""
    global _tk_root, _tk_label, _tk_photo
    
    _tk_root = tk.Tk()
    _tk_root.title("EV Dashboard Simulator")
    _tk_root.geometry(f"{width}x{height}")
    _tk_root.resizable(False, False)
    
    _tk_label = tk.Label(_tk_root)
    _tk_label.pack()
    
    # Handle window close
    _tk_root.protocol("WM_DELETE_WINDOW", lambda: sys.exit(0))


def blit(img: Image.Image) -> None:
    """Write image to framebuffer or display in simulator window."""
    global _tk_root, _tk_label, _tk_photo
    
    if IS_WINDOWS:
        # Windows simulator: display in tkinter window
        if _tk_root is None:
            _init_tk_window(img.width, img.height)
        
        # Convert PIL image to tkinter PhotoImage
        _tk_photo = ImageTk.PhotoImage(img)
        _tk_label.config(image=_tk_photo)
        _tk_label.image = _tk_photo  # Keep reference
        
        # Process events to update display
        _tk_root.update()
    else:
        # Linux: write to framebuffer
        payload = rgb_to_rgb565_bytes(img, _STRIDE)
        
        with open(FB0, "wb", buffering=0) as fb:
            fb.write(payload)
