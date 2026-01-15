#!/usr/bin/env python3

from typing import Optional, Tuple, Union
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math

from colors import *

ASSETS_DIR = Path(__file__).parent / "assets"
DEFAULT_FONT = ASSETS_DIR / "fonts" / "monofonto rg.otf"

SMALL_FONT = ImageFont.truetype(str(DEFAULT_FONT), 24)
MEDIUM_FONT = ImageFont.truetype(str(DEFAULT_FONT), 48)
LARGE_FONT = ImageFont.truetype(str(DEFAULT_FONT), 96)

# what font size to choose based on box pixels
SIZE_FONT_RATIO = 1.6

# ideally font times this equals pixels-ish
FONT_HEIGHT_RATIO = 1.2
FONT_WIDTH_RATIO = 0.6

LABEL_PADDING = 8

def _dim_to_font_size(w: int, h: int, text: str) -> int:
    width_per_char = w / len(text)

    return int(min(width_per_char / FONT_WIDTH_RATIO, h / FONT_HEIGHT_RATIO))

def _digits_left_of_decimal(n: int | float) -> int:
    if n == 0:
        return 1
    return math.floor(math.log10(abs(n))) + 1

def _normalize_chars(value: int | float, min_val: int | float, max_val: int | float, decimal_places: int) -> str:
    """
    Format a value to a fixed-width string with zero-padding.
    
    Width is calculated from max digits (ignoring sign) + optional decimal point and places.
    Negative values prepend a minus sign without affecting digit width.
    
    Example:
        value=24.379, min_val=-999, max_val=50, decimal_places=2
        max_digits = 3 (from |-999| and |50|)
        total_width = 3 + 1 + 2 = 6
        Positive result: "024.38" (6 chars)
        Negative -24.379: "-024.38" (7 chars, sign + 6)
        
        value=50, min_val=0, max_val=100, decimal_places=0
        max_digits = 3 (from 100)
        total_width = 3 (no decimal point or places)
        result: "050" (3 chars)
    """
    # Calculate max digits from absolute values
    max_digits = max(_digits_left_of_decimal(min_val), _digits_left_of_decimal(max_val))
    
    # Calculate total width for numeric part (excluding sign)
    if decimal_places == 0:
        total_width = max_digits
    else:
        total_width = max_digits + 1 + decimal_places  # digits + decimal point + decimal places
    
    # Format absolute value
    abs_value = abs(value)
    if decimal_places == 0:
        formatted = f"{abs_value:.0f}"
    else:
        formatted = f"{abs_value:.{decimal_places}f}"
    
    # Zero-pad the numeric part
    zero_padded = formatted.zfill(total_width)
    
    # Add sign if negative
    if value < 0:
        return "-" + zero_padded
    else:
        return zero_padded


def simple_gauge(
    img: Image.Image,
    label: str,
    value: int | float,
    min_val: int,
    max_val: int,
    decimal_places: int,
    box_xywh: Tuple[int, int, int, int],
    box_color: Tuple[int, int, int] | None = None,
    border_color: Tuple[int, int, int] | None = WHITE,
    text_color: Tuple[int, int, int] = WHITE,
) -> Image.Image:
    """
    Draws a rectangular readout onto the provided image.
    label in the top left corner
    text autosized in the middle cus its so freakyng cool
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
        label, 
        font=SMALL_FONT, 
        fill=text_color, 
        anchor="lt"
    )

    value_str = _normalize_chars(value, min_val, max_val, decimal_places)
    data_font_size = _dim_to_font_size(w, h, value_str)
    data_font = ImageFont.truetype(str(DEFAULT_FONT), data_font_size)
    # Center point of box
    cx, cy = x + w // 2, y + h // 2

    # Draw text centered at that point
    d.text(
        (cx, cy), 
        value_str, 
        font=data_font, 
        fill=text_color, 
        anchor="mm"
    )

    return img


def unsigned_linear_gauge(
    img: Image.Image,
    value: float,
    min_val: float,
    max_val: float,
    box_xywh: Tuple[int, int, int, int] = (50, 50, 500, 100),
    orientation: str = "horizontal",
    box_color: Tuple[int, int, int] | None = BLACK,
    border_color: Tuple[int, int, int] | None = WHITE,
    fill_color: Tuple[int, int, int] = (0, 255, 0),
    text_color: Tuple[int, int, int] = WHITE,
    show_value: bool = True,
    decimals: int = 2,
) -> Image.Image:
    """
    Draw a linear gauge (progress bar) onto the provided image.
    
    Args:
        img: PIL Image to draw on
        value: Current value to display
        min_val: Minimum value for the range
        max_val: Maximum value for the range
        box_xywh: (x, y, width, height) of the gauge box
        orientation: "horizontal" or "vertical"
        box_color: Background color of the gauge
        border_color: Border color
        fill_color: Color of the filled portion
        text_color: Color of the value text
        show_value: Whether to display the value as text
        decimals: Number of decimal places for value display
    """
    d = ImageDraw.Draw(img)
    
    x, y, w, h = box_xywh
    
    # Clamp value to min/max
    clamped = max(min_val, min(value, max_val))
    
    # Calculate fill ratio
    if max_val == min_val:
        ratio = 0.0
    else:
        ratio = (clamped - min_val) / (max_val - min_val)
    
    # Draw background box
    d.rectangle(
        [x, y, x + w, y + h],
        fill=box_color,
        outline=border_color,
        width=4
    )
    
    # Draw filled portion
    if orientation.lower() == "horizontal":
        fill_width = int(w * ratio)
        d.rectangle(
            [x, y, x + fill_width, y + h],
            fill=fill_color
        )
    elif orientation.lower() == "vertical":
        fill_height = int(h * ratio)
        d.rectangle(
            [x, y + h - fill_height, x + w, y + h],
            fill=fill_color
        )
    
    # Draw value text if requested
    if show_value:
        value_str = f"{clamped:.{decimals}f}"
        cx, cy = x + w // 2, y + h // 2
        
        font_size = max(12, int(min(w, h) * 0.3))
        try:
            value_font = ImageFont.truetype(str(DEFAULT_FONT), font_size)
        except:
            value_font = SMALL_FONT
        
        d.text(
            (cx, cy),
            value_str,
            font=value_font,
            fill=text_color,
            anchor="mm"
        )
    
    return img