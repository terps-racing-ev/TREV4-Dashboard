#!/usr/bin/env python3
"""
fb_pillow_dash.py

- Auto-detects framebuffer geometry/format from /dev/fb0 via ioctl:
  - xres, yres, bpp, stride(line_length)
- Renders using Pillow, then converts to the framebuffer pixel format:
  - 16bpp: RGB565 or BGR565 (auto-detected if possible; fallback RGB565)
  - 32bpp: XRGB8888 / ARGB8888 (writes as BGRA little-endian, common on Linux)
- Provides draw_box_text(text, ...) which draws a colored box with centered text.

Notes:
- Assumes /dev/fb0 is the active console framebuffer.
- If your fb is 24bpp or unusual formats, this will raise a clear error.
"""

from __future__ import annotations

import fcntl
import mmap
import os
import struct
from dataclasses import dataclass
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

FBIOGET_VSCREENINFO = 0x4600  # linux/fb.h
FBIOGET_FSCREENINFO = 0x4602  # linux/fb.h


@dataclass
class FBInfo:
    xres: int
    yres: int
    bpp: int
    stride: int  # bytes per line
    r: Tuple[int, int]  # (offset, length)
    g: Tuple[int, int]
    b: Tuple[int, int]
    a: Tuple[int, int]  # (offset, length)


def _get_fb_info(fd: int) -> FBInfo:
    """
    Read fb_var_screeninfo and fb_fix_screeninfo via ioctl.
    We only unpack the fields we need, but keep the packing compatible.
    """
    # fb_var_screeninfo is big; we fetch 160 bytes which is enough for the common layout.
    var = bytearray(160)
    fcntl.ioctl(fd, FBIOGET_VSCREENINFO, var, True)

    # Offsets based on linux fb_var_screeninfo layout:
    # u32 xres @ 0, yres @ 4, xres_virtual @ 8, yres_virtual @ 12
    xres, yres, xres_v, yres_v = struct.unpack_from("4I", var, 0)
    bpp = struct.unpack_from("I", var, 24)[0]

    # color bitfield layout: each is (offset u32, length u32, msb_right u32)
    # red @ 48, green @ 60, blue @ 72, transp @ 84
    r_off, r_len, _ = struct.unpack_from("3I", var, 48)
    g_off, g_len, _ = struct.unpack_from("3I", var, 60)
    b_off, b_len, _ = struct.unpack_from("3I", var, 72)
    a_off, a_len, _ = struct.unpack_from("3I", var, 84)

    # fb_fix_screeninfo: line_length at offset 44 in the common struct layout.
    fix = bytearray(64)
    fcntl.ioctl(fd, FBIOGET_FSCREENINFO, fix, True)
    stride = struct.unpack_from("I", fix, 44)[0]

    # Prefer the visible resolution, not virtual.
    return FBInfo(
        xres=int(xres),
        yres=int(yres),
        bpp=int(bpp),
        stride=int(stride),
        r=(int(r_off), int(r_len)),
        g=(int(g_off), int(g_len)),
        b=(int(b_off), int(b_len)),
        a=(int(a_off), int(a_len)),
    )


def _pack_16bit(img_rgb: Image.Image, info: FBInfo) -> bytes:
    """
    Pack RGB image into 16bpp framebuffer using detected bitfield offsets.
    Supports common RGB565 and BGR565.
    """
    if info.r[1] == 5 and info.g[1] == 6 and info.b[1] == 5:
        r_off, _ = info.r
        g_off, _ = info.g
        b_off, _ = info.b
    else:
        # Fallback for 16bpp formats we don't recognize
        raise RuntimeError(f"Unsupported 16bpp bitfield: r={info.r}, g={info.g}, b={info.b}")

    w, h = img_rgb.size
    px = img_rgb.load()
    out = bytearray(info.stride * h)

    for y in range(h):
        row_base = y * info.stride
        for x in range(w):
            r, g, b = px[x, y]
            rv = (r >> (8 - info.r[1])) & ((1 << info.r[1]) - 1)
            gv = (g >> (8 - info.g[1])) & ((1 << info.g[1]) - 1)
            bv = (b >> (8 - info.b[1])) & ((1 << info.b[1]) - 1)

            pix = (rv << r_off) | (gv << g_off) | (bv << b_off)
            off = row_base + x * 2
            out[off] = pix & 0xFF
            out[off + 1] = (pix >> 8) & 0xFF

    return bytes(out)


