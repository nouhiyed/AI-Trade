import json
from pathlib import Path

import pandas as pd

from core.technical import analyze as analyze_technical
from core.market_structure import analyze_market_structure
from core.orderbook import analyze_orderbook
from core.binance_market_data import BinanceMarketData


class MarketDataEngine:
    def __init__(self, raw_dir="data/raw"):
        self.raw_dir = Path(raw_dir)
        self.binance = BinanceMarketData()

        self.timeframes = {
            "futures": ["1m", "5m", "15m", "1h"],
            "spot": ["1m", "5m", "15m", "1h", "4h"],
            "alpha": ["1m", "5m", "15m", "1h"],
        }

        self.structure_columns = [
            "Swing_High", "Swing_Low", "BOS", "CHoCH",
            "Bullish_Sweep", "Bearish_Sweep",
            "Bullish_FVG", "Bearish_FVG",
            "FVG_Lower", "FVG_Upper",
            "Bullish_OB", "Bearish_OB",
            "OB_Lower", "OB_Upper", "Market_Trend"
        ]

    def _prepare_frame(self, df, symbol, market, timeframe):
        required = ["open", "high", "low", "close", "volume"]

        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"Missing columns: {missing}")

        df = df.copy()

        for col in required:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=required).reset_index(drop=True)

        if len(df) < 60:
            raise ValueError(
                f"{symbol} {timeframe}: only {len(df)} valid candles"
            )

        technical = analyze_technical(df)
        structure = analyze_market_structure(df)

        if len(technical) != len(df):
            raise ValueError("Technical analysis length mismatch")

        if len(structure) != len(df):
            raise ValueError("Market structure length mismatch")

        result = technical.copy()

        for col in self.structure_columns:
            if col not in structure.columns:
                raise ValueError(f"Missing structure column: {col}")
            result[col] = structure[col].values

        result.attrs.update(df.attrs)
        result.attrs["symbol"] = symbol
        result.attrs["market"] = market
        result.attrs["timeframe"] = timeframe
        result.attrs["source"] = df.attrs.get("source", "historical")

        return result

    def load_candles(self, symbol, timeframe):
        path = self.raw_dir / f"{symbol}_{timeframe}.csv"

        if not path.exists():
            raise FileNotFoundError(str(path))

        df = pd.read_csv(path)

        if len(df) < 210:
            raise ValueError(
                f"{symbol} {timeframe}: only {len(df)} candles"
            )

        return self._prepare_frame(
            df, symbol, "historical", timeframe
        )

    def load_orderbook(self, symbol):
        path = self.raw_dir / f"{symbol}_orderbook.json"

        if not path.exists():
            return {
                "available": False,
                "reason": "Order book file missing"
            }

        try:
            with open(path, "r") as file:
                book = json.load(file)

            result = analyze_orderbook(book)
            result["available"] = True
            return result

        except Exception as error:
            return {
                "available": False,
                "reason": str(error)
            }

    def build(self, symbol):
        result = {
            "symbol": symbol,
            "timeframes": {},
            "orderbook": self.load_orderbook(symbol),
            "errors": {}
        }

        for domain, frames in self.timeframes.items():
            result["timeframes"][domain] = {}

            for timeframe in frames:
                try:
                    result["timeframes"][domain][timeframe] = (
                        self.load_candles(symbol, timeframe)
                    )
                except Exception as error:
                    result["errors"][f"{domain}_{timeframe}"] = str(error)

        return result

    def build_live(self, symbol, domains=None):
        symbol = str(symbol).strip().upper()

        if not symbol:
            raise ValueError("Symbol cannot be empty")

        requested = set(domains or self.timeframes)
        unknown = requested.difference(self.timeframes)
        if unknown:
            raise ValueError("Unknown live market domain(s): " + ", ".join(sorted(unknown)))

        result = {
            "symbol": symbol,
            "source": "binance_rest",
            "timeframes": {
                "futures": {},
                "spot": {},
                "alpha": {}
            },
            "orderbooks": {
                "futures": {},
                "spot": {}
            },
            "errors": {}
        }

        market_domains = {}
        if "futures" in requested:
            market_domains["futures"] = "futures"
        if requested.intersection({"spot", "alpha"}):
            market_domains["spot"] = "spot"

        for market, domain in market_domains.items():
            if market == "spot":
                requested_frames = set()
                if "spot" in requested:
                    requested_frames.update(self.timeframes["spot"])
                if "alpha" in requested:
                    requested_frames.update(self.timeframes["alpha"])
                frames = [tf for tf in self.timeframes["spot"] if tf in requested_frames]
            else:
                frames = self.timeframes[domain]

            try:
                snapshot = self.binance.fetch_snapshot(
                    market=market,
                    symbol=symbol,
                    timeframes=frames,
                    candle_limit=500,
                    orderbook_limit=100
                )

                for timeframe, error in snapshot.get("errors", {}).items():
                    result["errors"][f"{market}_{timeframe}"] = error

                result["orderbooks"][domain] = snapshot.get(
                    "orderbook", {}
                )

                for timeframe, df in snapshot.get("candles", {}).items():
                    try:
                        prepared = self._prepare_frame(
                            df, symbol, market, timeframe
                        )
                        result["timeframes"][domain][timeframe] = prepared

                    except Exception as error:
                        result["errors"][
                            f"{market}_{timeframe}_processing"
                        ] = str(error)

            except Exception as error:
                result["errors"][f"{market}_snapshot"] = str(error)

        # Alpha currently analyzes Spot market candles.
        if "alpha" in requested:
            result["timeframes"]["alpha"] = {
                timeframe: result["timeframes"]["spot"][timeframe]
                for timeframe in self.timeframes["alpha"]
                if timeframe in result["timeframes"]["spot"]
            }
            result["orderbooks"]["alpha"] = result["orderbooks"]["spot"]

        return result

    def for_agent(self, market_data, domain):
        if domain not in self.timeframes:
            raise ValueError(f"Unknown domain: {domain}")

        orderbooks = market_data.get("orderbooks", {})
        orderbook = orderbooks.get(
            domain,
            market_data.get("orderbook", {})
        )

        agent_data = {
            "symbol": market_data["symbol"],
            "orderbook": orderbook
        }

        domain_frames = market_data.get("timeframes", {}).get(domain, {})

        for timeframe in self.timeframes[domain]:
            if timeframe in domain_frames:
                agent_data[timeframe] = domain_frames[timeframe]

        return agent_data

    def for_live_agent(self, live_data, domain):
        return self.for_agent(live_data, domain)
