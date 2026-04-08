#!/usr/bin/env python3
"""
TREV4 Dashboard - Pretty Test Version
Hardcoded layout for visual testing. Driven by pretty_gauges.json.
Simulates CAN data internally so no hardware is needed.
"""

from __future__ import annotations

import math
import time
import sys
import json
import threading
from pathlib import Path
from typing import Optional, Any, Dict
from python.shared_data import LatestValuesTable
from python.constants.events import *
import python.constants.fonts as fonts

import pygame
import gpiozero
from gpiozero.pins.lgpio import LGPIOFactory
gpiozero.Device.pin_Factory = LGPIOFactory
from gpiozero import Button

BLACK       = (0,   0,   0)
NEAR_BLACK  = (10,  10,  12)
DARK_PANEL  = (18,  18,  22)
PANEL       = (24,  24,  30)
PANEL_LIGHT = (36,  36,  44)
WHITE       = (255, 255, 255)
DIM_WHITE   = (180, 180, 190)
GRID_LINE   = (40,  40,  50)

RED         = (220,  30,  30)
RED_BRIGHT  = (255,  50,  50)
AMBER       = (255, 160,   0)
AMBER_DIM   = (180, 100,   0)
GREEN       = ( 40, 220,  80)
GREEN_DIM   = ( 20, 120,  40)
CYAN        = (  0, 210, 220)
BLUE        = ( 50, 120, 255)

# Tire temp zones
TEMP_COLD   = ( 60, 120, 220)
TEMP_OPT    = ( 40, 220,  80)
TEMP_HOT    = (255,  80,  30)


# ─────────────────────────────────────────────
#  Drawing helpers
# ─────────────────────────────────────────────

def draw_rounded_rect(surf, color, rect, radius=8, border=0, border_color=None):
    """Fill a rounded rectangle, optionally with a border."""
    x, y, w, h = rect
    pygame.draw.rect(surf, color, (x+radius, y, w-2*radius, h))
    pygame.draw.rect(surf, color, (x, y+radius, w, h-2*radius))
    for cx, cy in [(x+radius, y+radius), (x+w-radius, y+radius),
                   (x+radius, y+h-radius), (x+w-radius, y+h-radius)]:
        pygame.draw.circle(surf, color, (cx, cy), radius)
    if border and border_color:
        pygame.draw.rect(surf, border_color, (x+radius, y, w-2*radius, h), border)
        pygame.draw.rect(surf, border_color, (x, y+radius, w, h-2*radius), border)
        for cx, cy in [(x+radius, y+radius), (x+w-radius, y+radius),
                       (x+radius, y+h-radius), (x+w-radius, y+h-radius)]:
            pygame.draw.circle(surf, border_color, (cx, cy), radius, border)


def lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def bar_color(pct):
    """Green → Amber → Red gradient for fill bars."""
    if pct < 0.6:
        return lerp_color(GREEN, AMBER, pct / 0.6)
    else:
        return lerp_color(AMBER, RED_BRIGHT, (pct - 0.6) / 0.4)


def temp_color(val, lo, hi):
    """Cold-blue → optimal-green → hot-red for temperature."""
    mid = (lo + hi) / 2
    if val <= mid:
        return lerp_color(TEMP_COLD, TEMP_OPT, (val - lo) / max(1, mid - lo))
    else:
        return lerp_color(TEMP_OPT, TEMP_HOT, (val - mid) / max(1, hi - mid))


# ─────────────────────────────────────────────
#  Font cache
# ─────────────────────────────────────────────
_font_cache: Dict[tuple, pygame.font.Font] = {}

def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _font_cache:
        # Try to load the project font; fall back to a system monospace
        for path in [
            fonts.jetbrains,
            fonts.jetbrains_backslash
        ]:
            try:
                _font_cache[key] = pygame.font.Font(path, size)
                return _font_cache[key]
            except Exception:
                pass
        # Fallback
        name = pygame.font.match_font("couriernew,dejavusansmono,monospace", bold=bold)
        _font_cache[key] = pygame.font.Font(name, size)
    return _font_cache[key]


def render_text(surf, text, size, color, cx, cy, bold=False, anchor="center"):
    font = get_font(size, bold)
    img = font.render(text, True, color)
    r = img.get_rect()
    if anchor == "center":
        r.center = (cx, cy)
    elif anchor == "midleft":
        r.midleft = (cx, cy)
    elif anchor == "midright":
        r.midright = (cx, cy)
    elif anchor == "topleft":
        r.topleft = (cx, cy)
    surf.blit(img, r)
    return r


# ─────────────────────────────────────────────
#  Gauge base
# ─────────────────────────────────────────────
class Gauge:
    def __init__(self, signal, label, min_val, max_val, shared_data: LatestValuesTable):
        self.signal = signal
        self.label = label
        self.min_val = min_val
        self.max_val = max_val
        self.shared_data = shared_data

    def get_value(self) -> float:
        v = self.shared_data.get_signal(self.signal)
        return float(v) if v is not None else None 

    def clamp_pct(self, val) -> float:
        if val is None:
            return 0.0
        r = self.max_val - self.min_val
        if r == 0:
            return 0.0
        return max(0.0, min(1.0, (val - self.min_val) / r))

    def update(self, surf: pygame.Surface):
        pass


# ─────────────────────────────────────────────
#  Big Speedometer (centre-piece arc gauge)
# ─────────────────────────────────────────────
class SpeedArcGauge(Gauge):
    """
    Large semi-circular arc speedometer.
    box_xywh: (x, y, w, h) — bounding box; cx/cy derived from centre, radius from w//2.
    """
    def __init__(self, signal, label, min_val, max_val, box_xywh, shared_data,
                 unit="MPH", decimal_places=0):
        super().__init__(signal, label, min_val, max_val, shared_data)
        x, y, w, h = box_xywh
        self.cx = x + w // 2
        self.cy = y + h // 2
        self.radius = w // 2
        self.unit = unit
        self.decimal_places = decimal_places

    def update(self, surf):
        val = self.get_value()
        pct = self.clamp_pct(val)
        cx, cy, r = self.cx, self.cy, self.radius

        # ── Background arc (full sweep) ──────────────────────────
        start_deg = 210
        end_deg   = -30          # 240° sweep, going clockwise
        arc_w = 14

        # Draw tick marks
        for i in range(11):
            t = i / 10
            angle_deg = start_deg - t * 240
            angle = math.radians(angle_deg)
            is_major = True
            tick_len = 18 if is_major else 10
            tick_w = 3 if is_major else 1
            x1 = cx + math.cos(angle) * (r - arc_w - 4)
            y1 = cy - math.sin(angle) * (r - arc_w - 4)
            x2 = cx + math.cos(angle) * (r - arc_w - 4 - tick_len)
            y2 = cy - math.sin(angle) * (r - arc_w - 4 - tick_len)
            #pygame.draw.line(surf, PANEL_LIGHT, (int(x1), int(y1)), (int(x2), int(y2)), tick_w)
            # Tick label
            val_at_tick = self.min_val + t * (self.max_val - self.min_val)
            lx = cx + math.cos(angle) * (r - arc_w - 28)
            ly = cy - math.sin(angle) * (r - arc_w - 28)
            render_text(surf, str(int(val_at_tick)), 13, PANEL_LIGHT, int(lx), int(ly))

        # Track arc (dim)
        #rect = pygame.Rect(cx - r, cy - r, r*2, r*2)
        #pygame.draw.arc(surf, PANEL_LIGHT, rect,math.radians(end_deg), math.radians(start_deg), arc_w)

        # Active fill arc
        #if pct > 0:
            #fill_end = start_deg - pct * 240
            #fill_color = bar_color(pct)
            #pygame.draw.arc(surf, fill_color, rect,math.radians(fill_end), math.radians(start_deg), arc_w)

        # ── Centre readout ────────────────────────────────────────
        if val is None:
            render_text(surf, ':(', 72, WHITE, cx, cy - 10, bold=True)
        else:
            fmt = f"{val:.{self.decimal_places}f}"
            render_text(surf, fmt, 72, WHITE, cx, cy - 10, bold=True)
            render_text(surf, self.unit, 16, DIM_WHITE, cx, cy + 46)
            render_text(surf, self.label, 13, PANEL_LIGHT, cx, cy + 66)


