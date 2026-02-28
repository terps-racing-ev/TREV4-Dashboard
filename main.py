#!/usr/bin/env python3
"""
Handles RX, TX, and UI threads
"""
# import pygame
# pygame.init()

import threading
import time
import glob
from pathlib import Path

from shared_data import LatestValuesTable
from can_manager import CANManager
from dashboard import Dashboard
from page_manager import PageManager


def search_for_file(filename: str, search_paths: list | None = None) -> Path | None:
    """
    Search for a file in specified paths. Returns first match or None.
    
    Args:
        filename: Target filename (e.g., "test.dbc" or "config.json")
        search_paths: List of paths to search. Defaults to current directory.
    
    Returns:
        Path to file if found, None otherwise
    """
    if search_paths is None:
        search_paths = ["."]  
    
    for search_path in search_paths:
        pattern = f"{search_path}/**/{filename}"
        matches = glob.glob(pattern, recursive=True)
        if matches:
            found_path = Path(matches[0])
            print(f"Found {filename} at: {found_path}")
            return found_path
    
    print(f"No {filename} found in search paths")
    return None


def main():

    # Simulate values if you don't have CAN hardware
    SIM_MODE = False 
    
    SEARCH_PATHS = [".", "/pages"]  # TODO: add USB mount paths
    
    # Search for files
    print("Searching for .dbc file...")
    dbc_path = search_for_file("*.dbc", SEARCH_PATHS)
    if not dbc_path:
        return
    
    print("Searching for config.json... ALL OF THEM")
    config0 = search_for_file("config.json", SEARCH_PATHS)
    config1 = search_for_file("config1.json", SEARCH_PATHS)
    config2 = search_for_file("config2.json", SEARCH_PATHS)
    if not config0 or not config1 or not config2:
        return
    
    # Shared state for all threads to access values
    shared_data = LatestValuesTable()
    
    can_mgr = CANManager(shared_data=shared_data, dbc_path=dbc_path, sim_mode=SIM_MODE)

    # PAGES ARRAY
    page1 = Dashboard(shared_data=shared_data, config_path=config0)
    page2 = Dashboard(shared_data=shared_data, config_path=config1)
    page3 = Dashboard(shared_data=shared_data, config_path=config2)
    pages = PageManager([page1, page2, page3])
    
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

    # TODO wifi thread
    # TODO where does io belong
        
    try:
        while True:
            # Exit if UI thread stops
            if not ui_thread.is_alive():
                print("\nUI thread stopped, shutting down...")
                break
            time.sleep(0.1)
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
