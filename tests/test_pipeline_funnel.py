import tempfile
import unittest
from pathlib import Path

from core.pipeline_funnel import PipelineFunnel


class TestPipelineFunnel(unittest.TestCase):
    def test_cycle_passes_at_95_percent_and_reports_errors_separately(self):
        funnel = PipelineFunnel()
        cycle_id = funnel.start("futures", expected=20)
        for _ in range(19):
            funnel.record("futures", "events_received", cycle_id=cycle_id)
        funnel.record("futures", None, reason="WAIT signal", cycle_id=cycle_id)
        funnel.record("futures", None, error=True, reason="timeout", cycle_id=cycle_id)
        result = funnel.finish("futures", processed=19, expected=20)
        self.assertTrue(result["success"])
        self.assertEqual(result["completion_pct"], 95.0)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["top_rejections"][0],
                         {"reason": "WAIT signal", "count": 1})

    def test_cycle_below_95_percent_is_not_successful(self):
        funnel = PipelineFunnel()
        cycle_id = funnel.start("spot", expected=20)
        for _ in range(18):
            funnel.record("spot", "events_received", cycle_id=cycle_id)
        result = funnel.finish("spot", processed=18, expected=20)
        self.assertFalse(result["success"])
        self.assertEqual(result["completion_pct"], 90.0)

    def test_fatal_error_fails_cycle_even_with_full_coverage(self):
        funnel = PipelineFunnel()
        cycle_id = funnel.start("futures", expected=10)
        result = funnel.finish("futures", processed=10, expected=10, fatal=True)
        self.assertFalse(result["success"])
        self.assertEqual(result["fatal_errors"], 1)

    def test_completed_five_minute_cycles_are_retained_in_history(self):
        funnel = PipelineFunnel()
        first = funnel.start("futures", expected=10)
        result = funnel.finish("futures", processed=10, expected=10)
        self.assertTrue(result["success"])
        funnel._cycles["futures"]["candle_open"] -= 300
        second = funnel.start("futures", expected=10)
        self.assertNotEqual(first, second)
        snapshot = funnel.snapshot("futures")
        self.assertEqual(len(snapshot["history"]), 1)
        self.assertEqual(snapshot["history"][0]["cycle_id"], first)
        self.assertTrue(snapshot["history"][0]["success"])

    def test_funnel_history_survives_backend_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "funnel_history.json"
            funnel = PipelineFunnel(state_file=state_file)
            first = funnel.start("spot", expected=10)
            funnel.finish("spot", processed=10, expected=10)
            funnel._cycles["spot"]["candle_open"] -= 300
            funnel.start("spot", expected=10)

            restored = PipelineFunnel(state_file=state_file)
            snapshot = restored.snapshot("spot")
            self.assertEqual(snapshot["history"][0]["cycle_id"], first)
            self.assertTrue(snapshot["history"][0]["success"])

    def test_repeated_scan_passes_do_not_inflate_cycle_completion(self):
        funnel = PipelineFunnel()
        funnel.start("spot", expected=20)
        first = funnel.finish("spot", processed=18, expected=20)
        self.assertEqual(first["completion_pct"], 90.0)
        funnel.start("spot", expected=20)
        second = funnel.finish("spot", processed=18, expected=20)
        self.assertEqual(second["processed"], 18)
        self.assertEqual(second["completion_pct"], 90.0)
        self.assertFalse(second["success"])

    def test_cycles_are_aggregated_within_the_same_five_minute_candle(self):
        funnel = PipelineFunnel()
        first = funnel.start("futures", expected=20)
        second = funnel.start("futures", expected=20)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
