#!/usr/bin/env python3

import glob
import time
import random
from pathlib import Path
from typing import Optional, Dict, Any
import can
import cantools

from python.shared_data import LatestValuesTable

BAUD_RATE = 500000

# Note: This requires the pi to have can-init.service

class CANManager:
    
    def __init__(self, shared_data: LatestValuesTable, dbc_path: Path, sim_mode: bool = False):
        self.db: Optional[cantools.database.Database] = None
        self.dbc_path = dbc_path
        self.bus: Optional[can.Bus] = None
        
        # Shared state for latest values
        self.shared_data = shared_data
        
        # Thread control
        self._rx_thread_active = False
        self._tx_thread_active = False
        
        # Simulation mode
        self.sim_mode = sim_mode
    
    def load_dbc(self) -> bool:        
        try:
            self.db = cantools.database.load_file(str(self.dbc_path))
            print(f"Loaded {len(self.db.messages)} message(s) from dbc")
            return True
        except Exception as e:
            print(f"Error loading .dbc file: {e}")
            return False
    
    def decode_message(self, msg: can.Message) -> Dict[str, Any]:
        """Decode a CAN message and update shared data."""       
        try:
            # Find the message definition by arbitration ID
            dbc_message = self.db.get_message_by_frame_id(msg.arbitration_id)
            # Decode the message data
            decoded = dbc_message.decode(msg.data)
            # Update shared data (now keyed by signal name)
            self.shared_data.update(decoded)
            return decoded
        except KeyError:
            # Message ID not in database
            return {}
        except Exception as e:
            print(f"Error decoding message {msg.arbitration_id:X}: {e}")
            return {}

    def encode_message(self, msg_name: str, sigs: Dict[str, Any]) -> Optional[can.Message]:
        try:
            # Find the message definition by name
            msg = self.db.get_message_by_name(msg_name)
            # Encode the signals
            data = msg.encode(sigs)
            # Create CAN message
            return can.Message(arbitration_id=msg.frame_id, data=data)
        except Exception as e:
            print(f"Error encoding message {msg_name}: {e}")
            return None 

    
    # TODO support two busses
    def start_can_listener(self, interface: str = 'can0', bitrate: int = BAUD_RATE) -> bool:
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
            while self._rx_thread_active:
                msg = self.bus.recv(timeout=0.1)
                if msg is not None:
                    print(msg)
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
        start_time = time.time()

        try:
            while self._rx_thread_active:
                elapsed = time.time() - start_time

                # Generate simulated data for each message in the database
                for message in self.db.messages:
                    sim_signals = {}

                    if message.name == "statustest":
                        # Signals activate one-by-one in 5s increments, ordered by start bit
                        for i, signal in enumerate(sorted(message.signals, key=lambda s: s.start)):
                            sim_signals[signal.name] = 1 if elapsed >= (i + 1) * 5 else 0
                    else:
                        for signal in message.signals:
                            value = self.shared_data.get_signal(signal.name)
                            if not value or value >= signal.maximum:
                                continue
                            value += 1
                            sim_signals[signal.name] = value

                    # Update shared data
                    self.shared_data.update(sim_signals)

                time.sleep(0.05)
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
