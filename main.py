#!/usr/bin/env python3
"""
Handles RX, TX, and UI threads.
Config: prod_config.json and prod.dbc (local); when USB has these files, local copies are updated.
"""
# import pygame
# pygame.init()

import json
import threading
import time
from time import sleep
from sys import platform

from python.shared_data import LatestValuesTable
from python.can_manager import CANManager
from python.dashboard import Dashboard
from python.page_manager import PageManager
from python import config_loader


def ensure_builtin_pages(prod_config: dict) -> dict:
    """Append code-defined pages that should exist even when USB config is older."""
    retro_page = {
        "display": {
            "width": 800,
            "height": 480,
            "bg_color": [5, 5, 5],
        },
        "gauges": [
            {"type": "RetroHeroDash", "box_xywh": [0, 0, 800, 480]},
        ],
    }

    pages = prod_config.get("pages")
    if isinstance(pages, list):
        has_retro = any(
            any(gauge.get("type") == "RetroHeroDash" for gauge in page.get("gauges", []))
            for page in pages
            if isinstance(page, dict)
        )
        if not has_retro:
            pages.append(retro_page)
            print("Injected built-in RetroHeroDash page")
    return prod_config


def main():
    # Simulate values if you don't have CAN hardware
    SIM_MODE = False
    on_windows = platform == "win32"

    if on_windows:
        print("Running on Windows - using virtual CAN interface (sim mode)")
        SIM_MODE = True

    # On Windows, load local files only. On other platforms, refresh local copies from USB first.
    if not on_windows:
        config_loader.sync_config_from_usb()
        config_loader.sync_dbcs_from_usb()
    config_path = config_loader.get_local_config_path()
    dbc_paths = config_loader.get_local_dbc_paths()
    if not config_path.is_file():
        print("prod_config.json not found locally. Exiting.")
        return
    if not dbc_paths:
        print("No .dbc files found locally. Exiting.")
        return

    with open(config_path, encoding="utf-8") as f:
        prod_config = json.load(f)

        #getting rid of the evangelion shit 
    #prod_config = ensure_builtin_pages(prod_config)

    shared_data = LatestValuesTable()

    # Build dashboard list: multi-page ("pages" array) or single-page (legacy)
    if "pages" in prod_config and isinstance(prod_config["pages"], list):
        dashboards = [
            Dashboard(shared_data=shared_data, config_dict=page)
            for page in prod_config["pages"]
        ]
    else:
        dashboards = [Dashboard(shared_data=shared_data, config_dict=prod_config)]

    if not dashboards:
        print("No dashboard pages loaded from prod_config.json. Exiting.")
        return

    can_mgr = CANManager(shared_data=shared_data, dbc_paths=dbc_paths, sim_mode=SIM_MODE)

    pages = PageManager(dashboards)
    
    # Load DBC
    if not can_mgr.load_dbc():
        print("Failed to load .dbc file. Exiting.")
        return
    
    print("Starting CAN listener...")
    if not can_mgr.start_can_listener():
        print("Failed to start CAN listener. Exiting.")
        return
        
    # RX
    rx_thread = threading.Thread(target=can_mgr.run_rx_thread, daemon=True)
    rx_thread.name = "RX"
    rx_thread.start()

    # TX
    tx_thread = threading.Thread(target=can_mgr.run_tx_thread, daemon=True)
    tx_thread.name = "TX"
    tx_thread.start()
    
    # UI
    ui_thread = threading.Thread(target=pages.run_ui_thread, daemon=True)
    ui_thread.name = "UI"
    ui_thread.start()

    # Optional: periodically re-sync prod_config.json from USB when plugged in
    SYNC_INTERVAL_SEC = 30
    last_sync = 0.0

    try:
        while True:
            # Exit if UI thread stops
            if not ui_thread.is_alive():
                print("\nUI thread stopped, shutting down...")
                break
            if not on_windows:
                now = time.monotonic()
                if now - last_sync >= SYNC_INTERVAL_SEC:
                    config_loader.sync_config_from_usb()
                    config_loader.sync_dbcs_from_usb()
                    last_sync = now
            sleep(0.1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Signal threads to stop
        can_mgr._rx_thread_active = False
        can_mgr._tx_thread_active = False
        pages._ui_thread_active = False

        # Wait for threads to finish (with timeout)
        rx_thread.join(timeout=2.0)
        tx_thread.join(timeout=2.0)
        ui_thread.join(timeout=2.0)
        
        # Clean up CAN bus
        can_mgr.stop()
        
        print("Shutdown complete.")


if __name__ == "__main__":
    main()
