#!/usr/bin/env python3
"""
TREV4 Dashboard — Live JSON Implementation
800×480, three-column grid, arc speed gauge, shift-lights, and fault row.
Reads live telemetry from 'telemetry.json'.
"""

from __future__ import annotations
import math
import time
import threading
import json
import os
from typing import Optional, Any, Dict

import pygame

# ═══════════════════════════════════════════════════════════════════
#  SIGNAL NAMES — Must match your JSON keys exactly
# ═══════════════════════════════════════════════════════════════════
SIG_SPEED           = "Speed"
SIG_RPM             = "MotorRPM"
SIG_SOC             = "StateOfCharge"
SIG_PACK_VOLTAGE    = "PackVoltage"
SIG_PACK_CURRENT    = "PackCurrent"
SIG_PACK_TEMP       = "PackTemp"
SIG_INVERTER_TEMP   = "InverterTemp"
SIG_MOTOR_TEMP      = "MotorTemp"
SIG_CELL_MIN        = "CellVoltageMin"
SIG_CELL_MAX        = "CellVoltageMax"
SIG_LV_BATT         = "LVBatteryVoltage"
SIG_THROTTLE_PCT    = "ThrottlePct"
SIG_BRAKE_PRESSURE  = "BrakePressure"
SIG_TIRE_FL         = "TTempFL"
SIG_TIRE_FR         = "TTempFR"
SIG_TIRE_RL         = "TTempRL"
SIG_TIRE_RR         = "TTempRR"
SIG_FAULT_IMD       = "IMDFault"
SIG_FAULT_AMS       = "AMSFault"
SIG_FAULT_BSPD      = "BSPDFault"
SIG_FAULT_APPS      = "APPSFault"
SIG_FAULT_BRAKE     = "BrakeFault"

# ═══════════════════════════════════════════════════════════════════
#  THRESHOLDS
# ═══════════════════════════════════════════════════════════════════
LV_LOW              = 11.0
LV_HIGH             = 15.5
WARN_INV_TEMP       = 75.0
CRIT_INV_TEMP       = 90.0
WARN_MOT_TEMP       = 90.0
CRIT_MOT_TEMP       = 108.0
WARN_BAT_TEMP       = 48.0
CRIT_BAT_TEMP       = 57.0

# ═══════════════════════════════════════════════════════════════════
#  COLOURS
# ═══════════════════════════════════════════════════════════════════
BG          = (7,   7,   9)
CELL_BG     = (13,  13,  16)
BORDER      = (37,  37,  48)
BORDER_HI   = (56,  56,  74)
ORANGE      = (255, 106,  0)
ORANGE_DIM  = (106,  42,  0)
CYAN        = (0,  212, 232)
GREEN       = (0,  224,  96)
AMBER       = (255, 184,  0)
RED         = (255,  37,  37)
WHITE       = (242, 242, 242)
DIM         = (82,  82, 106)
LABEL_COL   = (114, 114, 138)
DARK_HEADER = (10,  10,  12)
DARK_FAULT  = (6,   6,   8)
TIRE_COLD   = (30,  60, 160)
TIRE_OPT    = (0,  140,  50)
TIRE_HOT    = (200,  40,  10)

# ═══════════════════════════════════════════════════════════════════
#  LAYOUT
# ═══════════════════════════════════════════════════════════════════
W, H            = 800, 480
SHIFT_H         = 10
HEADER_H        = 26
FAULT_H         = 28
CENTER_BOTTOM_H = 60
MAIN_H = H - SHIFT_H - HEADER_H - FAULT_H - CENTER_BOTTOM_H

COL_SIDE   = 175
COL_CENTER = W - 2 * COL_SIDE
SHIFT_Y, HEADER_Y, MAIN_Y = 0, SHIFT_H, SHIFT_H + HEADER_H
CB_Y = MAIN_Y + MAIN_H
FAULT_Y = CB_Y + CENTER_BOTTOM_H
LEFT_X, CENTER_X, RIGHT_X = 0, COL_SIDE, COL_SIDE + COL_CENTER

NUM_DOTS = 16
GCX, GCY = CENTER_X + COL_CENTER // 2, MAIN_Y + (MAIN_H - CENTER_BOTTOM_H) // 2 + 10
GRAD, ARC_START_DEG, ARC_SWEEP_DEG, ARC_W = 108, 135.0, 270.0, 14
MAX_SPEED = 99
ALERT_X, ALERT_W, ALERT_BOTTOM, ALERT_CARD_H = CENTER_X + 10, COL_CENTER - 20, FAULT_Y - 6, 36

# ═══════════════════════════════════════════════════════════════════
#  HELPERS & FONT CACHE
# ═══════════════════════════════════════════════════════════════════
_fonts: Dict[tuple, pygame.font.Font] = {}

