#!/usr/bin/env python3

import sys
import os
import mmap
import platform
from pathlib import Path
from typing import Iterable, Tuple
import pygame

# Audio is not used by the dashboard, and the dummy driver avoids ALSA noise on
# the Pi when no audio device is configured.
if platform.system() == "Linux":
    os.environ["SDL_AUDIODRIVER"] = "dummy"

# Initialize Pygame
pygame.init()

DISP_RES = (800, 480)
_screen = None
_clock = None
_fb = None
_INVISIBLE_VIDEO_DRIVERS = {"dummy", "offscreen"}


class Framebuffer:
    """Minimal /dev/fb0 RGB565 backend for the Pi display."""

    def __init__(self, path: str = "/dev/fb0") -> None:
        width, height = map(int, Path("/sys/class/graphics/fb0/virtual_size").read_text().split(","))
        bpp = int(Path("/sys/class/graphics/fb0/bits_per_pixel").read_text())
        self.stride = int(Path("/sys/class/graphics/fb0/stride").read_text())
        if (width, height) != DISP_RES or bpp != 16 or self.stride != width * 2:
            raise RuntimeError(f"Unsupported framebuffer mode: {width}x{height} {bpp}bpp stride {self.stride}")

        self.surface = pygame.Surface(DISP_RES, depth=16, masks=(0xF800, 0x07E0, 0x001F, 0))
        self.file = open(path, "r+b", buffering=0)
        self.map = mmap.mmap(self.file.fileno(), self.stride * height)

    def blit(self, surface: pygame.Surface) -> None:
        self.surface.blit(surface, (0, 0))
        self.map[:] = bytes(self.surface.get_buffer())

    def close(self) -> None:
        self.map[:] = b"\x00" * len(self.map)
        self.map.close()
        self.file.close()


def _linux_video_drivers() -> Iterable[str | None]:
    """Return SDL video drivers to try, in the order most likely to work."""
    configured_driver = os.environ.get("SDL_VIDEODRIVER")
    if configured_driver:
        yield configured_driver
        return

    # If the Pi is running a desktop session, SDL's default choice is usually
    # the right one. For console autostart, try direct display drivers first.
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"):
        yield None
        yield "wayland"
        yield "x11"
        yield "kmsdrm"
        yield "linuxfb"
    else:
        yield "kmsdrm"
        yield "linuxfb"
        yield None


def _try_display(driver: str | None, flags: int) -> pygame.Surface:
    """Try one SDL video driver and return the initialized display surface."""
    if driver is None:
        os.environ.pop("SDL_VIDEODRIVER", None)
        driver_name = "SDL default"
    else:
        os.environ["SDL_VIDEODRIVER"] = driver
        driver_name = driver

    pygame.display.quit()
    pygame.display.init()
    screen = pygame.display.set_mode(DISP_RES, flags)
    actual_driver = pygame.display.get_driver()
    if driver is None and actual_driver in _INVISIBLE_VIDEO_DRIVERS:
        pygame.display.quit()
        raise RuntimeError(
            f"SDL default selected invisible '{actual_driver}' backend. "
            "Run from the Pi display session or set DISPLAY/WAYLAND_DISPLAY."
        )
    print(
        f"Display initialized with {driver_name} backend "
        f"(actual: {actual_driver}): {DISP_RES}"
    )
    return screen


def _init_linux_display() -> pygame.Surface:
    """Try Linux SDL video backends in order until one initializes."""
    last_error: Exception | None = None

    requested_driver = os.environ.get("SDL_VIDEODRIVER")
    driver_candidates = [requested_driver] if requested_driver else ["kmsdrm", "fbcon", "x11", "dummy"]

    for driver in driver_candidates:
        try:
            os.environ["SDL_VIDEODRIVER"] = driver
            pygame.display.quit()
            pygame.display.init()
            try:
                _surface = pygame.display.set_mode(DISP_RES, pygame.SCALED)
            except Exception:
                _surface = pygame.display.set_mode(DISP_RES)
            print(f"Display initialized with SDL driver '{driver}': {DISP_RES}")
            return _surface
        except Exception as e:
            last_error = e
            print(f"SDL driver '{driver}' failed: {e}")

    raise RuntimeError(f"No usable SDL video driver found. Last error: {last_error}")


def init_display() -> pygame.Surface:
    """Initialize display and return the surface."""
    global _screen, _clock, _fb
    
    if platform.system() == "Linux":
        try:
            pygame.display.quit()
            _fb = Framebuffer()
            _screen = _fb.surface
            _clock = pygame.time.Clock()
            print(f"Display initialized with framebuffer backend: {DISP_RES}")
            return _screen
        except Exception as e:
            _fb = None
            print(f"Framebuffer initialization failed: {e}")

        last_error: Exception | None = None
        for driver in _linux_video_drivers():
            for flags in (pygame.SCALED, 0):
                try:
                    _screen = _try_display(driver, flags)
                    _clock = pygame.time.Clock()
                    return _screen
                except Exception as e:
                    last_error = e
                    driver_name = driver or "SDL default"
                    print(f"{driver_name} display initialization failed: {e}")
        raise RuntimeError(f"No usable SDL video driver found: {last_error}") from last_error
    else:
        # Windows simulator
        _screen = pygame.display.set_mode(DISP_RES)
        pygame.display.set_caption("TREV4 Dashboard")
        print(f"Windows simulator mode: {DISP_RES}")
    
    _clock = pygame.time.Clock()
    return _screen


def get_surface() -> pygame.Surface:
    """Get the current display surface."""
    global _screen
    if _screen is None:
        _screen = init_display()
    return _screen


def blit_surface(surface: pygame.Surface) -> None:
    """Blit the provided surface to the display and update."""
    if _fb is not None:
        _fb.blit(surface)
        return

    screen = get_surface()
    screen.blit(surface, (0, 0))
    pygame.display.flip()


def create_surface(width: int, height: int) -> pygame.Surface:
    """Create a new Pygame surface."""
    return pygame.Surface((width, height))


def fill_surface(surface: pygame.Surface, color: Tuple[int, int, int]) -> None:
    """Fill surface with a solid color."""
    surface.fill(color)


def get_clock() -> pygame.time.Clock:
    """Get the Pygame clock for FPS management."""
    global _clock
    if _clock is None:
        _clock = pygame.time.Clock()
    return _clock


def cleanup() -> None:
    """Clean up Pygame resources."""
    global _fb
    if _fb is not None:
        _fb.close()
        _fb = None
    pygame.quit()
