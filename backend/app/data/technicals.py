"""Technical indicators + chart-pattern detection.

Everything here is computed from OHLCV price data (no external TA library, to
keep deps light). The output is designed so the frontend can *draw* what the
Chartist referred to: each indicator series and each detected pattern comes
with the coordinates needed to overlay it on a chart.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    macd = _ema(close, 12) - _ema(close, 26)
    signal = _ema(macd, 9)
    hist = macd - signal
    return macd, signal, hist


def _bollinger(close: pd.Series, window: int = 20, k: float = 2.0):
    mid = _sma(close, window)
    std = close.rolling(window).std()
    return mid, mid + k * std, mid - k * std


def _clean(x: Any) -> Any:
    """Convert numpy/pandas NaN to None so it is JSON serializable."""
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def _series_to_list(s: pd.Series) -> list:
    return [_clean(v) for v in s.tolist()]


def compute_indicators(df: pd.DataFrame) -> dict:
    """df must have columns: Open, High, Low, Close, Volume, and a DatetimeIndex."""
    close = df["Close"]
    sma50 = _sma(close, 50)
    sma200 = _sma(close, 200)
    ema20 = _ema(close, 20)
    rsi = _rsi(close)
    macd, signal, hist = _macd(close)
    bb_mid, bb_up, bb_low = _bollinger(close)

    dates = [d.strftime("%Y-%m-%d") for d in df.index]

    candles = [
        {
            "date": dates[i],
            "open": _clean(df["Open"].iloc[i]),
            "high": _clean(df["High"].iloc[i]),
            "low": _clean(df["Low"].iloc[i]),
            "close": _clean(df["Close"].iloc[i]),
            "volume": _clean(df["Volume"].iloc[i]),
        }
        for i in range(len(df))
    ]

    latest = len(df) - 1
    last_rsi = _clean(rsi.iloc[latest])
    last_macd = _clean(macd.iloc[latest])
    last_signal = _clean(signal.iloc[latest])
    last_close = _clean(close.iloc[latest])
    last_sma50 = _clean(sma50.iloc[latest])
    last_sma200 = _clean(sma200.iloc[latest])

    # Golden/death cross detection over recent window
    cross = None
    if last_sma50 is not None and last_sma200 is not None:
        prev50 = sma50.iloc[latest - 1] if latest > 0 else np.nan
        prev200 = sma200.iloc[latest - 1] if latest > 0 else np.nan
        if not pd.isna(prev50) and not pd.isna(prev200):
            if prev50 <= prev200 and last_sma50 > last_sma200:
                cross = "golden_cross"
            elif prev50 >= prev200 and last_sma50 < last_sma200:
                cross = "death_cross"

    support, resistance = _support_resistance(df)

    signals = _read_signals(last_close, last_sma50, last_sma200, last_rsi,
                            last_macd, last_signal, cross)

    return {
        "candles": candles,
        "dates": dates,
        "series": {
            "sma50": _series_to_list(sma50),
            "sma200": _series_to_list(sma200),
            "ema20": _series_to_list(ema20),
            "rsi": _series_to_list(rsi),
            "macd": _series_to_list(macd),
            "macd_signal": _series_to_list(signal),
            "macd_hist": _series_to_list(hist),
            "bb_mid": _series_to_list(bb_mid),
            "bb_upper": _series_to_list(bb_up),
            "bb_lower": _series_to_list(bb_low),
        },
        "levels": {"support": support, "resistance": resistance},
        "latest": {
            "close": last_close,
            "rsi": last_rsi,
            "macd": last_macd,
            "macd_signal": last_signal,
            "sma50": last_sma50,
            "sma200": last_sma200,
            "cross": cross,
        },
        "signals": signals,
        "patterns": detect_patterns(df),
    }


def _support_resistance(df: pd.DataFrame, lookback: int = 120) -> tuple[float | None, float | None]:
    window = df.tail(lookback)
    if window.empty:
        return None, None
    return _clean(window["Low"].min()), _clean(window["High"].max())


def _read_signals(close, sma50, sma200, rsi, macd, signal, cross) -> list[dict]:
    out: list[dict] = []
    if rsi is not None:
        if rsi >= 70:
            out.append({"name": "RSI", "reading": f"{rsi:.1f}", "signal": "bearish",
                        "note": "Overbought (>70) — pullback risk"})
        elif rsi <= 30:
            out.append({"name": "RSI", "reading": f"{rsi:.1f}", "signal": "bullish",
                        "note": "Oversold (<30) — bounce potential"})
        else:
            out.append({"name": "RSI", "reading": f"{rsi:.1f}", "signal": "neutral",
                        "note": "Neutral zone"})
    if macd is not None and signal is not None:
        out.append({"name": "MACD", "reading": f"{macd:.2f} vs {signal:.2f}",
                    "signal": "bullish" if macd > signal else "bearish",
                    "note": "MACD above signal" if macd > signal else "MACD below signal"})
    if close is not None and sma200 is not None:
        out.append({"name": "Price vs 200DMA", "reading": f"{close:.2f} vs {sma200:.2f}",
                    "signal": "bullish" if close > sma200 else "bearish",
                    "note": "Above long-term trend" if close > sma200 else "Below long-term trend"})
    if cross == "golden_cross":
        out.append({"name": "MA Cross", "reading": "50DMA crossed above 200DMA",
                    "signal": "bullish", "note": "Golden cross"})
    elif cross == "death_cross":
        out.append({"name": "MA Cross", "reading": "50DMA crossed below 200DMA",
                    "signal": "bearish", "note": "Death cross"})
    return out


# ---------------------------------------------------------------------------
# Chart pattern detection. Each pattern returns the points needed to DRAW it.
# ---------------------------------------------------------------------------
def _local_extrema(values: np.ndarray, order: int = 5) -> tuple[list[int], list[int]]:
    highs, lows = [], []
    n = len(values)
    for i in range(order, n - order):
        window = values[i - order:i + order + 1]
        if values[i] == window.max() and np.argmax(window) == order:
            highs.append(i)
        if values[i] == window.min() and np.argmin(window) == order:
            lows.append(i)
    return highs, lows


def detect_patterns(df: pd.DataFrame) -> list[dict]:
    """Return detected patterns with draw coordinates (index+date+price points)."""
    if len(df) < 40:
        return []
    close = df["Close"].to_numpy()
    high = df["High"].to_numpy()
    low = df["Low"].to_numpy()
    dates = [d.strftime("%Y-%m-%d") for d in df.index]
    patterns: list[dict] = []

    peak_idx, trough_idx = _local_extrema(high, order=5)
    trough_idx_low, _ = _local_extrema(-low, order=5)  # troughs on lows

    def pt(i: int, price: float) -> dict:
        return {"index": int(i), "date": dates[i], "price": round(float(price), 2)}

    # --- Trend / channel via linear regression on closes ---
    x = np.arange(len(close))
    slope, intercept = np.polyfit(x, close, 1)
    trend_dir = "uptrend" if slope > 0 else "downtrend"
    patterns.append({
        "type": "trendline",
        "name": f"Primary {trend_dir}",
        "bias": "bullish" if slope > 0 else "bearish",
        "description": f"Linear regression of closing prices shows a {trend_dir} "
                       f"(slope {slope:.3f}/bar over {len(close)} bars).",
        "points": [pt(0, intercept), pt(len(close) - 1, slope * (len(close) - 1) + intercept)],
    })

    # --- Double top ---
    if len(peak_idx) >= 2:
        a, b = peak_idx[-2], peak_idx[-1]
        pa, pb = high[a], high[b]
        if abs(pa - pb) / max(pa, pb) < 0.03 and (b - a) > 5:
            valley = low[a:b].min() if b > a else low[a]
            patterns.append({
                "type": "double_top",
                "name": "Double Top",
                "bias": "bearish",
                "description": "Two peaks at similar highs with a trough between — "
                               "a bearish reversal pattern. Neckline break confirms.",
                "points": [pt(a, pa), pt(b, pb)],
                "neckline": round(float(valley), 2),
            })

    # --- Double bottom ---
    if len(trough_idx_low) >= 2:
        a, b = trough_idx_low[-2], trough_idx_low[-1]
        pa, pb = low[a], low[b]
        if abs(pa - pb) / max(pa, pb) < 0.03 and (b - a) > 5:
            crest = high[a:b].max() if b > a else high[a]
            patterns.append({
                "type": "double_bottom",
                "name": "Double Bottom",
                "bias": "bullish",
                "description": "Two troughs at similar lows — a bullish reversal "
                               "pattern. Break above the intervening peak confirms.",
                "points": [pt(a, pa), pt(b, pb)],
                "neckline": round(float(crest), 2),
            })

    # --- Head & shoulders (three peaks, middle highest) ---
    if len(peak_idx) >= 3:
        l, m, r = peak_idx[-3], peak_idx[-2], peak_idx[-1]
        pl, pm, pr = high[l], high[m], high[r]
        if pm > pl and pm > pr and abs(pl - pr) / max(pl, pr) < 0.05:
            patterns.append({
                "type": "head_and_shoulders",
                "name": "Head & Shoulders",
                "bias": "bearish",
                "description": "Three peaks with a higher middle (head) flanked by two "
                               "shoulders — classic bearish reversal.",
                "points": [pt(l, pl), pt(m, pm), pt(r, pr)],
            })

    # --- Bollinger squeeze (low volatility -> breakout watch) ---
    bb_mid, bb_up, bb_low = _bollinger(df["Close"])
    if bb_up.notna().iloc[-1]:
        width = (bb_up - bb_low) / bb_mid
        recent_width = width.iloc[-1]
        median_width = width.tail(120).median()
        if recent_width < median_width * 0.6:
            patterns.append({
                "type": "bollinger_squeeze",
                "name": "Bollinger Band Squeeze",
                "bias": "neutral",
                "description": "Bands have contracted well below their typical width — "
                               "volatility compression that often precedes a sharp move.",
                "points": [pt(len(close) - 1, close[-1])],
            })

    return patterns