def font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _fonts:
        name = pygame.font.match_font("couriernew,dejavusansmono,monospace", bold=bold)
        _fonts[key] = pygame.font.Font(name, size)
    return _fonts[key]

def text(surf, s, size, color, x, y, bold=False, anchor="midleft"):
    f = font(size, bold)
    img = f.render(str(s), True, color)
    r = img.get_rect()
    setattr(r, anchor, (int(x), int(y)))
    surf.blit(img, r)
    return r

def lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def gauge_color(pct):
    if pct < 0.6: return lerp_color((0, 210, 70), (255, 180, 0), pct / 0.6)
    return lerp_color((255, 180, 0), (255, 30, 30), (pct - 0.6) / 0.4)

def bar_color(pct):
    if pct < 0.6: return lerp_color(GREEN, AMBER, pct / 0.6)
    return lerp_color(AMBER, RED, (pct - 0.6) / 0.4)

def temp_accent(val, warn, crit):
    if val >= crit: return RED, RED
    if val >= warn: return AMBER, AMBER
    return GREEN, WHITE

def arc_point(cx, cy, deg, r):
    rad = math.radians(deg)
    return (cx + r * math.cos(rad), cy + r * math.sin(rad))

def draw_arc(surf, cx, cy, r, start_deg, end_deg, width, color, segments=120):
    delta = (end_deg - start_deg) % 360
    if delta < 0.01: return
    pts = [arc_point(cx, cy, start_deg + (i/segments)*delta, r) for i in range(segments + 1)]
    for i in range(len(pts) - 1):
        pygame.draw.line(surf, color, pts[i], pts[i+1], width)

def draw_rounded_rect(surf, color, rect, radius=4, border=0, border_col=None):
    x, y, w, h = rect
    pygame.draw.rect(surf, color, (x, y, w, h), border_radius=radius)
    if border and border_col:
        pygame.draw.rect(surf, border_col, (x, y, w, h), border, border_radius=radius)

# ═══════════════════════════════════════════════════════════════════
#  DATA HANDLING
# ═══════════════════════════════════════════════════════════════════
class LatestValuesTable:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}

    def update(self, signals: Dict[str, Any]):
        with self._lock:
            self._data.update(signals)

    def get_signal(self, name: str, default=None):
        with self._lock:
            return self._data.get(name, default)

class JSONTelemetryReader:
    """Reads telemetry from a JSON file and updates the Shared Data Table."""
    def __init__(self, shared_data: LatestValuesTable, file_path: str, interval: float = 0.05):
        self._sd = shared_data
        self.file_path = file_path
        self.interval = interval
        self._active = False

    def start(self):
        self._active = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._active = False

    def _run(self):
        while self._active:
            if os.path.exists(self.file_path):
                try:
                    with open(self.file_path, 'r') as f:
                        data = json.load(f)
                        self._sd.update(data)
                except (json.JSONDecodeError, IOError):
                    pass # Skip if file is being written to
            time.sleep(self.interval)

