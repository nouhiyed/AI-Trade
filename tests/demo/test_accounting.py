from decimal import Decimal

import pytest

from core.demo.accounting import (
    calculate_fee,
    calculate_fill_price,
    calculate_futures_pnl,
    calculate_initial_margin,
    calculate_unrealized_pnl,
)


D = Decimal


def test_buy_fill_includes_positive_slippage():
    result = calculate_fill_price(
        D("100"),
        side="BUY",
        slippage_rate=D("0.001"),
    )
    assert result == D("100.100")


def test_sell_fill_includes_negative_slippage():
    result = calculate_fill_price(
        D("100"),
        side="SELL",
        slippage_rate=D("0.001"),
    )
    assert result == D("99.900")


def test_fee_uses_actual_execution_notional():
    result = calculate_fee(
        price=D("100"),
        quantity=D("2"),
        fee_rate=D("0.001"),
    )
    assert result == D("0.200")


def test_futures_initial_margin():
    result = calculate_initial_margin(
        price=D("50000"),
        quantity=D("0.01"),
        leverage=D("10"),
    )
    assert result == D("50")


def test_futures_long_realized_pnl():
    result = calculate_futures_pnl(
        entry_price=D("100"),
        exit_price=D("110"),
        quantity=D("2"),
        direction="LONG",
    )
    assert result == D("20")


def test_futures_short_realized_pnl():
    result = calculate_futures_pnl(
        entry_price=D("100"),
        exit_price=D("90"),
        quantity=D("2"),
        direction="SHORT",
    )
    assert result == D("20")


def test_futures_long_unrealized_loss():
    result = calculate_unrealized_pnl(
        entry_price=D("100"),
        mark_price=D("95"),
        quantity=D("2"),
        direction="LONG",
    )
    assert result == D("-10")


def test_futures_short_unrealized_loss():
    result = calculate_unrealized_pnl(
        entry_price=D("100"),
        mark_price=D("105"),
        quantity=D("2"),
        direction="SHORT",
    )
    assert result == D("-10")


@pytest.mark.parametrize(
    "price,quantity,leverage",
    [
        (D("0"), D("1"), D("1")),
        (D("100"), D("0"), D("1")),
        (D("100"), D("1"), D("0")),
        (D("-100"), D("1"), D("2")),
    ],
)
def test_initial_margin_rejects_invalid_values(price, quantity, leverage):
    with pytest.raises((ValueError, ArithmeticError)):
        calculate_initial_margin(price, quantity, leverage)
