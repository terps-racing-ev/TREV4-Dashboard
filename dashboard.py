#!/usr/bin/env python3

from __future__ import annotations

import time
from pathlib import Path
from typing import Tuple
from PIL import Image

from artist import *
from fb_driver import *
from colors import *
from shared_data import LatestValuesTable

DISP_RES = 800, 480
FPS_CAP = 20

class Dashboard:
    """Handles framebuffer drawing with a cached background."""

    def __init__(self, shared_data: LatestValuesTable, 
                 bg_color: Tuple[int, int, int] = BLACK, font_path: Path | None = None ) -> None:
        self.xres, self.yres = DISP_RES

        self.font_path = font_path or DEFAULT_FONT
        self.background = self.create_background(bg_color)
        self.shared_data = shared_data

    def create_background(self, bg_color: Tuple[int, int, int]) -> Image.Image:
        """Create a base background layer once."""
        return Image.new("RGB", (self.xres, self.yres), bg_color)
    
    def render_frame(self) -> Image.Image:
        """
        Create an Image using the data from the shared state.
        Called by UI thread.
        Returns the rendered image (caller should blit).
        """
        frame = self.background.copy()
        
        # TODO read from a json config

        # Get data
        if self.shared_data:
            speed = self.shared_data.get_signal("Speed")
        else:
            speed = None
        
        display_value = speed if speed is not None else 0
        
        simple_gauge(
            frame,
            label_str="SPEED",
            data_str=str(display_value),
            box_xywh=(300, 100, 200, 200),
            box_color=None
        )
        
        return frame
    
    def run_ui_thread(self) -> None:
        """
        UI thread: Renders at fixed fps.
        """
        frame_time = 1.0 / FPS_CAP
        
        print(f"UI thread started ({FPS_CAP} fps)")
        
        try:
            while True:
                start = time.perf_counter()
                
                frame = self.render_frame()
                blit(frame)
                
                elapsed = time.perf_counter() - start
                sleep_time = frame_time - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        except Exception as e:
            print(f"UI thread error: {e}")
        finally:
            print("UI thread stopped")