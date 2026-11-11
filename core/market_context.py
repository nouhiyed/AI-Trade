"""Supporting context for a technical signal: derivatives, whale flow and news.

Technical analysis decides; this module only *supports* or *vetoes*:
  * funding rate and long/short ratio  -> crowded positioning warnings;
  * large aggressive trades (whales)   -> flow aligned or against the trade;
  * crypto news headlines (RSS)        -> a veto only for severe negative news.
Every source fails soft: missing data never blocks a trade by itself.
"""
import re
import threading
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

FAPI = "https://fapi.binance.com"
FEEDS = (
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
)
NAMES = {
    "BTC": ("bitcoin",), "ETH": ("ethereum", "ether"), "SOL": ("solana",),
    "BNB": ("bnb", "binance coin"), "XRP": ("ripple",), "DOGE": ("dogecoin",),
    "ADA": ("cardano",), "AVAX": ("avalanche",), "LINK": ("chainlink",),
    "TON": ("toncoin",), "TRX": ("tron",), "DOT": ("polkadot",),
}
SEVERE_NEG = ("hack", "hacked", "exploit", "drained", "delist", "delisting",
              "lawsuit", "sues", "halt", "halted", "insolven", "bankrupt",
              "rug pull", "ban", "banned")
NEG = SEVERE_NEG + ("crash", "plunge", "dump", "outflow", "sell-off", "probe")
POS = ("approval", "approved", "etf", "partnership", "listing", "listed",
       "upgrade", "adoption", "inflow", "surge", "rally", "record")
SEVERE_POS = ("etf approval", "etf approved", "lists", "binance will list")

WHALE_USD = 100_000.0


