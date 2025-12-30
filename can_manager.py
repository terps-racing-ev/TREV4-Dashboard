#!/usr/bin/env python3

import os
import glob
from pathlib import Path
from typing import Optional, Dict, Any
import can
import cantools


class CANManager:
    
    def __init__(self):
        self.db: Optional[cantools.database.Database] = None
        self.dbc_path: Optional[Path] = None
        self.signal_values: Dict[str, Any] = {}
        self.bus: Optional[can.Bus] = None
        
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
        return self.signal_values.get(signal_name, None)
    
    def decode_message(self, msg: can.Message) -> Dict[str, Any]:
        if self.db is None:
            return {}
        
        try:
            # Find the message definition by arbitration ID
            message = self.db.get_message_by_frame_id(msg.arbitration_id)
            # Decode the message data
            decoded = message.decode(msg.data)
            # Update stored values
            self.signal_values.update(decoded)
            return decoded
        except KeyError:
            # Message ID not in database
            return {}
        except Exception as e:
            print(f"Error decoding message {msg.arbitration_id:X}: {e}")
            return {}
    
    # TODO support two busses
    def start_can_listener(self, interface: str = 'can0', bitrate: int = 500000) -> bool:
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
        
        msg = self.bus.recv(timeout=timeout)
        if msg is not None:
            self.decode_message(msg)
    
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

def get_can_manager() -> CANManager:
    global _can_manager
    if _can_manager is None:
        _can_manager = CANManager()
    return _can_manager
