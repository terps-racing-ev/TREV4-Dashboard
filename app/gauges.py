#!/usr/bin/env python3

from typing import Any, Optional, Tuple, Union
import pygame
import math
import colorsys
from pathlib import Path

from .shared_data import LatestValuesTable

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FONT = str(ROOT_DIR / "assets" / "fonts" / "monofonto rg.otf")

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 200, 0)
RED = (255, 0, 0)

# Lazy-loaded fonts (initialized on first access)
_SMALL_FONT = None
_MEDIUM_FONT = None
_LARGE_FONT = None

def _get_small_font():
    global _SMALL_FONT
    if _SMALL_FONT is None:
        pygame.font.init()
        _SMALL_FONT = pygame.font.Font(DEFAULT_FONT, 24)
    return _SMALL_FONT

def _get_medium_font():
    global _MEDIUM_FONT
    if _MEDIUM_FONT is None:
        pygame.font.init()
        _MEDIUM_FONT = pygame.font.Font(DEFAULT_FONT, 48)
    return _MEDIUM_FONT

def _get_large_font():
    global _LARGE_FONT
    if _LARGE_FONT is None:
        pygame.font.init()
        _LARGE_FONT = pygame.font.Font(DEFAULT_FONT, 96)
    return _LARGE_FONT

BORDER_WIDTH = 4

# ideally font times this equals pixels-ish
FONT_HEIGHT_RATIO = 1.3
FONT_WIDTH_RATIO = 0.7

LABEL_PADDING = 8
TEXT_STROKE_WIDTH = 1
TEXT_STROKE_COLOR = BLACK
STALE_AFTER_SECONDS = 5.0

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


def _interpolate_color(
    min_color: Tuple[int, int, int],
    max_color: Tuple[int, int, int],
    ratio: float,
) -> Tuple[int, int, int]:
    clamped_ratio = max(0.0, min(1.0, ratio))

    start_rgb = tuple(component / 255 for component in min_color[:3])
    end_rgb = tuple(component / 255 for component in max_color[:3])
    start_h, start_s, start_v = colorsys.rgb_to_hsv(*start_rgb)
    end_h, end_s, end_v = colorsys.rgb_to_hsv(*end_rgb)

    if start_s == 0:
        start_h = end_h
    elif end_s == 0:
        end_h = start_h

    hue_delta = (end_h - start_h + 0.5) % 1.0 - 0.5
    hue = (start_h + hue_delta * clamped_ratio) % 1.0
    saturation = start_s + (end_s - start_s) * clamped_ratio
    value = start_v + (end_v - start_v) * clamped_ratio

    return tuple(
        round(component * 255)
        for component in colorsys.hsv_to_rgb(hue, saturation, value)
    )


def _blit_text_with_stroke(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    color: Tuple[int, int, int],
    rect: pygame.Rect,
) -> None:
    stroke_text = font.render(text, True, TEXT_STROKE_COLOR)
    for dx in range(-TEXT_STROKE_WIDTH, TEXT_STROKE_WIDTH + 1):
        for dy in range(-TEXT_STROKE_WIDTH, TEXT_STROKE_WIDTH + 1):
            if dx != 0 or dy != 0:
                surface.blit(stroke_text, rect.move(dx, dy))
    surface.blit(font.render(text, True, color), rect)


