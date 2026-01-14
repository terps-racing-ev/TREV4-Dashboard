#!/usr/bin/env python3

import glob
import time
import random
from pathlib import Path
from typing import Optional, Dict, Any
import can
import cantools

from shared_data import LatestValuesTable

# Note: This requires the pi to have can-init.service

class CANManager:
    
    def __init__(self, shared_data: LatestValuesTable, sim_mode: bool = False):
        self.db: Optional[cantools.database.Database] = None
        self.dbc_path: Optional[Path] = None
        self.bus: Optional[can.Bus] = None
        
        # Shared state for latest values
        self.shared_data = shared_data
        
        # Thread control
        self._rx_thread_active = False
        self._tx_thread_active = False
        
        # Simulation mode
        self.sim_mode = sim_mode
        
    def search_usb_for_dbc(self) -> Optional[Path]:
        # TODO figure out usb
        search_paths = [
            #"/media/*",
            #"/media/*/",
            #"/media/calebjllee/*",
            ".",  # current directory for testing
        ]
        
        for search_path in search_paths:
            pattern = f"{search_path}/**/*.dbc"
            dbc_files = glob.glob(pattern, recursive=True)
            if dbc_files:
                dbc_path = Path(dbc_files[0])
                print(f"Found .dbc file at: {dbc_path}")
                return dbc_path
        
        print("No .dbc file found on USB ports")
        return None
    
    def load_dbc(self, dbc_path: Optional[Path] = None) -> bool:
        if dbc_path is None:
            dbc_path = self.search_usb_for_dbc()
        
        if dbc_path is None:
            print("No .dbc file to load")
            return False
        
        try:
            self.db = cantools.database.load_file(str(dbc_path))
            self.dbc_path = dbc_path
            print(f"Successfully loaded .dbc file: {dbc_path}")
            print(f"Database contains {len(self.db.messages)} messages")
            return True
        except Exception as e:
            print(f"Error loading .dbc file: {e}")
            return False
    
    def get_signal_value(self, signal_name: str) -> Optional[Any]:
        """Get a signal value by name from shared data."""
        return self.shared_data.get_signal(signal_name)
    
    def decode_message(self, msg: can.Message) -> Dict[str, Any]:
        """Decode a CAN message and update shared data."""
        if self.db is None:
            return {}
        
        try:
            # Find the message definition by arbitration ID
            message = self.db.get_message_by_frame_id(msg.arbitration_id)
            # Decode the message data
            decoded = message.decode(msg.data)
            # Update shared data
            self.shared_data.update(msg.arbitration_id, decoded)
            return decoded
        except KeyError:
            # Message ID not in database
            return {}
        except Exception as e:
            print(f"Error decoding message {msg.arbitration_id:X}: {e}")
            return {}
    
    # TODO support two busses
    def start_can_listener(self, interface: str = 'can0', bitrate: int = 500000) -> bool:
        if self.sim_mode:
            print("CAN simulation mode enabled - no hardware interface")
            return True
        
        try:
            self.bus = can.interface.Bus(
                channel=interface,
                bustype='socketcan',
                bitrate=bitrate
            )
            print(f"CAN listener started on {interface} at {bitrate} bps")
            return True
        except Exception as e:
            print(f"Error starting CAN listener: {e}")
            return False
    
    def read_can_messages(self, timeout: float = 0.0):
        if self.bus is None:
            return
        
        while True:
            msg = self.bus.recv(timeout=timeout)
            if msg is not None:
                self.decode_message(msg)
            else:
                break
    
    def run_rx_thread(self) -> None:
        """
        RX thread main loop. Continuously reads CAN messages.
        Blocks waiting for frames; never returns (run in a daemon thread).
        """
        if self.sim_mode:
            self._run_sim_rx_thread()
            return
        
        if self.bus is None:
            print("CAN bus not initialized")
            return
        
        print("RX thread started")
        self._rx_thread_active = True
        
        try:
            # TODO is this sus with the deactivate in main
            while self._rx_thread_active:
                # Block indefinitely waiting for a message (no timeout)
                msg = self.bus.recv(timeout=None)
                if msg is not None:
                    self.decode_message(msg)
        except Exception as e:
            print(f"RX thread error: {e}")
        finally:
            self._rx_thread_active = False
            print("RX thread stopped")
    
    def _run_sim_rx_thread(self) -> None:
        """Simulated RX thread - generates random CAN values."""
        if self.db is None:
            print("No .dbc loaded for simulation")
            return
        
        print("RX simulation thread started")
        self._rx_thread_active = True
        
        try:
            while self._rx_thread_active:
                # Generate simulated data for each message in the database
                for message in self.db.messages:
                    if not self._rx_thread_active:
                        break
                    
                    # Create random signal values
                    sim_signals = {}
                    for signal in message.signals:
                        # Random value within signal min/max range
                        if signal.minimum is not None and signal.maximum is not None:
                            value = random.uniform(signal.minimum, signal.maximum)
                        else:
                            # Default range if not specified
                            value = random.uniform(0, 100)
                        
                        # Handle integer signals
                        if signal.is_signed or (signal.scale == 1 and signal.offset == 0):
                            value = int(value)
                        
                        sim_signals[signal.name] = value
                    
                    # Update shared data
                    self.shared_data.update(message.frame_id, sim_signals)
                
                # Sleep to simulate message rate (adjust for realism)
                time.sleep(0.05)  # 20 Hz update rate
        except Exception as e:
            print(f"RX simulation thread error: {e}")
        finally:
            self._rx_thread_active = False
            print("RX simulation thread stopped")
    
    def run_tx_thread(self) -> None:
        """
        TX thread main loop. Runs on 100 ms schedule (10 Hz).
        For now, this is a stub (no messages to transmit).
        """
        import time
        
        print("TX thread started")
        self._tx_thread_active = True
        tx_interval = 0.1  # 100 ms for 10 Hz
        
        try:
            while self._tx_thread_active:
                # TODO: Build and transmit scheduled messages here
                time.sleep(tx_interval)
        except Exception as e:
            print(f"TX thread error: {e}")
        finally:
            self._tx_thread_active = False
            print("TX thread stopped")
    
    # for debugging
    def get_all_signal_names(self) -> list:
        if self.db is None:
            return []
        
        signal_names = []
        for message in self.db.messages:
            for signal in message.signals:
                signal_names.append(signal.name)
        return signal_names
    
    def stop(self):
        if self.bus:
            self.bus.shutdown()
            self.bus = None

_can_manager = None

def get_can_manager(sim_mode: bool = False) -> CANManager:
    global _can_manager
    if _can_manager is None:
        _can_manager = CANManager(sim_mode=sim_mode)
    return _can_manager
