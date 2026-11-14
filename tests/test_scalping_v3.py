import unittest
import pandas as pd

from core.scalping_v3 import FuturesScalpingStrategyV3, SpotScalpingStrategyV3


def frames():
    n=80
    one=pd.DataFrame({
        "open":[100.0]*(n-1)+[100.1],
        "high":[100.3]*(n-1)+[100.55],
        "low":[99.9]*(n-1)+[99.95],
        "close":[100.05]*(n-1)+[100.45],
        "volume":[1000.0]*(n-1)+[1250.0],
        "EMA_9":[100.0]*(n-4)+[100.02,100.04,100.06,100.1],
        "EMA_20":[99.95]*(n-4)+[99.97,99.98,99.99,100.0],
        "ATR":[0.20]*n,
        "RSI":[54.0]*(n-1)+[57.0],
        "MACD_hist":[0.02]*(n-1)+[0.05],
        "BB_lower":[98.0]*n,"BB_upper":[102.0]*n,
    })
    five=pd.DataFrame({
        "open":[100.0]*n,"high":[101.0]*n,"low":[99.5]*n,"close":[100.5]*n,
        "EMA_21":[100.0]*n,"ATR":[0.50]*n,"ADX":[22.0]*n,
    })
    fifteen=pd.DataFrame({
        "close":[101.0]*n,"EMA_21":[100.5]*n,"EMA_50":[100.0]*n,
    })
    hourly=pd.DataFrame({"close":[105.0]*n,"EMA_200":[100.0]*n})
    four=pd.DataFrame({"close":[104.0]*n,"EMA_200":[100.0]*n})
    return {"1m":one,"5m":five,"15m":fifteen,"1h":hourly,"4h":four}


class ScalpingV3Tests(unittest.TestCase):
    def test_futures_v3_uses_micro_pullback_with_higher_timeframe_bias(self):
        result=FuturesScalpingStrategyV3().analyze(frames(),{"total_adverse_rate":0.00015})
        self.assertTrue(result.get("success"),result)
        self.assertEqual(result["strategy_version"],"v3")
        self.assertEqual(result["setup"],"MICRO_PULLBACK")
        self.assertEqual(result["direction"],"LONG")
        self.assertEqual(result["stop_atr_multiple"],0.90)

    def test_spot_v3_keeps_long_only_and_allows_normal_4h_pullbacks(self):
        data=frames()
        result=SpotScalpingStrategyV3().analyze(data,{"total_adverse_rate":0.00015})
        self.assertTrue(result.get("success"),result)
        self.assertEqual(result["direction"],"LONG")
        data["4h"]["close"]=90.0
        data["1h"]["close"]=90.0
        blocked=SpotScalpingStrategyV3().analyze(data,{"total_adverse_rate":0.00015})
        self.assertFalse(blocked.get("success"))
        self.assertIn("Deep 4h",blocked["reason"])


if __name__=="__main__":
    unittest.main()
