#!/usr/bin/env python3

import sys
import os
import platform
from typing import Tuple
import pygame

# KMSDRM setup for Linux: direct GPU access, avoids framebuffer bottleneck
if platform.system() == "Linux":
    os.environ["SDL_VIDEO_DRIVER"] = "kmsdrm"
    os.environ["SDL_AUDIO_DRIVER"] = "dummy"

# Initialize Pygame
pygame.init()

DISP_RES = (800, 480)
_screen = None
_clock = None


def init_display() -> pygame.Surface:
    """Initialize display and return the surface."""
    global _screen, _clock
    
    if platform.system() == "Linux":
        # KMSDRM backend on Linux - direct GPU access via DRM
        try:
            _screen = pygame.display.set_mode(DISP_RES, pygame.SCALED)
            print(f"Display initialized with KMSDRM backend: {DISP_RES}")
        except Exception as e:
            print(f"KMSDRM initialization failed: {e}. Falling back to default driver.")
            _screen = pygame.display.set_mode(DISP_RES)
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
    pygame.quit()