# ═══════════════════════════════════════════════════════════════════
#  DASHBOARD UI
# ═══════════════════════════════════════════════════════════════════
class Dashboard:
    def __init__(self, shared_data: LatestValuesTable):
        self._sd = shared_data
        self._ui_thread_active = False
        self._flash_state = False
        self._flash_t = 0.0

    def run_ui_thread(self):
        pygame.init()
        screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("TREV4 Dashboard")
        surf = pygame.Surface((W, H))
        clock = pygame.time.Clock()
        self._ui_thread_active = True

        while self._ui_thread_active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    self._ui_thread_active = False

            self._flash_t += clock.get_time() / 1000.0
            if self._flash_t >= 0.5:
                self._flash_t, self._flash_state = 0.0, not self._flash_state

            self._render(surf)
            screen.blit(surf, (0, 0))
            pygame.display.flip()
            clock.tick(60)
        pygame.quit()

    def _get(self, sig, default=0.0) -> float:
        v = self._sd.get_signal(sig, default)
        return float(v) if v is not None else float(default)

    def _render(self, surf: pygame.Surface):
        surf.fill(BG)
        self._draw_shift_lights(surf)
        self._draw_header(surf)
        self._draw_left_col(surf)
        self._draw_center_col(surf)
        self._draw_right_col(surf)
        self._draw_fault_row(surf)
        self._draw_alert_overlay(surf)

    def _draw_shift_lights(self, surf):
        rpm = self._get(SIG_RPM)
        pct = max(0.0, min(1.0, rpm / 6000.0))
        active = int(pct * NUM_DOTS)
        surf.fill(DARK_FAULT, (0, SHIFT_Y, W, SHIFT_H))
        dot_w = (W - 8 - (NUM_DOTS - 1) * 3) // NUM_DOTS
        for i in range(NUM_DOTS):
            col = (GREEN if i < 5 else AMBER if i < 11 else RED) if i < active else BORDER
            pygame.draw.rect(surf, col, (4 + i * (dot_w + 3), SHIFT_Y + 2, dot_w, SHIFT_H - 4), border_radius=2)

    def _draw_header(self, surf):
        surf.fill(DARK_HEADER, (0, HEADER_Y, W, HEADER_H))
        pygame.draw.line(surf, ORANGE, (0, HEADER_Y + HEADER_H - 2), (W, HEADER_Y + HEADER_H - 2), 2)
        cy = HEADER_Y + HEADER_H // 2
        text(surf, "TREV4", 11, ORANGE, 10, cy, bold=True, anchor="midleft")
        text(surf, "TERPS RACING EV · LIVE TELEMETRY", 8, DIM, W // 2, cy, anchor="center")
        text(surf, time.strftime("%H:%M:%S"), 10, LABEL_COL, W - 10, cy, anchor="midright")

    def _draw_cell(self, surf, x, y, w, h, label, value_str, unit_str, accent=BORDER_HI, bar_pct=None, bar_color_=None, value_color=WHITE, last=False):
        surf.fill(CELL_BG, (x, y, w, h))
        if not last: pygame.draw.line(surf, BORDER, (x, y + h - 1), (x + w, y + h - 1), 1)
        pygame.draw.rect(surf, accent, (x, y + 6, 3, h - 12), border_radius=1)
        text(surf, label, 7, LABEL_COL, x + 14, y + 10, anchor="midleft")
        text(surf, value_str, 28, value_color, x + 14, y + h - 14, anchor="midleft")
        if unit_str: text(surf, unit_str, 8, DIM, x + 14 + font(28).size(value_str)[0] + 3, y + h - 16, anchor="midleft")
        if bar_pct is not None: surf.fill(bar_color_, (x, y + h - 2, int(max(0, min(1, bar_pct)) * w), 2))

    def _draw_left_col(self, surf):
        x, cell_h = LEFT_X, MAIN_H // 5
        pygame.draw.line(surf, BORDER, (x + COL_SIDE, MAIN_Y), (x + COL_SIDE, MAIN_Y + MAIN_H), 1)
        cells = [
            ("PACK VOLTAGE", SIG_PACK_VOLTAGE, "V", 280, 420, CYAN, CYAN),
            ("PACK CURRENT", SIG_PACK_CURRENT, "A", 0, 300, AMBER, AMBER),
            ("STATE OF CHARGE", SIG_SOC, "%", 0, 100, GREEN, GREEN),
            (None,),
            ("LV BATTERY", SIG_LV_BATT, "V", 10, 16, ORANGE, ORANGE),
        ]
        for i, c in enumerate(cells):
            cy, last = MAIN_Y + i * cell_h, i == 4
            if c[0] is None:
                self._draw_cell_voltage(surf, x, cy, COL_SIDE, cell_h, last)
            else:
                val = self._get(c[1])
                pct = (val - c[3]) / (c[4] - c[3])
                self._draw_cell(surf, x, cy, COL_SIDE, cell_h, c[0], f"{val:.1f}", c[2], c[5], pct, c[6], last=last)

    def _draw_cell_voltage(self, surf, x, y, w, h, last):
        surf.fill(CELL_BG, (x, y, w, h))
        if not last: pygame.draw.line(surf, BORDER, (x, y + h - 1), (x + w, y + h - 1), 1)
        pygame.draw.rect(surf, BORDER_HI, (x, y + 6, 3, h - 12), border_radius=1)
        text(surf, "CELL VOLTAGE", 7, LABEL_COL, x + 14, y + 10, anchor="midleft")
        vmin, vmax = self._get(SIG_CELL_MIN), self._get(SIG_CELL_MAX)
        text(surf, f"{vmin:.2f}", 20, AMBER, x + 14, y + h//2 + 6, anchor="midleft")
        text(surf, f"{vmax:.2f}", 20, CYAN, x + w//2 + 10, y + h//2 + 6, anchor="midleft")

    def _draw_center_col(self, surf):
        surf.fill((8, 8, 11), (CENTER_X, MAIN_Y, COL_CENTER, MAIN_H - CENTER_BOTTOM_H))
        speed = self._get(SIG_SPEED)
        pct = max(0, min(1, speed / MAX_SPEED))
        draw_arc(surf, GCX, GCY, GRAD, ARC_START_DEG, ARC_START_DEG + ARC_SWEEP_DEG, ARC_W, (30, 30, 42))
        if pct > 0: draw_arc(surf, GCX, GCY, GRAD, ARC_START_DEG, ARC_START_DEG + pct * ARC_SWEEP_DEG, ARC_W, gauge_color(pct))
        text(surf, str(int(speed)), 72, WHITE, GCX, GCY - 6, bold=True, anchor="center")
        text(surf, "MPH", 10, ORANGE, GCX, GCY + 46, anchor="center")
        
        # Bottom bars
        thr, brk = self._get(SIG_THROTTLE_PCT), self._get(SIG_BRAKE_PRESSURE)
        self._draw_cell(surf, CENTER_X, CB_Y, COL_CENTER//2, CENTER_BOTTOM_H, "THROTTLE", f"{thr:.0f}", "%", GREEN, thr/100, GREEN, last=True)
        self._draw_cell(surf, CENTER_X + COL_CENTER//2, CB_Y, COL_CENTER//2, CENTER_BOTTOM_H, "BRAKE PRESS", f"{brk:.0f}", "%", RED, brk/100, RED, last=True)

    def _draw_right_col(self, surf):
        x, w, data_h = RIGHT_X, COL_SIDE, int(MAIN_H * 0.6)
        cell_h = data_h // 4
        # RPM + Temps
        vals = [(SIG_RPM, "MOTOR RPM", "", 6000, ORANGE), (SIG_INVERTER_TEMP, "INVERTER TEMP", "°C", 100, CYAN), 
                (SIG_MOTOR_TEMP, "MOTOR TEMP", "°C", 120, AMBER), (SIG_PACK_TEMP, "BATTERY TEMP", "°C", 60, RED)]
        for i, (sig, lbl, unit, mx, col) in enumerate(vals):
            v = self._get(sig)
            self._draw_cell(surf, x, MAIN_Y + i*cell_h, w, cell_h, lbl, f"{v:.0f}", unit, col, v/mx, col)
        
        # Tire Quad
        self._draw_tire_quad(surf, x, MAIN_Y + data_h, w, MAIN_H - data_h)

    def _draw_tire_quad(self, surf, x, y, w, h):
        hw, hh = w // 2, h // 2
        for i, (sig, lbl) in enumerate([(SIG_TIRE_FL, "FL"), (SIG_TIRE_FR, "FR"), (SIG_TIRE_RL, "RL"), (SIG_TIRE_RR, "RR")]):
            tx, ty = x + (i%2)*hw, y + (i//2)*hh
            val = self._get(sig)
            bg = TIRE_COLD if val < 60 else TIRE_OPT if val < 95 else TIRE_HOT
            surf.fill(tuple(c//4 for c in bg), (tx, ty, hw, hh))
            pygame.draw.rect(surf, BORDER, (tx, ty, hw, hh), 1)
            text(surf, f"{val:.0f}°", 18, WHITE, tx + hw//2, ty + hh//2 + 4, bold=True, anchor="center")

    def _draw_fault_row(self, surf):
        surf.fill(DARK_FAULT, (0, FAULT_Y, W, FAULT_H))
        faults = [("IMD", SIG_FAULT_IMD), ("AMS", SIG_FAULT_AMS), ("BSPD", SIG_FAULT_BSPD), ("APPS", SIG_FAULT_APPS), ("BRK", SIG_FAULT_BRAKE)]
        bx = 58
        for label, sig in faults:
            active = self._get(sig) >= 1.0
            bg = RED if active else (10, 32, 20)
            draw_rounded_rect(surf, bg, (bx, FAULT_Y + 6, 34, FAULT_H - 12), radius=2)
            text(surf, label, 7, WHITE if active else (26, 90, 40), bx + 17, FAULT_Y + FAULT_H//2, anchor="center")
            bx += 40

    def _draw_alert_overlay(self, surf):
        if not self._flash_state: return
        # Simple Logic for Alert Cards
        if self._get(SIG_PACK_TEMP) > WARN_BAT_TEMP:
            draw_rounded_rect(surf, RED, (ALERT_X, ALERT_BOTTOM-ALERT_CARD_H, ALERT_W, ALERT_CARD_H), radius=3, border=2, border_col=WHITE)
            text(surf, "HIGH BATTERY TEMP", 16, WHITE, ALERT_X + ALERT_W//2, ALERT_BOTTOM - ALERT_CARD_H//2, bold=True, anchor="center")

# ═══════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    
    # Configuration
    JSON_PATH = "config.json"
    
    shared = LatestValuesTable()
    reader = JSONTelemetryReader(shared, JSON_PATH)
    dash = Dashboard(shared)

    try:
        reader.start()
        dash.run_ui_thread() # Blocks until ESC or Close
    finally:
        reader.stop()
        sys.exit(0)