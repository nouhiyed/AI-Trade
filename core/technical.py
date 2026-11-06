import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import (
    EMAIndicator, SMAIndicator, MACD,
    ADXIndicator, CCIIndicator, IchimokuIndicator
)
from ta.volatility import (
    AverageTrueRange, BollingerBands, KeltnerChannel
)
from ta.volume import OnBalanceVolumeIndicator

def analyze(df):
    df = df.copy()

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Trend
    for period in [9, 21, 50, 200]:
        df[f"EMA_{period}"] = EMAIndicator(close, period).ema_indicator()
        df[f"SMA_{period}"] = SMAIndicator(close, period).sma_indicator()

    # Momentum
    df["RSI"] = RSIIndicator(close, 14).rsi()

    macd = MACD(close)
    df["MACD"] = macd.macd()
    df["MACD_signal"] = macd.macd_signal()
    df["MACD_hist"] = macd.macd_diff()

    stoch = StochasticOscillator(high, low, close)
    df["Stoch_K"] = stoch.stoch()
    df["Stoch_D"] = stoch.stoch_signal()

    df["CCI"] = CCIIndicator(high, low, close).cci()
    df["ADX"] = ADXIndicator(high, low, close).adx()

    # Volatility
    df["ATR"] = AverageTrueRange(high, low, close).average_true_range()

    bb = BollingerBands(close)
    df["BB_upper"] = bb.bollinger_hband()
    df["BB_lower"] = bb.bollinger_lband()
    df["BB_width"] = bb.bollinger_wband()

    kc = KeltnerChannel(high, low, close)
    df["KC_upper"] = kc.keltner_channel_hband()
    df["KC_lower"] = kc.keltner_channel_lband()

    # Ichimoku
    ichi = IchimokuIndicator(high, low)
    df["Ichimoku_conversion"] = ichi.ichimoku_conversion_line()
    df["Ichimoku_base"] = ichi.ichimoku_base_line()

    # Volume
    df["OBV"] = OnBalanceVolumeIndicator(close, volume).on_balance_volume()

    typical_price = (high + low + close) / 3
    df["VWAP"] = (
        (typical_price * volume).cumsum() /
        volume.cumsum().replace(0, np.nan)
    )

    # Support and resistance
    df["Support"] = low.rolling(20).min()
    df["Resistance"] = high.rolling(20).max()

    # Price structure
    df["Higher_High"] = high > high.shift(1)
    df["Higher_Low"] = low > low.shift(1)
    df["Lower_High"] = high < high.shift(1)
    df["Lower_Low"] = low < low.shift(1)

    # Candle patterns
    df["Bullish_Engulfing"] = (
        (df["close"] > df["open"]) &
        (df["close"].shift(1) < df["open"].shift(1)) &
        (df["close"] >= df["open"].shift(1)) &
        (df["open"] <= df["close"].shift(1))
    )

    df["Bearish_Engulfing"] = (
        (df["close"] < df["open"]) &
        (df["close"].shift(1) > df["open"].shift(1)) &
        (df["open"] >= df["close"].shift(1)) &
        (df["close"] <= df["open"].shift(1))
    )

    return df


if __name__ == "__main__":
    import glob
    import os

    os.makedirs("data/analysis", exist_ok=True)

    for path in glob.glob("data/raw/*.csv"):
        df = pd.read_csv(path)
        result = analyze(df)

        name = os.path.basename(path)
        output = f"data/analysis/{name}"

        result.to_csv(output, index=False)

        last = result.iloc[-1]

        print(
            f"{name} | RSI: {last['RSI']:.2f} | "
            f"ADX: {last['ADX']:.2f} | "
            f"MACD: {last['MACD']:.5f}"
        )

    print("\nTechnical analysis completed.")

