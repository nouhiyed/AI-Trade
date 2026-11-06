import pandas as pd
import numpy as np


def analyze_market_structure(df, swing_window=3):
    df = df.copy().reset_index(drop=True)

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    n = len(df)

    df["Swing_High"] = False
    df["Swing_Low"] = False
    df["BOS"] = ""
    df["CHoCH"] = ""
    df["Bullish_Sweep"] = False
    df["Bearish_Sweep"] = False
    df["Bullish_FVG"] = False
    df["Bearish_FVG"] = False
    df["FVG_Lower"] = np.nan
    df["FVG_Upper"] = np.nan
    df["Bullish_OB"] = False
    df["Bearish_OB"] = False
    df["OB_Lower"] = np.nan
    df["OB_Upper"] = np.nan

    last_high = None
    last_low = None
    trend = 0

    for i in range(n):

        # Confirmed swing: only use candles available now
        pivot = i - swing_window

        if pivot >= swing_window:
            start = pivot - swing_window
            end = i + 1

            window_high = df["high"].iloc[start:end]
            window_low = df["low"].iloc[start:end]

            if df["high"].iloc[pivot] == window_high.max():
                df.loc[i, "Swing_High"] = True
                confirmed_high = df["high"].iloc[pivot]
            else:
                confirmed_high = None

            if df["low"].iloc[pivot] == window_low.min():
                df.loc[i, "Swing_Low"] = True
                confirmed_low = df["low"].iloc[pivot]
            else:
                confirmed_low = None
        else:
            confirmed_high = None
            confirmed_low = None

        close = df["close"].iloc[i]

        # Break of previously confirmed structure
        if last_high is not None and close > last_high:
            if trend == -1:
                df.loc[i, "CHoCH"] = "BULLISH"
            else:
                df.loc[i, "BOS"] = "BULLISH"

            trend = 1
            last_high = None

        elif last_low is not None and close < last_low:
            if trend == 1:
                df.loc[i, "CHoCH"] = "BEARISH"
            else:
                df.loc[i, "BOS"] = "BEARISH"

            trend = -1
            last_low = None

        # Register newly confirmed levels after break checks
        if confirmed_high is not None:
            last_high = confirmed_high

        if confirmed_low is not None:
            last_low = confirmed_low

        # Liquidity sweeps
        if i >= 20:
            previous = df.iloc[i-20:i]

            if (
                df["low"].iloc[i] < previous["low"].min()
                and close > previous["low"].min()
            ):
                df.loc[i, "Bullish_Sweep"] = True

            if (
                df["high"].iloc[i] > previous["high"].max()
                and close < previous["high"].max()
            ):
                df.loc[i, "Bearish_Sweep"] = True

        # Fair Value Gaps
        if i >= 2:
            if df["low"].iloc[i] > df["high"].iloc[i-2]:
                df.loc[i, "Bullish_FVG"] = True
                df.loc[i, "FVG_Lower"] = df["high"].iloc[i-2]
                df.loc[i, "FVG_Upper"] = df["low"].iloc[i]

            elif df["high"].iloc[i] < df["low"].iloc[i-2]:
                df.loc[i, "Bearish_FVG"] = True
                df.loc[i, "FVG_Lower"] = df["high"].iloc[i]
                df.loc[i, "FVG_Upper"] = df["low"].iloc[i-2]

        # Candidate Order Blocks
        if i >= 2:
            previous = df.iloc[i-1]

            if (
                close > df["high"].iloc[i-1]
                and previous["close"] < previous["open"]
            ):
                df.loc[i, "Bullish_OB"] = True
                df.loc[i, "OB_Lower"] = previous["low"]
                df.loc[i, "OB_Upper"] = previous["high"]

            elif (
                close < df["low"].iloc[i-1]
                and previous["close"] > previous["open"]
            ):
                df.loc[i, "Bearish_OB"] = True
                df.loc[i, "OB_Lower"] = previous["low"]
                df.loc[i, "OB_Upper"] = previous["high"]

    # Trend filter
    average = df["close"].rolling(20).mean()

    df["Market_Trend"] = np.where(
        df["close"] > average,
        "BULLISH",
        "BEARISH"
    )

    return df


if __name__ == "__main__":
    import glob
    import os

    os.makedirs("data/analysis", exist_ok=True)

    for path in glob.glob("data/raw/*.csv"):
        df = pd.read_csv(path)
        result = analyze_market_structure(df)

        name = os.path.basename(path)
        result.to_csv(
            f"data/analysis/SMC_{name}",
            index=False
        )

        print(
            f"{name} | "
            f"BOS: {(result['BOS'] != '').sum()} | "
            f"CHoCH: {(result['CHoCH'] != '').sum()} | "
            f"Sweeps: {result['Bullish_Sweep'].sum() + result['Bearish_Sweep'].sum()} | "
            f"FVG: {(result['Bullish_FVG'] | result['Bearish_FVG']).sum()}"
        )

    print("\nCausal SMC analysis completed.")

