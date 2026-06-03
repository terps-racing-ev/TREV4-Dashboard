#!/usr/bin/env python3
"""
Handles RX, TX, and UI threads
"""

import threading
import time
import glob
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    ROOT_DIR = Path(__file__).resolve().parents[1]
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    from app.shared_data import LatestValuesTable
    from app.can_manager import CANManager
    from app.dashboard import Dashboard
else:
    from .shared_data import LatestValuesTable
    from .can_manager import CANManager
    from .dashboard import Dashboard


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

    # Enable simulation explicitly with TREV_SIM_MODE=1 when no CAN hardware is present.
    sim_mode = os.getenv("TREV_SIM_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
    CAN_INTERFACES = ("can0", "can1")
    
    ROOT_DIR = Path(__file__).resolve().parents[1]
    SEARCH_PATHS = [str(ROOT_DIR / "config"), str(ROOT_DIR)]  # TODO: add USB mount paths
    
    # Search for files
    print("Searching for .dbc file...")
    dbc_path = search_for_file("*.dbc", SEARCH_PATHS)
    if not dbc_path:
        return
    def resolve_dbc_paths() -> dict[str, Path]:
        return {
            interface: (ROOT_DIR / "config" / f"{interface}.dbc")
            if (ROOT_DIR / "config" / f"{interface}.dbc").exists()
            else dbc_path
            for interface in CAN_INTERFACES
        }

    dbc_paths = resolve_dbc_paths()
    
    print("Searching for config.json...")
    config_path = search_for_file("config.json", SEARCH_PATHS)
    if not config_path:
        return
    
    # Shared state for all threads to access values
    shared_data = LatestValuesTable()
    
    can_mgr = CANManager(shared_data=shared_data, dbc_paths=dbc_paths, sim_mode=sim_mode)
    dashboard = Dashboard(shared_data=shared_data, config_path=config_path)
    
    # Load DBC
    if not can_mgr.load_dbc():
        print("Failed to load .dbc file. Exiting.")
        return
    
    print("Starting CAN listener...")
    print(f"Simulation mode: {'enabled' if sim_mode else 'disabled'}")
    if not can_mgr.start_can_listener(CAN_INTERFACES):
        print("Failed to start CAN listener. Exiting.")
        return
        
    # Real CAN RX loops start inside CANManager. Simulation still needs a loop.
    rx_thread = None
    if can_mgr.sim_mode:
        rx_thread = threading.Thread(target=can_mgr.run_rx_thread, daemon=True, name="RX")
        rx_thread.start()

    # TX
    tx_thread = threading.Thread(target=can_mgr.run_tx_thread, daemon=True)
    tx_thread.name = "TX"
    tx_thread.start()
    
    # UI
    ui_thread = threading.Thread(target=dashboard.run_ui_thread, daemon=True)
    ui_thread.name = "UI"
    ui_thread.start()

    # TODO wifi thread
    # TODO where does io belong
        
    try:
        while True:
            can_mgr.replace_dbc_paths(resolve_dbc_paths())
            can_mgr.reload_dbc_if_changed()
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
        dashboard._ui_thread_active = False

        # Wait for threads to finish (with timeout)
        if rx_thread:
            rx_thread.join(timeout=2.0)
        tx_thread.join(timeout=2.0)
        ui_thread.join(timeout=2.0)
        
        # Clean up CAN bus
        can_mgr.stop()
        
        print("Shutdown complete.")


if __name__ == "__main__":
    main()