class Gauge:
    def __init__(
        self,
        signal: str,
        min_val: int | float,
        max_val: int | float,
        box_xywh: Tuple[int, int, int, int],
        decimal_places: int = 0,
        box_color: Tuple[int, int, int] | None = None,
        border_color: Tuple[int, int, int] | None = WHITE,
        text_color: Tuple[int, int, int] = WHITE,
        min_color: Tuple[int, int, int] = GREEN,
        max_color: Tuple[int, int, int] = RED,
        gradient_text: bool = False,
        gradient_box: bool = False,
        gradient_border: bool = False,
        gradient_fill: bool = False,
        shared_data: LatestValuesTable | None = None,
        default_value: int | float = 0,
    ) -> None:
        self.signal = signal
        self.min_val = min_val
        self.max_val = max_val
        self.box_xywh = box_xywh
        self.decimal_places = decimal_places
        self.box_color = box_color
        self.border_color = border_color
        self.text_color = text_color
        self.min_color = min_color
        self.max_color = max_color
        self.gradient_text = gradient_text
        self.gradient_box = gradient_box
        self.gradient_border = gradient_border
        self.gradient_fill = gradient_fill
        self.shared_data = shared_data
        self.default_value = default_value

        self.x, self.y, self.w, self.h = box_xywh
        self.cx, self.cy = self.x + self.w // 2, self.y + self.h // 2

    def _ratio(self, value: int | float) -> float:
        if self.max_val == self.min_val:
            return 0.0
        return (value - self.min_val) / (self.max_val - self.min_val)

    def _clamped_ratio(self, value: int | float) -> float:
        clamped = max(self.min_val, min(value, self.max_val))
        return max(0.0, min(1.0, self._ratio(clamped)))

    def _gradient_color(self, value: int | float) -> Tuple[int, int, int]:
        return _interpolate_color(self.min_color, self.max_color, self._clamped_ratio(value))

    def _mapped_color(self, base_color: Tuple[int, int, int] | None, enabled: bool, value: int | float) -> Tuple[int, int, int] | None:
        if base_color is None:
            return None
        return self._gradient_color(value) if enabled else base_color

    def _template_str(self) -> str:
        pos_template = _normalize_chars(self.max_val, self.min_val, self.max_val, self.decimal_places)
        if self.min_val < 0:
            neg_template = _normalize_chars(self.min_val, self.min_val, self.max_val, self.decimal_places)
        else:
            neg_template = pos_template
        return neg_template if len(neg_template) > len(pos_template) else pos_template

    def _make_value_font(self, enabled: bool = True, text: str | None = None) -> Optional[pygame.font.Font]:
        if not enabled:
            return None
        pygame.font.init()
        template = text if text is not None else self._template_str()
        size = _dim_to_font_size(self.w, self.h, template)
        return pygame.font.Font(DEFAULT_FONT, size)

    def _format_value(self, value: int | float) -> str:
        return _normalize_chars(value, self.min_val, self.max_val, self.decimal_places)

    def _current_value(self) -> int | float:
        val = self.shared_data.get_signal(self.signal)
        return val if val is not None else 0

    def _current_display_value(self) -> Any:
        if self.shared_data is None:
            return self._current_value()
        display_value = self.shared_data.get_display_signal(self.signal)
        return display_value if display_value is not None else self._current_value()

    def _signal_is_stale(self) -> bool:
        if self.shared_data is None:
            return False
        return self.shared_data.is_signal_stale(self.signal, STALE_AFTER_SECONDS)

    def _value_text(self, value: Any, *, stale: bool = False) -> str:
        if stale:
            if isinstance(value, str):
                return "-" * len(value)
            return "".join("-" if char.isdigit() else char for char in self._template_str())
        if isinstance(value, str):
            return value
        return self._format_value(value)

    def _make_display_font(self, value: Any, enabled: bool = True) -> Optional[pygame.font.Font]:
        if not enabled:
            return None
        if isinstance(value, str):
            return self._make_value_font(True, value)
        return self.data_font

    def _fill_background(self, surface: pygame.Surface, value: int | float | None = None) -> None:
        box_color = self.box_color
        if value is not None:
            box_color = self._mapped_color(box_color, self.gradient_box, value)
        if box_color is not None:
            pygame.draw.rect(surface, box_color, (self.x, self.y, self.w, self.h))

    def _draw_border(self, surface: pygame.Surface, value: int | float | None = None) -> None:
        border_color = self.border_color
        if value is not None:
            border_color = self._mapped_color(border_color, self.gradient_border, value)
        if border_color is not None:
            pygame.draw.rect(surface, border_color, (self.x, self.y, self.w, self.h), BORDER_WIDTH)


