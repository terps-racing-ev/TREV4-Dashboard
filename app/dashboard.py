#!/usr/bin/env python3

from __future__ import annotations

import time
import sys
from pathlib import Path
import pygame

from .graphics_driver import *
from .colors import *
from .gauge_config import DISPLAY_SIZE, instantiate_gauge, load_dashboard_config
from .shared_data import LatestValuesTable

FPS_CAP = 30
ROOT_DIR = Path(__file__).resolve().parents[1]

class Dashboard:
    """Handles rendering to a Pygame surface."""

    def __init__(
        self,
        shared_data: LatestValuesTable,
        config_path: Path | None = None,
        config: dict | None = None,
    ) -> None:
        
        self.shared_data = shared_data
        self.config_path = config_path
        self._config_override = config
        
        # Default values
        self.font_path = str(ROOT_DIR / "assets" / "fonts" / "monofonto rg.otf")
        self.bg_color = BLACK
        self.xres, self.yres = DISPLAY_SIZE
        self.gauges = []

        self._ui_thread_active = False
        
        # Load config and instantiate gauges
        if not self.load_config():
            return
    
    def load_config(self) -> bool:
        """Load gauges from config.json. Returns True if successful."""
        try:
            if self._config_override is not None:
                config = self._config_override
            elif self.config_path is not None:
                config = load_dashboard_config(self.config_path)
            else:
                raise ValueError("Either config_path or config must be provided")
            self.bg_color = tuple(config["display"]["bg_color"])
            
            gauge_configs = config.get("gauges", [])
            if not gauge_configs:
                print("No gauges in config")
                return False
            
            for gauge_cfg in gauge_configs:
                self.gauges.append(instantiate_gauge(gauge_cfg, self.shared_data))
            
            print(f"Loaded {len(self.gauges)} gauge(s) from config")
            return len(self.gauges) > 0
        except Exception as e:
            print(f"Error loading config: {e}")
            return False
        
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
        try:
            # Initialize display
            init_display()
            clock = get_clock()

            self._ui_thread_active = True
            print(f"UI thread started ({FPS_CAP} fps)")

            while self._ui_thread_active:
                # Process Pygame events to prevent freezing
                if pygame.display.get_init():
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
