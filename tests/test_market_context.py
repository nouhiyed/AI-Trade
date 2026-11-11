import unittest

from core.market_context import MarketContext


class FakeResponse:
    text = """<rss><channel><item><title>Bitcoin ETF approval headline</title></item></channel></rss>"""
    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return FakeResponse()


class TestMarketContextNewsRefresh(unittest.TestCase):
    def test_digest_is_12h_and_urgent_feed_refreshes_every_15m(self):
        now = [100000.0]
        session = FakeSession()
        context = MarketContext(
            session=session, clock=lambda: now[0],
            news_ttl=12 * 3600, urgent_news_ttl=15 * 60,
            news_max_age_h=12, feeds=("https://feed.test/rss",),
        )

        first = context.news("BTCUSDT")
        self.assertEqual(first["digest_interval_hours"], 12)
        self.assertEqual(first["urgent_refresh_seconds"], 900)
        self.assertEqual(first["items"][0]["sentiment"], 1)
        self.assertEqual(session.calls, 2)  # full digest + urgent poll

        now[0] += 901
        context.news("BTCUSDT")
        self.assertEqual(session.calls, 3)  # urgent only

        now[0] += 12 * 3600
        context.news("BTCUSDT")
        self.assertEqual(session.calls, 5)  # both caches refreshed


if __name__ == "__main__":
    unittest.main()
