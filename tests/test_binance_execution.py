import unittest
from unittest.mock import Mock

from core.binance_execution import BinanceExecutionEngine


class TestBinanceExecution(unittest.TestCase):

    def setUp(self):
        self.engine = BinanceExecutionEngine(mode="DEMO")

    def sample_filters(self):
        return {
            "step_size": "0.001",
            "min_qty": "0.001",
            "max_qty": "1000",
            "tick_size": "0.10",
            "min_price": "0.10",
            "max_price": "1000000",
            "min_notional": "5",
        }

    def mock_exchange_info(self, symbol_filters, status='TRADING'):
        response = Mock()
        response.json.return_value = {
            "symbols": [{
                "symbol": "BTCUSDT",
                "status": status,
                "filters": symbol_filters,
            }]
        }
        self.engine.session.get = Mock(return_value=response)

    def test_quantity_rounding(self):
        result = self.engine.round_futures_quantity(
            0.12389, self.sample_filters()
        )
        self.assertEqual(result, "0.123")

    def test_price_rounding(self):
        result = self.engine.round_futures_price(
            65432.198, self.sample_filters()
        )
        self.assertEqual(result, "65432.1")

    def test_quantity_below_minimum_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.round_futures_quantity(
                0.0009, self.sample_filters()
            )

    def test_quantity_above_maximum_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.round_futures_quantity(
                1001, self.sample_filters()
            )

    def test_price_outside_limits_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.round_futures_price(
                0.01, self.sample_filters()
            )

    def test_market_lot_size_preferred_when_valid(self):
        self.mock_exchange_info([
            {
                "filterType": "MARKET_LOT_SIZE",
                "stepSize": "0.01",
                "minQty": "0.01",
                "maxQty": "500",
            },
            {
                "filterType": "LOT_SIZE",
                "stepSize": "0.001",
                "minQty": "0.001",
                "maxQty": "1000",
            },
            {
                "filterType": "PRICE_FILTER",
                "tickSize": "0.10",
                "minPrice": "0.10",
                "maxPrice": "1000000",
            },
            {
                "filterType": "MIN_NOTIONAL",
                "notional": "5",
            },
        ])

        result = self.engine.get_futures_symbol_filters("BTCUSDT")
        self.assertEqual(result["step_size"], "0.01")

    def test_invalid_market_lot_falls_back_to_lot_size(self):
        self.mock_exchange_info([
            {
                "filterType": "MARKET_LOT_SIZE",
                "stepSize": "0",
                "minQty": "0",
                "maxQty": "0",
            },
            {
                "filterType": "LOT_SIZE",
                "stepSize": "0.001",
                "minQty": "0.001",
                "maxQty": "1000",
            },
            {
                "filterType": "PRICE_FILTER",
                "tickSize": "0.10",
                "minPrice": "0.10",
                "maxPrice": "1000000",
            },
        ])

        result = self.engine.get_futures_symbol_filters("BTCUSDT")
        self.assertEqual(result["step_size"], "0.001")
        self.assertEqual(result["min_qty"], "0.001")

    def test_non_trading_symbol_rejected(self):
        self.mock_exchange_info([], status="BREAK")
        with self.assertRaises(ValueError):
            self.engine.get_futures_symbol_filters("BTCUSDT")


if __name__ == "__main__":
    unittest.main()
