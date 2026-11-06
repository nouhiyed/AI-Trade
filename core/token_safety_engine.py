import importlib.util
import importlib.machinery

_loader = importlib.machinery.SourcelessFileLoader(
    "token_safety_engine_original",
    "core/token_safety_engine_original.pyc"
)
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
_original = importlib.util.module_from_spec(_spec)
_loader.exec_module(_original)

class TokenSafetyEngine(_original.TokenSafetyEngine):

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
