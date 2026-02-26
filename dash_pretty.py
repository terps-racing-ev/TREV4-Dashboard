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

import pygame

# ╔══════════════════════════════════════════════════════════════════╗
# ║                     SIGNAL CONFIGURATION                        ║
# ║  Edit these to match your .dbc signal names and value ranges.   ║
# ║  Sim ranges control the animation bounds in testing mode.       ║
# ╚══════════════════════════════════════════════════════════════════╝

# ── Signal names (must match .dbc exactly) ───────────────────────
SIG_SPEED           = "Speed"
SIG_RPM             = "MotorRPM"
SIG_SOC             = "StateOfCharge"
SIG_PACK_VOLTAGE    = "PackVoltage"
SIG_PACK_CURRENT    = "PackCurrent"
SIG_PACK_TEMP       = "PackTemp"
SIG_INVERTER_TEMP   = "InverterTemp"
SIG_MOTOR_TEMP      = "MotorTemp"
SIG_APPS            = "APPS"           # torque / throttle pedal
SIG_TIRE_FL         = "TTempFL"
SIG_TIRE_FR         = "TTempFR"
SIG_TIRE_RL         = "TTempRL"
SIG_TIRE_RR         = "TTempRR"
SIG_LV_BATT         = "LVBatteryVoltage"
SIG_G_LONG          = "G_Long"
SIG_THROTTLE_PCT    = "ThrottlePct"
SIG_BRAKE_PRESSURE  = "BrakePressure"
# Fault signals (active when value >= 1.0)
SIG_FAULT_IMD       = "IMDFault"
SIG_FAULT_AMS       = "AMSFault"
SIG_FAULT_BSPD      = "BSPDFault"
SIG_FAULT_APPS      = "APPSFault"
SIG_FAULT_BRAKE     = "BrakeFault"

# ── Value ranges (min / max for gauge scaling) ───────────────────
RANGE_SPEED         = (0,    99)
RANGE_RPM           = (0,  6000)
RANGE_SOC           = (0,   100)    # %
RANGE_PACK_VOLTAGE  = (200, 420)    # V
RANGE_PACK_CURRENT  = (0,   300)    # A
RANGE_PACK_TEMP     = (0,    60)    # °C
RANGE_INVERTER_TEMP = (0,   100)    # °C
RANGE_MOTOR_TEMP    = (0,   120)    # °C
RANGE_APPS          = (-230, 230)   # Nm (signed)
RANGE_TIRE_TEMP     = (20,  120)    # °C  (all four corners)
RANGE_LV_BATT       = (10,   16)    # V
RANGE_G_LONG        = (-2.0, 2.0)   # g
RANGE_THROTTLE      = (0,   100)    # %
RANGE_BRAKE         = (0,   100)    # %

# ── Warning / critical thresholds (fraction of max range, 0–1) ───
WARN_INVERTER_TEMP  = 0.75   # amber at 75°C
CRIT_INVERTER_TEMP  = 0.90   # red   at 90°C
WARN_MOTOR_TEMP     = 0.75   # amber at 90°C
CRIT_MOTOR_TEMP     = 0.90   # red   at 108°C
WARN_PACK_TEMP      = 0.80   # amber at 48°C
CRIT_PACK_TEMP      = 0.95   # red   at 57°C
WARN_LV_BATT        = 0.40   # amber — low LV voltage
CRIT_LV_BATT        = 0.20   # red   — critical LV voltage

# ── Simulation wave parameters (freq, lo, hi, phase) ─────────────
# Adjust lo/hi to test gauge behaviour at specific value ranges.
SIM_SPEED           = (0.30,   0,    99,   0.0)
SIM_RPM             = (0.30,   0,  6000,   0.0)
SIM_SOC             = (0.05,  10,   100,   1.0)
SIM_PACK_VOLTAGE    = (0.04, 280,   420,   0.0)
SIM_PACK_CURRENT    = (0.40,   0,   280,   0.5)
SIM_PACK_TEMP       = (0.07,  22,    58,   2.0)
SIM_INVERTER_TEMP   = (0.06,  30,    95,   0.3)
SIM_MOTOR_TEMP      = (0.05,  25,   110,   1.5)
SIM_APPS            = (0.50, -230,  230,   0.8)
SIM_TIRE_FL         = (0.08,  25,   115,   0.0)
SIM_TIRE_FR         = (0.08,  25,   115,   0.5)
SIM_TIRE_RL         = (0.08,  25,   115,   1.0)
SIM_TIRE_RR         = (0.08,  25,   115,   1.5)
SIM_LV_BATT         = (0.03,  11.5, 14.8,  0.2)
SIM_G_LONG          = (0.40,  -1.8,  1.8,  1.1)
SIM_THROTTLE        = (0.50,   0,   100,   0.2)
SIM_BRAKE           = (0.35,   0,   100,   2.5)

