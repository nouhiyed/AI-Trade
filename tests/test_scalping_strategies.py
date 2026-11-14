import unittest
import pandas as pd
from core.scalping_strategies import FuturesScalpingStrategy, SpotScalpingStrategy


def sample_frames():
    n=80
    five=pd.DataFrame({
        "open":[99.8]*(n-1)+[100.0],"high":[100.4]*(n-1)+[100.8],
        "low":[99.5]*(n-1)+[99.7],"close":[100.0]*(n-1)+[100.6],
        "volume":[1000.0]*n,"EMA_9":[100.0]*n,"EMA_21":[100.1]*n,
        "ATR":[0.35]*n,"RSI":[55.0]*n,"MACD_hist":[0.2]*(n-1)+[0.3],
        "BB_lower":[98.0]*n,"BB_upper":[102.0]*n})
    fifteen=pd.DataFrame({"close":[102.0]*n,"EMA_21":[101.0]*n,"EMA_50":[100.0]*n,"ADX":[24.0]*n})
    hourly=pd.DataFrame({"close":[105.0]*n,"EMA_200":[100.0]*n})
    four=pd.DataFrame({"close":[105.0]*n,"EMA_200":[100.0]*n})
    return {"5m":five,"15m":fifteen,"1h":hourly,"4h":four}


class ScalpingStrategyTests(unittest.TestCase):
    def test_futures_long_pullback_plan(self):
        plan=FuturesScalpingStrategy().analyze(sample_frames(),{"total_adverse_rate":0.00015})
        self.assertTrue(plan["success"],plan)
        self.assertEqual((plan["market"],plan["direction"]),("futures","LONG"))
        self.assertLess(plan["stop_loss"],plan["entry"])
        self.assertGreater(plan["take_profit"],plan["entry"])

    def test_spot_long_only_plan(self):
        plan=SpotScalpingStrategy().analyze(sample_frames(),{"total_adverse_rate":0.00015})
        self.assertTrue(plan["success"],plan)
        self.assertEqual((plan["market"],plan["direction"]),("spot","LONG"))

    def test_spot_four_hour_bear_trend_block(self):
        data=sample_frames(); data["4h"]["close"]=90.0
        plan=SpotScalpingStrategy().analyze(data,{"total_adverse_rate":0.00015})
        self.assertFalse(plan["success"])
        self.assertIn("4h trend filter",plan["reason"])

    def test_cost_filter_rejects_unviable_trade(self):
        plan=FuturesScalpingStrategy().analyze(sample_frames(),{"total_adverse_rate":0.01})
        self.assertFalse(plan["success"])
        self.assertIn("costs",plan["reason"])


if __name__=="__main__":
    unittest.main()
