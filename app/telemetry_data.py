"""Forward CANManager's per-frame results to the separate telemetry sender."""

import json
import math
import os
import socket
import sys


# Match telemetry/canmanager_input.py. Linux abstract sockets have no file to
# remove when telemetry stops; either process can be started first.
DEFAULT_SOCKET_NAME = "trevcan-telemetry"


class TelemetryData:
    def __init__(self, socket_name: str | None = None):
        name = socket_name or os.getenv("TREVCAN_TELEMETRY_SOCKET", DEFAULT_SOCKET_NAME)
        self.address = "\0" + name
        self._socket = None
        self.dropped = 0

        # Open one sending socket before CANManager starts its two RX threads.
        # An unconnected datagram socket works even while telemetry is stopped.
        # Simulation on other platforms does not need a local telemetry socket.
        if sys.platform == "linux":
            try:
                self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                self._socket.setblocking(False)
            except OSError:
                self.close()

    @staticmethod
    def _signal_value(value):
        # Preserve the raw frame even when a floating-point CAN signal is NaN
        # or infinite. JSON null is valid; the dashboard keeps its original value.
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    def put(self, msg, decoded: dict, *, timestamp_ns: int,
            labels: dict | None = None, dbc: str = "", message: str = "",
            bus: str | None = None) -> bool:
        """Offer one raw/decoded pair without waiting for telemetry to receive it."""
        if self._socket is None:
            return False

        try:
            # Keep the raw bytes, flags, capture time, and this decode together.
            # Telemetry's CarBuffer assigns the stream ID and sequence number.
            record = {
                "bus": str(bus if bus is not None else msg.channel or "unknown"),
                "can_id": msg.arbitration_id,
                "timestamp_ns": timestamp_ns,
                "is_extended": msg.is_extended_id,
                "is_remote": msg.is_remote_frame,
                "is_fd": msg.is_fd,
                "is_error": msg.is_error_frame,
                "dlc": msg.dlc,
                "data": bytes(msg.data).hex().upper(),
                "decoded": {name: self._signal_value(value)
                            for name, value in decoded.items()},
                "dbc": dbc,
                "message": message,
                # Labels are already resolved by CANManager. No DBC work happens
                # in this output connection or in the car telemetry process.
                "labels": labels or {},
            }
            payload = json.dumps(record, separators=(",", ":"), allow_nan=False).encode("utf-8")
            self._socket.sendto(payload, self.address)
            return True
        except (OSError, TypeError, ValueError):
            # An absent receiver or a full socket queue drops only this telemetry
            # copy. Dashboard CAN reception and latest-value updates continue.
            self.dropped += 1
            return False

    def close(self):
        # CANManager calls this after its RX threads stop. Closing this sending
        # socket does not stop the separate telemetry receiver or its TCP sender.
        if self._socket is not None:
            self._socket.close()
            self._socket = None
