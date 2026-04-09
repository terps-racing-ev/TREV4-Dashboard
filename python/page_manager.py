import sys
from typing import Dict
from python.dashboard import Dashboard
from python.debug_simulator import DebugSimulator
from python.graphics_driver import *
import pygame

from gpiozero import Button 
import gpiozero
from gpiozero.pins.lgpio import LGPIOFactory
from python.constants.events import SCROLL
gpiozero.Device.pin_Factory = LGPIOFactory


SIG_PACK_TEMP  = "PackTemp"
WARN_BAT_TEMP  = 48.0

LEFT_PAGE_BUTTON = Button(17, bounce_time=0.1)    # GPIO PIN 5
RIGHT_PAGE_BUTTON = Button(27, bounce_time=0.1)    # GPIO PIN 6
SCROLL_LIST_BUTTON= Button(4, bounce_time=0.1)  # GPIO PIN 4

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
        self.shared_data = pages[0].shared_data if pages else None
        self.debug_simulator = DebugSimulator(self.shared_data) if self.shared_data is not None else None
        self.page_names = [self._describe_page(page) for page in pages]

    def _describe_page(self, page: Dashboard) -> str:
        gauge_names = [type(gauge).__name__ for gauge in page.gauges]
        if "RetroHeroDash" in gauge_names:
            return "Retro"
        if "DarkSpeedArc" in gauge_names:
            return "Main"
        return gauge_names[0] if gauge_names else "Empty"

    def _switch_to_page(self, index: int) -> None:
        if not self.pages:
            return
        self.current_page = index % len(self.pages)
        print(f"\nSwitched to page {self.current_page + 1}/{len(self.pages)}: {self.page_names[self.current_page]}")

    def _draw_debug_overlay(self, surf: pygame.Surface) -> None:
        if not self._flash_state or self.debug_simulator is None or not self.debug_simulator.enabled:
            return
        _overlay_rounded_rect(
            surf,
            (255, 37, 37),
            (_ALERT_X, _ALERT_BOTTOM - _ALERT_H, _ALERT_W, _ALERT_H),
            radius=3,
            border=2,
            border_col=(242, 242, 242),
        )
        _overlay_text(
            surf,
            "DEBUG MODE",
            16,
            (242, 242, 242),
            _ALERT_X + _ALERT_W // 2,
            _ALERT_BOTTOM - _ALERT_H // 2,
            bold=True,
            anchor="center",
        )

    def run_ui_thread(self) -> None:
        """
        UI thread: Renders at fixed fps.
        """
        clock = get_clock()
        
        self._ui_thread_active = True
        print(f"UI thread started ({self.FPS_CAP} fps)")

        def _move_page_right():
            self._switch_to_page(self.current_page + 1)

        def _move_page_left():
            self._switch_to_page(self.current_page - 1)

        def _scroll_list():
            print("PRESSED THE SCROLL BUTTON")
            pygame.event.post(pygame.event.Event(SCROLL))

        LEFT_PAGE_BUTTON.when_pressed = _move_page_left
        RIGHT_PAGE_BUTTON.when_pressed = _move_page_right
        SCROLL_LIST_BUTTON.when_pressed = _scroll_list
        
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

                
                frame = self.pages[self.current_page].render_frame()
                self._draw_debug_overlay(frame)
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
