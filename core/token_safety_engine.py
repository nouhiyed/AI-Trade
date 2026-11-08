"""Alpha token safety engine.

The original checks live in a compiled module (token_safety_engine_original.pyc) that is
NOT committed (`*.pyc` is git-ignored). When it is missing or was compiled for another
Python version, we fall back to a *fail-closed* base class: every token is reported as
UNKNOWN, so the Alpha agent never treats a token as safe by accident.
"""
import importlib.machinery
import importlib.util
from pathlib import Path

import requests

_PYC = Path(__file__).with_name("token_safety_engine_original.pyc")


class _FailClosedBase:
    """Minimal base: never passes a token."""

    DEX = "https://api.dexscreener.com/latest/dex"
    ORIGINAL_AVAILABLE = False

    def __init__(self, timeout=10):
        self.timeout = timeout

    def _get_json(self, url):
        response = requests.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _number(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number == number and abs(number) != float("inf") else None

    def check_token(self, chain, address):
        return {
            "status": "UNKNOWN",
            "passed": False,
            "critical": False,
            "reason": "Token safety engine is unavailable (fail-closed)",
        }


def _load_original():
    if not _PYC.exists():
        return None
    try:
        loader = importlib.machinery.SourcelessFileLoader(
            "token_safety_engine_original", str(_PYC)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module.TokenSafetyEngine
    except Exception as error:  # wrong Python version, corrupt file, ...
        print("token_safety_engine_original unavailable:", error)
        return None


_Base = _load_original() or _FailClosedBase


class TokenSafetyEngine(_Base):

    DEX_CHAINS = {
        "1": "ethereum",
        "56": "bsc",
        "8453": "base",
        "42161": "arbitrum",
        "137": "polygon",
        "10": "optimism",
        "43114": "avalanche"
    }

    def _dex_data(self, address, chain_id):
        chain_name = self.DEX_CHAINS.get(str(chain_id))
        if not chain_name:
            return None

        data = self._get_json(
            f"{self.DEX}/tokens/{address}"
        )

        valid = []

        for pair in data.get("pairs") or []:
            if not isinstance(pair, dict):
                continue

            if str(pair.get("chainId", "")).lower() != chain_name:
                continue

            base = (pair.get("baseToken") or {}).get("address", "").lower()
            quote = (pair.get("quoteToken") or {}).get("address", "").lower()

            if address.lower() not in (base, quote):
                continue

            liquidity = self._number(
                (pair.get("liquidity") or {}).get("usd")
            )

            if liquidity is not None:
                valid.append((liquidity, pair))

        if not valid:
            return None

        valid.sort(key=lambda x: x[0], reverse=True)
        return valid[0][1]
