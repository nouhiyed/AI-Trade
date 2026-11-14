import unittest
from unittest.mock import patch

from core.market_scanner import FuturesMarketScanner


class TestFuturesMarketScanner(unittest.TestCase):
    def setUp(self):
        self.scanner = FuturesMarketScanner()
        symbols = [
            {
                "symbol": f"COIN{i}USDT",
                "status": "TRADING",
                "contractType": "PERPETUAL",
                "quoteAsset": "USDT",
            }
            for i in range(35)
        ]
        # These contracts are not eligible and must never enter the universe.
        symbols.extend([
            {"symbol": "OLDUSDT", "status": "BREAK", "contractType": "PERPETUAL", "quoteAsset": "USDT"},
            {"symbol": "COINUSDC", "status": "TRADING", "contractType": "PERPETUAL", "quoteAsset": "USDC"},
            {"symbol": "DELIVERYUSDT", "status": "TRADING", "contractType": "CURRENT_QUARTER", "quoteAsset": "USDT"},
        ])
        self.exchange = {"symbols": symbols}
        self.tickers = [
            {
                "symbol": f"COIN{i}USDT",
                "quoteVolume": "1" if i == 34 else str(1000 - i),
                "lastPrice": "1",
                "priceChangePercent": "0",
            }
            for i in range(35)
        ]

    def test_default_scan_includes_all_eligible_pairs_without_volume_floor_or_30_cap(self):
        def request(_market, endpoint, _params):
            return self.exchange if endpoint.endswith("exchangeInfo") else self.tickers

        with patch.object(self.scanner.market, "_request", side_effect=request):
            result = self.scanner.scan_universe()

        self.assertEqual(len(result), 35)
        self.assertEqual({item["symbol"] for item in result},
                         {f"COIN{i}USDT" for i in range(35)})
        self.assertIn("COIN34USDT", {item["symbol"] for item in result})

    def test_explicit_manual_limit_remains_supported(self):
        def request(_market, endpoint, _params):
            return self.exchange if endpoint.endswith("exchangeInfo") else self.tickers

        with patch.object(self.scanner.market, "_request", side_effect=request):
            result = self.scanner.scan_universe(limit=5)

        self.assertEqual(len(result), 5)


if __name__ == "__main__":
    unittest.main()