class SimpleGauge(Gauge):
    def __init__(
        self,
        signal: str,
        label: str,
        min_val: int | float,
        max_val: int | float,
        box_xywh: Tuple[int, int, int, int],
        decimal_places: int = 0,
        box_color: Tuple[int, int, int] | None = None,
        border_color: Tuple[int, int, int] | None = WHITE,
        text_color: Tuple[int, int, int] = WHITE,
        min_color: Tuple[int, int, int] = GREEN,
        max_color: Tuple[int, int, int] = RED,
        gradient_text: bool = False,
        gradient_box: bool = False,
        gradient_border: bool = False,
        show_value: bool = True,
        shared_data: LatestValuesTable | None = None,
    ) -> None:
        super().__init__(
            signal=signal,
            min_val=min_val,
            max_val=max_val,
            box_xywh=box_xywh,
            decimal_places=decimal_places,
            box_color=box_color,
            border_color=border_color,
            text_color=text_color,
            min_color=min_color,
            max_color=max_color,
            gradient_text=gradient_text,
            gradient_box=gradient_box,
            gradient_border=gradient_border,
            shared_data=shared_data,
        )
        self.label = label
        self.show_value = show_value
        self.data_font = self._make_value_font(show_value)

    def update(self, surface: pygame.Surface) -> pygame.Surface:
        value = self._current_value()
        display_value = self._current_display_value()
        is_stale = self._signal_is_stale()

        # Background + border
        self._fill_background(surface, value)
        self._draw_border(surface, value)
        render_text_color = self._mapped_color(self.text_color, self.gradient_text, value)
        if render_text_color is None:
            return surface

        # Label (static font size)
        label_font = _get_small_font()
        label_text = label_font.render(self.label, True, render_text_color)
        if self.show_value:
            label_rect = label_text.get_rect(topleft=(self.x + LABEL_PADDING, self.y + LABEL_PADDING))
        else:
            label_rect = label_text.get_rect(center=(self.cx, self.cy))
        _blit_text_with_stroke(surface, label_font, self.label, render_text_color, label_rect)

        if self.show_value and self.data_font is not None:
            # Value (pre-sized font, centered below label accounting for its height)
            value_str = self._value_text(display_value, stale=is_stale)
            available_height = self.h - label_rect.height - 2 * LABEL_PADDING
            # Recalculate font size based on available height to prevent overflow
            if isinstance(display_value, str):
                value_font = self._make_value_font(True, value_str)
            else:
                template = value_str
                size = int(min(self.w / len(template) / FONT_WIDTH_RATIO, available_height / FONT_HEIGHT_RATIO))
                value_font = pygame.font.Font(DEFAULT_FONT, max(8, size))
            value_text = value_font.render(value_str, True, render_text_color)
            center_y = self.y + label_rect.height + LABEL_PADDING + available_height // 2
            value_rect = value_text.get_rect(center=(self.cx, center_y))
            _blit_text_with_stroke(surface, value_font, value_str, render_text_color, value_rect)

        return surface


