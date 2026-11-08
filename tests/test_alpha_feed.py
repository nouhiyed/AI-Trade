import unittest

from core.alpha_feed import AlphaFeed


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.headers = {}
        self.response = FakeResponse(payload)
        self.calls = 0

    def get(self, url, timeout):
        self.calls += 1
        return self.response


class AlphaTokenDirectoryTests(unittest.TestCase):
    def test_uses_binance_alpha_id_and_preserves_tokens_without_price(self):
        session = FakeSession({
            "code": "000000",
            "success": True,
            "data": [
                {
                    "alphaId": "ALPHA_175",
                    "name": "gorilla",
                    "symbol": "gorilla",
                    "price": "0.0008",
                    "offline": False,
                },
                {
                    "alphaId": "ALPHA_176",
                    "name": "example token",
                    "symbol": "EXM",
                    "price": None,
                    "offline": False,
                },
            ],
        })
        feed = AlphaFeed(session=session, ttl=0)

        rows = feed.symbols()

        by_symbol = {row["symbol"]: row for row in rows}
        self.assertIn("ALPHA_175USDT", by_symbol)
        self.assertIn("ALPHA_176USDT", by_symbol)
        self.assertEqual(by_symbol["ALPHA_175USDT"]["name"], "gorilla")
        self.assertEqual(by_symbol["ALPHA_176USDT"]["name"], "example token")
        self.assertIsNone(by_symbol["ALPHA_176USDT"]["price"])
        with self.assertRaisesRegex(ValueError, "no valid live price"):
            feed.price("ALPHA_176USDT")

    def test_rejects_binance_error_code(self):
        session = FakeSession({
            "code": "100001",
            "success": False,
            "message": "request rejected",
            "data": [],
        })
        feed = AlphaFeed(session=session, ttl=0)

        with self.assertRaisesRegex(RuntimeError, "request rejected"):
            feed.symbols()


if __name__ == "__main__":
    unittest.main()