def _f(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def classify_headline(title):
    text = title.lower()
    severe_neg = any(re.search(r"\b" + re.escape(w), text) for w in SEVERE_NEG)
    neg = any(re.search(r"\b" + re.escape(w), text) for w in NEG)
    pos = any(re.search(r"\b" + re.escape(w), text) for w in POS)
    if severe_neg:
        return -2
    if neg and not pos:
        return -1
    if pos and not neg:
        return 1
    return 0


def parse_rss(xml_text):
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        when = None
        raw = item.findtext("pubDate")
        if raw:
            try:
                when = parsedate_to_datetime(raw).timestamp()
            except (TypeError, ValueError):
                when = None
        if title:
            items.append({"title": title, "ts": when})
    return items


class MarketContext:

    def __init__(self, session=None, timeout=6, clock=time.time,
                 news_ttl=43200, urgent_news_ttl=900, news_max_age_h=12, feeds=FEEDS):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "AI-Trader-Context/1.0"})
        self.timeout = timeout
        self.clock = clock
        self.news_ttl = news_ttl
        self.urgent_news_ttl = urgent_news_ttl
        self.news_max_age = news_max_age_h * 3600
        self.feeds = tuple(feeds)
        self._news_cache = None
        self._urgent_news_cache = None
        self._lock = threading.Lock()

    def _json(self, path, params):
        r = self.session.get(FAPI + path, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ---- derivatives -------------------------------------------------------

    def funding_rate(self, symbol):
        data = self._json("/fapi/v1/premiumIndex", {"symbol": symbol})
        return _f(data.get("lastFundingRate"))

    def long_short_ratio(self, symbol):
        rows = self._json("/futures/data/globalLongShortAccountRatio",
                          {"symbol": symbol, "period": "5m", "limit": 1})
        return _f(rows[-1].get("longShortRatio")) if rows else None

    def open_interest_change(self, symbol, hours=4):
        rows = self._json("/futures/data/openInterestHist",
                          {"symbol": symbol, "period": "1h", "limit": hours + 1})
        if not rows or len(rows) < 2:
            return None
        first, last = _f(rows[0].get("sumOpenInterest")), _f(rows[-1].get("sumOpenInterest"))
        if not first or last is None:
            return None
        return round((last - first) / first * 100, 3)

    def whale_flow(self, symbol, threshold=WHALE_USD):
        trades = self._json("/fapi/v1/aggTrades", {"symbol": symbol, "limit": 1000})
        buy = sell = 0.0
        count = 0
        for t in trades:
            price, qty = _f(t.get("p")), _f(t.get("q"))
            if price is None or qty is None:
                continue
            notional = price * qty
            if notional < threshold:
                continue
            count += 1
            if t.get("m"):      # buyer is maker -> the aggressor sold
                sell += notional
            else:
                buy += notional
        return {"buy_usd": round(buy), "sell_usd": round(sell),
                "net_usd": round(buy - sell), "large_trades": count}

    # ---- news --------------------------------------------------------------

    def _all_news(self):
        now = self.clock()
        with self._lock:
            if self._news_cache and now - self._news_cache[0] < self.news_ttl:
                return self._news_cache[1]
        items = []
        for url in self.feeds:
            try:
                r = self.session.get(url, timeout=self.timeout)
                r.raise_for_status()
                items.extend(parse_rss(r.text))
            except Exception:
                continue
        with self._lock:
            self._news_cache = (now, items)
        return items

    def _urgent_news(self):
        """Refresh recent headlines every 15m, independent of the 12h digest."""
        now = self.clock()
        with self._lock:
            if self._urgent_news_cache and now - self._urgent_news_cache[0] < self.urgent_news_ttl:
                return self._urgent_news_cache[1]
        items = []
        for url in self.feeds:
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                items.extend(parse_rss(response.text))
            except Exception:
                continue
        recent = [item for item in items if item.get("ts") is None or now - item["ts"] <= 6 * 3600]
        with self._lock:
            self._urgent_news_cache = (now, recent)
        return recent

    def news(self, symbol):
        base = symbol[:-4] if symbol.endswith("USDT") else symbol
        words = [re.escape(base.lower())] + [re.escape(n) for n in NAMES.get(base, ())]
        pattern = re.compile(r"\b(" + "|".join(words) + r")\b")
        now = self.clock()
        matched = []
        combined = {}
        # Full 12h digest plus a separate 15m urgent-news poll.
        for item in self._all_news() + self._urgent_news():
            if item.get("ts") and now - item["ts"] > self.news_max_age:
                continue
            combined[item["title"].strip().lower()] = item
        for item in combined.values():
            if pattern.search(item["title"].lower()):
                matched.append({"title": item["title"],
                                "sentiment": classify_headline(item["title"]),
                                "published_at": item.get("ts")})
        matched.sort(key=lambda item: item.get("published_at") or 0, reverse=True)
        return {"items": matched[:5], "score": sum(i["sentiment"] for i in matched),
                "digest_interval_hours": 12,
                "urgent_refresh_seconds": self.urgent_news_ttl,
                "sources": list(self.feeds)}

    # ---- decision support --------------------------------------------------

    def assess(self, symbol, direction):
        """Score the context for a LONG/SHORT idea. Never raises."""
        direction = str(direction).upper()
        sign = 1 if direction == "LONG" else -1
        score, flags, details, veto = 0, [], {}, None

        def safe(name, fn):
            try:
                details[name] = fn()
            except Exception as error:
                details[name] = None
                details[name + "_error"] = type(error).__name__

        safe("funding_rate", lambda: self.funding_rate(symbol))
        safe("long_short_ratio", lambda: self.long_short_ratio(symbol))
        safe("oi_change_4h_pct", lambda: self.open_interest_change(symbol))
        safe("whales", lambda: self.whale_flow(symbol))
        safe("news", lambda: self.news(symbol))

        funding = details.get("funding_rate")
        if funding is not None and funding * sign > 0.0008:
            score -= 1
            flags.append("Crowded funding against the trade")
        ratio = details.get("long_short_ratio")
        if ratio is not None:
            if direction == "LONG" and ratio > 2.5:
                score -= 1
                flags.append("Retail crowded long")
            if direction == "SHORT" and ratio < 0.6:
                score -= 1
                flags.append("Retail crowded short")
        whales = details.get("whales")
        if whales and whales["large_trades"] >= 3:
            aligned = whales["net_usd"] * sign
            if aligned > 300_000:
                score += 1
                flags.append("Whale flow supports the trade")
            elif aligned < -300_000:
                score -= 1
                flags.append("Whale flow against the trade")
        news = details.get("news")
        if news and news["items"]:
            aligned = news["score"] * sign
            if aligned <= -2:
                veto = "Severe adverse news: " + news["items"][0]["title"][:120]
            elif aligned < 0:
                score -= 1
                flags.append("News leans against the trade")
            elif aligned > 0:
                score += 1
                flags.append("News supports the trade")
        if veto is None and score <= -3:
            veto = "Context strongly against the trade"
        return {"score": score, "flags": flags, "veto": veto, "details": details}
