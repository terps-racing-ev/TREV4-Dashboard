import time
import sys
import json
from pathlib import Path
from typing import Tuple, Dict
from dashboard import Dashboard
from graphics_driver import *
import pygame

SIG_PACK_TEMP  = "PackTemp"
WARN_BAT_TEMP  = 48.0

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

class PageManager:
    def __init__(self, pages: list[Dashboard]):
        self.pages = pages
        self._ui_thread_active = False
        self.current_page = 0
        self._flash_state = False
        self._flash_t     = 0.0
        self.FPS_CAP = 60

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
        print(f"UI thread started ({self.FPS_CAP} fps)")
        
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
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_RIGHT:
                        print(f"\n Switching to page: {(self.current_page + 1) % len(self.pages)}")
                        self.current_page = (self.current_page + 1) % len(self.pages)
                                
                frame = self.pages[self.current_page].render_frame()
                blit_surface(frame)

                dt = clock.tick_busy_loop(self.FPS_CAP)
                self._flash_t += dt / 1000.0
                if self._flash_t >= 0.5:
                    self._flash_t, self._flash_state = 0.0, not self._flash_state
        except Exception as e:
            print(f"UI thread error: {e}")
        finally:
            cleanup()
            print("UI thread stopped")
