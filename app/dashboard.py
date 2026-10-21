#!/usr/bin/env python3

from __future__ import annotations

import time
import sys
from pathlib import Path
import pygame

from .graphics_driver import *
from .gauge_config import DISPLAY_SIZE, instantiate_gauge, load_dashboard_config
from .shared_data import LatestValuesTable
from .generic_textmenu import *

FPS_CAP = 30
ROOT_DIR = Path(__file__).resolve().parents[1]
BLACK = (0, 0, 0)

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
        self.brightness = 100
        self.xres, self.yres = DISPLAY_SIZE
        self.gauges = []
        self._config_mtime_ns: int | None = None
        self._next_config_check_at = 0.0

        self._ui_thread_active = False

        # Initialize the system which lets you scroll
        # through options on the dashboard using the rotary encoder (or the keyboard
        # if you just need to test it)
        self.encoder_menu_state_machine = TextMenu(TEST_MENU_TREE_1)
        self.encoder_menu_visible = True
        
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
            bg_color = tuple(config["display"]["bg_color"])
            brightness = int(config.get("brightness", 100))
            gauge_configs = config.get("gauges", [])
            if not gauge_configs:
                print("No gauges in config")
                return False

            gauges = []
            for gauge_cfg in gauge_configs:
                gauges.append(instantiate_gauge(gauge_cfg, self.shared_data))

            self.bg_color = bg_color
            self.brightness = brightness
            self.gauges = gauges
            if self.config_path is not None:
                self._config_mtime_ns = self.config_path.stat().st_mtime_ns

            print(f"Loaded {len(self.gauges)} gauge(s) from config")
            return len(self.gauges) > 0
        except Exception as e:
            print(f"Error loading config: {e}")
            return False

    def _reload_config_if_changed(self) -> None:
        if self.config_path is None or self._config_override is not None:
            return

        now = time.monotonic()
        if now < self._next_config_check_at:
            return
        self._next_config_check_at = now + 1.0

        try:
            latest_mtime_ns = self.config_path.stat().st_mtime_ns
        except OSError as exc:
            print(f"Could not check config for reload: {exc}")
            return

        if self._config_mtime_ns is None:
            self._config_mtime_ns = latest_mtime_ns
            return
        if latest_mtime_ns == self._config_mtime_ns:
            return

        print("Config changed, reloading dashboard...")
        if not self.load_config():
            print("Config reload failed; keeping previous dashboard state")
        
    def create_frame(self) -> pygame.Surface:
        """Create a fresh frame surface."""
        surface = create_surface(self.xres, self.yres)
        fill_surface(surface, self.bg_color)
        return surface
    
    def render_frame(self) -> pygame.Surface:
        """
        Create a surface using the data from the shared state and the locally
        stored rotary encoder menu state. 
        Called by UI thread.
        Returns the rendered surface.
        """
        self._reload_config_if_changed()
        frame = self.create_frame()
        
        # Update all gauges
        for gauge in self.gauges:
            gauge.update(frame)

        if self.brightness < 100:
            level = max(0, min(255, round(self.brightness * 255 / 100)))
            frame.fill((level, level, level), special_flags=pygame.BLEND_RGB_MULT)

        # If the rotary encoder menu is supposed to be visible, 
        # blit it 
        if self.encoder_menu_visible:
            font = pygame.font.SysFont('Consolas', 35)
            transparent_bgd_surface = pygame.Surface((DISPLAY_SIZE[0], DISPLAY_SIZE[1]), pygame.SRCALPHA)
            pygame.draw.rect(transparent_bgd_surface, (0, 0, 0, 220), transparent_bgd_surface.get_rect())
            y_offset = 20
            for line in self.encoder_menu_state_machine.draw_text().split("\n"):
                text_surface = font.render(line, True, (255, 255, 255))
                transparent_bgd_surface.blit(text_surface, (10, y_offset))
                y_offset += font.get_linesize()  # Move down by the font's line height
            frame.blit(transparent_bgd_surface, (0, 0))
        
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
                        # Stop signal handle
                        if event.type == pygame.QUIT:
                            print("\nWindow closed by user")
                            cleanup()
                            sys.exit(0)

                        # Forward up/down/select events to the rotary encoder 
                        # menu handler
                        elif event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_UP:
                                self.encoder_menu_state_machine.scroll_up()
                            elif event.key == pygame.K_DOWN:
                                self.encoder_menu_state_machine.scroll_down()
                            elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                                self.encoder_menu_state_machine.select()
                                
                frame = self.render_frame()
                blit_surface(frame)
                
                clock.tick_busy_loop(FPS_CAP)
        except Exception as e:
            print(f"UI thread error: {e}")
        finally:
            cleanup()
            print("UI thread stopped")
