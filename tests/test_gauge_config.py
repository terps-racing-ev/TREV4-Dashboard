import unittest

from app.gauge_config import normalize_dashboard_library_config, validate_layout


def minimal_library(**overrides):
    payload = {
        "brightness": 100,
        "active_dashboard_id": "dash-1",
        "dashboards": [
            {
                "id": "dash-1",
                "name": "Dash",
                "display": {},
                "gauges": [],
            }
        ],
    }
    payload.update(overrides)
    return payload


class GaugeConfigLapTimerTests(unittest.TestCase):
    def test_missing_lap_timer_gets_defaults(self) -> None:
        normalized = normalize_dashboard_library_config(minimal_library())

        self.assertEqual(normalized["lap_timer"]["enabled"], True)
        self.assertEqual(normalized["lap_timer"]["latitude_signal"], "Latitude")
        self.assertEqual(normalized["lap_timer"]["pit_limit_latitude"], 42.0681971316922)
        self.assertEqual(normalized["lap_timer"]["bucket_samples"], 10)

    def test_custom_pit_limit_round_trips(self) -> None:
        normalized = normalize_dashboard_library_config(
            minimal_library(lap_timer={"pit_limit_latitude": 42.123456789})
        )

        self.assertEqual(normalized["lap_timer"]["pit_limit_latitude"], 42.123456789)

    def test_synthetic_lap_signals_validate(self) -> None:
        dashboard = {
            "id": "dash-1",
            "name": "Dash",
            "display": {},
            "gauges": [
                {
                    "type": "SimpleGauge",
                    "signal": "Dashboard_Lap_Count",
                    "label": "LAP #",
                    "min_val": 0,
                    "max_val": 50,
                    "box_xywh": [0, 0, 100, 100],
                    "decimal_places": 0,
                },
                {
                    "type": "SimpleGauge",
                    "signal": "Dashboard_Current_Lap_s",
                    "label": "CURR LAP",
                    "min_val": 0,
                    "max_val": 200,
                    "box_xywh": [100, 0, 120, 100],
                    "decimal_places": 0,
                },
            ],
        }

        warnings = validate_layout(
            dashboard,
            signal_names={"Dashboard_Lap_Count", "Dashboard_Current_Lap_s"},
        )

        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
