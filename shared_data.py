#!/usr/bin/env python3

import threading
import time
from typing import Dict, Any, Optional


class LatestValuesTable:
    """Thread-safe table of latest CAN signal values keyed by signal name."""
    
    def __init__(self):
        self._locks: Dict[str, Any] = {}
        self._table: Dict[str, Dict[str, Any]] = {}  # signal_name -> {value, timestamp}
    
    def update(self, decoded_signals: Dict[str, Any]) -> None:
        """
        Update the table with decoded signals.
        
        Args:
            decoded_signals: Dictionary of signal_name: value pairs
        """
        timestamp = time.perf_counter()

        for signal_name, value in decoded_signals.items():
            with self._locks.setdefault(signal_name, threading.RLock()): # initialize a new RLock for new signals
                self._table[signal_name] = {
                    'value': value,
                    'timestamp': timestamp
                }
                
    
    def get_signal(self, signal_name: str) -> Optional[Any]:
        """
        Get a signal value by name.
        Returns the value or None if not found.
        """
        with self._locks.setdefault(signal_name, threading.RLock()):
            entry = self._table.get(signal_name)
            if entry:
                return entry['value']

        return None
    
    def get_snapshot(self) -> Dict[str, Any]:
        """
        Get a thread-safe snapshot of all signal values.
        Returns a copy to avoid lock contention during rendering.
        """
        snapshot: Dict[str, Any] = {}
        
        for signal_name, entry in self._table.items():
            with self._locks.setdefault(signal_name, threading.RLock()):
                snapshot[signal_name] = entry['value']

        return snapshot
