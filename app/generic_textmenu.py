#!/usr/bin/env python3

"""
Author: Charles Hu w/ AI assist

The code in this file handles the logic which lets you select through text-based
menus like this:

.  (Up one)
.  (Home)

>  Option 1
.  Option 2

to change settings and fire callbacks when settings are changed.

This functionality comes in the form of the TextMenu class which contains 
(A) a tree of all the potential options 
(B) the ability to scroll through menus, select items, etc. with method calls
(C) the ability to draw some text to be printed to show to the user what they can do

The driver code for this class is responsible for the following:
1. Listening for I/O (network requests, keyboard presses, knob/button activity on GPIO pins)
   and forwarding that information to the TextMenu through the scroll_up(), etc. methods.
2. Specifying the menu structure, including defining and providing callbacks which contain 
   instructions on what to do when a setting is changed.
"""

import sys
import os
import json


class TextMenu:
    """
    Text-based hierarchical configuration menu.
    Menu specification:

        {
            "option1": ["enum", ["A", "B", "Off"], callback],
            "option2": {
                "suboption": ["range", 0, 100, 5, callback]
            }
        }

    Controls are handled by the driver:
        scroll_up()
        scroll_down()
        select()

    The class itself knows nothing about the keyboard.
    """

    def __init__(self, menu):
        self.root = menu

        # Stack of dictionaries representing our path through the tree.
        self.menu_stack = []

        # Current menu dictionary.
        self.current_menu = self.root

        # Index of currently highlighted item.
        # -2 = Prev Page
        # -1 = Home
        #  0+ = actual menu items
        self.selected = 0

        # If not None, we're editing a leaf item.
        self.editing = None

        # Current values of configuration options.
        self.values = {}

        self._initialize_values(self.root)

    # ------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------

    def _initialize_values(self, menu, path=()):
        """Initialize every leaf option to its first enum value
        or minimum range value."""

        for name, spec in menu.items():
            new_path = path + (name,)

            if isinstance(spec, dict):
                self._initialize_values(spec, new_path)

            elif spec[0] == "enum":
                self.values[new_path] = spec[1][0]

            elif spec[0] == "range":
                self.values[new_path] = spec[1]

    # ------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------

    def _items(self):
        return list(self.current_menu.keys())

    def _selection_count(self):
        """
        Number of selectable things on the current page.

        Every page has:
            Prev Page
            Home
            actual menu options
        """
        return len(self._items()) + 2

    def scroll_up(self):
        if self.editing is not None:
            self._change_value(-1)
            return

        self.selected -= 1

        if self.selected < 0:
            self.selected = self._selection_count() - 1

    def scroll_down(self):
        if self.editing is not None:
            self._change_value(+1)
            return

        self.selected += 1

        if self.selected >= self._selection_count():
            self.selected = 0

    def select(self):
        # --------------------------------------------------------
        # If currently editing a leaf, select exits edit mode.
        # --------------------------------------------------------
        if self.editing is not None:
            self.editing = None
            return

        # --------------------------------------------------------
        # Prev Page
        # --------------------------------------------------------
        if self.selected == 0:
            if self.menu_stack:
                self.current_menu = self.menu_stack.pop()
                self.selected = 0

            return

        # --------------------------------------------------------
        # Home
        # --------------------------------------------------------
        if self.selected == 1:
            self.current_menu = self.root
            self.menu_stack.clear()
            self.selected = 0
            return

        # --------------------------------------------------------
        # Actual menu item
        # --------------------------------------------------------
        index = self.selected - 2
        name = self._items()[index]
        spec = self.current_menu[name]

        # Submenu
        if isinstance(spec, dict):
            self.menu_stack.append(self.current_menu)
            self.current_menu = spec
            self.selected = 0
            return

        # Leaf configuration option
        self.editing = self._get_path(name)

    # ------------------------------------------------------------
    # Value editing
    # ------------------------------------------------------------

    def _get_path(self, name):
        """
        Construct the full path to the current menu item.
        """

        # Reconstruct the path from the menu stack.

        path = []

        def find_path(menu, target, current_path):
            if menu is target:
                return current_path

            for key, value in menu.items():
                if isinstance(value, dict):
                    result = find_path(
                        value,
                        target,
                        current_path + [key]
                    )

                    if result is not None:
                        return result

            return None

        base = find_path(self.root, self.current_menu, [])

        if base is None:
            base = []

        return tuple(base + [name])

    def _get_spec_for_editing(self):
        menu = self.root

        for part in self.editing:
            spec = menu[part]

            if isinstance(spec, dict):
                menu = spec
            else:
                return spec

        return None

    def _change_value(self, direction):
        spec = self._get_spec_for_editing()

        if spec is None:
            return

        kind = spec[0]

        # --------------------------------------------------------
        # ENUM
        # --------------------------------------------------------
        if kind == "enum":
            options = spec[1]

            current = self.values[self.editing]
            index = options.index(current)

            index += direction
            index %= len(options)

            self.values[self.editing] = options[index]

        # --------------------------------------------------------
        # RANGE
        # --------------------------------------------------------
        elif kind == "range":
            minimum = spec[1]
            maximum = spec[2]
            step = spec[3]

            value = self.values[self.editing]
            value += direction * step

            value = max(minimum, min(maximum, value))

            self.values[self.editing] = value

        # Notify callback after changing the value.
        self._call_callback(spec)

    def _call_callback(self, spec):
        callback = spec[-1]

        if callable(callback):
            callback(self.values[self.editing])

    # ------------------------------------------------------------
    # Display
    # ------------------------------------------------------------

    def _current_value(self, name):
        path = self._get_path(name)
        return self.values[path]

    def draw_text(self):
        """
        Return the current screen as a string.
        """

        lines = []

        # Navigation entries

        lines.append(
            ("> " if self.selected == 0 else ". ") +
            "(Prev Page)"
        )

        lines.append(
            ("> " if self.selected == 1 else ". ") +
            "(Home)"
        )

        lines.append("")

        # Menu entries
        for i, name in enumerate(self._items()):
            selection_number = i + 2

            prefix = "> " if self.selected == selection_number else ". "

            spec = self.current_menu[name]

            # Currently editing this option
            if (
                self.editing is not None
                and self.editing == self._get_path(name)
            ):
                # If currently editing, take the > away from the front of the line and 
                # put it < around the value > you're editing
                prefix = ". " 
                value = self._current_value(name)
                lines.append(
                    f"{prefix}{name}: < {value} >"
                )

            # Normal leaf option -- don't show its value
            else:
                if isinstance(self.current_menu[name], list):
                    cur_val = ": " + str(self._current_value(name))
                else:
                    cur_val = ""
                lines.append(
                    f"{prefix}{name}{cur_val}"
                )

        return "\n".join(lines)

    def get_values(self):
        """
        Return the current configuration as a dictionary with
        hierarchical paths converted to dotted strings.
        """

        return {
            "/".join(path): value
            for path, value in self.values.items()
        }



