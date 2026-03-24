#!/usr/bin/env python3

from __future__ import annotations

import time
import sys
import json
from pathlib import Path
from typing import Tuple, Dict
import pygame

from python.gauges import *
from python.new_gauges import (SpeedArcGauge, VerticalBarGauge, NumericCard,
                        TireTempsWidget, SoCRingGauge, RPMBar,
                        StatusBar, WarningLights,
                        DarkStatusBar, ShiftLightsGauge, DarkCell,
                        CellVoltageCard, DarkSpeedArc, DarkTireQuad, DarkFaultRow,
                        FullListCard)
from python.graphics_driver import *
from python.constants.colors import *
from python.shared_data import LatestValuesTable

FPS_CAP = 60

# ── Alert overlay (from new_dash) ────────────────────────────────────────────
SIG_PACK_TEMP  = "PackTemp"
WARN_BAT_TEMP  = 48.0

# Position: centred in a 450 px wide column starting at x=175, bottom near y=446
_ALERT_X, _ALERT_W        = 185, 430
_ALERT_BOTTOM, _ALERT_H   = 446,  36

_overlay_fonts: Dict[tuple, pygame.font.Font] = {}

def _overlay_font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _overlay_fonts:
        name = pygame.font.match_font("couriernew,dejavusansmono,monospace", bold=bold)
        _overlay_fonts[key] = pygame.font.Font(name, size)
    return _overlay_fonts[key]

def _overlay_text(surf, s, size, color, x, y, bold=False, anchor="midleft"):
    f = _overlay_font(size, bold)
    img = f.render(str(s), True, color)
    r = img.get_rect()
    setattr(r, anchor, (int(x), int(y)))
    surf.blit(img, r)

def _overlay_rounded_rect(surf, color, rect, radius=4, border=0, border_col=None):
    x, y, w, h = rect
    pygame.draw.rect(surf, color, (x, y, w, h), border_radius=radius)
    if border and border_col:
        pygame.draw.rect(surf, border_col, (x, y, w, h), border, border_radius=radius)

# ─────────────────────────────────────────────────────────────────────────────

