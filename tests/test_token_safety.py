import unittest

from core.token_safety_engine import TokenSafetyEngine


class TokenSafetyFallbackTests(unittest.TestCase):
    def test_imports_on_a_clean_checkout_and_fails_closed(self):
        engine = TokenSafetyEngine()
        result = engine.check_token("56", "0x0000000000000000000000000000000000000001")
        # Without the compiled original this must never report a token as safe.
        if not getattr(engine, "ORIGINAL_AVAILABLE", True):
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertFalse(result["passed"])

    def test_dex_chain_map_is_kept(self):
        self.assertEqual(TokenSafetyEngine.DEX_CHAINS["56"], "bsc")


if __name__ == "__main__":
    unittest.main()
