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

    def __init__(self, shared_data: LatestValuesTable, dbc_paths: list[Path], sim_mode: bool = False):
        self.db: Optional[cantools.database.Database] = None
        self.dbs: list[cantools.database.Database] = []
        self.dbc_paths = dbc_paths
        self.buses: list[can.Bus] = []

        # Shared state for latest values
        self.shared_data = shared_data

        # Thread control
        self._rx_thread_active = False
        self._tx_thread_active = False

        # Simulation mode
        self.sim_mode = sim_mode
    
    def load_dbc(self) -> bool:        
        try:
            self.dbs = []
            for dbc_path in self.dbc_paths:
                db = cantools.database.load_file(str(dbc_path))
                self.dbs.append(db)
                print(f"Loaded {len(db.messages)} message(s) from {dbc_path}")

            if not self.dbs:
                print("No DBC files were loaded")
                return False

            self.db = self.dbs[0]
            return True
        except Exception as e:
            print(f"Error loading .dbc file: {e}")
            return False
    
    def decode_message(self, msg: can.Message) -> Dict[str, Any]:
        """Decode a CAN message and update shared data."""       
        try:
            for db in self.dbs:
                try:
                    dbc_message = db.get_message_by_frame_id(msg.arbitration_id)
                    decoded = dbc_message.decode(msg.data)
                    self.shared_data.update(decoded)
                    return decoded
                except KeyError:
                    continue

            return {}
        except Exception as e:
            print(f"Error decoding message {msg.arbitration_id:X}: {e}")
            return {}

    def encode_message(self, msg_name: str, sigs: Dict[str, Any]) -> Optional[can.Message]:
        try:
            for db in self.dbs:
                try:
                    msg = db.get_message_by_name(msg_name)
                    data = msg.encode(sigs)
                    return can.Message(arbitration_id=msg.frame_id, data=data)
                except KeyError:
                    continue

            raise KeyError(msg_name)
        except Exception as e:
            print(f"Error encoding message {msg_name}: {e}")
            return None 

    
    def start_can_listener(self, interfaces: list[str] | None = None, bitrate: int = BAUD_RATE) -> bool:
        # TODO: driver stuff
        if interfaces is None:
            interfaces = ['can0', 'can1']

        if self.sim_mode:
            print("CAN simulation mode enabled - no hardware interface")
            return True

        self.buses = []
        failed = []
        for interface in interfaces:
            try:
                bus = can.interface.Bus(
                    channel=interface,
                    bustype='socketcan',
                    bitrate=bitrate
                )
                self.buses.append(bus)
                print(f"CAN listener started on {interface} at {bitrate} bps")
            except Exception as e:
                print(f"Error starting CAN listener on {interface}: {e}")
                failed.append(interface)

        if not self.buses:
            return False
        if failed:
            print(f"Warning: failed to open interfaces: {failed}")
        return True
    
    def run_rx_thread(self) -> None:
        """
        RX thread main loop. Continuously reads CAN messages.
        Blocks waiting for frames; never returns (run in a daemon thread).
        """
        if self.sim_mode:
            self._run_sim_rx_thread()
            return
        
        if not self.buses:
            print("CAN bus not initialized")
            return
        
        print(f"RX thread started ({len(self.buses)} bus(es))")
        self._rx_thread_active = True
        
        try:
            while self._rx_thread_active:
                for bus in self.buses:
                    msg = bus.recv(timeout=0.01)
                    if msg is not None:
                        print(msg)
                        self.decode_message(msg)
        except Exception as e:
            print(f"RX thread error: {e}")
        finally:
            self._rx_thread_active = False
            print("RX thread stopped")
    
    def _get_spiral_values(self, elapsed: float) -> tuple:
        """Generate spiral path coordinates for G-force visualization.
        Returns (lateral_g, longitudinal_g) following an expanding spiral.
        """
        import math
        # Angle increases with time (one full rotation every 4 seconds)
        angle = (elapsed / 4.0) * 2 * math.pi
        # Radius expands slowly, cycling back when too large
        radius = (elapsed / 10.0) % 2.0
        # Generate spiral coordinates, scaled to ±2G range
        lateral = radius * math.cos(angle)
        longitudinal = radius * math.sin(angle)
        return (lateral, longitudinal)

    def _run_sim_rx_thread(self) -> None:
        """Simulated RX thread - generates CAN values that cycle through their ranges."""
        if not self.dbs:
            print("No .dbc loaded for simulation")
            return
        
        print("RX simulation thread started")
        self._rx_thread_active = True
        start_time = time.time()
        value = 0

        try:
            while self._rx_thread_active:
                elapsed = time.time() - start_time

                # Generate simulated data for each message in every loaded database
                for db in self.dbs:
                    for message in db.messages:
                        sim_signals = {}

                        if message.name == "statustest":
                            # Signals activate one-by-one in 5s increments, ordered by start bit
                            for i, signal in enumerate(sorted(message.signals, key=lambda s: s.start)):
                                sim_signals[signal.name] = 1 if elapsed >= (i + 1) * 5 else 0
                        else:
                            for signal in message.signals:
                                # Special handling for G-force signals (spiral path)
                                if signal.name in ("LateralG", "LongitudinalG"):
                                    spiral_lat, spiral_lon = self._get_spiral_values(elapsed)
                                    if signal.name == "LateralG":
                                        sim_signals[signal.name] = max(signal.minimum, min(signal.maximum, spiral_lat))
                                    else:  # LongitudinalG
                                        sim_signals[signal.name] = max(signal.minimum, min(signal.maximum, spiral_lon))
                                else:
                                    # Cycle the value through the signal's range using modulo
                                    max_val = signal.maximum
                                    min_val = signal.minimum
                                    range_val = max_val - min_val
                                    cycled_value = min_val + (value % (int(range_val) + 1))
                                    sim_signals[signal.name] = cycled_value

                        # Update shared data
                        self.shared_data.update(sim_signals)

                value += 1
                time.sleep(0.05)
        except Exception as e:
            print(f"RX simulation thread error: {e}")
        finally:
            self._rx_thread_active = False
            print("RX simulation thread stopped")
    
    def run_tx_thread(self) -> None:
        """
        TX thread main loop. Runs on 100 ms schedule (10 Hz).
        Broadcasts all configured messages from shared_data.
        """
        import time

        print("TX thread started")
        self._tx_thread_active = True
        tx_interval = 0.1  # 100 ms / 10 Hz

        # Messages to transmit, mapped to their signals with defaults
        TX_MESSAGES = {

        }

        try:
            while self._tx_thread_active:
                for msg_name, signal_names in TX_MESSAGES.items():
                    # Pull latest values from shared_data, defaulting to 0
                    sigs = {
                        name: (self.shared_data.get_signal(name) or 0)
                        for name in signal_names
                    }

                    can_msg = self.encode_message(msg_name, sigs)
                    if can_msg is None:
                        continue

                    # Mark as extended frame (29-bit ID) to match J1939PG format
                    can_msg.is_extended_id = True

                    if self.sim_mode:
                        pass
                        #print(f"[TX SIM] {msg_name}: {sigs}")
                    else:
                        for bus in self.buses:
                            bus.send(can_msg)

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
        for db in self.dbs:
            for message in db.messages:
                for signal in message.signals:
                    signal_names.append(signal.name)
        return signal_names
    
    def stop(self):
        for bus in self.buses:
            bus.shutdown()
        self.buses = []
