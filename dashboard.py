#!/usr/bin/env python3

from __future__ import annotations

import time
import sys
import json
from pathlib import Path
from typing import Tuple
import pygame

from gauges import *
from graphics_driver import *
from colors import *
from shared_data import LatestValuesTable

FPS_CAP = 30

class Dashboard:
    """Handles rendering to a Pygame surface."""

    def __init__(self, shared_data: LatestValuesTable, config_path: Path) -> None:
        
        self.shared_data = shared_data
        self.config_path = config_path
        
        # Default values
        self.font_path = "assets\fonts\monofonto rg.otf"
        self.bg_color = BLACK
        self.xres, self.yres = 800, 480
        self.gauges = []

        self._ui_thread_active = False
        
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
        
        # Update all gauges
        for gauge in self.gauges:
            gauge.update(frame)
        
        return frame
    
    def run_ui_thread(self) -> None:
        """
        UI thread: Renders at fixed fps.
        """
        # Initialize display
        init_display()
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
                                
                frame = self.render_frame()
                blit_surface(frame)
                
                clock.tick_busy_loop(FPS_CAP)
        except Exception as e:
            print(f"UI thread error: {e}")
        finally:
            cleanup()
            print("UI thread stopped")