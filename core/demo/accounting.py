from decimal import Decimal, InvalidOperation


def _decimal(value, name):
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{name} must be a valid decimal")

    if not result.is_finite():
        raise ValueError(f"{name} must be finite")

    return result


def _positive(value, name):
    result = _decimal(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return result


def _non_negative(value, name):
    result = _decimal(value, name)
    if result < 0:
        raise ValueError(f"{name} cannot be negative")
    return result


def calculate_fill_price(price, side, slippage_rate):
    price = _positive(price, "price")
    slippage = _non_negative(slippage_rate, "slippage_rate")
    side = str(side).upper()

    if slippage >= 1:
        raise ValueError("slippage_rate must be less than 1")

    if side == "BUY":
        return price * (Decimal("1") + slippage)

    if side == "SELL":
        return price * (Decimal("1") - slippage)

    raise ValueError("side must be BUY or SELL")


def calculate_fee(price, quantity, fee_rate):
    price = _positive(price, "price")
    quantity = _positive(quantity, "quantity")
    fee_rate = _non_negative(fee_rate, "fee_rate")

    return price * quantity * fee_rate


def calculate_initial_margin(price, quantity, leverage):
    price = _positive(price, "price")
    quantity = _positive(quantity, "quantity")
    leverage = _positive(leverage, "leverage")

    return (price * quantity) / leverage


def calculate_futures_pnl(entry_price, exit_price, quantity, direction):
    entry = _positive(entry_price, "entry_price")
    exit_ = _positive(exit_price, "exit_price")
    quantity = _positive(quantity, "quantity")
    direction = str(direction).upper()

    if direction == "LONG":
        return (exit_ - entry) * quantity

    if direction == "SHORT":
        return (entry - exit_) * quantity

    raise ValueError("direction must be LONG or SHORT")


def calculate_unrealized_pnl(entry_price, mark_price, quantity, direction):
    return calculate_futures_pnl(
        entry_price=entry_price,
        exit_price=mark_price,
        quantity=quantity,
        direction=direction,
    )
