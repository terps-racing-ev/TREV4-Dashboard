#!/usr/bin/env python3
"""
Handles RX, TX, and UI threads
"""

import threading
import time

from shared_data import LatestValuesTable
from can_manager import CANManager
from dashboard import Dashboard
from fb_driver import hide_cursor, show_cursor


def main():

    # Simulate values if you don't have CAN hardware
    SIM_MODE = True
    
    # Shared state for all threads to access values
    shared_data = LatestValuesTable()
    
    can_mgr = CANManager(shared_data=shared_data, sim_mode=SIM_MODE)
    dashboard = Dashboard(shared_data=shared_data)
    
    # Initialize CAN
    print("Loading .dbc file...")
    if not can_mgr.load_dbc():
        print("Failed to load .dbc file. Exiting.")
        return
    
    print("Starting CAN listener...")
    if not can_mgr.start_can_listener():
        print("Failed to start CAN listener. Exiting.")
        return
    
    hide_cursor()
    
    # RX
    rx_thread = threading.Thread(target=can_mgr.run_rx_thread, daemon=True)
    rx_thread.name = "RX"
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
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Signal threads to stop
        can_mgr._rx_thread_active = False
        can_mgr._tx_thread_active = False
        
        # Wait for threads to finish (with timeout)
        rx_thread.join(timeout=2.0)
        tx_thread.join(timeout=2.0)
        
        # Clean up CAN bus
        can_mgr.stop()
        
        show_cursor()
        print("Shutdown complete.")


if __name__ == "__main__":
    main()
