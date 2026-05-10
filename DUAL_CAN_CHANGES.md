# Dual CAN Changes

## Current Implementation

- `CANManager` opens `can0` and `can1` by default.
- `CANManager` keeps a separate DBC database per CAN interface.
- Each bus gets its own tiny RX loop.
- Each RX loop calls `CANManager.decode_message()` with that bus's DBC for every received frame.
- The dashboard sees one logical stream of decoded signals; it does not need to know which bus a frame used.
- `start_can_listener()` still accepts either one interface string or a sequence of interface names.

## Optimization Pass

The first optimized version used `python-can.Notifier` directly:

- Removed the `BufferedReader` queue.
- Removed the real-hardware RX polling loop.
- Removed the extra app-level RX thread for real CAN.
- Kept the simulation RX thread only for `sim_mode`.
- Kept shutdown explicit: stop the notifier, then shut down each CAN bus.

That was short, but it exposed an important behavior: if a CAN interface was
bounced while the app was running, the notifier receive thread could die with:

```text
can.exceptions.CanOperationError: Error receiving: Network is down [Error Code 100]
```

The final implementation uses one small resilient RX loop per interface. If a
SocketCAN receive call fails, that loop closes the stale socket, waits briefly,
and reopens the interface.

Current path:

```text
socketcan can0 -> can0 DBC -> decode_message() -> shared_data
socketcan can1 -> can1 DBC -> decode_message() -> shared_data
```

## Files Changed

- `can_manager.py`
  - Stores multiple CAN buses in `self.buses`.
  - Stores loaded DBCs in `self.dbs`, keyed by interface name.
  - Accepts either one legacy DBC path or a mapping like `{"can0": can0_path, "can1": can1_path}`.
  - Starts one daemon RX thread per configured interface.
  - Uses `interface='socketcan'`, the current `python-can` keyword.
  - Reopens a CAN socket if an interface drops and comes back.
  - Leaves `run_rx_thread()` as a simulation-only loop.
  - Cleans up RX threads and all bus objects in `stop()`.

- `main.py`
  - Defaults `SIM_MODE = False`.
  - Looks for `can0.dbc` and `can1.dbc`.
  - Falls back to the first discovered `*.dbc` for any bus-specific DBC that does not exist yet.
  - Starts an RX thread only when simulation mode is enabled.

## Per-Bus DBC Convention

Place bus-specific DBC files at the repo root using these names:

```text
can0.dbc
can1.dbc
```

At startup, `main.py` builds this mapping:

```python
{
    "can0": can0_dbc_path,
    "can1": can1_dbc_path,
}
```

If `can0.dbc` or `can1.dbc` is missing, that bus temporarily uses the first
discovered `*.dbc` file. This keeps the current `test.dbc` setup working while
allowing each bus to move to its own DBC independently.

The loaded DBC output now looks like:

```text
Loaded 2 message(s) from can0 dbc
Loaded 2 message(s) from can1 dbc
```

The old single-DBC constructor style still works for tests or one-bus tools:

```python
CANManager(shared_data, dbc_path=Path("test.dbc"))
```

## Hardware Checks

Both connected CAN interfaces are present and healthy:

```text
can0: UP, LOWER_UP, ERROR-ACTIVE, 500000 bps, mcp251x on spi0.0
can1: UP, LOWER_UP, ERROR-ACTIVE, 500000 bps, mcp251x on spi0.1
```

Earlier notifier open/close smoke test:

```text
Loaded 2 message(s) from dbc
CAN listener started on can0, can1 at 500000 bps
notifier Notifier
buses ["socketcan channel 'can0'", "socketcan channel 'can1'"]
stopped 0 None
```

Passive callback receive test:

```text
Loaded 2 message(s) from dbc
CAN listener started on can0, can1 at 500000 bps
counts_by_channel {}
total 0
```

No live CAN frames were observed during the passive test window, so decode-on-receive could not be validated with real incoming vehicle traffic. The hardware interfaces do open, attach to the notifier, and shut down cleanly.

Final per-bus RX loop smoke test:

```text
Loaded 2 message(s) from dbc
CAN listener started on can0, can1 at 500000 bps
{'Speed': 55.5, 'APPS': 123.4}
clean stop
```

## CAN1 ACK / Bus-Off Fix

Observed `can1` in `BUS-OFF` after unacknowledged transmit testing:

```text
can1: state BUS-OFF
```

Reset `can1` to normal receive/transmit mode:

```bash
sudo ip link set can1 down
sudo ip link set can1 type can bitrate 500000 restart-ms 100 loopback off listen-only off
sudo ip link set can1 up
```

With a PCAN sending the GUI test frame every 100 ms, `can1` now receives and
decodes correctly:

```text
seen_total 31
('can1', '0xabc123', True, 8, '2b02d20400000000', {'Speed': 55.5, 'APPS': 123.4})
snapshot {'Speed': 55.5, 'APPS': 123.4}
can1: state ERROR-ACTIVE
RX: 3160 bytes, 395 packets, 0 errors
```

Updated `/etc/systemd/system/can-init.service` so boot-time CAN setup is also
explicitly normal mode and auto-recovers from bus-off:

```text
/sbin/ip link set can0 type can bitrate 500000 restart-ms 100 loopback off listen-only off
/sbin/ip link set can1 type can bitrate 500000 restart-ms 100 loopback off listen-only off
```

## Final GUI Test Result

After resetting `can1` and replacing the fragile notifier receive path with
resilient per-interface RX loops, the dashboard updates from the PCAN message:

```text
Extended CAN ID: 0x00ABC123
Payload:         2B02D20400000000
Decoded:         Speed = 55.5, APPS = 123.4
```

The GUI speed value updates correctly now.
