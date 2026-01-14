#!/usr/bin/env python3

import threading
import time
from typing import Dict, Any, Optional


class LatestValuesTable:
    """Thread-safe table of latest CAN message values keyed by CAN ID."""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._table: Dict[int, Dict[str, Any]] = {}
    
    def update(self, can_id: int, decoded_signals: Dict[str, Any]) -> None:
        """
        Update the table with decoded signals for a CAN ID.
        
        Args:
            can_id: CAN arbitration ID (frame ID)
            decoded_signals: Dictionary of signal_name: value pairs
        """
        with self._lock:
            self._table[can_id] = {
                'signals': decoded_signals,
                'timestamp': time.perf_counter(),
            }
    
    def get_signal(self, signal_name: str) -> Optional[Any]:
        """
        Get a signal value by name (searches all message entries).
        Returns the value or None if not found.
        """
        with self._lock:
            for can_id, entry in self._table.items():
                if signal_name in entry['signals']:
                    return entry['signals'][signal_name]
        return None
    
    # TODO useful? maybe
    def get_snapshot(self) -> Dict[int, Dict[str, Any]]:
        """
        Get a thread-safe snapshot of the entire table.
        Returns a copy to avoid lock contention during rendering.
        """
        with self._lock:
            # Deep copy the dict
            return {
                can_id: {
                    'signals': entry['signals'].copy(),
                    'timestamp': entry['timestamp'],
                }
                for can_id, entry in self._table.items()
            }
    
    # Prolly don't need
    def get_signals_for_id(self, can_id: int) -> Optional[Dict[str, Any]]:
        """
        Get all signals decoded from a specific CAN ID.
        Returns None if CAN ID not in table.
        """
        with self._lock:
            entry = self._table.get(can_id)
            if entry:
                return entry['signals'].copy()
        return None
