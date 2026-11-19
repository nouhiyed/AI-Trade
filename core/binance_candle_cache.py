"""Local Binance candle cache fed by startup REST warmup and live WebSocket streams."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import websocket

from core.binance_market_data import BinanceMarketData
from core.orderbook import analyze_orderbook


class BinanceCandleCache:
    # 2,400 five-minute bars are required to derive 200 complete hourly bars,
    # which preserves the existing V3 Spot EMA-200 hourly context.
    FIVE_MINUTE_HISTORY = 2400
    ONE_MINUTE_HISTORY = 250
    FOUR_HOUR_HISTORY = 200
    MAX_WORKERS = 6
    STREAMS_PER_SOCKET = 180

    WS_URLS = {
        "spot": "wss://stream.binance.com:9443/stream?streams=",
        "futures": "wss://fstream.binance.com/stream?streams=",
    }

    def __init__(self, market_feed=None, clock=time.time):
        self.market_feed = market_feed or BinanceMarketData()
        self.clock = clock
        self._lock = threading.RLock()
        self._candles = {}
        self._quotes = {}
        self._books = {}
        self._errors = {}
        self._symbols = {"spot": [], "futures": []}
        self._threads = []
        self._stop = threading.Event()
        self._started = False
        self._last_4h_refresh = 0.0

    @staticmethod
    def _key(market, symbol, timeframe):
        return (str(market).lower(), str(symbol).upper(), str(timeframe))

    @staticmethod
    def _aggregate(frame, minutes):
        if frame is None or frame.empty:
            return pd.DataFrame()
        data = frame.copy()
        data["open_time"] = pd.to_datetime(data["open_time"], utc=True)
        data["close_time"] = pd.to_datetime(data["close_time"], utc=True)
        data = data.sort_values("open_time").drop_duplicates("open_time")
        data["_bucket"] = data["open_time"].dt.floor(f"{minutes}min")
        aggregations = {
            "open_time": "first", "open": "first", "high": "max",
            "low": "min", "close": "last", "volume": "sum",
            "close_time": "last",
        }
        for column in ("quote_volume", "trades", "taker_buy_base",
                       "taker_buy_quote"):
            if column in data.columns:
                aggregations[column] = "sum"
        grouped = data.groupby("_bucket", sort=True).agg(aggregations)
        counts = data.groupby("_bucket").size()
        grouped = grouped[counts == minutes // 5].reset_index(drop=True)
        if "is_closed" in data.columns:
            closed = data.groupby("_bucket")["is_closed"].all()
            grouped["is_closed"] = closed.loc[
                pd.to_datetime(grouped["open_time"], utc=True).dt.floor(f"{minutes}min")
            ].to_numpy()
        grouped.attrs.update(frame.attrs)
        grouped.attrs["interval"] = f"{minutes}m" if minutes < 60 else f"{minutes // 60}h"
        grouped.attrs["source"] = "binance_websocket_cache"
        return grouped

    def _fetch_history(self, market, symbol, interval, count, minimum_rows=None):
        batches = []
        remaining = int(count)
        end_time = None
        while remaining > 0:
            size = min(1000, remaining)
            frame = self.market_feed.fetch_candles(
                market, symbol, interval=interval, limit=size,
                closed_only=True, end_time=end_time)
            if frame.empty:
                break
            batches.append(frame)
            first = pd.Timestamp(frame["open_time"].iloc[0])
            end_time = int(first.timestamp() * 1000) - 1
            remaining -= len(frame)
            if len(frame) < size:
                break
        if not batches:
            raise RuntimeError(f"No closed {interval} history for {symbol}")
        result = pd.concat(reversed(batches), ignore_index=True)
        result = result.drop_duplicates("open_time").sort_values("open_time")
        result = result.tail(count).reset_index(drop=True)
        required = (minimum_rows if minimum_rows is not None else
                    min(count, 200))
        if len(result) < required:
            raise RuntimeError(
                f"Insufficient {interval} history for {symbol}: {len(result)} / {required}")
        result.attrs.update({
            "market": market, "symbol": symbol,
            "interval": interval, "source": "binance_rest_warmup",
        })
        return result

    def _warm_symbol(self, market, symbol):
        key1 = self._key(market, symbol, "1m")
        key5 = self._key(market, symbol, "5m")
        key4 = self._key(market, symbol, "4h")
        with self._lock:
            if key1 in self._candles and key5 in self._candles:
                return True
        try:
            five_count = self.FIVE_MINUTE_HISTORY if market == "spot" else 800
            one = self._fetch_history(
                market, symbol, "1m", self.ONE_MINUTE_HISTORY)
            five = self._fetch_history(
                market, symbol, "5m", five_count,
                minimum_rows=five_count if market == "spot" else 200)
            with self._lock:
                self._candles[key1] = one
                self._candles[key5] = five
                self._errors.pop(f"{market}:{symbol}", None)
            if market == "spot":
                try:
                    four = self._fetch_history(
                        market, symbol, "4h", self.FOUR_HOUR_HISTORY,
                        minimum_rows=self.FOUR_HOUR_HISTORY)
                    with self._lock:
                        self._candles[key4] = four
                except Exception as error:
                    self._set_error(f"spot:{symbol}:4h", error)
            return True
        except Exception as error:
            with self._lock:
                self._errors[f"{market}:{symbol}"] = str(error)
            return False

    def warmup(self, symbols_by_market):
        normalized = {}
        for market in ("spot", "futures"):
            symbols = list(dict.fromkeys(
                str(value).strip().upper() for value in symbols_by_market.get(market, [])
                if str(value).strip()))
            normalized[market] = symbols[:30]
        self._symbols = normalized
        jobs = []
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as pool:
            for market, symbols in normalized.items():
                for symbol in symbols:
                    jobs.append(pool.submit(self._warm_symbol, market, symbol))
            return sum(1 for job in as_completed(jobs) if job.result())

    def _store_kline(self, market, symbol, interval, kline):
        if not kline.get("x"):
            return
        row = {
            "open_time": pd.to_datetime(int(kline["t"]), unit="ms", utc=True),
            "open": float(kline["o"]), "high": float(kline["h"]),
            "low": float(kline["l"]), "close": float(kline["c"]),
            "volume": float(kline["v"]),
            "close_time": pd.to_datetime(int(kline["T"]), unit="ms", utc=True),
            "quote_volume": float(kline.get("q", 0)),
            "trades": int(kline.get("n", 0)),
            "taker_buy_base": float(kline.get("V", 0)),
            "taker_buy_quote": float(kline.get("Q", 0)),
            "is_closed": True,
        }
        key = self._key(market, symbol, interval)
        with self._lock:
            current = self._candles.get(key)
            updated = pd.concat([current, pd.DataFrame([row])],
                                ignore_index=True) if current is not None else pd.DataFrame([row])
            updated = updated.drop_duplicates("open_time", keep="last")
            updated = updated.sort_values("open_time").tail(
                self.FIVE_MINUTE_HISTORY if interval == "5m" else self.ONE_MINUTE_HISTORY
            ).reset_index(drop=True)
            updated.attrs.update({"market": market, "symbol": symbol,
                                  "interval": interval,
                                  "source": "binance_websocket_cache"})
            self._candles[key] = updated

    def _on_message(self, market, _ws, message):
        try:
            envelope = json.loads(message)
            data = envelope.get("data", envelope)
            stream = envelope.get("stream", "")
            if "k" in data:
                kline = data["k"]
                self._store_kline(market, str(kline["s"]).upper(),
                                  str(kline["i"]), kline)
            elif "b" in data and "a" in data and "s" in data:
                symbol = str(data["s"]).upper()
                bid, ask = float(data["b"]), float(data["a"])
                if bid > 0 and ask >= bid:
                    with self._lock:
                        self._quotes[(market, symbol)] = {
                            "market": market, "symbol": symbol,
                            "bid": bid, "ask": ask,
                            "mid_price": (bid + ask) / 2,
                            "spread": ask - bid,
                            "spread_percent": ((ask - bid) / ((ask + bid) / 2)) * 100,
                            "source": "binance_websocket",
                            "received_at": self.clock(),
                        }
            elif "lastUpdateId" in data and "bids" in data and "asks" in data:
                symbol = stream.split("@", 1)[0].upper()
                book = {"symbol": symbol, "bids": data["bids"], "asks": data["asks"]}
                analyzed = analyze_orderbook(book)
                analyzed.update({"available": True, "market": market,
                                 "source": "binance_websocket"})
                with self._lock:
                    self._books[(market, symbol)] = analyzed
        except Exception as error:
            with self._lock:
                self._errors[f"{market}:websocket_message"] = str(error)

    def _stream_worker(self, market, symbols):
        streams = []
        for symbol in symbols:
            key = symbol.lower()
            streams.extend((f"{key}@kline_1m", f"{key}@kline_5m",
                            f"{key}@bookTicker", f"{key}@depth20@100ms"))
        for start in range(0, len(streams), self.STREAMS_PER_SOCKET):
            group = streams[start:start + self.STREAMS_PER_SOCKET]
            url = self.WS_URLS[market] + "/".join(group)
            thread = threading.Thread(
                target=self._socket_loop, args=(market, url),
                name=f"binance-{market}-ws-{start // self.STREAMS_PER_SOCKET}",
                daemon=True)
            self._threads.append(thread)
            thread.start()

    def _socket_loop(self, market, url):
        while not self._stop.is_set():
            app = websocket.WebSocketApp(
                url,
                on_message=lambda ws, msg: self._on_message(market, ws, msg),
                on_error=lambda _ws, error: self._set_error(
                    f"{market}:websocket", error),
            )
            try:
                app.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as error:
                self._set_error(f"{market}:websocket", error)
            self._stop.wait(3)

    def _set_error(self, key, error):
        with self._lock:
            self._errors[key] = str(error)

    def _refresh_spot_4h(self):
        while not self._stop.wait(3600):
            for symbol in self._symbols.get("spot", []):
                if self._stop.is_set():
                    return
                try:
                    frame = self._fetch_history(
                        "spot", symbol, "4h", self.FOUR_HOUR_HISTORY)
                    with self._lock:
                        self._candles[self._key("spot", symbol, "4h")] = frame
                except Exception as error:
                    self._set_error(f"spot:{symbol}:4h", error)

    def start(self, symbols_by_market):
        if not self._started:
            self._symbols = {
                market: list(dict.fromkeys(
                    str(value).strip().upper()
                    for value in symbols_by_market.get(market, []) if str(value).strip()
                ))[:30]
                for market in ("spot", "futures")
            }
            self._started = True
            first_start = True
        else:
            first_start = False
        warmed = self.warmup(self._symbols)
        if first_start:
            for market, symbols in self._symbols.items():
                if symbols:
                    self._stream_worker(market, symbols)
            refresh = threading.Thread(target=self._refresh_spot_4h,
                                       name="spot-4h-refresh", daemon=True)
            refresh.start()
            self._threads.append(refresh)
        return {"started": True, "already_started": not first_start,
                "warmed_symbols": warmed,
                "requested_symbols": sum(map(len, self._symbols.values())),
                "errors": self.status()["errors"]}

    def stop(self):
        self._stop.set()

    def get_frame(self, market, symbol, timeframe):
        market, symbol = str(market).lower(), str(symbol).upper()
        with self._lock:
            if timeframe == "15m":
                base = self._candles.get(self._key(market, symbol, "5m"))
                frame = self._aggregate(base, 15) if base is not None else None
            elif timeframe == "1h":
                base = self._candles.get(self._key(market, symbol, "5m"))
                frame = self._aggregate(base, 60) if base is not None else None
            else:
                frame = self._candles.get(self._key(market, symbol, timeframe))
            return frame.copy() if frame is not None else None

    def get_quote(self, market, symbol, max_age_seconds=10):
        with self._lock:
            quote = self._quotes.get((str(market).lower(), str(symbol).upper()))
            if not quote:
                return None
            age = self.clock() - float(quote.get("received_at", 0))
            if age < 0 or age > float(max_age_seconds):
                return None
            return dict(quote)

    def get_orderbook(self, market, symbol):
        with self._lock:
            book = self._books.get((str(market).lower(), str(symbol).upper()))
            return dict(book) if book else {"available": False,
                "reason": "Waiting for Binance depth stream",
                "source": "binance_websocket"}

    def snapshot(self, market, symbol, timeframes):
        candles, errors = {}, {}
        for timeframe in timeframes:
            frame = self.get_frame(market, symbol, timeframe)
            if frame is None or frame.empty:
                errors[timeframe] = "Candle cache is not warmed or stream is not ready"
            else:
                candles[timeframe] = frame
        return {"candles": candles, "orderbook": self.get_orderbook(market, symbol),
                "errors": errors}

    def status(self):
        with self._lock:
            ready = {
                (market, symbol)
                for market, symbol, timeframe in self._candles
                if timeframe == "1m"
            }.intersection({
                (market, symbol)
                for market, symbol, timeframe in self._candles
                if timeframe == "5m"
            })
            ready_by_market = {
                market: sum(1 for item_market, _ in ready if item_market == market)
                for market in ("spot", "futures")
            }
            return {
                "ready_symbols": len(ready),
                "ready_by_market": ready_by_market,
                "errors": dict(self._errors),
                "symbols": {key: list(value) for key, value in self._symbols.items()},
                "stream_threads": len(self._threads),
            }
