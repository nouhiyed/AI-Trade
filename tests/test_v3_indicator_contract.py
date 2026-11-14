import unittest

import numpy as np
import pandas as pd

from core.technical import analyze


class V3IndicatorContractTests(unittest.TestCase):
    def test_v3_required_ema_columns_are_generated(self):
        count = 260
        close = pd.Series(100 + np.linspace(0, 8, count) + np.sin(np.arange(count) / 5))
        frame = pd.DataFrame({
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(count, 1000.0),
        })
        result = analyze(frame)
        for column in ("EMA_9", "EMA_20", "EMA_21", "EMA_50", "EMA_200",
                       "ATR", "RSI", "MACD_hist", "ADX", "BB_lower", "BB_upper"):
            self.assertIn(column, result.columns)
            self.assertTrue(np.isfinite(float(result[column].iloc[-1])), column)


if __name__ == "__main__":
    unittest.main()