# ─────────────────────────────────────────────
#  Minimal shared data shim (no import needed)
# ─────────────────────────────────────────────
class LatestValuesTable:
    def __init__(self):
        self._lock = threading.Lock()
        self._table: Dict[str, Any] = {}

    def update(self, signals: Dict[str, Any]):
        with self._lock:
            self._table.update(signals)

    def get_signal(self, name: str, timeout: float = 1e7) -> Optional[Any]:
        with self._lock:
            return self._table.get(name)


# ─────────────────────────────────────────────
#  Color palette
# ─────────────────────────────────────────────
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
            "assets/fonts/monofonto rg.otf",
            r"assets\fonts\monofonto rg.otf",
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
    def __init__(self, signal, label, min_val, max_val, shared_data):
        self.signal = signal
        self.label = label
        self.min_val = min_val
        self.max_val = max_val
        self.shared_data = shared_data

    def get_value(self) -> float:
        v = self.shared_data.get_signal(self.signal)
        return float(v) if v is not None else 0.0

    def clamp_pct(self, val) -> float:
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
    box_xywh: (cx, cy, radius, _) — cx/cy are centre, radius is arc radius.
    """
    def __init__(self, signal, label, min_val, max_val, cx, cy, radius, shared_data,
                 unit="MPH", decimal_places=0):
        super().__init__(signal, label, min_val, max_val, shared_data)
        self.cx = cx
        self.cy = cy
        self.radius = radius
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
            pygame.draw.line(surf, PANEL_LIGHT, (int(x1), int(y1)), (int(x2), int(y2)), tick_w)
            # Tick label
            val_at_tick = self.min_val + t * (self.max_val - self.min_val)
            lx = cx + math.cos(angle) * (r - arc_w - 28)
            ly = cy - math.sin(angle) * (r - arc_w - 28)
            render_text(surf, str(int(val_at_tick)), 13, PANEL_LIGHT, int(lx), int(ly))

        # Track arc (dim)
        rect = pygame.Rect(cx - r, cy - r, r*2, r*2)
        pygame.draw.arc(surf, PANEL_LIGHT, rect,
                        math.radians(end_deg), math.radians(start_deg), arc_w)

        # Active fill arc
        if pct > 0:
            fill_end = start_deg - pct * 240
            fill_color = bar_color(pct)
            pygame.draw.arc(surf, fill_color, rect,
                            math.radians(fill_end), math.radians(start_deg), arc_w)

        # ── Centre readout ────────────────────────────────────────
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
    def __init__(self, cx, cy, shared_data, min_val=20, max_val=120):
        self.cx = cx
        self.cy = cy
        self.shared_data = shared_data
        self.min_val = min_val
        self.max_val = max_val
        self.corners = [
            ("FL", SIG_TIRE_FL, -48, -28),
            ("FR", SIG_TIRE_FR,  48, -28),
            ("RL", SIG_TIRE_RL, -48,  28),
            ("RR", SIG_TIRE_RR,  48,  28),
        ]
        self.tw, self.th = 52, 32

    def get_val(self, sig):
        v = self.shared_data.get_signal(sig)
        return float(v) if v is not None else self.min_val

    def update(self, surf):
        cx, cy = self.cx, self.cy

        # Car body outline (simple rectangle)
        body_w, body_h = 40, 70
        draw_rounded_rect(surf, PANEL, (cx - body_w//2, cy - body_h//2, body_w, body_h), radius=6)
        pygame.draw.rect(surf, PANEL_LIGHT, (cx - body_w//2, cy - body_h//2, body_w, body_h), 1)
        render_text(surf, "TREV4", 9, DIM_WHITE, cx, cy)

        for label, sig, dx, dy in self.corners:
            val = self.get_val(sig)
            col = temp_color(val, self.min_val, self.max_val)
            tx = cx + dx - self.tw//2
            ty = cy + dy - self.th//2
            draw_rounded_rect(surf, col, (tx, ty, self.tw, self.th), radius=4)
            render_text(surf, label, 10, BLACK, tx + self.tw//2, ty + 10)
            render_text(surf, f"{val:.0f}°", 14, BLACK, tx + self.tw//2, ty + 22, bold=True)


# ─────────────────────────────────────────────
#  State-of-charge arc gauge (thin ring)
# ─────────────────────────────────────────────
class SoCRingGauge(Gauge):
    def __init__(self, signal, cx, cy, radius, shared_data,
                 min_val=0, max_val=100, label="SOC"):
        super().__init__(signal, label, min_val, max_val, shared_data)
        self.cx, self.cy, self.radius = cx, cy, radius

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
    LIGHTS = [
        ("IMD",   SIG_FAULT_IMD,   RED,   1.0),
        ("AMS",   SIG_FAULT_AMS,   RED,   1.0),
        ("BSPD",  SIG_FAULT_BSPD,  RED,   1.0),
        ("APPS",  SIG_FAULT_APPS,  AMBER, 1.0),
        ("BRK",   SIG_FAULT_BRAKE, AMBER, 1.0),
    ]

    def __init__(self, cx, y=None, shared_data=None, cy=None):
        self.cx = cx
        self.y = cy if cy is not None else y
        self.shared_data = shared_data

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
#  Grid background
# ─────────────────────────────────────────────
def draw_background(surf, w, h):
    surf.fill(NEAR_BLACK)
    # Subtle dot grid
    spacing = 30
    for gx in range(0, w, spacing):
        for gy in range(26, h, spacing):
            pygame.draw.circle(surf, GRID_LINE, (gx, gy), 1)


# ─────────────────────────────────────────────
#  Dashboard
# ─────────────────────────────────────────────

class PrettyDashboard:
    W = 800
    H = 480

    def __init__(self, shared_data: LatestValuesTable):
        self.shared_data = shared_data
        self.sd = shared_data
        self._build_widgets()

    def _build_widgets(self):
        sd = self.shared_data
        W, H = self.W, self.H
        HEADER_H = 26

        self.static = [
            StatusBar(0, 0, W, HEADER_H),
        ]

        self.widgets = [
            # ── Centre: big speed arc ────────────────────────
            SpeedArcGauge(SIG_SPEED, "SPEED", *RANGE_SPEED,
                          cx=400, cy=260, radius=130, shared_data=sd,
                          unit="MPH", decimal_places=0),

            # ── RPM bar across the top (below header) ────────
            RPMBar(SIG_RPM, x=10, y=32, w=780, h=22,
                   shared_data=sd, min_val=RANGE_RPM[0], max_val=RANGE_RPM[1], label="RPM"),

            # ── Left column: battery + power bars ────────────
            SoCRingGauge(SIG_SOC, cx=80, cy=290, radius=58,
                         shared_data=sd, min_val=RANGE_SOC[0], max_val=RANGE_SOC[1], label="SOC"),

            VerticalBarGauge(SIG_PACK_VOLTAGE, "VOLTS", *RANGE_PACK_VOLTAGE,
                             x=18, y=60, w=32, h=200, shared_data=sd,
                             fill_color=CYAN, show_value=True, decimal_places=0),

            VerticalBarGauge(SIG_PACK_CURRENT, "AMPS", *RANGE_PACK_CURRENT,
                             x=56, y=60, w=32, h=200, shared_data=sd,
                             fill_color=AMBER, show_value=True, decimal_places=0),

            # ── Right column: torque + temps ─────────────────
            VerticalBarGauge(SIG_APPS, "TORQUE", *RANGE_APPS,
                             x=750, y=60, w=36, h=200, shared_data=sd,
                             signed=True, pos_color=GREEN, neg_color=RED,
                             show_value=False, decimal_places=0),

            NumericCard(SIG_INVERTER_TEMP, "INV TEMP", *RANGE_INVERTER_TEMP,
                        x=660, y=60, w=82, h=38, shared_data=sd,
                        unit="°C", decimal_places=0,
                        warn_pct=WARN_INVERTER_TEMP, crit_pct=CRIT_INVERTER_TEMP),
            NumericCard(SIG_MOTOR_TEMP, "MOT TEMP", *RANGE_MOTOR_TEMP,
                        x=660, y=103, w=82, h=38, shared_data=sd,
                        unit="°C", decimal_places=0,
                        warn_pct=WARN_MOTOR_TEMP, crit_pct=CRIT_MOTOR_TEMP),
            NumericCard(SIG_PACK_TEMP, "BAT TEMP", *RANGE_PACK_TEMP,
                        x=660, y=146, w=82, h=38, shared_data=sd,
                        unit="°C", decimal_places=0,
                        warn_pct=WARN_PACK_TEMP, crit_pct=CRIT_PACK_TEMP),

            # ── Bottom: tire temps + warning lights ──────────
            TireTempsWidget(cx=400, cy=415, shared_data=sd,
                            min_val=RANGE_TIRE_TEMP[0], max_val=RANGE_TIRE_TEMP[1]),
            WarningLights(cx=400, cy=360, shared_data=sd),

            # ── Bottom-left: LV battery + G-force ────────────
            NumericCard(SIG_LV_BATT, "LV BATT", *RANGE_LV_BATT,
                        x=10, y=390, w=130, h=36, shared_data=sd,
                        unit="V", decimal_places=1,
                        warn_pct=WARN_LV_BATT, crit_pct=CRIT_LV_BATT),
            NumericCard(SIG_G_LONG, "G-LONG", *RANGE_G_LONG,
                        x=10, y=432, w=130, h=36, shared_data=sd,
                        unit="g", decimal_places=2, warn_pct=0.95, crit_pct=1.0),

            # ── Bottom-right: throttle + brake ───────────────
            NumericCard(SIG_THROTTLE_PCT, "THROTTLE", *RANGE_THROTTLE,
                        x=660, y=390, w=130, h=36, shared_data=sd,
                        unit="%", decimal_places=0, warn_pct=0.9, crit_pct=1.0),
            NumericCard(SIG_BRAKE_PRESSURE, "BRAKE", *RANGE_BRAKE,
                        x=660, y=432, w=130, h=36, shared_data=sd,
                        unit="%", decimal_places=0, warn_pct=0.9, crit_pct=1.0),
        ]

    def render(self, surf: pygame.Surface):
        draw_background(surf, self.W, self.H)
        for w in self.static:
            w.update(surf)
        for w in self.widgets:
            w.update(surf)


# ─────────────────────────────────────────────
#  Simulator — ramps signal values for testing
# ─────────────────────────────────────────────
class SignalSimulator:
    def __init__(self, shared_data: LatestValuesTable):
        self.sd = shared_data
        self._active = False
        self._t = 0.0

    def start(self):
        self._active = True
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        while self._active:
            t = self._t
            self._t += 0.02

            def wave(freq, lo, hi, phase=0):
                return lo + (hi - lo) * (0.5 + 0.5 * math.sin(t * freq + phase))

            self.sd.update({
                SIG_SPEED:          wave(*SIM_SPEED),
                SIG_RPM:            wave(*SIM_RPM),
                SIG_SOC:            wave(*SIM_SOC),
                SIG_PACK_VOLTAGE:   wave(*SIM_PACK_VOLTAGE),
                SIG_PACK_CURRENT:   wave(*SIM_PACK_CURRENT),
                SIG_PACK_TEMP:      wave(*SIM_PACK_TEMP),
                SIG_INVERTER_TEMP:  wave(*SIM_INVERTER_TEMP),
                SIG_MOTOR_TEMP:     wave(*SIM_MOTOR_TEMP),
                SIG_APPS:           wave(*SIM_APPS),
                SIG_TIRE_FL:        wave(*SIM_TIRE_FL),
                SIG_TIRE_FR:        wave(*SIM_TIRE_FR),
                SIG_TIRE_RL:        wave(*SIM_TIRE_RL),
                SIG_TIRE_RR:        wave(*SIM_TIRE_RR),
                SIG_LV_BATT:        wave(*SIM_LV_BATT),
                SIG_G_LONG:         wave(*SIM_G_LONG),
                SIG_THROTTLE_PCT:   wave(*SIM_THROTTLE),
                SIG_BRAKE_PRESSURE: wave(*SIM_BRAKE),
                # Faults — occasionally flicker
                SIG_FAULT_IMD:   1.0 if (math.sin(t * 0.10)       > 0.95) else 0.0,
                SIG_FAULT_AMS:   1.0 if (math.sin(t * 0.07 + 1.0) > 0.97) else 0.0,
                SIG_FAULT_BSPD:  0.0,
                SIG_FAULT_APPS:  1.0 if (math.sin(t * 0.15 + 2.0) > 0.92) else 0.0,
                SIG_FAULT_BRAKE: 0.0,
            })
            time.sleep(0.02)

    def stop(self):
        self._active = False


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────
def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 480))
    # Uncomment for real deployment:
    # screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.display.set_caption("TREV4 Dashboard")

    shared_data = LatestValuesTable()

    # Start simulated data
    sim = SignalSimulator(shared_data)
    sim.start()

    dashboard = PrettyDashboard(shared_data)
    frame = pygame.Surface((800, 480))
    clock = pygame.time.Clock()
    FPS = 60

    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.KEYUP:
                    return

            dashboard.render(frame)
            screen.blit(frame, (0, 0))
            pygame.display.flip()
            clock.tick(FPS)
    finally:
        sim.stop()
        pygame.quit()
        sys.exit(0)


if __name__ == "__main__":
    main()