# ─────────────────────────────────────────────
#  Vertical bar gauge (battery SoC / torque)
# ─────────────────────────────────────────────
class VerticalBarGauge(Gauge):
    def __init__(self, signal, label, min_val, max_val, x, y, w, h, shared_data,
                 fill_color=None, show_value=True, unit="", decimal_places=0,
                 signed=False, pos_color=None, neg_color=None):
        super().__init__(signal, label, min_val, max_val, shared_data)
        self.x, self.y, self.w, self.h = x, y, w, h
        self._fill_color = fill_color
        self.show_value = show_value
        self.unit = unit
        self.decimal_places = decimal_places
        self.signed = signed
        self.pos_color = pos_color or GREEN
        self.neg_color = neg_color or RED

    def update(self, surf):
        val = self.get_value()
        x, y, w, h = self.x, self.y, self.w, self.h
        pad = 3

        # Panel background
        draw_rounded_rect(surf, PANEL, (x, y, w, h), radius=6)
        pygame.draw.rect(surf, PANEL_LIGHT, (x, y, w, h), 1)

        inner_h = h - 40  # leave room for label at bottom
        bar_x = x + pad
        bar_w = w - pad*2

        if self.signed:
            mid_val = (self.min_val + self.max_val) / 2
            mid_y = y + 4 + inner_h // 2
            if val >= mid_val:
                pct = (val - mid_val) / max(1, self.max_val - mid_val)
                fill_h = int(pct * (inner_h // 2 - 4))
                color = self.pos_color
                bar_y = mid_y - fill_h
                pygame.draw.rect(surf, color, (bar_x, bar_y, bar_w, fill_h))
            else:
                pct = (mid_val - val) / max(1, mid_val - self.min_val)
                fill_h = int(pct * (inner_h // 2 - 4))
                color = self.neg_color
                bar_y = mid_y
                pygame.draw.rect(surf, color, (bar_x, bar_y, bar_w, fill_h))
            # Centre line
            pygame.draw.line(surf, DIM_WHITE, (x, mid_y), (x+w, mid_y), 1)
        else:
            pct = self.clamp_pct(val)
            fill_h = int(pct * (inner_h - 8))
            color = self._fill_color or bar_color(pct)
            bar_y = y + 4 + (inner_h - 8) - fill_h
            pygame.draw.rect(surf, color, (bar_x, bar_y, bar_w, fill_h))

        # Label at bottom
        render_text(surf, self.label, 11, DIM_WHITE, x + w//2, y + h - 14)

        # Value overlay
        if self.show_value:
            if val is None:
                render_text(surf, '-', 14, WHITE, x + w//2, y + 16)
            else:
                fmt = f"{val:.{self.decimal_places}f}"
                render_text(surf, fmt, 14, WHITE, x + w//2, y + 16)


# ─────────────────────────────────────────────
#  Compact numeric readout card
# ─────────────────────────────────────────────
class NumericCard(Gauge):
    def __init__(self, signal, label, min_val, max_val, x, y, w, h, shared_data,
                 unit="", decimal_places=1, warn_pct=0.85, crit_pct=0.95):
        super().__init__(signal, label, min_val, max_val, shared_data)
        self.x, self.y, self.w, self.h = x, y, w, h
        self.unit = unit
        self.decimal_places = decimal_places
        self.warn_pct = warn_pct
        self.crit_pct = crit_pct

    def update(self, surf):
        val = self.get_value()
        pct = self.clamp_pct(val)
        x, y, w, h = self.x, self.y, self.w, self.h

        # Colour based on threshold
        if pct >= self.crit_pct:
            accent = RED_BRIGHT
        elif pct >= self.warn_pct:
            accent = AMBER
        else:
            accent = CYAN

        # Panel
        draw_rounded_rect(surf, PANEL, (x, y, w, h), radius=6)
        # Left accent stripe
        pygame.draw.rect(surf, accent, (x, y+6, 3, h-12))

        # Label
        render_text(surf, self.label, 11, DIM_WHITE, x + 12, y + 13, anchor="midleft")
        # Value
        if val is None:
            render_text(surf, '-', 22, WHITE, x + w - 8, y + h//2, anchor="midright")
        else:
            fmt = f"{val:.{self.decimal_places}f}"
            if self.unit:
                fmt += f" {self.unit}"
            render_text(surf, fmt, 22, WHITE, x + w - 8, y + h//2, anchor="midright")

        # Thin fill bar at base
        bar_w = int((w - 6) * pct)
        pygame.draw.rect(surf, (*accent[:3], 120), (x+3, y+h-4, bar_w, 3))


# ─────────────────────────────────────────────
#  Tire temperature quad widget
# ─────────────────────────────────────────────
class TireTempsWidget:
    """
    Draws 4 tire cells (FL, FR, RL, RR) in a car-outline layout.
    Signals: TTempFL, TTempFR, TTempRL, TTempRR
    """
    def __init__(self, box_xywh, FL: str, FR: str, RL: str, RR: str, shared_data, min_val=20, max_val=120):
        x, y, w, h = box_xywh
        self.cx = x + w // 2
        self.cy = y + h // 2
        self.shared_data = shared_data
        self.min_val = min_val
        self.max_val = max_val
        self.corners = [
            ("FL", FL, -48, -28),
            ("FR", FR,  48, -28),
            ("RL", RL, -48,  28),
            ("RR", RR,  48,  28),
        ]
        self.tw, self.th = 52, 32

    def get_val(self, sig):
        v = self.shared_data.get_signal(sig)
        return float(v) if v is not None else None

    def update(self, surf):
        cx, cy = self.cx, self.cy

        # Car body outline (simple rectangle)
        body_w, body_h = 40, 70
        draw_rounded_rect(surf, PANEL, (cx - body_w//2, cy - body_h//2, body_w, body_h), radius=6)
        pygame.draw.rect(surf, PANEL_LIGHT, (cx - body_w//2, cy - body_h//2, body_w, body_h), 1)
        render_text(surf, "TREV4", 9, DIM_WHITE, cx, cy)

        for label, sig, dx, dy in self.corners:
            val = self.get_val(sig)
            col = PANEL if val is None else temp_color(val, self.min_val, self.max_val)
            tx = cx + dx - self.tw//2
            ty = cy + dy - self.th//2
            draw_rounded_rect(surf, col, (tx, ty, self.tw, self.th), radius=4)
            render_text(surf, label, 10, BLACK, tx + self.tw//2, ty + 10)
            if val is None:
                render_text(surf, '-', 14, BLACK, tx + self.tw//2, ty + 22, bold=True)
            else:
                render_text(surf, f"{val:.0f}°", 14, BLACK, tx + self.tw//2, ty + 22, bold=True)


# ─────────────────────────────────────────────
#  State-of-charge arc gauge (thin ring)
# ─────────────────────────────────────────────
class SoCRingGauge(Gauge):
    def __init__(self, signal, box_xywh, shared_data,
                 min_val=0, max_val=100, label="SOC"):
        super().__init__(signal, label, min_val, max_val, shared_data)
        x, y, w, h = box_xywh
        self.cx = x + w // 2
        self.cy = y + h // 2
        self.radius = w // 2

    def update(self, surf):
        val = self.get_value()
        pct = self.clamp_pct(val)
        cx, cy, r = self.cx, self.cy, self.radius

        rect = pygame.Rect(cx - r, cy - r, r*2, r*2)

        # Track
        pygame.draw.arc(surf, PANEL_LIGHT, rect,
                        math.radians(-210), math.radians(30), 8)

        # Fill (counterclockwise from top-left, going right)
        if pct > 0:
            fill_color = lerp_color(RED, GREEN, pct)
            end_a = 30 - pct * 240
            pygame.draw.arc(surf, fill_color, rect,
                            math.radians(end_a), math.radians(30), 8)

        # Centre text
        if val is None:
            render_text(surf, '-', 26, WHITE, cx, cy - 4, bold=True)
        else:
            render_text(surf, f"{val:.0f}%", 26, WHITE, cx, cy - 4, bold=True)
        render_text(surf, self.label, 11, DIM_WHITE, cx, cy + 18)


# ─────────────────────────────────────────────
#  RPM / motor speed horizontal bar
# ─────────────────────────────────────────────
class RPMBar(Gauge):
    def __init__(self, signal, x, y, w, h, shared_data,
                 min_val=0, max_val=6000, label="RPM", decimal_places=0):
        super().__init__(signal, label, min_val, max_val, shared_data)
        self.x, self.y, self.w, self.h = x, y, w, h
        self.decimal_places = decimal_places

    def update(self, surf):
        val = self.get_value()
        pct = self.clamp_pct(val)
        x, y, w, h = self.x, self.y, self.w, self.h

        draw_rounded_rect(surf, PANEL, (x, y, w, h), radius=4)

        # Segmented look (20 segments)
        segs = 24
        seg_gap = 2
        seg_w = (w - 8 - (segs-1)*seg_gap) // segs
        active = int(pct * segs)
        for i in range(segs):
            sx = x + 4 + i * (seg_w + seg_gap)
            sy = y + 4
            sh = h - 8
            color = bar_color(i / segs) if i < active else PANEL_LIGHT
            pygame.draw.rect(surf, color, (sx, sy, seg_w, sh))

        # Label + value
        render_text(surf, self.label, 11, DIM_WHITE, x + 8, y + h//2, anchor="midleft")
        if val is None:
            render_text(surf, '-', 14, WHITE, x + w - 8, y + h//2, anchor="midright")
        else:
            fmt = f"{val:.{self.decimal_places}f}"
            render_text(surf, fmt, 14, WHITE, x + w - 8, y + h//2, anchor="midright")


# ─────────────────────────────────────────────
#  Header / status bar
# ─────────────────────────────────────────────
class StatusBar:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def update(self, surf):
        x, y, w, h = self.x, self.y, self.w, self.h
        draw_rounded_rect(surf, PANEL, (x, y, w, h), radius=0)
        # Left: team name
        render_text(surf, "TREV4", 16, RED_BRIGHT, x+14, y+h//2, bold=True, anchor="midleft")
        # Centre: lap / status placeholder
        render_text(surf, "TERPS RACING EV  ·  LIVE TELEMETRY", 11, PANEL_LIGHT, x+w//2, y+h//2)
        # Right: clock
        now = time.strftime("%H:%M:%S")
        render_text(surf, now, 13, DIM_WHITE, x+w-12, y+h//2, anchor="midright")
        # Bottom divider line
        pygame.draw.line(surf, RED, (x, y+h-1), (x+w, y+h-1), 2)


# ─────────────────────────────────────────────
#  Warning light strip
# ─────────────────────────────────────────────
class WarningLights:

    def __init__(self, box_xywh, IMD: str, AMS: str, BSPD: str, APPS: str, BRAKE: str, shared_data=None):
        x, y, w, h = box_xywh
        self.cx = x + w // 2
        self.y = y
        self.shared_data = shared_data
        self.LIGHTS = [
            ("IMD",   IMD,   RED,   1.0),
            ("AMS",   AMS,   RED,   1.0),
            ("BSPD",  BSPD,  RED,   1.0),
            ("APPS",  APPS,  AMBER, 1.0),
            ("BRK",   BRAKE, AMBER, 1.0),
        ]

    def update(self, surf):
        n = len(self.LIGHTS)
        lw, lh, gap = 60, 22, 6
        total = n * lw + (n-1) * gap
        sx = self.cx - total // 2
        for i, (name, sig, color, thresh) in enumerate(self.LIGHTS):
            v = self.shared_data.get_signal(sig)
            active = (v is not None and float(v) >= thresh)
            lx = sx + i * (lw + gap)
            bg = color if active else PANEL
            draw_rounded_rect(surf, bg, (lx, self.y, lw, lh), radius=4)
            text_col = BLACK if active else PANEL_LIGHT
            render_text(surf, name, 11, text_col, lx + lw//2, self.y + lh//2, bold=active)


# ─────────────────────────────────────────────
#  new_dash-style components
#  Colour palette matching new_dash.py exactly
# ─────────────────────────────────────────────

_ND_CELL_BG    = (13,  13,  16)
_ND_BORDER     = (37,  37,  48)
_ND_BORDER_HI  = (56,  56,  74)
_ND_ORANGE     = (255, 106,   0)
_ND_CYAN       = (  0, 212, 232)
_ND_GREEN      = (  0, 224,  96)
_ND_AMBER      = (255, 184,   0)
_ND_RED        = (255,  37,  37)
_ND_WHITE      = (242, 242, 242)
_ND_DIM        = ( 82,  82, 106)
_ND_LABEL      = (114, 114, 138)
_ND_DARK_HDR   = ( 10,  10,  12)
_ND_DARK_FAULT = (  6,   6,   8)
_ND_TIRE_COLD  = ( 30,  60, 160)
_ND_TIRE_OPT   = (  0, 140,  50)
_ND_TIRE_HOT   = (200,  40,  10)
_ND_CENTER_BG  = (  8,   8,  11)
_ND_AQUA        = (  0, 210, 220)


def _nd_gauge_color(pct):
    if pct < 0.6:
        return lerp_color((0, 210, 70), (255, 180, 0), pct / 0.6)
    return lerp_color((255, 180, 0), (255, 30, 30), (pct - 0.6) / 0.4)


def _nd_draw_arc(surf, cx, cy, r, start_deg, end_deg, width, color, segments=120):
    """Draw an arc as line segments to avoid pygame aliasing."""
    delta = (end_deg - start_deg) % 360
    if delta < 0.01:
        return
    pts = []
    for i in range(segments + 1):
        a = math.radians(start_deg + (i / segments) * delta)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    for i in range(len(pts) - 1):
        pygame.draw.line(surf, color, pts[i], pts[i + 1], width)


class DarkStatusBar:
    """Header bar styled like new_dash: dark bg, orange bottom line, orange TREV4."""

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def update(self, surf):
        x, y, w, h = self.x, self.y, self.w, self.h
        surf.fill(_ND_DARK_HDR, (x, y, w, h))
        pygame.draw.line(surf, _ND_ORANGE, (x, y + h - 2), (x + w, y + h - 2), 2)
        cy = y + h // 2
        render_text(surf, "TREV4", 11, _ND_ORANGE, x + 10, cy, bold=True, anchor="midleft")
        render_text(surf, "TERPS RACING EV \u00b7 LIVE TELEMETRY", 8, _ND_DIM, x + w // 2, cy)
        render_text(surf, time.strftime("%H:%M:%S"), 10, _ND_LABEL, x + w - 10, cy, anchor="midright")


class ShiftLightsGauge(Gauge):
    """16-dot RPM shift light bar across the very top."""

    _NUM = 16

    def __init__(self, signal, min_val, max_val, box_xywh, shared_data, label=""):
        x, y, w, h = box_xywh
        super().__init__(signal, label, min_val, max_val, shared_data)
        self.x, self.y, self.w, self.h = x, y, w, h

    def update(self, surf):
        x, y, w, h = self.x, self.y, self.w, self.h
        pct = self.clamp_pct(self.get_value())
        active = int(pct * self._NUM)
        surf.fill(_ND_DARK_FAULT, (x, y, w, h))
        dot_w = (w - 8 - (self._NUM - 1) * 3) // self._NUM
        for i in range(self._NUM):
            col = (_ND_GREEN if i < 5 else _ND_AMBER if i < 11 else _ND_RED) if i < active else _ND_BORDER
            pygame.draw.rect(surf, col, (x + 4 + i * (dot_w + 3), y + 2, dot_w, h - 4), border_radius=2)


class DarkCell(Gauge):
    """Cell card styled like new_dash: dark bg, left accent stripe, label top-left, big value, bottom bar."""

    def __init__(self, signal, label, min_val, max_val, box_xywh, shared_data,
                 unit="", decimal_places=1, accent_color=None, value_color=None, last=False):
        x, y, w, h = box_xywh
        super().__init__(signal, label, min_val, max_val, shared_data)
        self.x, self.y, self.w, self.h = x, y, w, h
        self.unit = unit
        self.decimal_places = decimal_places
        self.accent = tuple(accent_color) if accent_color else _ND_BORDER_HI
        self.value_color = tuple(value_color) if value_color else _ND_WHITE
        self.last = last

    def update(self, surf):
        x, y, w, h = self.x, self.y, self.w, self.h
        val = self.get_value()
        pct = self.clamp_pct(val)
        surf.fill(_ND_CELL_BG, (x, y, w, h))
        bar_w = int(max(0.0, min(1.0, pct)) * w)
        if bar_w > 0:
            alpha_bar = pygame.Surface((bar_w, h), pygame.SRCALPHA)
            alpha_bar.fill((*self.accent, 75))
            surf.blit(alpha_bar, (x, y))
        if not self.last:
            pygame.draw.line(surf, _ND_BORDER, (x, y + h - 1), (x + w, y + h - 1), 1)
        pygame.draw.rect(surf, self.accent, (x, y + 6, 3, h - 12), border_radius=1)
        render_text(surf, self.label, 18, self.value_color, x + 14, y + 16, anchor="midleft")
        if val is None:
            render_text(surf, '-', 28, self.value_color, x + 14, y + h - 14, anchor="midleft")
        else:
            val_str = f"{val:.{self.decimal_places}f}"
            render_text(surf, val_str, 28, self.value_color, x + 14, y + h - 14, anchor="midleft")
            if self.unit:
                val_px_w = get_font(28).size(val_str)[0]
                render_text(surf, self.unit, 14, self.value_color, x + 14 + val_px_w + 3, y + h - 16, anchor="midleft")
        


class CellVoltageCard:
    """Min/max cell voltage dual-readout card styled like new_dash."""

    def __init__(self, signal_min, signal_max, box_xywh, shared_data, last=False):
        x, y, w, h = box_xywh
        self.x, self.y, self.w, self.h = x, y, w, h
        self.signal_min = signal_min
        self.signal_max = signal_max
        self.shared_data = shared_data
        self.last = last

    def update(self, surf):
        x, y, w, h = self.x, self.y, self.w, self.h
        surf.fill(_ND_CELL_BG, (x, y, w, h))
        if not self.last:
            pygame.draw.line(surf, _ND_BORDER, (x, y + h - 1), (x + w, y + h - 1), 1)
        pygame.draw.rect(surf, _ND_BORDER_HI, (x, y + 6, 3, h - 12), border_radius=1)
        render_text(surf, "CELL VOLTAGE", 18,"white", x + 14, y + 16, anchor="midleft")
        vmin_v = self.shared_data.get_signal(self.signal_min)
        vmax_v = self.shared_data.get_signal(self.signal_max)
        vmin = float(vmin_v) if vmin_v is not None else None
        vmax = float(vmax_v) if vmax_v is not None else None
        render_text(surf, '-' if vmin is None else f"{vmin:.2f}", 20, _ND_AMBER, x + 14, y + h // 2 + 6, anchor="midleft")
        render_text(surf, '-' if vmax is None else f"{vmax:.2f}", 20, _ND_CYAN, x + w // 2 + 10, y + h // 2 + 6, anchor="midleft")


class DarkSpeedArc(Gauge):
    """Large arc speedometer styled exactly like new_dash."""

    _ARC_R     = 108
    _ARC_W     = 20
    _ARC_START = 135.0
    _ARC_SWEEP = 270.0
    _BG_ARC    = (30, 30, 42)

    def __init__(self, signal, brake_signal, throttle_signal, min_val, max_val, box_xywh, shared_data,
                 unit="MPH", decimal_places=0, label=""):
        x, y, w, h = box_xywh
        super().__init__(signal, label, min_val, max_val, shared_data)
        self.brake_signal = brake_signal
        self.throttle_signal = throttle_signal
        self.x, self.y, self.w, self.h = x, y, w, h
        self.cx = x + w // 2
        # Mirrors new_dash: GCY = MAIN_Y + (MAIN_H - CENTER_BOTTOM_H) // 2 + 10
        # With box (175, 36, 450, 356): cy = 36 + (356-60)//2 + 10 = 194
        self.cy = y + (h - 60) // 2 + 10
        self.unit = unit
        self.decimal_places = decimal_places

    def get_brake_value(self):
        v = self.shared_data.get_signal(self.brake_signal)
        return float(v) if v is not None else None

    def get_throttle_value(self):
        v = self.shared_data.get_signal(self.throttle_signal)
        return float(v) if v is not None else None

    def get_brake_pct(self, brake_val):
        if brake_val is None:
            return 0.0
        return max(0.0, min(1.0, brake_val / 100.0))

    def get_throttle_pct(self, throttle_val):
        if throttle_val is None:
            return 0.0
        return max(0.0, min(1.0, throttle_val / 100.0))

    def update(self, surf):
        x, y, w, h = self.x, self.y, self.w, self.h
        val = self.get_value()
        pct = self.clamp_pct(val)
        brake_val = self.get_brake_value()
        throttle_val = self.get_throttle_value()
        brake_pct = self.get_brake_pct(brake_val)
        throttle_pct = self.get_throttle_pct(throttle_val)
        cx, cy = self.cx, self.cy

        surf.fill(_ND_CENTER_BG, (x, y, w, h))
        # Column border lines
        pygame.draw.line(surf, _ND_BORDER, (x, y), (x, y + h), 1)
        pygame.draw.line(surf, _ND_BORDER, (x + w - 1, y), (x + w - 1, y + h), 1)

        # # Background arc
        # _nd_draw_arc(surf, cx, cy, self._ARC_R,
        #              self._ARC_START, self._ARC_START + self._ARC_SWEEP,
        #              self._ARC_W, self._BG_ARC)
        # # Fill arc
        # if pct > 0:
        #     _nd_draw_arc(surf, cx, cy, self._ARC_R,
        #                  self._ARC_START, self._ARC_START + pct * self._ARC_SWEEP,
        #                  self._ARC_W, _nd_gauge_color(pct))

        #ALTERNATIVE SCORLLING TRANSPARENT COLOR
        if val is not None:
            # Vertical fill from bottom to top based on speed percent
            fill_h = int(pct * h)
            fill_y = y + h - fill_h
            overlay = pygame.Surface((w, fill_h), pygame.SRCALPHA)
            overlay.fill((*_nd_gauge_color(pct), 25))
            surf.blit(overlay, (x, fill_y))

            # Top bar at the top edge of the scrolling fill area
            if fill_h > 0:
                bar_y = max(fill_y, y)
                pygame.draw.rect(surf, _nd_gauge_color(pct), (x, bar_y, w, 10))
        
        #border
        rect = pygame.Rect(cx-80, cy-80, 160, 160)
        radius = 16
        border_width = 4

        # solid black background behind outline
        pygame.draw.rect(surf, BLACK, rect, width=0, border_radius=radius)
        pygame.draw.rect(surf, _nd_gauge_color(pct), rect, width=border_width, border_radius=radius)

        # brake/throttle dashes
        dashes = 13
        bar_w = 8
        total_w = 240
        padding = 14
        available_w = total_w - padding * 2
        gap = max(2, (available_w - dashes * bar_w) / (dashes - 1))

        bar_rect_x = cx - 120
        pygame.draw.rect(surf, BLACK, pygame.Rect(bar_rect_x, cy + 120, total_w, 35), width=0, border_radius=4)
        pygame.draw.rect(surf, _nd_gauge_color(pct), pygame.Rect(bar_rect_x, cy + 120, total_w, 35), width=border_width, border_radius=4)

        num_brake_dashes = int((brake_pct + .05) * 6)
        num_throttle_dashes = int((throttle_pct + .05) * 6)
        for i in range(dashes):
            dash_x = int(bar_rect_x + padding + i * (bar_w + gap))
            if i == 6:
                color = WHITE
            elif i < 6:
                if 5-i < num_brake_dashes:
                    color = RED
                else:
                    color = _ND_BORDER
            else:
                if i - 7 < num_throttle_dashes:
                    color = GREEN
                else:
                    color = _ND_BORDER
            pygame.draw.rect(surf, color, (dash_x, cy + 125, bar_w, 35-10), border_radius=2)

        if val is None:
            render_text(surf, '-', 86, _ND_WHITE, cx, cy - 6, bold=True)
        else:
            val_str = (("00" if val < 10 else ("0" if val < 100 else "")) + str(int(val))) if self.decimal_places == 0 else f"{val:.{self.decimal_places}f}"
            render_text(surf, val_str, 86, _ND_WHITE, cx, cy - 6, bold=True)
        render_text(surf, self.unit, 24, _ND_ORANGE, cx, cy + 46)
        render_text(surf, "BRAKE PRES    THROTTLE", 12, _ND_ORANGE, cx-7, cy + 160)

class GMeter(Gauge):
    #its a fucking g meter bro isnt ts tuff
    #radius is in G, as in the max G force that is at the edge
    def __init__(self, x_signal, y_signal, radius, box_xywh, shared_data, label="G-Meter"):
        
        x, y, w, h = box_xywh
        if w != h:
            raise ValueError("GMeter box must be square (w == h)")
        
        self.x_signal = x_signal
        self.y_signal = y_signal
        self.shared_data = shared_data
        self.x, self.y, self.w, self.h = x, y, w, h
        self.cx = x + w // 2
        self.cy = y + h // 2
        self.radius = radius
        self.label = label

    def update(self, surf):
        x, y, w, h = self.x, self.y, self.w, self.h
        g_x = self.shared_data.get_signal(self.x_signal)
        g_y = self.shared_data.get_signal(self.y_signal)
        g_x_val = float(g_x) if g_x is not None else 0.
        g_y_val = float(g_y) if g_y is not None else 0.
        surf.fill(_ND_CENTER_BG, (x, y, w, h))
        
        #pygame.draw.line(surf, _ND_BORDER, (self.cx - self.radius, self.cy), (self.cx + self.radius, self.cy), 1)
        #pygame.draw.line(surf, _ND_BORDER, (self.cx, self.cy - self.radius), (self.cx, self.cy + self.radius), 1)
         
        #graph background
        pygame.draw.arc(surf, _ND_BORDER, pygame.Rect(self.cx - 0.4 * w, self.cy - 0.4 * h, 0.8 * w, 0.8 * h), 0, 2*3.14159, 1)
        pygame.draw.arc(surf, _ND_BORDER, pygame.Rect(self.cx - 0.2 * w, self.cy - 0.2 * h, 0.4 * w, 0.4 * h), 0, 2*3.14159, 1)
        pygame.draw.arc(surf, _ND_BORDER, pygame.Rect(self.cx - 0.1 * w, self.cy - 0.1 * h, 0.2 * w, 0.2 * h), 0, 2*3.14159, 1)
        pygame.draw.arc(surf, _ND_BORDER, pygame.Rect(self.cx - 0.3 * w, self.cy - 0.3 * h, 0.6 * w, 0.6 * h), 0, 2*3.14159, 1)
        pygame.draw.line(surf, _ND_BORDER, (self.cx - 0.4 * w, self.cy), (self.cx + 0.4 * w, self.cy), 1)
        pygame.draw.line(surf, _ND_BORDER, (self.cx, self.cy - 0.4 * h), (self.cx, self.cy + 0.4 * h), 1)

        xdot = self.cx + int((g_x_val / self.radius) * 0.4 * w)
        ydot = self.cy - int((g_y_val / self.radius) * 0.4 * h)

        mag = math.sqrt(g_x_val**2 + g_y_val**2)

        pygame.draw.line(surf, _ND_RED, (self.cx, self.cy), (xdot, ydot), 1)

        pygame.draw.circle(surf, _ND_AQUA, (xdot, ydot), 4)
        render_text(surf, self.label, 12, _ND_WHITE, self.cx, self.cy + self.radius + 14)
        render_text(surf, str(self.radius), 12, _ND_WHITE, self.cx + 0.4 * w, self.cy)
        render_text(surf, str(self.radius), 12, _ND_WHITE, self.cx, self.cy - 0.4 * h)
        render_text(surf, "MAG: " + str(format(round(mag, 2), ".2f")), 12, _ND_WHITE, self.cx, self.cy+0.4*h)

        


class DarkTireQuad:
    """2×2 tire temperature grid styled like new_dash."""

    def __init__(self, box_xywh, FL, FR, RL, RR, shared_data):
        x, y, w, h = box_xywh
        self.x, self.y, self.w, self.h = x, y, w, h
        self.corners = [(FL, "FL"), (FR, "FR"), (RL, "RL"), (RR, "RR")]
        self.shared_data = shared_data

    def update(self, surf):
        x, y, w, h = self.x, self.y, self.w, self.h
        hw, hh = w // 2, h // 2
        for i, (sig, _lbl) in enumerate(self.corners):
            tx, ty = x + (i % 2) * hw, y + (i // 2) * hh
            v = self.shared_data.get_signal(sig)
            val = float(v) if v is not None else None
            bg = _ND_BORDER if val is None else (_ND_TIRE_COLD if val < 60 else _ND_TIRE_OPT if val < 95 else _ND_TIRE_HOT)
            surf.fill(tuple(c // 4 for c in bg), (tx, ty, hw, hh))
            pygame.draw.rect(surf, _ND_BORDER, (tx, ty, hw, hh), 1)
            if val is None:
                render_text(surf, '-', 18, _ND_WHITE, tx + hw // 2, ty + hh // 2 + 4, bold=True)
            else:
                render_text(surf, f"{val:.0f}\u00b0", 18, _ND_WHITE, tx + hw // 2, ty + hh // 2 + 4, bold=True)


class DarkFaultRow:
    """Fault light strip styled like new_dash."""

    def __init__(self, box_xywh, IMD, AMS, BSPD, APPS, BRAKE, shared_data):
        x, y, w, h = box_xywh
        self.x, self.y, self.w, self.h = x, y, w, h
        self.lights = [("IMD", IMD), ("AMS", AMS), ("BSPD", BSPD), ("APPS", APPS), ("BRK", BRAKE)]
        self.shared_data = shared_data

    def update(self, surf):
        x, y, w, h = self.x, self.y, self.w, self.h
        surf.fill(_ND_DARK_FAULT, (x, y, w, h))
        bx = x + 58
        for label, sig in self.lights:
            v = self.shared_data.get_signal(sig)
            active = v is not None and float(v) >= 1.0
            bg = _ND_RED if active else (10, 32, 20)
            pygame.draw.rect(surf, bg, (bx, y + 6, 34, h - 12), border_radius=2)
            text_col = _ND_WHITE if active else (26, 90, 40)
            render_text(surf, label, 14, text_col, bx + 17, y + h // 2)
            bx += 40

class Alert(Gauge):
    def __init__(self, signal, thresh, box_xywh, shared_data, label=""):
        x, y, w, h = box_xywh
        super().__init__(signal, label, 0, 0, shared_data)
        self.x, self.y, self.w, self.h = x, y, w, h
        self.cx = x + w // 2
        self.cy = y + h // 2
        self.thresh = thresh

    def update(self, surf):
        """Flash a warning card over the centre column when thresholds are exceeded."""
        v = self.shared_data.get_signal(self.signal)
        if v is not None and float(v) > self.thresh and int(time.time() * 2) % 2 == 0:
            draw_rounded_rect(surf, _ND_RED, (self.x, self.y, self.w, self.h),
                              radius=3, border=2, border_color=_ND_WHITE)
            render_text(surf, self.label, 16, _ND_WHITE,
                        self.cx, self.cy, bold=True, anchor="center")

class StatusHeader(Gauge):
    """
    Header bar with interlocking chevron sections.
    Left half: hardware signals (right-pointing arrows).
    Right half: software signals (left-pointing arrows).
    Centre: diamond divider.
    Active sections light up amber; inactive stay dark.
    Configured from JSON with hw_signals / sw_signals lists.
    """

    # Chevrons are the arrow things

    _ACTIVE   = _ND_AMBER
    _INACTIVE = (22, 22, 30)
    _DIVIDER  = _ND_ORANGE
    _BORDER   = _ND_BORDER

    def __init__(self, box_xywh, hw_signals: list, sw_signals: list, shared_data):
        x, y, w, h = box_xywh
        super().__init__("", "", 0, 1, shared_data)
        self.x, self.y, self.w, self.h = x, y, w, h
        self.hw_signals = hw_signals
        self.sw_signals = sw_signals

    def _chevron_r(self, x, y, w, h, tip):
        """Right-pointing chevron polygon. Flat left edge if flush with box."""
        cy = y + h // 2
        left = [(x, y), (x + w - tip, y), (x + w, cy), (x + w - tip, y + h), (x, y + h)]
        if x != self.x:
            left.append((x + tip, cy))
        return left

    def _chevron_l(self, x, y, w, h, tip):
        """Left-pointing chevron polygon. Flat right edge if flush with box."""
        cy = y + h // 2
        pts = [(x + tip, y), (x + w, y)]
        if self.x + self.w - (x + w) >= w:
            pts.append((x + w - tip, cy))
        pts += [(x + w, y + h), (x + tip, y + h), (x, cy)]
        return pts

    def update(self, surf):
        x, y, w, h = self.x, self.y, self.w, self.h
        surf.fill(_ND_DARK_HDR, (x, y, w, h))


        tip  = max(4, h // 3)    # chevron point depth
        div  = tip * 2           # centre divider width
        pad  = max(1, h // 12)  # vertical inset
        half_w = (w - div) // 2

        def _draw_sections(signals, start_x, fn):
            n = len(signals)
            if not n:
                return

            gap  = max(2, h // 6)   # px between each chevron
            sec_w = (half_w - gap * (n - 1)) // n

            for i, sig in enumerate(signals):
                v = self.shared_data.get_signal(sig)
                active = v is not None and v == 1
                sx = start_x + i * (sec_w + gap)
                pts = fn(sx, y + pad, sec_w, h - pad * 2, tip)
                pygame.draw.polygon(surf, self._ACTIVE if active else self._INACTIVE, pts)
                pygame.draw.polygon(surf, self._BORDER, pts, 1)
                render_text(surf, sig, max(6, h // 3), BLACK if active else _ND_DIM,
                            sx + sec_w // 2, y + h // 2)

        _draw_sections(self.hw_signals, x, self._chevron_r)
        _draw_sections(list(reversed(self.sw_signals)), x + half_w + div, self._chevron_l)

        # Centre diamond divider
        cx = x + half_w + div // 2
        cy = y + h // 2
        pygame.draw.polygon(surf, self._DIVIDER, [
            (cx,          y + pad),
            (cx + div//2, cy),
            (cx,          y + h - pad),
            (cx - div//2, cy),
        ])


class FSAEEVReferenceDash(Gauge):
    """Full-screen FSAE EV dashboard styled after the reference timing display."""

    _BG = BLACK
    _GRID = WHITE
    _GREEN = (18, 255, 102)
    _RED = (255, 34, 18)
    _YELLOW = (255, 231, 0)
    _CYAN = (0, 232, 255)
    _DARK = (12, 12, 12)
    _MID = (26, 26, 26)

    def __init__(self, box_xywh, shared_data):
        x, y, w, h = box_xywh
        super().__init__("", "", 0, 1, shared_data)
        self.x, self.y, self.w, self.h = x, y, w, h
        self._display_fonts: Dict[tuple[int, bool], pygame.font.Font] = {}

    def _display_font(self, size: int, bold: bool = False) -> pygame.font.Font:
        key = (size, bold)
        if key not in self._display_fonts:
            for path in [
                fonts.monofonto,
                fonts.monofonto_backslash,
                fonts.jetbrains,
                fonts.jetbrains_backslash,
            ]:
                try:
                    self._display_fonts[key] = pygame.font.Font(path, size)
                    return self._display_fonts[key]
                except Exception:
                    pass
            self._display_fonts[key] = pygame.font.Font(
                pygame.font.match_font("couriernew,dejavusansmono,monospace", bold=bold),
                size,
            )
        return self._display_fonts[key]

    def _render(self, surf, text, size, color, x, y, anchor="center", bold=False, display=False):
        font = self._display_font(size, bold) if display else get_font(size, bold)
        img = font.render(str(text), True, color)
        rect = img.get_rect()
        setattr(rect, anchor, (int(x), int(y)))
        surf.blit(img, rect)
        return rect

    def _sig(self, name: str, default=None):
        value = self.shared_data.get_signal(name)
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _fault_active(self, name: str) -> bool:
        value = self.shared_data.get_signal(name)
        if value is None:
            return False
        try:
            return float(value) >= 1.0
        except (TypeError, ValueError):
            return bool(value)

    def _clamp(self, value: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, value))

    def _fmt(self, value, digits=0, fallback="--"):
        if value is None:
            return fallback
        return f"{value:.{digits}f}"

    def _box(self, surf, rect, border=2, fill=None):
        fill_color = self._BG if fill is None else fill
        pygame.draw.rect(surf, fill_color, rect)
        pygame.draw.rect(surf, self._GRID, rect, border)

    def _tile(self, surf, rect, label, value, value_color, *, unit="", value_size=54, digits=0, fill=None):
        self._box(surf, rect, fill=fill)
        x, y, w, h = rect
        self._render(surf, label, 15, self._GRID, x + 10, y + 16, anchor="midleft", bold=True)
        if value is None:
            val_text = "--"
        else:
            val_text = f"{value:.{digits}f}"
        self._render(
            surf,
            val_text,
            value_size,
            value_color,
            x + w // 2,
            y + h // 2 + 8,
            display=True,
        )
        if unit:
            self._render(surf, unit, 12, self._GRID, x + w - 12, y + h - 12, anchor="midright", bold=True)

    def _summary_tile(self, surf, rect, label, value_text, color):
        self._box(surf, rect)
        x, y, w, h = rect
        self._render(surf, label, 16, self._GRID, x + 10, y + 16, anchor="midleft", bold=True)
        self._render(surf, value_text, 64, color, x + w // 2, y + h // 2 + 8, display=True)

    def _draw_shift_lights(self, surf, rpm, rect):
        x, y, w, h = rect
        pygame.draw.rect(surf, self._BG, rect)
        segs = 18
        gap = 3
        seg_w = (w - gap * (segs - 1)) // segs
        pct = self._clamp((rpm or 0.0) / 6000.0)
        active = int(round(pct * segs))
        for i in range(segs):
            sx = x + i * (seg_w + gap)
            if i < active:
                color = self._GREEN if i < 6 else self._YELLOW if i < 12 else self._RED
            else:
                color = self._MID
            pygame.draw.rect(surf, color, (sx, y, seg_w, h))

    def _chevron_points_right(self, x, y, w, h, tip):
        cy = y + h // 2
        return [(x, y), (x + w - tip, y), (x + w, cy), (x + w - tip, y + h), (x, y + h)]

    def _chevron_points_left(self, x, y, w, h, tip):
        cy = y + h // 2
        return [(x + tip, y), (x + w, y), (x + w, y + h), (x + tip, y + h), (x, cy)]

    def _draw_chevron_strip(self, surf, rect, left_items, right_items):
        x, y, w, h = rect
        pygame.draw.rect(surf, self._BG, rect)
        pygame.draw.rect(surf, self._GRID, rect, 2)
        tip = max(6, h // 3)
        gap = 4
        div_w = tip * 2
        half_w = (w - div_w) // 2

        def draw_items(items, start_x, direction):
            if not items:
                return
            sec_w = (half_w - gap * (len(items) - 1)) // len(items)
            for idx, (label, active, active_color) in enumerate(items):
                sx = start_x + idx * (sec_w + gap)
                rect_h = h - 6
                sy = y + 3
                pts = (
                    self._chevron_points_right(sx, sy, sec_w, rect_h, tip)
                    if direction == "right"
                    else self._chevron_points_left(sx, sy, sec_w, rect_h, tip)
                )
                color = active_color if active else self._MID
                pygame.draw.polygon(surf, color, pts)
                pygame.draw.polygon(surf, self._GRID, pts, 1)
                self._render(
                    surf,
                    label,
                    11,
                    self._BG if active else self._GRID,
                    sx + sec_w // 2,
                    y + h // 2,
                    bold=True,
                )

        draw_items(left_items, x + 2, "right")
        draw_items(list(reversed(right_items)), x + half_w + div_w - 2, "left")

        cx = x + half_w + div_w // 2
        cy = y + h // 2
        pygame.draw.polygon(
            surf,
            self._YELLOW,
            [(cx, y + 4), (cx + div_w // 2, cy), (cx, y + h - 4), (cx - div_w // 2, cy)],
        )

    def _draw_status_tile(self, surf, rect, title, body, fill, text_color):
        self._box(surf, rect, fill=fill)
        x, y, w, h = rect
        self._render(surf, title, 15, text_color, x + 10, y + 18, anchor="midleft", bold=True)
        self._render(surf, body, 44, text_color, x + w // 2, y + h // 2 + 10, bold=True)

    def _draw_center_speed(self, surf, rect, speed):
        self._box(surf, rect)
        x, y, w, h = rect
        self._render(surf, "SPEED", 20, self._GRID, x + 14, y + 18, anchor="midleft", bold=True)
        pct = self._clamp((speed or 0.0) / 140.0)
        fill_h = int(pct * max(0, h - 2))
        if fill_h > 0:
            overlay = pygame.Surface((w - 4, fill_h), pygame.SRCALPHA)
            overlay.fill((*bar_color(pct), 38))
            surf.blit(overlay, (x + 2, y + h - fill_h - 2))
        speed_text = "--" if speed is None else f"{int(round(speed)):02d}"
        self._render(surf, speed_text, 142, self._GRID, x + w // 2, y + h // 2 + 16, display=True)
        self._render(surf, "MPH", 22, self._YELLOW, x + w // 2, y + h - 22, bold=True)

    def _draw_cell_band(self, surf, rect, left_label, left_value, left_digits, right_label, right_value, right_digits):
        self._box(surf, rect)
        x, y, w, h = rect
        mid_x = x + w // 2
        pygame.draw.line(surf, self._GRID, (mid_x, y), (mid_x, y + h), 2)
        self._render(surf, left_label, 14, self._GRID, x + 10, y + 16, anchor="midleft", bold=True)
        self._render(
            surf,
            self._fmt(left_value, left_digits),
            34,
            self._CYAN,
            x + w // 4,
            y + h // 2 + 8,
            display=True,
        )
        self._render(surf, right_label, 14, self._GRID, mid_x + 10, y + 16, anchor="midleft", bold=True)
        self._render(
            surf,
            self._fmt(right_value, right_digits),
            34,
            self._YELLOW,
            x + (3 * w) // 4,
            y + h // 2 + 8,
            display=True,
        )

    def _draw_segment_bar(self, surf, rect, throttle, brake, good_color, warn_color):
        x, y, w, h = rect
        self._box(surf, rect)
        dot_color = self._RED if (brake or 0) > 5 else good_color
        pygame.draw.circle(surf, dot_color, (x + 14, y + h // 2), 8)

        seg_x = x + 28
        seg_w = w - 34
        left_count = 4
        center_count = 2
        right_count = 10
        total = left_count + center_count + right_count
        gap = 3
        cell_w = (seg_w - gap * (total - 1)) // total

        brake_active = int(round(self._clamp((brake or 0.0) / 100.0) * left_count))
        throttle_active = int(round(self._clamp((throttle or 0.0) / 100.0) * right_count))

        index = 0
        for i in range(left_count):
            sx = seg_x + index * (cell_w + gap)
            color = self._RED if i >= left_count - brake_active else self._BG
            pygame.draw.rect(surf, color, (sx, y + 3, cell_w, h - 6))
            pygame.draw.rect(surf, self._GRID, (sx, y + 3, cell_w, h - 6), 1)
            index += 1
        for _ in range(center_count):
            sx = seg_x + index * (cell_w + gap)
            pygame.draw.rect(surf, self._BG, (sx, y + 3, cell_w, h - 6))
            pygame.draw.rect(surf, self._GRID, (sx, y + 3, cell_w, h - 6), 1)
            index += 1
        for i in range(right_count):
            sx = seg_x + index * (cell_w + gap)
            color = good_color if i < throttle_active else self._BG
            pygame.draw.rect(surf, color, (sx, y + 3, cell_w, h - 6))
            pygame.draw.rect(surf, self._GRID, (sx, y + 3, cell_w, h - 6), 1)
            index += 1

    def _draw_battery_icon(self, surf, rect, soc, color):
        x, y, w, h = rect
        self._box(surf, rect)
        body = pygame.Rect(x + 12, y + 10, w - 28, h - 20)
        nub = pygame.Rect(body.right + 2, y + h // 2 - 6, 8, 12)
        pygame.draw.rect(surf, self._GRID, body, 2)
        pygame.draw.rect(surf, self._GRID, nub)
        fill_pct = self._clamp((soc or 0.0) / 100.0)
        inner = body.inflate(-6, -6)
        inner_w = int(inner.w * fill_pct)
        if inner_w > 0:
            pygame.draw.rect(surf, color, (inner.x, inner.y, inner_w, inner.h))
        self._render(surf, "BAT", 11, self._GRID, x + w // 2, y + h - 8, bold=True)

    def _draw_motor_icon(self, surf, rect, color):
        x, y, w, h = rect
        self._box(surf, rect)
        cx, cy = x + w // 2, y + h // 2 - 3
        pygame.draw.circle(surf, self._GRID, (cx, cy), 16, 2)
        pygame.draw.circle(surf, color, (cx, cy), 7)
        for offset in (-12, 0, 12):
            pygame.draw.line(surf, self._GRID, (cx + offset, cy - 18), (cx + offset, cy - 12), 2)
            pygame.draw.line(surf, self._GRID, (cx + offset, cy + 18), (cx + offset, cy + 12), 2)
        self._render(surf, "MTR", 11, self._GRID, x + w // 2, y + h - 8, bold=True)

    def _draw_tire_icon(self, surf, rect, color):
        x, y, w, h = rect
        self._box(surf, rect)
        tire = pygame.Rect(x + w // 2 - 12, y + 8, 24, h - 20)
        pygame.draw.rect(surf, self._GRID, tire, 2, border_radius=4)
        for offset in range(4):
            ty = tire.y + 4 + offset * 7
            pygame.draw.line(surf, color, (tire.x + 4, ty), (tire.right - 4, ty), 2)
        self._render(surf, "TIRE", 10, self._GRID, x + w // 2, y + h - 8, bold=True)

    def _draw_warning_icon(self, surf, rect, color):
        x, y, w, h = rect
        self._box(surf, rect)
        pts = [(x + w // 2, y + 8), (x + 10, y + h - 14), (x + w - 10, y + h - 14)]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, self._GRID, pts, 2)
        self._render(surf, "!", 24, self._BG, x + w // 2, y + h // 2 + 2, bold=True)
        self._render(surf, "WARN", 10, self._GRID, x + w // 2, y + h - 8, bold=True)

    def update(self, surf):
        x, y, w, h = self.x, self.y, self.w, self.h
        pygame.draw.rect(surf, self._BG, (x, y, w, h))

        speed = self._sig("Speed")
        rpm = self._sig("MotorRPM")
        apps = self._sig("APPS")
        brake = self._sig("BrakePressure")
        pack_v = self._sig("PackVoltage")
        pack_i = self._sig("PackCurrent")
        soc = self._sig("StateOfCharge")
        lv = self._sig("LVBatteryVoltage")
        pack_temp = self._sig("PackTemp")
        inv_temp = self._sig("InverterTemp")
        motor_temp = self._sig("MotorTemp")
        cell_min = self._sig("CellVoltageMin")
        cell_max = self._sig("CellVoltageMax")
        tires = [self._sig(sig) for sig in ("TTempFL", "TTempFR", "TTempBL", "TTempBR")]
        tire_values = [val for val in tires if val is not None]
        tire_avg = sum(tire_values) / len(tire_values) if tire_values else None

        pack_power = (pack_v * pack_i / 1000.0) if pack_v is not None and pack_i is not None else None
        cell_delta = ((cell_max - cell_min) * 1000.0) if cell_min is not None and cell_max is not None else None

        faults = {
            "IMD": self._fault_active("IMDFault"),
            "AMS": self._fault_active("AMSFault"),
            "BSPD": self._fault_active("BSPDFault"),
            "APPS": self._fault_active("APPSFault"),
            "BRK": self._fault_active("BrakeFault"),
        }
        fault_count = sum(1 for active in faults.values() if active)

        hot_limit = (
            (pack_temp is not None and pack_temp >= 50.0)
            or (motor_temp is not None and motor_temp >= 100.0)
            or (inv_temp is not None and inv_temp >= 85.0)
        )
        caution = (
            (soc is not None and soc <= 25.0)
            or (lv is not None and lv < 12.0)
            or (cell_delta is not None and cell_delta >= 30.0)
        )
        ready = (pack_v is not None and pack_v > 250.0) and fault_count == 0 and not hot_limit

        status_label, status_fill, status_text = "READY", self._GREEN, self._BG
        if fault_count:
            status_label, status_fill, status_text = "FAULT", self._RED, self._GRID
        elif hot_limit:
            status_label, status_fill, status_text = "LIMIT", self._YELLOW, self._BG
        elif caution:
            status_label, status_fill, status_text = "CHECK", self._YELLOW, self._BG

        soc_color = self._GREEN if (soc or 0.0) >= 35 else self._YELLOW if (soc or 0.0) >= 20 else self._RED
        power_color = self._CYAN if (pack_power or 0.0) < 20 else self._YELLOW if (pack_power or 0.0) < 55 else self._RED
        lv_color = self._GREEN if lv is not None and 12.2 <= lv <= 15.0 else self._YELLOW if lv is not None and lv >= 11.8 else self._RED
        temp_pack_color = self._GREEN if (pack_temp or 0.0) < 42 else self._YELLOW if (pack_temp or 0.0) < 50 else self._RED
        temp_inv_color = self._GREEN if (inv_temp or 0.0) < 70 else self._YELLOW if (inv_temp or 0.0) < 82 else self._RED
        temp_motor_color = self._GREEN if (motor_temp or 0.0) < 85 else self._YELLOW if (motor_temp or 0.0) < 100 else self._RED
        apps_color = self._GREEN if (apps or 0.0) < 80 else self._YELLOW if (apps or 0.0) < 95 else self._RED
        brake_color = self._RED if (brake or 0.0) > 0 else self._GRID
        tire_color = self._GREEN if (tire_avg or 0.0) < 58 else self._YELLOW if (tire_avg or 0.0) < 78 else self._RED
        cell_color = self._GREEN if (cell_delta or 0.0) < 15 else self._YELLOW if (cell_delta or 0.0) < 30 else self._RED

        self._draw_shift_lights(surf, rpm, (x, y, w, 10))
        left_chevrons = [
            ("PACK", pack_v is not None and pack_v > 250.0, self._GREEN),
            ("LV", lv is not None and lv > 12.0, self._CYAN),
            ("BRK", brake is not None and brake > 5.0, self._RED),
        ]
        right_chevrons = [
            ("IMD", faults["IMD"], self._RED),
            ("TEMP", hot_limit, self._YELLOW),
            ("R2D", ready, self._GREEN),
        ]
        self._draw_chevron_strip(surf, (x, y + 10, w, 24), left_chevrons, right_chevrons)

        top_y = y + 34
        top_h = 74
        third = w // 3
        self._summary_tile(surf, (x, top_y, third, top_h), "SOC", self._fmt(soc, 1), soc_color)
        self._summary_tile(
            surf,
            (x + third, top_y, third, top_h),
            "PACK PWR",
            self._fmt(pack_power, 1),
            power_color,
        )
        self._summary_tile(surf, (x + 2 * third, top_y, w - 2 * third, top_h), "LV", self._fmt(lv, 1), lv_color)

        main_y = top_y + top_h
        main_h = 214
        left_big_w = 186
        slim_w = 74
        center_w = 280
        # Explicit layout keeps the reference-style proportions stable on 800×480.
        x1 = x
        x2 = x1 + left_big_w
        x3 = x2 + slim_w
        x4 = x3 + center_w
        x5 = x4 + slim_w
        right_big_w = w - (left_big_w + slim_w + center_w + slim_w)
        half_main = main_h // 2

        self._tile(surf, (x1, main_y, left_big_w, half_main), "PACK TEMP", pack_temp, temp_pack_color, unit="C", value_size=70, digits=0)
        self._tile(surf, (x2, main_y, slim_w, half_main), "INV", inv_temp, temp_inv_color, unit="C", value_size=40, digits=0)
        self._draw_center_speed(surf, (x3, main_y, center_w, main_h), speed)
        self._tile(surf, (x4, main_y, slim_w, half_main), "APPS", apps, apps_color, unit="%", value_size=40, digits=0)
        self._tile(surf, (x5, main_y, right_big_w, half_main), "PACK V", pack_v, self._GRID, unit="V", value_size=72, digits=0)

        self._tile(surf, (x1, main_y + half_main, left_big_w, main_h - half_main), "MOTOR TEMP", motor_temp, temp_motor_color, unit="C", value_size=64, digits=0)
        self._tile(surf, (x2, main_y + half_main, slim_w, main_h - half_main), "TIRE", tire_avg, tire_color, unit="C", value_size=34, digits=0)
        self._tile(surf, (x4, main_y + half_main, slim_w, main_h - half_main), "BRK", brake, brake_color, unit="%", value_size=40, digits=0)
        self._tile(surf, (x5, main_y + half_main, right_big_w, main_h - half_main), "RPM", rpm, self._GRID, unit="", value_size=70, digits=0)

        lower_y = main_y + main_h
        lower_h = 102
        self._tile(surf, (x, lower_y, 188, lower_h), "PACK CUR", pack_i, self._YELLOW, unit="A", value_size=62, digits=0)
        self._tile(surf, (x + 188, lower_y, 72, lower_h), "dV", cell_delta, cell_color, unit="mV", value_size=28, digits=0)
        self._draw_cell_band(surf, (x + 260, lower_y, 280, lower_h), "CELL MIN", cell_min, 2, "CELL MAX", cell_max, 2)
        self._tile(surf, (x + 540, lower_y, 72, lower_h), "FLT", fault_count, self._RED if fault_count else self._GREEN, unit="", value_size=34, digits=0)
        self._draw_status_tile(surf, (x + 612, lower_y, 188, lower_h), "VEHICLE STATE", status_label, status_fill, status_text)

        bottom_y = lower_y + lower_h
        bottom_h = h - (bottom_y - y)
        self._draw_segment_bar(surf, (x, bottom_y, 560, bottom_h), apps, brake, self._GREEN, self._YELLOW)

        icon_w = 60
        self._draw_battery_icon(surf, (x + 560, bottom_y, icon_w, bottom_h), soc, soc_color)
        self._draw_motor_icon(surf, (x + 620, bottom_y, icon_w, bottom_h), temp_motor_color)
        self._draw_tire_icon(surf, (x + 680, bottom_y, icon_w, bottom_h), tire_color)
        self._draw_warning_icon(surf, (x + 740, bottom_y, 60, bottom_h), status_fill if fault_count or hot_limit or caution else self._GREEN)

class FullListCard(Gauge):
    '''this is just a list of all the signals that are defined for the gauge'''
    def __init__(self, box_xywh, text_size: int, signals: list, shared_data, scroll_button: Button):
        x, y, w, h = box_xywh
        super().__init__("", "", 0, 1, shared_data)
        self.x, self.y, self.w, self.h = x, y, w, h
        self.text_size = text_size
        self.signals = signals
        self.scroll_offset = 0
        self.scroll_button = scroll_button
        self._prev_pressed = False

    def update(self, surf):
        x, y, w, h = self.x, self.y, self.w, self.h
        surf.fill(_ND_CELL_BG, (x, y, w, h))
        
        # Handle space bar press
        pressed = self.scroll_button.is_pressed
        if pressed and not self._prev_pressed:
            self.scroll_offset += 3 * self.text_size

            # Calculate total content height
            total_height = len(self.signals) * self.text_size

            # If bottom of text is above bottom of viewport, reset to top
            if y + 10 + total_height - self.scroll_offset < y + h:
                self.scroll_offset = 0
        self._prev_pressed = pressed
        
        # Draw signals with scroll offset
        for i, sig in enumerate(self.signals):
            v = self.shared_data.get_signal(sig)
            val_str = '-' if v is None else str(v)
            text_y = y + 10 + i * self.text_size - self.scroll_offset
            
            # Only render if text is within visible bounds
            if text_y + self.text_size > y and text_y < y + h:
                render_text(surf, f"{sig}: {val_str}", self.text_size, _ND_LABEL, x + 10, text_y, anchor="midleft")



# ─────────────────────────────────────────────
#  Grid background
# ─────────────────────────────────────────────
def draw_background(surf, w, h):
    surf.fill(NEAR_BLACK)
    # Subtle dot grid
    spacing = 30
    for gx in range(0, w, spacing):
        for gy in range(26, h, spacing):
            pygame.draw.circle(surf, GRID_LINE, (gx, gy), 1)
