#!/usr/bin/env python3

from typing import Optional, Tuple, Union
from pathlib import Path
import pygame
import math

from colors import *
from shared_data import LatestValuesTable

DEFAULT_FONT = "assets/fonts/monofonto rg.otf"

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
        self.shared_data = shared_data
        self.default_value = default_value

        self.x, self.y, self.w, self.h = box_xywh
        self.cx, self.cy = self.x + self.w // 2, self.y + self.h // 2

    def _template_str(self) -> str:
        pos_template = _normalize_chars(self.max_val, self.min_val, self.max_val, self.decimal_places)
        if self.min_val < 0:
            neg_template = _normalize_chars(self.min_val, self.min_val, self.max_val, self.decimal_places)
        else:
            neg_template = pos_template
        return neg_template if len(neg_template) > len(pos_template) else pos_template

    def _make_value_font(self, enabled: bool = True) -> Optional[pygame.font.Font]:
        if not enabled:
            return None
        pygame.font.init()
        template = self._template_str()
        size = _dim_to_font_size(self.w, self.h, template)
        return pygame.font.Font(DEFAULT_FONT, size)

    def _format_value(self, value: int | float) -> str:
        return _normalize_chars(value, self.min_val, self.max_val, self.decimal_places)

    def _current_value(self) -> int | float:
        val = self.shared_data.get_signal(self.signal)
        return val if val is not None else 0

    def _fill_background(self, surface: pygame.Surface) -> None:
        if self.box_color is not None:
            pygame.draw.rect(surface, self.box_color, (self.x, self.y, self.w, self.h))

    def _draw_border(self, surface: pygame.Surface) -> None:
        if self.border_color is not None:
            pygame.draw.rect(surface, self.border_color, (self.x, self.y, self.w, self.h), BORDER_WIDTH)


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
            shared_data=shared_data,
        )
        self.label = label
        self.data_font = self._make_value_font(True)

    def update(self, surface: pygame.Surface) -> pygame.Surface:
        value = self._current_value()

        # Background + border
        self._fill_background(surface)
        self._draw_border(surface)

        # Label (static font size)
        label_text = _get_small_font().render(self.label, True, self.text_color)
        label_rect = label_text.get_rect(topleft=(self.x + LABEL_PADDING, self.y + LABEL_PADDING))
        surface.blit(label_text, label_rect)

        # Value (pre-sized font, centered below label accounting for its height)
        value_str = self._format_value(value)
        value_text = self.data_font.render(value_str, True, self.text_color)
        available_height = self.h - label_rect.height - 2 * LABEL_PADDING
        center_y = self.y + label_rect.height + LABEL_PADDING + available_height // 2
        value_rect = value_text.get_rect(center=(self.cx, center_y))
        surface.blit(value_text, value_rect)

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
            shared_data=shared_data,
        )
        self.label = label
        self.fill_color = fill_color
        self.vertical = vertical
        self.show_value = show_value
        self.data_font = self._make_value_font(show_value)

    def update(self, surface: pygame.Surface) -> pygame.Surface:
        value = self._current_value()

        # Compute ratio
        clamped = max(self.min_val, min(value, self.max_val))
        ratio = 0.0 if self.max_val == self.min_val else (clamped - self.min_val) / (self.max_val - self.min_val)

        # Draw background fill
        self._fill_background(surface)

        # Draw fill next
        if self.vertical:
            fill_height = int(self.h * ratio)
            if fill_height > 0:
                pygame.draw.rect(surface, self.fill_color, (self.x, self.y + self.h - fill_height, self.w, fill_height))
        else:
            fill_width = int(self.w * ratio)
            if fill_width > 0:
                pygame.draw.rect(surface, self.fill_color, (self.x, self.y, fill_width, self.h))

        # Draw the border on top
        self._draw_border(surface)

        # Label (static font size)
        label_text = _get_small_font().render(self.label, True, self.text_color)
        label_rect = label_text.get_rect(midbottom=(self.cx, self.y + self.h + LABEL_PADDING))
        surface.blit(label_text, label_rect)

        # Optional value text (accounting for available space)
        if self.show_value and self.data_font is not None:
            value_str = self._format_value(value)
            value_text = self.data_font.render(value_str, True, self.text_color)
            if self.vertical:
                # Top center for vertical (account for label padding)
                value_rect = value_text.get_rect(midtop=(self.cx, self.y + LABEL_PADDING))
            else:
                # Right middle for horizontal (account for available width)
                value_rect = value_text.get_rect(midright=(self.x + self.w - LABEL_PADDING, self.cy))
            surface.blit(value_text, value_rect)

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

        clamped = max(self.min_val, min(value, self.max_val))
        zero_ratio = self._zero_ratio()
        value_ratio = self._ratio(clamped)

        # Background fill if requested
        self._fill_background(surface)

        # Draw fill from zero toward value
        if self.vertical:
            zero_y = self.y + self.h - int(self.h * zero_ratio)
            val_y = self.y + self.h - int(self.h * value_ratio)
            if value_ratio > zero_ratio:
                # Positive fill upward from zero
                top = min(val_y, zero_y)
                bottom = max(val_y, zero_y)
                pygame.draw.rect(surface, self.pos_color, (self.x, top, self.w, bottom - top))
            elif value_ratio < zero_ratio:
                # Negative fill downward from zero
                top = min(val_y, zero_y)
                bottom = max(val_y, zero_y)
                pygame.draw.rect(surface, self.neg_color, (self.x, top, self.w, bottom - top))
            # Zero marker line
            pygame.draw.line(surface, WHITE, (self.x, zero_y), (self.x + self.w, zero_y), BORDER_WIDTH)
        else:
            zero_x = self.x + int(self.w * zero_ratio)
            val_x = self.x + int(self.w * value_ratio)
            if value_ratio > zero_ratio:
                left = min(val_x, zero_x)
                right = max(val_x, zero_x)
                pygame.draw.rect(surface, self.pos_color, (left, self.y, right - left, self.h))
            elif value_ratio < zero_ratio:
                left = min(val_x, zero_x)
                right = max(val_x, zero_x)
                pygame.draw.rect(surface, self.neg_color, (left, self.y, right - left, self.h))
            # Zero marker line
            pygame.draw.line(surface, WHITE, (zero_x, self.y), (zero_x, self.y + self.h), BORDER_WIDTH)

        self._draw_border(surface)

        # Label
        label_text = _get_small_font().render(self.label, True, self.text_color)
        label_rect = label_text.get_rect(midtop=(self.cx, self.y + self.h + LABEL_PADDING))
        surface.blit(label_text, label_rect)

        # Value (accounting for available vertical space)
        if self.show_value and self.data_font is not None:
            value_str = self._format_value(value)
            value_text = self.data_font.render(value_str, True, self.text_color)
            if self.vertical:
                # Left middle for vertical, vertically centered in box (so text outside the box)
                value_rect = value_text.get_rect(midright=(self.x - LABEL_PADDING, self.cy))
            else:
                # Right middle for horizontal, vertically centered in box
                value_rect = value_text.get_rect(midright=(self.x + self.w - LABEL_PADDING, self.cy))
            surface.blit(value_text, value_rect)

        return surface