class UnsignedLinearGauge(Gauge):
    def __init__(
        self,
        signal: str,
        label: str,
        min_val: int | float,
        max_val: int | float,
        box_xywh: Tuple[int, int, int, int],
        decimal_places: int = 0,
        box_color: Tuple[int, int, int] | None = None,
        border_color: Tuple[int, int, int] | None = WHITE,
        fill_color: Tuple[int, int, int] = GREEN,
        text_color: Tuple[int, int, int] = WHITE,
        min_color: Tuple[int, int, int] = GREEN,
        max_color: Tuple[int, int, int] = RED,
        gradient_text: bool = False,
        gradient_box: bool = False,
        gradient_border: bool = False,
        gradient_fill: bool = False,
        vertical: bool = True,
        show_value: bool = True,
        shared_data: LatestValuesTable | None = None,
    ) -> None:
        super().__init__(
            signal=signal,
            min_val=min_val,
            max_val=max_val,
            box_xywh=box_xywh,
            decimal_places=decimal_places,
            box_color=box_color,
            border_color=border_color,
            text_color=text_color,
            min_color=min_color,
            max_color=max_color,
            gradient_text=gradient_text,
            gradient_box=gradient_box,
            gradient_border=gradient_border,
            gradient_fill=gradient_fill,
            shared_data=shared_data,
        )
        self.label = label
        self.fill_color = fill_color
        self.vertical = vertical
        self.show_value = show_value
        self.data_font = self._make_value_font(show_value)

    def update(self, surface: pygame.Surface) -> pygame.Surface:
        value = self._current_value()
        display_value = self._current_display_value()
        is_stale = self._signal_is_stale()

        # Compute ratio
        ratio = self._clamped_ratio(value)
        fill_color = self._mapped_color(self.fill_color, self.gradient_fill, value)
        render_text_color = self._mapped_color(self.text_color, self.gradient_text, value)

        # Draw background fill
        self._fill_background(surface, value)

        # Draw fill next
        if self.vertical:
            fill_height = int(self.h * ratio)
            if fill_height > 0 and fill_color is not None:
                pygame.draw.rect(surface, fill_color, (self.x, self.y + self.h - fill_height, self.w, fill_height))
        else:
            fill_width = int(self.w * ratio)
            if fill_width > 0 and fill_color is not None:
                pygame.draw.rect(surface, fill_color, (self.x, self.y, fill_width, self.h))

        # Draw the border on top
        self._draw_border(surface, value)

        # Label (static font size)
        if render_text_color is None:
            return surface
        label_font = _get_small_font()
        label_text = label_font.render(self.label, True, render_text_color)
        label_rect = label_text.get_rect(midtop=(self.cx, self.y + self.h + LABEL_PADDING))
        _blit_text_with_stroke(surface, label_font, self.label, render_text_color, label_rect)

        # Optional value text (accounting for available space)
        if self.show_value and self.data_font is not None:
            value_str = self._value_text(display_value, stale=is_stale)
            value_font = self._make_display_font(display_value)
            value_text = value_font.render(value_str, True, render_text_color)
            if self.vertical:
                # Top center for vertical (account for label padding)
                value_rect = value_text.get_rect(midtop=(self.cx, self.y + LABEL_PADDING))
            else:
                # Right middle for horizontal (account for available width)
                value_rect = value_text.get_rect(midright=(self.x + self.w - LABEL_PADDING, self.cy))
            _blit_text_with_stroke(surface, value_font, value_str, render_text_color, value_rect)

        return surface


