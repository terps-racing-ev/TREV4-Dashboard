#!/usr/bin/env python3

from typing import Optional, Tuple, Union
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from colors import *


def draw_box_text(
    img: Image.Image,
    text: str,
    box_xywh: Tuple[int, int, int, int] = (50, 50, 500, 200),
    box_color: Tuple[int, int, int] = (0, 200, 0),
    text_color: Tuple[int, int, int] = (0, 0, 0),
    font_path: Optional[Union[str, Path]] = None,
    font_size: int = 48,
) -> Image.Image:
    """Draw a colored box with centered text onto the provided image."""
    d = ImageDraw.Draw(img)

    x, y, w, h = box_xywh
    d.rectangle([x, y, x + w, y + h], fill=box_color)

    try:
        path_str = str(font_path) if font_path else None
        font = ImageFont.truetype(path_str, font_size) if path_str else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = x + (w - tw) // 2
    ty = y + (h - th) // 2
    d.text((tx, ty), text, font=font, fill=text_color)
    return img