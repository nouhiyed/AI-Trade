import os
import time
import hmac
import hashlib
from urllib.parse import urlencode
from decimal import Decimal
import requests


class BinanceExecutionEngine:
    URLS = {
        "DEMO": {
            "spot": "https://testnet.binance.vision",
            "futures": "https://testnet.binancefuture.com",
        },
        "LIVE": {
            "spot": "https://api.binance.com",
            "futures": "https://fapi.binance.com",
        },
    }

    def __init__(self, mode=None, timeout=15):
        self.mode = str(mode or os.getenv("BINANCE_MODE", "DEMO")).upper()
        if self.mode == "LIVE":
            raise RuntimeError("LIVE trading is permanently disabled")
        if self.mode != "DEMO":
            raise ValueError("Unsupported Binance execution mode")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AI-Trader-Execution/1.0"
        })

    def _credentials(self, market):
        prefix = f"BINANCE_{self.mode}_{market.upper()}"
        key = os.getenv(prefix + "_API_KEY")
        secret = os.getenv(prefix + "_API_SECRET")

        if not key or not secret:
            raise RuntimeError(
                f"Missing credentials: {prefix}_API_KEY / API_SECRET"
            )
        return key, secret

    def _signed_request(self, market, method, endpoint, params=None):
        raise RuntimeError("Signed Binance requests are disabled")

    @staticmethod
    def _positive(value, name):
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0:
            raise ValueError(f"{name} must be positive")
        return format(number, "f")

    def place_market_order(
        self,
        market,
        symbol,
        side,
        quantity,
        reduce_only=False,
        quote_order_qty=None,
        client_order_id=None,
        position_side=None,
    ):
        market = str(market).lower()
        symbol = str(symbol).strip().upper()
        side = str(side).strip().upper()

        if market not in ("spot", "futures"):
            raise ValueError("Market must be spot or futures")
        if not symbol or side not in ("BUY", "SELL"):
            raise ValueError("Invalid symbol or side")
        if reduce_only and market != "futures":
            raise ValueError("reduceOnly is futures-only")

        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "newOrderRespType": "FULL",
        }

        if quote_order_qty is not None:
            if market != "spot" or side != "BUY":
                raise ValueError("quoteOrderQty is only supported for Spot BUY")
            params["quoteOrderQty"] = self._positive(
                quote_order_qty, "quote_order_qty"
            )
        else:
            params["quantity"] = self._positive(quantity, "quantity")

        if position_side is not None:
            position_side = str(position_side).upper()
            if market != "futures" or position_side not in ("LONG", "SHORT"):
                raise ValueError("position_side must be LONG or SHORT for Futures")
            if reduce_only:
                raise ValueError(
                    "Hedge-mode orders use positionSide, not reduceOnly"
                )
            params["positionSide"] = position_side

        if reduce_only:
            params["reduceOnly"] = "true"

        if client_order_id:
            params["newClientOrderId"] = str(client_order_id)

        endpoint = (
            "/api/v3/order"
            if market == "spot"
            else "/fapi/v1/order"
        )

        return self._signed_request(
            market, "POST", endpoint, params
        )


    def get_futures_positions(self, symbol=None):
        """Return Binance USD-M Futures position-risk records."""
        params = {}
        if symbol:
            params["symbol"] = str(symbol).strip().upper()
        result = self._signed_request(
            "futures", "GET", "/fapi/v2/positionRisk", params
        )
        if not isinstance(result, list):
            raise RuntimeError("Unexpected Binance positionRisk response")
        return [
            item for item in result
            if abs(Decimal(str(item.get("positionAmt", "0")))) > 0
        ]

    def get_futures_position_mode(self):
        """Return Binance USD-M position mode."""
        return self._signed_request(
            "futures", "GET", "/fapi/v1/positionSide/dual", {}
        )

    def get_open_futures_algo_orders(self, symbol=None):
        """Read open conditional Futures orders."""
        params = {}
        if symbol:
            params["symbol"] = str(symbol).strip().upper()
        return self._signed_request(
            "futures", "GET", "/fapi/v1/openAlgoOrders", params
        )

    def cancel_futures_algo_order(self, symbol, algo_id):
        """Cancel one conditional Futures order."""
        return self._signed_request(
            "futures", "DELETE", "/fapi/v1/algoOrder",
            {
                "symbol": str(symbol).strip().upper(),
                "algoId": int(algo_id),
            },
        )

    def place_futures_protection(
        self,
        symbol,
        direction,
        stop_loss,
        take_profit,
        position_side=None,
        working_type="MARK_PRICE",
    ):
        """
        Place exchange-side STOP_MARKET and TAKE_PROFIT_MARKET.
        Both orders close the position; neither opens a reverse trade.
        """
        symbol = str(symbol).strip().upper()
        direction = str(direction).strip().upper()
        if direction not in ("LONG", "SHORT"):
            raise ValueError("direction must be LONG or SHORT")

        stop_loss = Decimal(self._positive(stop_loss, "stop_loss"))
        take_profit = Decimal(self._positive(take_profit, "take_profit"))

        if direction == "LONG" and not stop_loss < take_profit:
            raise ValueError("LONG requires stop_loss < take_profit")
        if direction == "SHORT" and not take_profit < stop_loss:
            raise ValueError("SHORT requires take_profit < stop_loss")

        working_type = str(working_type).upper()
        if working_type not in ("MARK_PRICE", "CONTRACT_PRICE"):
            raise ValueError("Invalid working_type")

        mode = self.get_futures_position_mode()
        hedge_mode = bool(mode.get("dualSidePosition"))

        if hedge_mode:
            expected_side = direction
            if position_side and str(position_side).upper() != expected_side:
                raise ValueError("position_side conflicts with direction")
            position_side = expected_side
        else:
            position_side = "BOTH"

        exit_side = "SELL" if direction == "LONG" else "BUY"

        def place_conditional(order_type, trigger):
            params = {
                "algoType": "CONDITIONAL",
                "symbol": symbol,
                "side": exit_side,
                "type": order_type,
                "triggerPrice": format(trigger, "f"),
                "workingType": working_type,
                "closePosition": "true",
                "positionSide": position_side,
                "newOrderRespType": "ACK",
            }
            result = self._signed_request(
                "futures", "POST", "/fapi/v1/algoOrder", params
            )
            if not isinstance(result, dict):
                raise RuntimeError("Invalid Binance algo-order response")
            if result.get("algoStatus") not in ("NEW", "ACCEPTED"):
                raise RuntimeError(
                    f"Conditional order was not confirmed: {result}"
                )
            if not result.get("algoId"):
                raise RuntimeError(
                    f"Conditional order has no algoId: {result}"
                )
            return result

        # Place SL first: if TP placement fails, SL remains active.
        stop_order = place_conditional("STOP_MARKET", stop_loss)

        try:
            target_order = place_conditional(
                "TAKE_PROFIT_MARKET", take_profit
            )
        except Exception as error:
            raise RuntimeError(
                "STOP LOSS was accepted but TAKE PROFIT failed. "
                f"Keep the existing stop order active. "
                f"SL algoId={stop_order.get('algoId')}. "
                f"TP error={error}"
            ) from error

        # Verify that both orders are still present at the exchange.
        open_orders = self.get_open_futures_algo_orders(symbol)
        if not isinstance(open_orders, list):
            raise RuntimeError(
                "Could not verify protective orders at Binance"
            )

        ids = {
            str(item.get("algoId"))
            for item in open_orders
            if isinstance(item, dict)
        }
        expected = {
            str(stop_order["algoId"]),
            str(target_order["algoId"]),
        }
        if not expected.issubset(ids):
            raise RuntimeError(
                "Protective orders were submitted but could not both "
                "be verified in open Futures algo orders. "
                f"Expected={sorted(expected)}, found={sorted(ids)}"
            )

        return {
            "success": True,
            "market": "futures",
            "symbol": symbol,
            "direction": direction,
            "positionSide": position_side,
            "workingType": working_type,
            "stop_loss": stop_order,
            "take_profit": target_order,
            "verified": True,
        }

    def place_spot_oco_exit(
        self,
        symbol,
        quantity,
        entry_price,
        stop_loss,
        stop_limit_price,
        take_profit,
    ):
        """
        Place a Spot SELL OCO exit for an existing long position.
        Caller must round quantity/prices using exchange filters first.
        """
        symbol = str(symbol).strip().upper()
        quantity = self._positive(quantity, "quantity")
        entry = Decimal(self._positive(entry_price, "entry_price"))
        stop = Decimal(self._positive(stop_loss, "stop_loss"))
        stop_limit = Decimal(
            self._positive(stop_limit_price, "stop_limit_price")
        )
        target = Decimal(self._positive(take_profit, "take_profit"))

        if not stop_limit < stop < entry < target:
            raise ValueError(
                "Spot SELL OCO requires stop_limit < stop_loss "
                "< entry_price < take_profit"
            )

        result = self._signed_request(
            "spot",
            "POST",
            "/api/v3/orderList/oco",
            {
                "symbol": symbol,
                "side": "SELL",
                "quantity": quantity,
                "listClientOrderId": f"ait_{int(time.time() * 1000)}",
                "aboveType": "LIMIT_MAKER",
                "abovePrice": format(target, "f"),
                "belowType": "STOP_LOSS_LIMIT",
                "belowStopPrice": format(stop, "f"),
                "belowPrice": format(stop_limit, "f"),
                "belowTimeInForce": "GTC",
                "newOrderRespType": "RESULT",
            },
        )

        if not isinstance(result, dict):
            raise RuntimeError("Invalid Binance OCO response")

        orders = result.get("orders") or []
        if (
            not result.get("orderListId")
            or len(orders) != 2
            or result.get("listOrderStatus") not in
               ("EXECUTING", "ALL_DONE")
        ):
            raise RuntimeError(
                f"Spot OCO was not confirmed: {result}"
            )

        return {
            "success": True,
            "market": "spot",
            "symbol": symbol,
            "order_list": result,
            "verified": True,
        }


    def get_futures_symbol_filters(self, symbol):
        """Fetch and normalize Binance Futures trading filters."""
        symbol = str(symbol).strip().upper()
        response = self.session.get(
            self.URLS[self.mode]["futures"] + "/fapi/v1/exchangeInfo",
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()

        item = next(
            (
                x for x in data.get("symbols", [])
                if x.get("symbol") == symbol
                and x.get("status") == "TRADING"
            ),
            None,
        )
        if item is None:
            raise ValueError(f"Futures symbol is not trading: {symbol}")

        filters = {
            x.get("filterType"): x
            for x in item.get("filters", [])
        }
        market_lot = filters.get("MARKET_LOT_SIZE")
        regular_lot = filters.get("LOT_SIZE")

        lot = None
        for candidate in (market_lot, regular_lot):
            if not candidate:
                continue
            try:
                step = Decimal(str(candidate.get("stepSize", "0")))
                minimum = Decimal(str(candidate.get("minQty", "0")))
                maximum = Decimal(str(candidate.get("maxQty", "0")))
                if step > 0 and minimum >= 0 and maximum >= minimum:
                    lot = candidate
                    break
            except Exception:
                continue

        price = filters.get("PRICE_FILTER")
        notional = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL")

        if not lot or not price:
            raise RuntimeError(f"Incomplete Binance filters for {symbol}")

        return {
            "step_size": lot.get("stepSize"),
            "min_qty": lot.get("minQty"),
            "max_qty": lot.get("maxQty"),
            "tick_size": price.get("tickSize"),
            "min_price": price.get("minPrice"),
            "max_price": price.get("maxPrice"),
            "min_notional": (
                notional.get("notional")
                if notional else None
            ),
        }

    @staticmethod
    def round_futures_quantity(quantity, filters):
        from decimal import ROUND_DOWN

        value = Decimal(str(quantity))
        step = Decimal(str(filters["step_size"]))
        minimum = Decimal(str(filters["min_qty"]))
        maximum = Decimal(str(filters["max_qty"]))

        if step <= 0:
            raise ValueError("Invalid quantity step size")

        value = (value / step).to_integral_value(
            rounding=ROUND_DOWN
        ) * step

        if value < minimum or value > maximum:
            raise ValueError("Quantity outside Binance limits")

        return format(value, "f")

    @staticmethod
    def round_futures_price(price, filters):
        from decimal import ROUND_DOWN

        value = Decimal(str(price))
        tick = Decimal(str(filters["tick_size"]))
        minimum = Decimal(str(filters["min_price"]))
        maximum = Decimal(str(filters["max_price"]))

        if tick <= 0:
            raise ValueError("Invalid price tick size")

        value = (value / tick).to_integral_value(
            rounding=ROUND_DOWN
        ) * tick

        if value < minimum or value > maximum:
            raise ValueError("Price outside Binance limits")

        return format(value.normalize(), "f")

    def set_futures_leverage(self, symbol, leverage):
        symbol = str(symbol).strip().upper()
        leverage = int(leverage)

        if not symbol or not 1 <= leverage <= 125:
            raise ValueError("Invalid symbol or leverage")

        return self._signed_request(
            "futures",
            "POST",
            "/fapi/v1/leverage",
            {"symbol": symbol, "leverage": leverage},
        )

    def get_order(self, market, symbol, order_id):
        market = str(market).lower()
        endpoint = (
            "/api/v3/order"
            if market == "spot"
            else "/fapi/v1/order"
        )
        return self._signed_request(
            market,
            "GET",
            endpoint,
            {"symbol": symbol.upper(), "orderId": int(order_id)},
        )

    def cancel_order(self, market, symbol, order_id):
        market = str(market).lower()
        endpoint = (
            "/api/v3/order"
            if market == "spot"
            else "/fapi/v1/order"
        )
        return self._signed_request(
            market,
            "DELETE",
            endpoint,
            {"symbol": symbol.upper(), "orderId": int(order_id)},
        )
