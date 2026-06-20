#!/usr/bin/env python3

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from .shared_data import LatestValuesTable

DEFAULT_PIT_LIMIT_LATITUDE = 42.0681971316922
DEFAULT_LATITUDE_SIGNAL = "Latitude"
DEFAULT_BUCKET_SAMPLES = 10
DEFAULT_LAP_COUNT_SIGNAL = "Dashboard_Lap_Count"
DEFAULT_CURRENT_LAP_SIGNAL = "Dashboard_Current_Lap_s"

LAP_TIMER_SYNTHETIC_SIGNALS = (
    DEFAULT_LAP_COUNT_SIGNAL,
    DEFAULT_CURRENT_LAP_SIGNAL,
)


@dataclass(frozen=True)
class LapTimerConfig:
    enabled: bool = True
    latitude_signal: str = DEFAULT_LATITUDE_SIGNAL
    pit_limit_latitude: float = DEFAULT_PIT_LIMIT_LATITUDE
    bucket_samples: int = DEFAULT_BUCKET_SAMPLES
    lap_count_signal: str = DEFAULT_LAP_COUNT_SIGNAL
    current_lap_signal: str = DEFAULT_CURRENT_LAP_SIGNAL


def normalize_lap_timer_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    config = raw or {}
    bucket_samples = int(config.get("bucket_samples", DEFAULT_BUCKET_SAMPLES))
    if bucket_samples <= 0:
        raise ValueError("lap_timer.bucket_samples must be greater than 0")

    latitude_signal = str(config.get("latitude_signal", DEFAULT_LATITUDE_SIGNAL)).strip()
    lap_count_signal = str(config.get("lap_count_signal", DEFAULT_LAP_COUNT_SIGNAL)).strip()
    current_lap_signal = str(config.get("current_lap_signal", DEFAULT_CURRENT_LAP_SIGNAL)).strip()
    if not latitude_signal:
        raise ValueError("lap_timer.latitude_signal is required")
    if not lap_count_signal:
        raise ValueError("lap_timer.lap_count_signal is required")
    if not current_lap_signal:
        raise ValueError("lap_timer.current_lap_signal is required")

    return {
        "enabled": bool(config.get("enabled", True)),
        "latitude_signal": latitude_signal,
        "pit_limit_latitude": float(config.get("pit_limit_latitude", DEFAULT_PIT_LIMIT_LATITUDE)),
        "bucket_samples": bucket_samples,
        "lap_count_signal": lap_count_signal,
        "current_lap_signal": current_lap_signal,
    }


def lap_timer_signal_metadata(config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    normalized = normalize_lap_timer_config(config)
    return {
        normalized["lap_count_signal"]: {"name": normalized["lap_count_signal"], "choices": []},
        normalized["current_lap_signal"]: {"name": normalized["current_lap_signal"], "choices": []},
    }


class LapTimer:
    def __init__(
        self,
        shared_data: LatestValuesTable,
        config: dict[str, Any] | None = None,
        *,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.shared_data = shared_data
        self.config = LapTimerConfig(**normalize_lap_timer_config(config))
        self.clock = clock
        self.bucket: int | None = None
        self.stable_state: bool | None = None
        self.lap_count = 0
        self.lap_start = self.clock()
        self.publish()

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def publish(self) -> None:
        if not self.enabled:
            return
        current_lap = max(0.0, self.clock() - self.lap_start)
        self.shared_data.update(
            {
                self.config.lap_count_signal: self.lap_count,
                self.config.current_lap_signal: current_lap,
            }
        )

    def process_signals(self, decoded_signals: dict[str, Any]) -> None:
        if not self.enabled or self.config.latitude_signal not in decoded_signals:
            return

        try:
            latitude = float(decoded_signals[self.config.latitude_signal])
        except (TypeError, ValueError):
            return

        sample_is_in_pit = latitude > self.config.pit_limit_latitude
        if self.bucket is None:
            self.bucket = 0 if sample_is_in_pit else self.config.bucket_samples

        if sample_is_in_pit:
            self.bucket = min(self.config.bucket_samples, self.bucket + 1)
        else:
            self.bucket = max(0, self.bucket - 1)

        next_state: bool | None = None
        if self.bucket == self.config.bucket_samples:
            next_state = True
        elif self.bucket == 0:
            next_state = False

        if next_state is not None and next_state != self.stable_state:
            if self.stable_state is True and next_state is False:
                self.lap_count += 1
                self.lap_start = self.clock()
            self.stable_state = next_state

        self.publish()
