import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import scan_rotation


class ScanRotationTests(unittest.TestCase):
    def test_batches_cover_the_full_universe_without_dropping_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "scan_rotation.json"
            universe = [{"symbol": f"COIN{i:02d}USDT"} for i in range(11)]
            seen = []
            batch_sizes = []

            with patch.object(scan_rotation, "_STATE_FILE", state_file):
                for _ in range(3):
                    batch, meta = scan_rotation.next_scan_batch(
                        "futures", universe, batch_size=4
                    )
                    seen.extend(item["symbol"] for item in batch)
                    batch_sizes.append(len(batch))

            self.assertEqual(batch_sizes, [4, 4, 3])
            self.assertEqual(len(seen), 11)
            self.assertEqual(set(seen), {item["symbol"] for item in universe})
            self.assertEqual(len(set(seen)), 11)
            self.assertTrue(meta["cycle_complete"])
            self.assertEqual(meta["universe_total"], 11)

    def test_cursor_persists_between_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "scan_rotation.json"
            universe = [{"symbol": f"COIN{i:02d}USDT"} for i in range(8)]

            with patch.object(scan_rotation, "_STATE_FILE", state_file):
                first, _ = scan_rotation.next_scan_batch(
                    "spot", universe, batch_size=3
                )
                second, _ = scan_rotation.next_scan_batch(
                    "spot", universe, batch_size=3
                )

            self.assertEqual(
                [item["symbol"] for item in first],
                ["COIN00USDT", "COIN01USDT", "COIN02USDT"],
            )
            self.assertEqual(
                [item["symbol"] for item in second],
                ["COIN03USDT", "COIN04USDT", "COIN05USDT"],
            )

    def test_batch_preserves_market_priority_order(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "scan_rotation.json"
            universe = [
                {"symbol": "TOPUSDT", "quote_volume": 100},
                {"symbol": "MIDUSDT", "quote_volume": 50},
                {"symbol": "LOWUSDT", "quote_volume": 10},
            ]
            with patch.object(scan_rotation, "_STATE_FILE", state_file):
                batch, _ = scan_rotation.next_scan_batch(
                    "spot", universe, batch_size=2
                )
            self.assertEqual(
                [item["symbol"] for item in batch],
                ["TOPUSDT", "MIDUSDT"],
            )


if __name__ == "__main__":
    unittest.main()