class SignedLinearGauge(Gauge):
    def __init__(
        self,
        signal: str,
        label: str,
        min_val: int | float,
        max_val: int | float,
        box_xywh: Tuple[int, int, int, int],
        decimal_places: int = 0,
        box_color: Tuple[int, int, int] | None = None,
        border_color: Tuple[int, int, int] | None = WHITE,
        pos_color: Tuple[int, int, int] = GREEN,
        neg_color: Tuple[int, int, int] = RED,
        text_color: Tuple[int, int, int] = WHITE,
        min_color: Tuple[int, int, int] = GREEN,
        max_color: Tuple[int, int, int] = RED,
        gradient_text: bool = False,
        gradient_box: bool = False,
        gradient_border: bool = False,
        gradient_fill: bool = False,
        vertical: bool = True,
        show_value: bool = True,
        shared_data: LatestValuesTable | None = None,
    ) -> None:
        super().__init__(
            signal=signal,
            min_val=min_val,
            max_val=max_val,
            box_xywh=box_xywh,
            decimal_places=decimal_places,
            box_color=box_color,
            border_color=border_color,
            text_color=text_color,
            min_color=min_color,
            max_color=max_color,
            gradient_text=gradient_text,
            gradient_box=gradient_box,
            gradient_border=gradient_border,
            gradient_fill=gradient_fill,
            shared_data=shared_data,
        )
        self.label = label
        self.pos_color = pos_color
        self.neg_color = neg_color
        self.vertical = vertical
        self.show_value = show_value
        self.data_font = self._make_value_font(show_value)

    def _ratio(self, value: int | float) -> float:
        if self.max_val == self.min_val:
            return 0.0
        return (value - self.min_val) / (self.max_val - self.min_val)

    def _zero_ratio(self) -> float:
        if self.max_val == self.min_val:
            return 0.0
        zr = (0 - self.min_val) / (self.max_val - self.min_val)
        return max(0.0, min(1.0, zr))

    def update(self, surface: pygame.Surface) -> pygame.Surface:
        value = self._current_value()
        display_value = self._current_display_value()
        is_stale = self._signal_is_stale()

        clamped = max(self.min_val, min(value, self.max_val))
        zero_ratio = self._zero_ratio()
        value_ratio = self._ratio(clamped)
        pos_color = self._mapped_color(self.pos_color, self.gradient_fill, value)
        neg_color = self._mapped_color(self.neg_color, self.gradient_fill, value)
        render_text_color = self._mapped_color(self.text_color, self.gradient_text, value)

        # Background fill if requested
        self._fill_background(surface, value)

        # Draw fill from zero toward value
        if self.vertical:
            zero_y = self.y + self.h - int(self.h * zero_ratio)
            val_y = self.y + self.h - int(self.h * value_ratio)
            if value_ratio > zero_ratio and pos_color is not None:
                # Positive fill upward from zero
                top = min(val_y, zero_y)
                bottom = max(val_y, zero_y)
                pygame.draw.rect(surface, pos_color, (self.x, top, self.w, bottom - top))
            elif value_ratio < zero_ratio and neg_color is not None:
                # Negative fill downward from zero
                top = min(val_y, zero_y)
                bottom = max(val_y, zero_y)
                pygame.draw.rect(surface, neg_color, (self.x, top, self.w, bottom - top))
            # Zero marker line
            # todo idk why we need -1, this whole class is fucked
            pygame.draw.line(surface, WHITE, (self.x, zero_y), (self.x + self.w - 1, zero_y), 2)
        else:
            zero_x = self.x + int(self.w * zero_ratio)
            val_x = self.x + int(self.w * value_ratio)
            if value_ratio > zero_ratio and pos_color is not None:
                left = min(val_x, zero_x)
                right = max(val_x, zero_x)
                pygame.draw.rect(surface, pos_color, (left, self.y, right - left, self.h))
            elif value_ratio < zero_ratio and neg_color is not None:
                left = min(val_x, zero_x)
                right = max(val_x, zero_x)
                pygame.draw.rect(surface, neg_color, (left, self.y, right - left, self.h))
            # Zero marker line
            pygame.draw.line(surface, WHITE, (zero_x, self.y), (zero_x, self.y + self.h), 2)

        self._draw_border(surface, value)

        # Label
        if render_text_color is None:
            return surface
        label_font = _get_small_font()
        label_text = label_font.render(self.label, True, render_text_color)
        label_rect = label_text.get_rect(midtop=(self.cx, self.y + self.h + LABEL_PADDING))
        _blit_text_with_stroke(surface, label_font, self.label, render_text_color, label_rect)

        # Value (accounting for available vertical space)
        if self.show_value and self.data_font is not None:
            value_str = self._value_text(display_value, stale=is_stale)
            value_font = self._make_display_font(display_value)
            value_text = value_font.render(value_str, True, render_text_color)
            if self.vertical:
                # Left middle for vertical, vertically centered in box (so text outside the box)
                value_rect = value_text.get_rect(midright=(self.x - LABEL_PADDING, self.cy))
            else:
                # Right middle for horizontal, vertically centered in box
                value_rect = value_text.get_rect(midright=(self.x + self.w - LABEL_PADDING, self.cy))
            _blit_text_with_stroke(surface, value_font, value_str, render_text_color, value_rect)

        return surface
