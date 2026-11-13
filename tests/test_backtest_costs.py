import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from core.backtest_costs import BacktestCostModel, apply_funding, load_funding_history


class BacktestCostTests(unittest.TestCase):
    def test_costs_increase_with_volatility_and_fall_with_liquidity(self):
        model = BacktestCostModel("spot")
        quiet = model.components({"close": 100, "ATR": 0.1, "quote_volume": 10_000_000})
        volatile = model.components({"close": 100, "ATR": 2.0, "quote_volume": 10_000_000})
        illiquid = model.components({"close": 100, "ATR": 0.1, "quote_volume": 10_000})
        self.assertGreater(volatile["total_adverse_rate"], quiet["total_adverse_rate"])
        self.assertGreater(illiquid["total_adverse_rate"], quiet["total_adverse_rate"])
        self.assertLessEqual(volatile["total_adverse_rate"], 0.0037)

    def test_funding_sign_depends_on_side_and_rate(self):
        long = {"market": "futures", "direction": "LONG", "remaining_quantity": 2}
        short = {"market": "futures", "direction": "SHORT", "remaining_quantity": 2}
        self.assertAlmostEqual(apply_funding(long, 0.001, 100), -0.2)
        self.assertAlmostEqual(apply_funding(short, 0.001, 100), 0.2)
        self.assertAlmostEqual(apply_funding(long, -0.001, 100), 0.2)

    def test_spot_has_no_funding(self):
        spot = {"market": "spot", "direction": "LONG", "remaining_quantity": 2}
        self.assertEqual(apply_funding(spot, 0.01, 100), 0.0)

    def test_rest_451_falls_back_to_official_vision_archive(self):
        csv_bytes = (
            "calc_time,funding_interval_hours,last_funding_rate\n"
            "1730419200000,8,0.00010000\n"
            "1730448000000,8,-0.00020000\n"
        ).encode()
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("BNBUSDT-fundingRate-2024-11.csv", csv_bytes)

        blocked = Mock()
        blocked.raise_for_status.side_effect = requests.HTTPError("451 Client Error")
        vision = Mock()
        vision.status_code = 200
        vision.content = archive_buffer.getvalue()
        vision.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as tmp, patch(
            "core.backtest_costs.requests.get", side_effect=[blocked, vision]
        ):
            events = load_funding_history(
                "BNBUSDT", 1730419200000, 1730505600000, tmp
            )
            self.assertEqual(len(events), 2)
            self.assertAlmostEqual(events[0]["funding_rate"], 0.0001)
            cache = json.loads(next(Path(tmp).glob("*.json")).read_text())
            self.assertEqual(cache["source"], "BINANCE_VISION_MONTHLY_ARCHIVE")
            self.assertTrue(cache["complete"])


if __name__ == "__main__":
    unittest.main()
