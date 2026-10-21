#!/usr/bin/env python3

"""
Implements a new feature for TREV5: when you operate the rotary encoder
on the dashboard, a menu will pop up allowing you to change settings which don't 
normally need to be changed while driving but are still good to have out.

This file contains the following classes:
1. RotaryConfigMenu (actually draws the options on screen)
"""

from .graphics_driver import *
from .gauge_config import DISPLAY_SIZE
import pygame
from .generic_textmenu import *


# initialize state machine for config menu
MENU = {
    "option1": [
        "enum",
        ["Primary", "Off"],
        function1_1
    ],

    "option2": {
        "option2.1": [
            "range",
            0,
            100,
            5,
            function2_1
        ],

        "option2.2": [
            "enum",
            ["A", "B", "Off"],
            function2_2
        ]
    }
}
MENU_SM = TextMenu(MENU)

POPUP_MENU_BGD = (0, 0, 40)

class RotaryConfigMenu: 
    def __init__(
        self,
        config_path: Path | None = None,
        config: dict | None = None
    ):
        self.config_path = config_path
        self._config_override = config
        self.xsize = 0.75 * DISPLAY_SIZE[0]
        self.ysize = 0.60 * DISPLAY_SIZE[1]
        print(f"[RotaryConfigMenu] Pop up size: {self.xsize}x {self.ysize}y")

    def load_config(self) -> bool:
        return True
        # TODO: make it actually load config dynamically

    def create_frame(self) -> pygame.Surface:
        """Creates a blank frame surface to draw text on."""
        frame = create_surface(self.xsize, self.ysize)
        fill_surface(frame, POPUP_MENU_BGD)
        return frame

    def render_frame(self) -> pygame.Surface:
        """Creates a new blank frame and draws the menu text."""
        # 1. Get a blank new frame
        frame = self.create_frame()

        # 2. Draw the text on it
        font = pygame.font.SysFont('Consolas', 35)
        text_surface = font.render(MENU_SM.draw_text(), True, (255, 255, 255))
        frame.blit(text_surface, (10, 10))

        # 3. Return the frame 
        return frame

RCM = RotaryConfigMenu(None, None)

# pygame setup
pygame.init()
screen = pygame.display.set_mode(DISPLAY_SIZE)
clock = pygame.time.Clock()
running = True

while running:
    # poll for events
    # pygame.QUIT event means the user clicked X to close your window
    for event in pygame.event.get():
        # Handle stop signal
        if event.type == pygame.QUIT:
            running = False

        # Handle key presses
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                MENU_SM.scroll_up()
            elif event.key == pygame.K_DOWN:
                MENU_SM.scroll_down()
            elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                MENU_SM.select()

    # fill the screen with a color to wipe away anything from last frame
    screen.fill("purple")

    # RENDER YOUR GAME HERE
    to_draw = RCM.render_frame()
    screen.blit(to_draw, to_draw.get_rect(center=screen.get_rect().center))

    # flip() the display to put your work on screen
    pygame.display.flip()

    clock.tick(60)  # limits FPS to 60

pygame.quit()
        