"""
TEST DRIVER CODE for WINDOWS ONLY
"""

# ================================================================
# Example callbacks
# ================================================================

def function1_1(value):
    print(f"option1 changed to {value}")


def function2_1(value):
    print(f"option2.1 changed to {value}")


def function2_2(value):
    print(f"option2.2 changed to {value}")




# ================================================================
# Example menu
# ================================================================

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


# ================================================================
# Keyboard driver
# ================================================================

def clear_screen():
    # ANSI escape sequences work in modern Windows terminals,
    # Linux terminals, macOS terminals, etc.
    os.system("cls")


def get_key():
    """
    Get one keypress without requiring Enter.

    Returns:
        "up"
        "down"
        "select"
        "quit"
    """

    if os.name == "nt":
        import msvcrt

        while True:
            key = msvcrt.getch()

            # Arrow keys produce 0x00 or 0xe0 followed by another byte.
            if key in (b"\x00", b"\xe0"):
                key = msvcrt.getch()

                if key == b"H":
                    return "up"

                if key == b"P":
                    return "down"

            elif key in (b"\r", b" "):
                return "select"

            elif key.lower() == b"q":
                return "quit"

    else:
        import tty
        import termios

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setraw(fd)
            key = sys.stdin.read(1)

            if key == "\x1b":
                # Arrow key sequence: ESC [ A/B
                key2 = sys.stdin.read(1)

                if key2 == "[":
                    key3 = sys.stdin.read(1)

                    if key3 == "A":
                        return "up"

                    if key3 == "B":
                        return "down"

            elif key in ("\r", "\n", " "):
                return "select"

            elif key.lower() == "q":
                return "quit"

        finally:
            termios.tcsetattr(
                fd,
                termios.TCSADRAIN,
                old_settings
            )

def main():
    menu = TextMenu(MENU)

    try:
        while True:
            clear_screen()

            print(menu.draw_text())

            print()
            print("Arrow keys: navigate    Enter/Space: select    Q: quit")

            key = get_key()

            if key == "up":
                menu.scroll_up()

            elif key == "down":
                menu.scroll_down()

            elif key == "select":
                menu.select()

            elif key == "quit":
                break

    except KeyboardInterrupt:
        pass

    finally:
        clear_screen()

    print("Final configuration:")
    print(json.dumps(menu.get_values(), indent=4))


if __name__ == "__main__":
    main()