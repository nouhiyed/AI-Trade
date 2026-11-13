import unittest
import pandas as pd

from core.trailing_stop import calculate_trailing_stop


class TestTrailingStop(unittest.TestCase):
    def frame(self, start=100.0, step=0.25):
        rows = []
        for i in range(24):
            close = start + i * step
            rows.append({
                "open": close - 0.05,
                "high": close + 0.50,
                "low": close - 0.50,
                "close": close,
            })
        return pd.DataFrame(rows)

    def test_long_stop_tightens_and_never_loops_back(self):
        frame = self.frame()
        first = calculate_trailing_stop(
            frame, "LONG", 90, 100, 105)
        self.assertIsNotNone(first)
        self.assertGreater(first["stop"], 90)
        second = calculate_trailing_stop(
            self.frame(start=103, step=0.25), "LONG",
            first["stop"], first["best_price"], 110)
        self.assertGreaterEqual(second["stop"], first["stop"])
        pulled_back = calculate_trailing_stop(
            self.frame(start=102, step=-0.05), "LONG",
            second["stop"], second["best_price"], 104)
        self.assertGreaterEqual(pulled_back["stop"], second["stop"])

    def test_short_stop_tightens_downward_and_never_loops_back(self):
        frame = self.frame(start=110, step=-0.25)
        first = calculate_trailing_stop(frame, "SHORT", 120, 110, 105)
        self.assertIsNotNone(first)
        self.assertLess(first["stop"], 120)
        second = calculate_trailing_stop(
            self.frame(start=106, step=-0.25), "SHORT",
            first["stop"], first["best_price"], 100)
        self.assertLessEqual(second["stop"], first["stop"])
        rebound = calculate_trailing_stop(
            self.frame(start=104, step=0.05), "SHORT",
            second["stop"], second["best_price"], 108)
        self.assertLessEqual(rebound["stop"], second["stop"])

    def test_rejects_insufficient_or_malformed_candles(self):
        self.assertIsNone(calculate_trailing_stop(
            self.frame().head(8), "LONG", 90, 100, 105))
        self.assertIsNone(calculate_trailing_stop(
            pd.DataFrame({"close": [100] * 30}),
            "LONG", 90, 100, 105))


if __name__ == "__main__":
    unittest.main()
