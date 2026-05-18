#!/usr/bin/env python3

import threading
import time
from typing import Dict, Any, Optional


class LatestValuesTable:
    """Thread-safe table of latest CAN signal values keyed by signal name."""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._table: Dict[str, Dict[str, Any]] = {}  # signal_name -> {value, timestamp}
    
    def update(self, decoded_signals: Dict[str, Any], display_signals: Dict[str, Any] | None = None) -> None:
        """
        Update the table with decoded signals.
        
        Args:
            decoded_signals: Dictionary of signal_name: value pairs
            display_signals: Optional dictionary of signal_name: display_text pairs
        """
        timestamp = time.perf_counter()
        with self._lock:
            for signal_name, value in decoded_signals.items():
                display_value = value if display_signals is None else display_signals.get(signal_name, value)
                self._table[signal_name] = {
                    'value': value,
                    'display_value': display_value,
                    'timestamp': timestamp,
                }
    
    def get_signal(self, signal_name: str) -> Optional[Any]:
        """
        Get a signal value by name.
        Returns the value or None if not found.
        """
        with self._lock:
            entry = self._table.get(signal_name)
            if entry:
                return entry['value']
        return None

    def get_display_signal(self, signal_name: str) -> Optional[Any]:
        """
        Get the display value for a signal by name.
        Returns the display value or None if not found.
        """
        with self._lock:
            entry = self._table.get(signal_name)
            if entry:
                return entry.get('display_value', entry['value'])
        return None
    
    def get_snapshot(self) -> Dict[str, Any]:
        """
        Get a thread-safe snapshot of all signal values.
        Returns a copy to avoid lock contention during rendering.
        """
        with self._lock:
            return {
                signal_name: entry['value']
                for signal_name, entry in self._table.items()
            }