class Dashboard:
    """Handles rendering to a Pygame surface."""

    def __init__(self, shared_data: LatestValuesTable, config_path: Path) -> None:
        
        self.shared_data = shared_data
        self.config_path = config_path
        
        # Default values
        self.font_path = "/assets/monofonto_rg.otf"
        self.bg_color = BLACK
        self.xres, self.yres = 800, 480
        self.gauges = []

        self._ui_thread_active = False
        self._flash_state = False
        self._flash_t     = 0.0

        # Load config and instantiate gauges
        if not self.load_config():
            return
    
    def load_config(self) -> bool:
        """Load gauges from config.json. Returns True if successful."""
        try:
            with open(self.config_path) as f:
                config = json.load(f)

            self.bg_color = config.get("display").get("bg_color")
            
            gauge_configs = config.get("gauges", [])
            if not gauge_configs:
                print("No gauges in config")
                return False
            
            for gauge_cfg in gauge_configs:
                gauge = self._instantiate_gauge(gauge_cfg)
                if gauge:
                    self.gauges.append(gauge)
            
            print(f"Loaded {len(self.gauges)} gauge(s) from config")
            return len(self.gauges) > 0
        except Exception as e:
            print(f"Error loading config: {e}")
            return False
    
    def _instantiate_gauge(self, cfg: dict) -> Gauge | None:
        """Create a gauge instance from config dict."""
        try:
            gauge_type = cfg.get("type")
            signal = cfg.get("signal")
            label = cfg.get("label")
            min_val = cfg.get("min_val", 0)
            max_val = cfg.get("max_val", 100)
            box_xywh = tuple(cfg.get("box_xywh", (0, 0, 100, 100)))
            decimal_places = cfg.get("decimal_places", 0)
            box_color = cfg.get("box_color")
            border_color = tuple(cfg.get("border_color", WHITE))
            text_color = tuple(cfg.get("text_color", WHITE))

            gauge_type = gauge_type.replace(" ", "")
            if gauge_type == "SimpleGauge":
                return SimpleGauge(
                    signal=signal,
                    label=label,
                    min_val=min_val,
                    max_val=max_val,
                    box_xywh=box_xywh,
                    decimal_places=decimal_places,
                    box_color=box_color,
                    border_color=border_color,
                    text_color=text_color,
                    shared_data=self.shared_data,
                )
            elif gauge_type == "UnsignedLinearGauge":
                fill_color = tuple(cfg.get("fill_color", GREEN))
                vertical = cfg.get("vertical", True)
                show_value = cfg.get("show_value", True)
                return UnsignedLinearGauge(
                    signal=signal,
                    label=label,
                    min_val=min_val,
                    max_val=max_val,
                    box_xywh=box_xywh,
                    decimal_places=decimal_places,
                    box_color=box_color,
                    border_color=border_color,
                    fill_color=fill_color,
                    text_color=text_color,
                    vertical=vertical,
                    show_value=show_value,
                    shared_data=self.shared_data,
                )
            elif gauge_type == "SignedLinearGauge":
                pos_color = tuple(cfg.get("pos_color", GREEN))
                neg_color = tuple(cfg.get("neg_color", RED))
                vertical = cfg.get("vertical", True)
                show_value = cfg.get("show_value", True)
                return SignedLinearGauge(
                    signal=signal,
                    label=label,
                    min_val=min_val,
                    max_val=max_val,
                    box_xywh=box_xywh,
                    decimal_places=decimal_places,
                    box_color=box_color,
                    border_color=border_color,
                    pos_color=pos_color,
                    neg_color=neg_color,
                    text_color=text_color,
                    vertical=vertical,
                    show_value=show_value,
                    shared_data=self.shared_data,
                )
            elif gauge_type == "SpeedArcGauge":
                return SpeedArcGauge(
                    signal=signal,
                    label=label,
                    min_val=min_val,
                    max_val=max_val,
                    box_xywh=box_xywh,
                    shared_data=self.shared_data,
                    unit=cfg.get("unit", "MPH"),
                    decimal_places=decimal_places,
                )
            elif gauge_type == "VerticalBarGauge":
                fill_color = cfg.get("fill_color")
                if fill_color is not None:
                    fill_color = tuple(fill_color)
                pos_color = cfg.get("pos_color")
                if pos_color is not None:
                    pos_color = tuple(pos_color)
                neg_color = cfg.get("neg_color")
                if neg_color is not None:
                    neg_color = tuple(neg_color)
                return VerticalBarGauge(
                    signal=signal,
                    label=label,
                    min_val=min_val,
                    max_val=max_val,
                    x=box_xywh[0],
                    y=box_xywh[1],
                    w=box_xywh[2],
                    h=box_xywh[3],
                    shared_data=self.shared_data,
                    fill_color=fill_color,
                    show_value=cfg.get("show_value", True),
                    unit=cfg.get("unit", ""),
                    decimal_places=decimal_places,
                    signed=cfg.get("signed", False),
                    pos_color=pos_color,
                    neg_color=neg_color,
                )
            elif gauge_type == "NumericCard":
                return NumericCard(
                    signal=signal,
                    label=label,
                    min_val=min_val,
                    max_val=max_val,
                    x=box_xywh[0],
                    y=box_xywh[1],
                    w=box_xywh[2],
                    h=box_xywh[3],
                    shared_data=self.shared_data,
                    unit=cfg.get("unit", ""),
                    decimal_places=decimal_places,
                    warn_pct=cfg.get("warn_pct", 0.85),
                    crit_pct=cfg.get("crit_pct", 0.95),
                )
            elif gauge_type == "TireTempsWidget":
                return TireTempsWidget(
                    box_xywh=box_xywh,
                    FL=cfg.get("FL"),
                    FR=cfg.get("FR"),
                    RL=cfg.get("RL"),
                    RR=cfg.get("RR"),
                    shared_data=self.shared_data,
                    min_val=min_val,
                    max_val=max_val,
                )
            elif gauge_type == "SoCRingGauge":
                return SoCRingGauge(
                    signal=signal,
                    box_xywh=box_xywh,
                    shared_data=self.shared_data,
                    min_val=min_val,
                    max_val=max_val,
                    label=label,
                )
            elif gauge_type == "RPMBar":
                return RPMBar(
                    signal=signal,
                    x=box_xywh[0],
                    y=box_xywh[1],
                    w=box_xywh[2],
                    h=box_xywh[3],
                    shared_data=self.shared_data,
                    min_val=min_val,
                    max_val=max_val,
                    label=label,
                    decimal_places=decimal_places,
                )
            elif gauge_type == "StatusBar":
                return StatusBar(
                    x=box_xywh[0],
                    y=box_xywh[1],
                    w=box_xywh[2],
                    h=box_xywh[3],
                )
            elif gauge_type == "WarningLights":
                return WarningLights(
                    box_xywh=box_xywh,
                    IMD=cfg.get("IMD"),
                    AMS=cfg.get("AMS"),
                    BSPD=cfg.get("BSPD"),
                    APPS=cfg.get("APPS"),
                    BRAKE=cfg.get("BRAKE"),
                    shared_data=self.shared_data,
                )
            elif gauge_type == "DarkStatusBar":
                return DarkStatusBar(
                    x=box_xywh[0],
                    y=box_xywh[1],
                    w=box_xywh[2],
                    h=box_xywh[3],
                )
            elif gauge_type == "ShiftLightsGauge":
                return ShiftLightsGauge(
                    signal=signal,
                    min_val=min_val,
                    max_val=max_val,
                    box_xywh=box_xywh,
                    shared_data=self.shared_data,
                    label=label or "",
                )
            elif gauge_type == "DarkCell":
                accent_color = cfg.get("accent_color")
                if accent_color is not None:
                    accent_color = tuple(accent_color)
                value_color = cfg.get("value_color")
                if value_color is not None:
                    value_color = tuple(value_color)
                return DarkCell(
                    signal=signal,
                    label=label or "",
                    min_val=min_val,
                    max_val=max_val,
                    box_xywh=box_xywh,
                    shared_data=self.shared_data,
                    unit=cfg.get("unit", ""),
                    decimal_places=decimal_places,
                    accent_color=accent_color,
                    value_color=value_color,
                    last=cfg.get("last", False),
                )
            elif gauge_type == "CellVoltageCard":
                return CellVoltageCard(
                    signal_min=cfg.get("signal_min"),
                    signal_max=cfg.get("signal_max"),
                    box_xywh=box_xywh,
                    shared_data=self.shared_data,
                    last=cfg.get("last", False),
                )
            elif gauge_type == "DarkSpeedArc":
                return DarkSpeedArc(
                    signal=signal,
                    min_val=min_val,
                    max_val=max_val,
                    box_xywh=box_xywh,
                    shared_data=self.shared_data,
                    unit=cfg.get("unit", "MPH"),
                    decimal_places=decimal_places,
                    label=label or "",
                )
            elif gauge_type == "DarkTireQuad":
                return DarkTireQuad(
                    box_xywh=box_xywh,
                    FL=cfg.get("FL"),
                    FR=cfg.get("FR"),
                    RL=cfg.get("RL"),
                    RR=cfg.get("RR"),
                    shared_data=self.shared_data,
                )
            elif gauge_type == "DarkFaultRow":
                return DarkFaultRow(
                    box_xywh=box_xywh,
                    IMD=cfg.get("IMD"),
                    AMS=cfg.get("AMS"),
                    BSPD=cfg.get("BSPD"),
                    APPS=cfg.get("APPS"),
                    BRAKE=cfg.get("BRAKE"),
                    shared_data=self.shared_data,
                )
            elif gauge_type == "FullList":
                signals = cfg.get("signals", [])
                return FullListCard(
                    box_xywh=box_xywh,
                    signals=signals,
                    shared_data=self.shared_data,
                    text_size=cfg.get("text_size", 16),
                )
            else:
                print(f"Unknown gauge type: {gauge_type}")
                return None
        except Exception as e:
            print(f"Error instantiating gauge: {e}")
            return None

    def create_frame(self) -> pygame.Surface:
        """Create a fresh frame surface."""
        surface = create_surface(self.xres, self.yres)
        fill_surface(surface, self.bg_color)
        return surface
    
    def render_frame(self) -> pygame.Surface:
        """
        Create a surface using the data from the shared state.
        Called by UI thread.
        Returns the rendered surface.
        """
        frame = self.create_frame()
        
        #check if a can bus error was raised
        if self.shared_data.get_signal("CAN_ERROR"):
            _overlay_text(frame, "CAN BUS ERROR", 32, RED, self.xres // 2, self.yres // 2, bold=True, anchor="center")
            return frame
        else:
            # Update all gauges
            for gauge in self.gauges:
                gauge.update(frame)

        # self._draw_alert_overlay(frame)
        return frame
    
    def _get(self, sig, default=0.0) -> float:
        v = self.shared_data.get_signal(sig)
        return float(v) if v is not None else float(default)

    def _draw_alert_overlay(self, surf: pygame.Surface) -> None:
        """Flash a warning card over the centre column when thresholds are exceeded."""
        if not self._flash_state:
            return
        if self._get(SIG_PACK_TEMP) > WARN_BAT_TEMP:
            _overlay_rounded_rect(surf, (255, 37, 37),
                                  (_ALERT_X, _ALERT_BOTTOM - _ALERT_H, _ALERT_W, _ALERT_H),
                                  radius=3, border=2, border_col=(242, 242, 242))
            _overlay_text(surf, "HIGH BATTERY TEMP", 16, (242, 242, 242),
                          _ALERT_X + _ALERT_W // 2, _ALERT_BOTTOM - _ALERT_H // 2,
                          bold=True, anchor="center")

    def run_ui_thread(self) -> None:
        """
        UI thread: Renders at fixed fps.
        """
        clock = get_clock()
        
        self._ui_thread_active = True
        print(f"UI thread started ({FPS_CAP} fps)")
        
        try:
            while self._ui_thread_active:
                # Process Pygame events to prevent freezing
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        print("\nWindow closed by user")
                        cleanup()
                        sys.exit(0)
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        print("\nEscape pressed, exiting...")
                        cleanup()
                        sys.exit(0)
                                
                frame = self.render_frame()
                blit_surface(frame)

                dt = clock.tick_busy_loop(FPS_CAP)
                self._flash_t += dt / 1000.0
                if self._flash_t >= 0.5:
                    self._flash_t, self._flash_state = 0.0, not self._flash_state
        except Exception as e:
            print(f"UI thread error: {e}")
        finally:
            cleanup()
            print("UI thread stopped")
