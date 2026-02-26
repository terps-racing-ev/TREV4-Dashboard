#!/usr/bin/env python3

from __future__ import annotations

import time
import sys
import json
from pathlib import Path
from typing import Tuple
import pygame
import threading

from gauges import *
from graphics_driver import *
from colors import *
from shared_data import LatestValuesTable

FPS_CAP = 60

class Dashboard:
    """Handles rendering to a Pygame surface."""

    def __init__(self, shared_data: LatestValuesTable, config_path: Path) -> None:
        
        self.shared_data = shared_data
        self.config_path = config_path
        
        # Default values
        self.font_path = "assets/fonts/monofonto rg.otf"
        self.bg_color = BLACK
        self.xres, self.yres = 800, 480
        self.gauges = []

        self._ui_thread_active = False
        
        # Warning screen state
        self._warning_lock = threading.Lock()
        self._warning_active = False
        self._warning_color = WHITE
        self._warning_text = "WARNING"
        self._warning_start_time = 0
        self._warning_duration = 0
        
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
    
    def warning_screen(self, color: Tuple[int, int, int], text: str, duration: float) -> None:
        """
        Display a warning screen overlay with specified color and text for a duration.
        
        Args:
            color: RGB tuple for the warning screen color (e.g., RED, YELLOW)
            text: Text to display in the center of the screen
            duration: How long to show the warning in seconds
        """
        with self._warning_lock:
            self._warning_active = True
            self._warning_color = color
            self._warning_text = text
            self._warning_start_time = time.time()
            self._warning_duration = duration
    
    def _draw_warning_overlay(self, frame: pygame.Surface) -> None:
        """Draw the warning overlay on the frame if active."""
        with self._warning_lock:
            if not self._warning_active:
                return
            
            # Check if warning duration has elapsed
            elapsed = time.time() - self._warning_start_time
            if elapsed > self._warning_duration:
                self._warning_active = False
                return
            
            # Create semi-transparent overlay
            overlay = create_surface(self.xres, self.yres)
            overlay.fill(self._warning_color)
            overlay.set_alpha(200)  # 200/255 opacity for visibility
            
            # Blit overlay onto frame
            frame.blit(overlay, (0, 0))
            
            # Draw text in center
            try:
                font = pygame.font.Font(self.font_path, 48)
                text_surf = font.render(self._warning_text, True, WHITE)
                text_rect = text_surf.get_rect(center=(self.xres // 2, self.yres // 2))
                frame.blit(text_surf, text_rect)
            except Exception as e:
                print(f"Error rendering warning text: {e}")
    
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
        
        # Draw warning overlay if active
        self._draw_warning_overlay(frame)
        
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
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_SPACE:
                            self.warning_screen(RED, "Good Test", 1.0)
                                
                frame = self.render_frame()
                blit_surface(frame)
                
                clock.tick_busy_loop(FPS_CAP)
        except Exception as e:
            print(f"UI thread error: {e}")
        finally:
            cleanup()
            print("UI thread stopped")
