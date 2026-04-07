#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from python.shared_data import LatestValuesTable

_MPS_PER_MPH = 0.44704
_MPH_PER_MPS = 1.0 / _MPS_PER_MPH
_SIM_SIGNALS = [
    "Speed",
    "APPS",
    "BrakePressure",
    "MotorRPM",
    "PackCurrent",
    "PackVoltage",
    "StateOfCharge",
    "CellVoltageMin",
    "CellVoltageMax",
    "LVBatteryVoltage",
    "MotorTemp",
    "InverterTemp",
    "PackTemp",
    "TTempFL",
    "TTempFR",
    "TTempBL",
    "TTempBR",
    "IMDFault",
    "AMSFault",
    "BSPDFault",
    "APPSFault",
    "BrakeFault",
]


@dataclass
class DebugSimulator:
    shared_data: LatestValuesTable
    enabled: bool = False
    throttle_pressed: bool = False
    brake_pressed: bool = False
    speed_mps: float = 0.0
    throttle_pct: float = 0.0
    brake_pct: float = 0.0
    pack_soc: float = 82.0
    motor_temp: float = 32.0
    inverter_temp: float = 30.0
    pack_temp: float = 27.0
    tire_temps: Dict[str, float] = field(default_factory=lambda: {
        "TTempFL": 28.0,
        "TTempFR": 28.0,
        "TTempBL": 29.0,
        "TTempBR": 29.0,
    })
    lv_battery_voltage: float = 13.4

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self.throttle_pressed = False
            self.brake_pressed = False
            self.throttle_pct = 0.0
            self.brake_pct = 0.0
            self.shared_data.invalidate(_SIM_SIGNALS)

    def set_throttle(self, pressed: bool) -> None:
        if self.enabled:
            self.throttle_pressed = pressed

    def set_brake(self, pressed: bool) -> None:
        if self.enabled:
            self.brake_pressed = pressed

    def update(self, dt: float) -> None:
        if not self.enabled:
            return

        dt = max(0.0, min(dt, 0.1))

        throttle_target = 100.0 if self.throttle_pressed and not self.brake_pressed else 0.0
        brake_target = 100.0 if self.brake_pressed else 0.0

        self.throttle_pct = self._approach(self.throttle_pct, throttle_target, 180.0 * dt)
        self.brake_pct = self._approach(self.brake_pct, brake_target, 260.0 * dt)

        speed_mph = self.speed_mps * _MPH_PER_MPS
        accel_gain = max(0.0, 1.0 - speed_mph / 120.0)
        traction_accel = 5.2 * (self.throttle_pct / 100.0) * accel_gain
        brake_decel = 8.5 * (self.brake_pct / 100.0)
        aero_drag = 0.00075 * self.speed_mps * self.speed_mps
        rolling_drag = 0.16 if self.speed_mps > 0.05 else 0.0
        net_accel = traction_accel - brake_decel - aero_drag - rolling_drag

        if self.speed_mps <= 0.02 and net_accel < 0.0 and self.throttle_pct == 0.0:
            net_accel = 0.0

        self.speed_mps = max(0.0, self.speed_mps + net_accel * dt)
        speed_mph = self.speed_mps * _MPH_PER_MPS

        motor_rpm = min(6000.0, speed_mph * 58.0)
        pack_current = max(0.0, self.throttle_pct * 2.35 + max(net_accel, 0.0) * 22.0)
        if self.brake_pct > 0.0 and self.speed_mps > 1.0:
            pack_current *= max(0.15, 1.0 - 0.35 * (self.brake_pct / 100.0))

        pack_voltage = 402.0 - 0.35 * (100.0 - self.pack_soc) - 0.045 * pack_current
        pack_voltage = max(300.0, min(405.0, pack_voltage))
        cell_nominal = pack_voltage / 120.0
        cell_spread = 0.012 + 0.018 * (pack_current / 300.0)

        self.pack_soc = max(0.0, self.pack_soc - pack_current * dt / 18000.0)
        self.motor_temp = self._approach(
            self.motor_temp,
            31.0 + 0.010 * motor_rpm + 0.035 * pack_current,
            (2.6 + 0.02 * self.speed_mps) * dt,
        )
        self.inverter_temp = self._approach(
            self.inverter_temp,
            29.0 + 0.026 * pack_current + 0.0018 * motor_rpm,
            (2.2 + 0.015 * self.speed_mps) * dt,
        )
        self.pack_temp = self._approach(
            self.pack_temp,
            26.0 + 0.018 * pack_current,
            0.38 * dt,
        )
        self.lv_battery_voltage = self._approach(
            self.lv_battery_voltage,
            13.5 - 0.0045 * (pack_current / 10.0),
            0.3 * dt,
        )

        front_tire_target = 28.0 + 0.22 * speed_mph + 0.055 * self.brake_pct
        rear_tire_target = 29.0 + 0.24 * speed_mph + 0.02 * self.throttle_pct
        self.tire_temps["TTempFL"] = self._approach(self.tire_temps["TTempFL"], front_tire_target, 0.9 * dt)
        self.tire_temps["TTempFR"] = self._approach(self.tire_temps["TTempFR"], front_tire_target + 0.4, 0.9 * dt)
        self.tire_temps["TTempBL"] = self._approach(self.tire_temps["TTempBL"], rear_tire_target, 0.8 * dt)
        self.tire_temps["TTempBR"] = self._approach(self.tire_temps["TTempBR"], rear_tire_target + 0.4, 0.8 * dt)

        self.shared_data.update({
            "Speed": speed_mph,
            "APPS": self.throttle_pct,
            "BrakePressure": self.brake_pct,
            "MotorRPM": motor_rpm,
            "PackCurrent": pack_current,
            "PackVoltage": pack_voltage,
            "StateOfCharge": self.pack_soc,
            "CellVoltageMin": max(2.5, cell_nominal - cell_spread),
            "CellVoltageMax": min(4.25, cell_nominal + cell_spread),
            "LVBatteryVoltage": self.lv_battery_voltage,
            "MotorTemp": self.motor_temp,
            "InverterTemp": self.inverter_temp,
            "PackTemp": self.pack_temp,
            "IMDFault": 0,
            "AMSFault": 0,
            "BSPDFault": 0,
            "APPSFault": 0,
            "BrakeFault": 0,
            **self.tire_temps,
        })

    @staticmethod
    def _approach(current: float, target: float, delta: float) -> float:
        if current < target:
            return min(target, current + delta)
        return max(target, current - delta)
