import unittest

from app.lap_timer import LapTimer
from app.shared_data import LatestValuesTable


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class LapTimerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.shared_data = LatestValuesTable()
        self.timer = LapTimer(self.shared_data, clock=self.clock)

    def process(self, latitude: float, count: int = 1) -> None:
        for _ in range(count):
            self.clock.advance(0.2)
            self.timer.process_signals({"Latitude": latitude})

    def test_in_pit_stabilization_does_not_increment(self) -> None:
        self.process(42.1, 10)

        self.assertEqual(self.timer.stable_state, True)
        self.assertEqual(self.shared_data.get_signal("Dashboard_Lap_Count"), 0)

    def test_in_pit_to_out_of_pit_counts_one_lap_and_resets_timer(self) -> None:
        self.process(42.1, 10)
        self.clock.advance(12.0)
        self.process(42.0, 10)

        self.assertEqual(self.shared_data.get_signal("Dashboard_Lap_Count"), 1)
        self.assertAlmostEqual(self.shared_data.get_signal("Dashboard_Current_Lap_s"), 0.0)

    def test_noisy_samples_do_not_transition_until_bucket_reaches_endpoint(self) -> None:
        self.process(42.1, 10)
        for index in range(9):
            latitude = 42.0 if index % 2 == 0 else 42.1
            self.process(latitude)

        self.assertEqual(self.timer.stable_state, True)
        self.assertEqual(self.shared_data.get_signal("Dashboard_Lap_Count"), 0)

    def test_initial_out_of_pit_stabilization_does_not_create_lap(self) -> None:
        self.process(42.0, 10)

        self.assertEqual(self.timer.stable_state, False)
        self.assertEqual(self.shared_data.get_signal("Dashboard_Lap_Count"), 0)


if __name__ == "__main__":
    unittest.main()
