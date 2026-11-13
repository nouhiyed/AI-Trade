import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import (
    EMAIndicator, SMAIndicator, MACD,
    ADXIndicator, CCIIndicator, IchimokuIndicator
)
from ta.volatility import AverageTrueRange, BollingerBands, KeltnerChannel
from ta.volume import OnBalanceVolumeIndicator


def analyze(df):
    df = df.copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]

    for period in [9, 21, 50, 200]:
        df[f"EMA_{period}"] = EMAIndicator(close, period).ema_indicator()
        df[f"SMA_{period}"] = SMAIndicator(close, period).sma_indicator()

    df["RSI"] = RSIIndicator(close, 14).rsi()
    macd = MACD(close)
    df["MACD"], df["MACD_signal"], df["MACD_hist"] = macd.macd(), macd.macd_signal(), macd.macd_diff()
    stoch = StochasticOscillator(high, low, close)
    df["Stoch_K"], df["Stoch_D"] = stoch.stoch(), stoch.stoch_signal()
    df["CCI"] = CCIIndicator(high, low, close).cci()

    adx_indicator = ADXIndicator(high, low, close)
    df["ADX"] = adx_indicator.adx()
    df["PLUS_DI"] = adx_indicator.adx_pos()
    df["MINUS_DI"] = adx_indicator.adx_neg()

    df["ATR"] = AverageTrueRange(high, low, close).average_true_range()
    bb = BollingerBands(close)
    df["BB_upper"], df["BB_lower"], df["BB_width"] = bb.bollinger_hband(), bb.bollinger_lband(), bb.bollinger_wband()
    kc = KeltnerChannel(high, low, close)
    df["KC_upper"], df["KC_lower"] = kc.keltner_channel_hband(), kc.keltner_channel_lband()

    ichi = IchimokuIndicator(high, low)
    df["Ichimoku_conversion"], df["Ichimoku_base"] = ichi.ichimoku_conversion_line(), ichi.ichimoku_base_line()
    df["OBV"] = OnBalanceVolumeIndicator(close, volume).on_balance_volume()
    typical_price = (high + low + close) / 3
    df["VWAP"] = (typical_price * volume).cumsum() / volume.cumsum().replace(0, np.nan)
    df["Support"], df["Resistance"] = low.rolling(20).min(), high.rolling(20).max()
    df["Higher_High"], df["Higher_Low"] = high > high.shift(1), low > low.shift(1)
    df["Lower_High"], df["Lower_Low"] = high < high.shift(1), low < low.shift(1)

    df["Bullish_Engulfing"] = (
        (df["close"] > df["open"]) & (df["close"].shift(1) < df["open"].shift(1))
        & (df["close"] >= df["open"].shift(1)) & (df["open"] <= df["close"].shift(1))
    )
    df["Bearish_Engulfing"] = (
        (df["close"] < df["open"]) & (df["close"].shift(1) > df["open"].shift(1))
        & (df["open"] >= df["close"].shift(1)) & (df["close"] <= df["open"].shift(1))
    )
    return df


if __name__ == "__main__":
    import glob
    import os
    os.makedirs("data/analysis", exist_ok=True)
    for path in glob.glob("data/raw/*.csv"):
        result = analyze(pd.read_csv(path))
        name = os.path.basename(path)
        result.to_csv(f"data/analysis/{name}", index=False)
        last = result.iloc[-1]
        print(f"{name} | RSI: {last['RSI']:.2f} | ADX: {last['ADX']:.2f} | MACD: {last['MACD']:.5f}")
    print("\nTechnical analysis completed.")