def _pack_32bit(img_rgb: Image.Image, info: FBInfo) -> bytes:
    """
    Pack RGB into 32bpp using bitfield offsets.
    Common on Pi console is XRGB8888 (BGRX little-endian in memory).
    We'll respect offsets/lengths and write a=all-ones if alpha exists.
    """
    # Require 8-bit channels for RGB at least
    if not (info.r[1] == info.g[1] == info.b[1] == 8):
        raise RuntimeError(f"Unsupported 32bpp bitfield: r={info.r}, g={info.g}, b={info.b}, a={info.a}")

    r_off, _ = info.r
    g_off, _ = info.g
    b_off, _ = info.b
    a_off, a_len = info.a

    w, h = img_rgb.size
    px = img_rgb.load()
    out = bytearray(info.stride * h)

    a_val = (1 << a_len) - 1 if a_len > 0 else 0

    for y in range(h):
        row_base = y * info.stride
        for x in range(w):
            r, g, b = px[x, y]
            pix = (r << r_off) | (g << g_off) | (b << b_off)
            if a_len:
                pix |= (a_val << a_off)

            off = row_base + x * 4
            # little-endian u32
            out[off:off + 4] = struct.pack("<I", pix)

    return bytes(out)


def blit_image_to_fb(img: Image.Image, fb_path: str = "/dev/fb0") -> FBInfo:
    """
    Convert a Pillow image to the framebuffer format and blit it.
    Returns detected FBInfo.
    """
    if img.mode != "RGB":
        img = img.convert("RGB")

    with open(fb_path, "r+b", buffering=0) as fb:
        info = _get_fb_info(fb.fileno())

        # Resize to current fb size if needed
        if img.size != (info.xres, info.yres):
            img = img.resize((info.xres, info.yres), Image.NEAREST)

        fb_size = info.stride * info.yres
        fbmap = mmap.mmap(fb.fileno(), fb_size, mmap.MAP_SHARED, mmap.PROT_WRITE)

        try:
            if info.bpp == 16:
                payload = _pack_16bit(img, info)
            elif info.bpp == 32:
                payload = _pack_32bit(img, info)
            else:
                raise RuntimeError(f"Unsupported framebuffer bpp: {info.bpp} (need 16 or 32)")

            fbmap.seek(0)
            fbmap.write(payload)
        finally:
            fbmap.close()

    return info


def draw_box_text(
    text: str,
    box_xywh: Tuple[int, int, int, int] = (50, 50, 600, 250),
    box_color: Tuple[int, int, int] = (30, 160, 255),
    text_color: Tuple[int, int, int] = (0, 0, 0),
    bg_color: Tuple[int, int, int] = (0, 0, 0),
    font_size: int = 48,
    fb_path: str = "/dev/fb0",
) -> FBInfo:
    """
    Creates a full-screen image, draws a colored box with centered text, blits to fb0.
    """
    with open(fb_path, "r+b", buffering=0) as fb:
        info = _get_fb_info(fb.fileno())

    img = Image.new("RGB", (info.xres, info.yres), bg_color)
    draw = ImageDraw.Draw(img)

    x, y, w, h = box_xywh
    draw.rectangle([x, y, x + w, y + h], fill=box_color)

    # Use a decent default font; DejaVuSans exists on most Raspberry Pi OS installs.
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    # Center text in the box
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = x + (w - tw) // 2
    ty = y + (h - th) // 2
    draw.text((tx, ty), text, font=font, fill=text_color)

    return blit_image_to_fb(img, fb_path=fb_path)


if __name__ == "__main__":
    info = draw_box_text(
        "HELLO DASH",
        box_xywh=(100, 100, 800, 300),
        box_color=(0, 255, 0),
        text_color=(0, 0, 0),
        bg_color=(40, 0, 0),
        font_size=72,
    )
    print(f"fb0: {info.xres}x{info.yres} bpp={info.bpp} stride={info.stride} "
          f"RGB off/len r={info.r} g={info.g} b={info.b} a={info.a}")
