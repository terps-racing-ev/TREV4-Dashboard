#!/usr/bin/env python3

from typing import Any, Optional, Tuple, Union
import pygame
import math
from pathlib import Path

from .colors import *
from .shared_data import LatestValuesTable

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FONT = str(ROOT_DIR / "assets" / "fonts" / "monofonto rg.otf")

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
    return tuple(
        round(start + (end - start) * clamped_ratio)
        for start, end in zip(min_color, max_color)
    )


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
        display_value = self._current_display_value()
        is_stale = self._signal_is_stale()

        # Background + border
        self._fill_background(surface)
        self._draw_border(surface)

        # Label (static font size)
        label_text = _get_small_font().render(self.label, True, self.text_color)
        label_rect = label_text.get_rect(topleft=(self.x + LABEL_PADDING, self.y + LABEL_PADDING))
        surface.blit(label_text, label_rect)

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
        value_text = value_font.render(value_str, True, self.text_color)
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
        display_value = self._current_display_value()
        is_stale = self._signal_is_stale()

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
            value_str = self._value_text(display_value, stale=is_stale)
            value_font = self._make_display_font(display_value)
            value_text = value_font.render(value_str, True, self.text_color)
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
        display_value = self._current_display_value()
        is_stale = self._signal_is_stale()

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
            # todo idk why we need -1, this whole class is fucked
            pygame.draw.line(surface, WHITE, (self.x, zero_y), (self.x + self.w - 1, zero_y), 2)
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
            pygame.draw.line(surface, WHITE, (zero_x, self.y), (zero_x, self.y + self.h), 2)

        self._draw_border(surface)

        # Label
        label_text = _get_small_font().render(self.label, True, self.text_color)
        label_rect = label_text.get_rect(midtop=(self.cx, self.y + self.h + LABEL_PADDING))
        surface.blit(label_text, label_rect)

        # Value (accounting for available vertical space)
        if self.show_value and self.data_font is not None:
            value_str = self._value_text(display_value, stale=is_stale)
            value_font = self._make_display_font(display_value)
            value_text = value_font.render(value_str, True, self.text_color)
            if self.vertical:
                # Left middle for vertical, vertically centered in box (so text outside the box)
                value_rect = value_text.get_rect(midright=(self.x - LABEL_PADDING, self.cy))
            else:
                # Right middle for horizontal, vertically centered in box
                value_rect = value_text.get_rect(midright=(self.x + self.w - LABEL_PADDING, self.cy))
            surface.blit(value_text, value_rect)

        return surface


class GradientGauge(Gauge):
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
        gradient_text: bool = True,
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
            shared_data=shared_data,
        )
        self.label = label
        self.min_color = min_color
        self.max_color = max_color
        self.gradient_text = gradient_text
        self.gradient_box = gradient_box
        self.gradient_border = gradient_border
        self.show_value = show_value
        self.data_font = self._make_value_font(show_value)

    def _gradient_color(self, value: int | float) -> Tuple[int, int, int]:
        if self.max_val == self.min_val:
            ratio = 0.0
        else:
            clamped = max(self.min_val, min(value, self.max_val))
            ratio = (clamped - self.min_val) / (self.max_val - self.min_val)
        return _interpolate_color(self.min_color, self.max_color, ratio)

    def update(self, surface: pygame.Surface) -> pygame.Surface:
        value = self._current_value()
        display_value = self._current_display_value()
        is_stale = self._signal_is_stale()
        mapped_color = self._gradient_color(value)

        if self.gradient_box:
            pygame.draw.rect(surface, mapped_color, (self.x, self.y, self.w, self.h))
        else:
            self._fill_background(surface)

        border_color = mapped_color if self.gradient_border else self.border_color
        if border_color is not None:
            pygame.draw.rect(surface, border_color, (self.x, self.y, self.w, self.h), BORDER_WIDTH)

        render_text_color = mapped_color if self.gradient_text else self.text_color
        label_text = _get_small_font().render(self.label, True, render_text_color)
        if self.show_value:
            label_rect = label_text.get_rect(topleft=(self.x + LABEL_PADDING, self.y + LABEL_PADDING))
        else:
            label_rect = label_text.get_rect(center=(self.cx, self.cy))
        surface.blit(label_text, label_rect)

        if self.show_value and self.data_font is not None:
            value_str = self._value_text(display_value, stale=is_stale)
            available_height = self.h - label_rect.height - 2 * LABEL_PADDING
            if isinstance(display_value, str):
                value_font = self._make_value_font(True, value_str)
            else:
                template = value_str
                size = int(min(self.w / len(template) / FONT_WIDTH_RATIO, available_height / FONT_HEIGHT_RATIO))
                value_font = pygame.font.Font(DEFAULT_FONT, max(8, size))
            value_text = value_font.render(value_str, True, render_text_color)
            center_y = self.y + label_rect.height + LABEL_PADDING + available_height // 2
            value_rect = value_text.get_rect(center=(self.cx, center_y))
            surface.blit(value_text, value_rect)

        return surface


