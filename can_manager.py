#!/usr/bin/env python3

import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Mapping, Sequence
import can
import cantools

from shared_data import LatestValuesTable

BAUD_RATE = 500000

# Note: This requires the pi to have can-init.service

class CANManager:
    
    def __init__(
        self,
        shared_data: LatestValuesTable,
        dbc_paths: Path | Mapping[str, Path] | None = None,
        sim_mode: bool = False,
        dbc_path: Path | None = None,
    ):
        self.db: Optional[cantools.database.Database] = None
        dbc_paths = dbc_paths or dbc_path
        if dbc_paths is None:
            raise ValueError("A DBC path or interface-to-DBC mapping is required")
        self.dbc_paths = dict(dbc_paths) if isinstance(dbc_paths, Mapping) else {"default": dbc_paths}
        self.dbs: dict[str, cantools.database.Database] = {}
        self.buses: list[can.Bus] = []
        self.threads: list[threading.Thread] = []
        
        # Shared state for latest values
        self.shared_data = shared_data
        
        # Thread control
        self._rx_thread_active = False
        self._tx_thread_active = False
        
        # Simulation mode
        self.sim_mode = sim_mode
    
    def load_dbc(self) -> bool:
        try:
            self.dbs = {
                interface: cantools.database.load_file(str(path))
                for interface, path in self.dbc_paths.items()
            }
            self.db = next(iter(self.dbs.values()), None)
            for interface, db in self.dbs.items():
                print(f"Loaded {len(db.messages)} message(s) from {interface} dbc")
            return True
        except Exception as e:
            print(f"Error loading .dbc file: {e}")
            return False
    
    def _db_for(self, interface: str | None) -> Optional[cantools.database.Database]:
        return self.dbs.get(str(interface)) or self.dbs.get("default")

    def decode_message(self, msg: can.Message, db: Optional[cantools.database.Database] = None) -> Dict[str, Any]:
        """Decode a CAN message with the DBC for its bus and update shared data."""
        db = db or self._db_for(msg.channel)
        if db is None:
            return {}

        try:
            # Find the message definition by arbitration ID
            dbc_message = db.get_message_by_frame_id(msg.arbitration_id)
            # Decode the message data twice so we keep raw numbers for gauge math
            # while also preserving enum labels for display.
            decoded = dbc_message.decode(msg.data, decode_choices=False)
            display_decoded = dbc_message.decode(msg.data)
            # Update shared data (now keyed by signal name)
            self.shared_data.update(decoded, display_decoded)
            return display_decoded
        except KeyError:
            # Message ID not in database
            return {}
        except Exception as e:
            print(f"Error decoding message {msg.arbitration_id:X}: {e}")
            return {}
    
    def start_can_listener(
        self, interfaces: str | Sequence[str] = ("can0", "can1"), bitrate: int = BAUD_RATE
    ) -> bool:
        if self.sim_mode:
            print("CAN simulation mode enabled - no hardware interface")
            return True

        if isinstance(interfaces, str):
            interfaces = (interfaces,)
        
        try:
            self._rx_thread_active = True
            for interface in interfaces:
                thread = threading.Thread(target=self._rx_loop, args=(interface, bitrate), daemon=True, name=f"RX-{interface}")
                thread.start()
                self.threads.append(thread)
            print(f"CAN listener started on {', '.join(interfaces)} at {bitrate} bps")
            return True
        except Exception as e:
            print(f"Error starting CAN listener: {e}")
            self.stop()
            return False
    
    def run_rx_thread(self) -> None:
        """Simulation RX loop. Real CAN receive loops start with start_can_listener()."""
        if self.sim_mode:
            self._run_sim_rx_thread()

    def _rx_loop(self, interface: str, bitrate: int) -> None:
        bus = None
        while self._rx_thread_active:
            try:
                if bus is None:
                    bus = can.interface.Bus(channel=interface, interface='socketcan', bitrate=bitrate)
                    self.buses.append(bus)
                msg = bus.recv(timeout=1.0)
                if msg is not None:
                    self.decode_message(msg, self._db_for(interface))
            except Exception as e:
                if not self._rx_thread_active:
                    break
                print(f"{interface} RX error: {e}; reopening")
                if bus is not None:
                    bus.shutdown()
                    if bus in self.buses:
                        self.buses.remove(bus)
                    bus = None
                time.sleep(1.0)

        if bus is not None:
            bus.shutdown()
    
    def _run_sim_rx_thread(self) -> None:
        """Simulated RX thread - generates random CAN values."""
        if not self.dbs:
            print("No .dbc loaded for simulation")
            return
        
        print("RX simulation thread started")
        self._rx_thread_active = True
        
        try:
            while self._rx_thread_active:
                # Generate simulated data for each message in the database
                for db in self.dbs.values():
                    for message in db.messages:
                    
                        # Create random signal values
                        sim_signals = {}
                        for signal in message.signals:
                            value = self.shared_data.get_signal(signal.name) or 0
                            
                            value += 1
                            if value >= signal.maximum:
                                value = signal.minimum
                            
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
        if not self.dbs:
            return []
        
        signal_names = []
        for db in self.dbs.values():
            for message in db.messages:
                for signal in message.signals:
                    signal_names.append(signal.name)
        return signal_names
    
    def stop(self):
        self._rx_thread_active = False
        for bus in self.buses:
            bus.shutdown()
        for thread in self.threads:
            thread.join(timeout=2.0)
        self.buses = []
        self.threads = []
