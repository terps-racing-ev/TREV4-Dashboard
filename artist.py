#!/usr/bin/env python3

from typing import Optional, Tuple, Union
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from colors import *


def simple_gauge(
    img: Image.Image,
    label: str,
    data: str,
    box_xywh: Tuple[int, int, int, int] = (50, 50, 500, 200),
    box_color: Tuple[int, int, int] = BLACK,
    border_color: Tuple[int, int, int] = WHITE,
    text_color: Tuple[int, int, int] = WHITE,
    label_font_path: Optional[Union[str, Path]] = None,
    label_font_size: int = 48,
    data_font_path: Optional[Union[str, Path]] = None,
    data_font_size: int = 48,
) -> Image.Image:
    """Draw a colored box with centered text onto the provided image."""
    d = ImageDraw.Draw(img)

    x, y, w, h = box_xywh
    d.rectangle(
        [x, y, x + w, y + h], 
        fill=box_color, 
        outline=border_color, 
        width=4
    )

    try:
        path_str = str(label_font_path) if label_font_path else None
        label_font = ImageFont.truetype(path_str, label_font_size) if path_str else ImageFont.load_default()
    except Exception:
        label_font = ImageFont.load_default()

    try:
        path_str = str(data_font_path) if data_font_path else None
        data_font = ImageFont.truetype(path_str, data_font_size) if path_str else ImageFont.load_default()
    except Exception:
        data_font = ImageFont.load_default()

    # Center point of box
    cx, cy = x + w // 2, y + h // 2
    # Draw text centered at that point
    d.text((cx, cy), data, font=data_font, fill=text_color, anchor="mm")

    d.text((x, y), label, font=label_font, fill=text_color, anchor="lt")

    return img