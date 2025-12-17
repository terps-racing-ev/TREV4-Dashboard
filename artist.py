#!/usr/bin/env python3

from typing import Optional, Tuple, Union
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from colors import *

ASSETS_DIR = Path(__file__).parent / "assets"
DEFAULT_FONT = ASSETS_DIR / "fonts" / "monofonto rg.otf"

SMALL_FONT = ImageFont.truetype(str(DEFAULT_FONT), 24)
MEDIUM_FONT = ImageFont.truetype(str(DEFAULT_FONT), 48)
LARGE_FONT = ImageFont.truetype(str(DEFAULT_FONT), 96)

# what font size to choose based on box pixels
SIZE_FONT_RATIO = 0.66

LABEL_PADDING = 8


def _dim_to_font_size(w: int, h: int) -> int:
    return int(min(w, h) * SIZE_FONT_RATIO)

def simple_gauge(
    img: Image.Image,
    label_str: str,
    data_str: str,
    box_xywh: Tuple[int, int, int, int] = (50, 50, 500, 200),
    box_color: Tuple[int, int, int] | None = BLACK,
    border_color: Tuple[int, int, int] | None = WHITE,
    text_color: Tuple[int, int, int] = WHITE,
) -> Image.Image:
    """
    Draw a simple gauge onto the provided image.
    label in the top left corner
    data autosized in the middle
    """
    d = ImageDraw.Draw(img)

    x, y, w, h = box_xywh
    d.rectangle(
        [x, y, x + w, y + h], 
        fill=box_color, 
        outline=border_color, 
        width=4
    )


    # Draw the label
    d.text(
        (x + LABEL_PADDING, y + LABEL_PADDING), 
        label_str, 
        font=SMALL_FONT, 
        fill=text_color, 
        anchor="lt"
    )

    data_font_size = _dim_to_font_size(w, h)
    data_font = ImageFont.truetype(str(DEFAULT_FONT), data_font_size)
    # Center point of box
    cx, cy = x + w // 2, y + h // 2

    # Draw text centered at that point
    d.text(
        (cx, cy), 
        data_str, 
        font=data_font, 
        fill=text_color, 
        anchor="mm"
    )

    return img