"""Market data: prices, fundamentals, corporate actions.

Primary source is yfinance (no API key, NSE via .NS etc.). If yfinance is
unavailable or rate-limited, we fall back to a deterministic synthetic series
so the app remains fully functional offline (clearly flagged as synthetic).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

import httpx
import numpy as np
import pandas as pd

from .currency import normalize_ticker, resolve_currency
from .technicals import compute_indicators


def _synthetic_history(ticker: str, days: int = 400,
                       end_price: float | None = None) -> pd.DataFrame:
    """Deterministic pseudo-random walk seeded by the ticker.

    If `end_price` is given (from a real quote), the series is scaled so its
    LAST close equals that real price — so charts terminate at the true price
    even though the historical shape is synthesized.
    """
    seed = abs(hash(ticker)) % (2**32)
    rng = np.random.default_rng(seed)
    start_price = 50 + (seed % 3000)
    dates = pd.date_range(end=datetime.utcnow().date(), periods=days, freq="B")
    returns = rng.normal(0.0004, 0.018, size=days)
    close = start_price * np.exp(np.cumsum(returns))
    if end_price:
        close = close * (float(end_price) / close[-1])  # anchor to real price
    high = close * (1 + np.abs(rng.normal(0, 0.01, days)))
    low = close * (1 - np.abs(rng.normal(0, 0.01, days)))
    open_ = close * (1 + rng.normal(0, 0.006, days))
    volume = rng.integers(5e5, 5e6, days)
    df = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    )
    return df


_YAHOO_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}


def _try_yahoo_chart(ticker: str) -> tuple[pd.DataFrame, dict, str] | None:
    """Fetch REAL OHLCV + quote from Yahoo's raw chart API.

    Unlike the yfinance library (which Yahoo rate-limits/blocks on cloud IPs),
    the raw v8 chart endpoint with a browser User-Agent works from datacenters.
    Covers US, NSE (.NS), BSE (.BO), and every other Yahoo-supported exchange —
    with real historical candles, so charts are real too.
    """
    try:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            "?range=2y&interval=1d&events=div,split"
        )
        with httpx.Client(timeout=12, headers=_YAHOO_UA) as c:
            r = c.get(url)
            r.raise_for_status()
            j = r.json()
        res = (j.get("chart", {}).get("result") or [None])[0]
        if not res:
            return None
        meta = res.get("meta", {})
        ts = res.get("timestamp") or []
        qcols = (res.get("indicators", {}).get("quote") or [{}])[0]
        opens, highs = qcols.get("open") or [], qcols.get("high") or []
        lows, closes = qcols.get("low") or [], qcols.get("close") or []
        vols = qcols.get("volume") or []
        if not ts or not closes:
            return None
        df = pd.DataFrame(
            {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": vols},
            index=pd.to_datetime(pd.Series(ts), unit="s"),
        ).dropna()
        if len(df) < 5:
            return None
        info = {
            "currentPrice": meta.get("regularMarketPrice"),
            "previousClose": meta.get("chartPreviousClose") or meta.get("previousClose"),
            "longName": meta.get("longName") or meta.get("shortName"),
            "currency": meta.get("currency"),
            "exchange": meta.get("exchangeName"),
            "fiftyTwoWeekHigh": meta.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": meta.get("fiftyTwoWeekLow"),
        }
        info["_actions"] = _yahoo_actions(res)  # real dividends/splits
        return df, info, "yahoo"
    except Exception:
        return None


def _classify_action(subject: str) -> str:
    """Map an NSE action 'subject' string to a normalized type."""
    s = subject.lower()
    if "buy back" in s or "buyback" in s:
        return "buyback"
    if "bonus" in s:
        return "bonus"
    if "split" in s or "face value" in s:
        return "split"
    if "demerger" in s or "spin" in s:
        return "demerger"
    if "rights" in s:
        return "rights"
    if "dividend" in s:
        return "dividend"
    if "meeting" in s or "agm" in s:
        return "meeting"
    return "other"


def _nse_actions(ticker: str) -> list[dict]:
    """Real corporate actions (dividends, splits, BONUS, BUYBACK, demergers...)
    from NSE's public corporate-actions API. Only for NSE/BSE tickers.

    NSE's website blocks scrapers, but the /api endpoint answers directly with a
    browser User-Agent. India-only — the richest free source for bonus/buyback.
    """
    t = ticker.upper()
    if not (t.endswith(".NS") or t.endswith(".BO")):
        return []
    symbol = t.rsplit(".", 1)[0]
    url = f"https://www.nseindia.com/api/corporates-corporateActions?index=equities&symbol={symbol}"
    headers = {
        "User-Agent": _YAHOO_UA["User-Agent"],
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        with httpx.Client(timeout=12, headers=headers, follow_redirects=True) as c:
            r = c.get(url)
            r.raise_for_status()
            data = r.json()
        out: list[dict] = []
        for a in data:
            subject = (a.get("subject") or "").strip()
            if not subject:
                continue
            # NSE dates look like "25-May-2026"; keep as-is if reformat fails.
            raw = a.get("exDate") or a.get("recDate") or ""
            try:
                date = datetime.strptime(raw, "%d-%b-%Y").strftime("%Y-%m-%d")
            except Exception:
                date = raw
            out.append({"type": _classify_action(subject), "date": date,
                        "detail": subject, "value": None})
        return out[:12]
    except Exception:
        return []


def _yahoo_actions(chart_result: dict) -> list[dict]:
    """Extract real dividends + splits from the Yahoo chart 'events' block."""
    out: list[dict] = []
    events = chart_result.get("events", {}) or {}
    for d in (events.get("dividends", {}) or {}).values():
        try:
            date = datetime.utcfromtimestamp(d["date"]).strftime("%Y-%m-%d")
            out.append({"type": "dividend", "date": date,
                        "detail": f"Dividend of {d['amount']:.2f} per share",
                        "value": float(d["amount"])})
        except Exception:
            pass
    for sp in (events.get("splits", {}) or {}).values():
        try:
            date = datetime.utcfromtimestamp(sp["date"]).strftime("%Y-%m-%d")
            out.append({"type": "split", "date": date,
                        "detail": f"Stock split {sp.get('splitRatio', '')}",
                        "value": None})
        except Exception:
            pass
    out.sort(key=lambda e: e["date"], reverse=True)
    return out


def _try_finnhub(ticker: str) -> tuple[dict, list, str] | None:
    """Fetch REAL quote + profile + fundamentals + corporate actions from
    Finnhub (free tier, cloud-friendly). Returns (info_dict, actions, source)
    or None. Historical candles are premium, so the caller synthesizes the
    series anchored to the real quote price. US symbols only on the free tier."""
    from ..config import get_settings

    s = get_settings()
    if not s.finnhub_api_key:
        return None
    sym = ticker.split(".")[0].upper()  # Finnhub free tier = US symbols
    base = "https://finnhub.io/api/v1"
    tok = s.finnhub_api_key
    try:
        with httpx.Client(timeout=12) as c:
            q = c.get(f"{base}/quote?symbol={sym}&token={tok}").json()
            if not q.get("c"):
                return None  # no price -> unknown/unsupported symbol
            prof = c.get(f"{base}/stock/profile2?symbol={sym}&token={tok}").json()
            met = c.get(f"{base}/stock/metric?symbol={sym}&metric=all&token={tok}").json()
        m = met.get("metric", {}) if isinstance(met, dict) else {}
        info = {
            "currentPrice": q.get("c"),
            "previousClose": q.get("pc"),
            "longName": prof.get("name"),
            "currency": prof.get("currency"),
            "exchange": prof.get("exchange"),
            # marketCap from Finnhub profile2 is in millions
            "marketCap": (prof.get("marketCapitalization") or 0) * 1e6 or None,
            "trailingPE": m.get("peTTM") or m.get("peBasicExclExtraTTM"),
            "forwardPE": m.get("forwardPE"),
            "priceToBook": m.get("pbQuarterly") or m.get("pbAnnual"),
            "trailingEps": m.get("epsTTM") or m.get("epsBasicExclExtraItemsTTM"),
            "revenueGrowth": (m.get("revenueGrowthTTMYoy") or 0) / 100 or None,
            "debtToEquity": m.get("totalDebt/totalEquityQuarterly"),
            "returnOnEquity": (m.get("roeTTM") or 0) / 100 or None,
            "profitMargins": (m.get("netProfitMarginTTM") or 0) / 100 or None,
            "dividendYield": (m.get("dividendYieldIndicatedAnnual") or 0) / 100 or None,
            "beta": m.get("beta"),
            "fiftyTwoWeekHigh": m.get("52WeekHigh"),
            "fiftyTwoWeekLow": m.get("52WeekLow"),
        }
        return info, [], "finnhub"
    except Exception:
        return None


def _try_yfinance(ticker: str) -> tuple[pd.DataFrame | None, dict, list, str]:
    """Return (history_df, info, corporate_actions, source)."""
    try:
        import yfinance as yf

        tk = yf.Ticker(ticker)
        hist = tk.history(period="2y", auto_adjust=False)
        if hist is None or hist.empty:
            return None, {}, [], "synthetic"
        hist = hist[["Open", "High", "Low", "Close", "Volume"]].dropna()

        info: dict = {}
        try:
            info = tk.info or {}
        except Exception:
            info = {}

        actions = _extract_corporate_actions(tk)
        return hist, info, actions, "yfinance"
    except Exception:
        return None, {}, [], "synthetic"


def _extract_corporate_actions(tk) -> list[dict]:
    """Dividends + splits from yfinance -> normalized corporate-action events."""
    events: list[dict] = []
    try:
        divs = tk.dividends
        for date, amt in divs.tail(12).items():
            events.append({
                "type": "dividend",
                "date": date.strftime("%Y-%m-%d"),
                "detail": f"Dividend of {amt:.2f} per share",
                "value": float(amt),
            })
    except Exception:
        pass
    try:
        splits = tk.splits
        for date, ratio in splits.tail(8).items():
            events.append({
                "type": "split",
                "date": date.strftime("%Y-%m-%d"),
                "detail": f"Stock split {ratio:g}:1",
                "value": float(ratio),
            })
    except Exception:
        pass
    events.sort(key=lambda e: e["date"], reverse=True)
    return events


def _synthetic_corporate_actions(ticker: str) -> list[dict]:
    seed = abs(hash(ticker + "ca")) % 1000
    today = datetime.utcnow().date()
    out = [{
        "type": "dividend",
        "date": (today - timedelta(days=90 + seed % 60)).strftime("%Y-%m-%d"),
        "detail": "Interim dividend declared (synthetic demo data)",
        "value": round(1 + (seed % 10) * 0.5, 2),
    }]
    if seed % 3 == 0:
        out.append({
            "type": "split",
            "date": (today - timedelta(days=200 + seed % 100)).strftime("%Y-%m-%d"),
            "detail": "Stock split 2:1 (synthetic demo data)",
            "value": 2.0,
        })
    if seed % 4 == 0:
        out.append({
            "type": "buyback",
            "date": (today - timedelta(days=150)).strftime("%Y-%m-%d"),
            "detail": "Board approved share buyback (synthetic demo data)",
            "value": None,
        })
    return out


def _num(info: dict, *keys) -> Any:
    for k in keys:
        v = info.get(k)
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            return v
    return None


def _stooq_symbol(ticker: str) -> str | None:
    """Map a yfinance ticker to a Stooq symbol. Stooq is free, keyless, and
    (unlike Yahoo) does not block cloud/datacenter IPs."""
    t = ticker.upper()
    suffix_map = {".NS": ".IN", ".BO": ".IN", ".L": ".UK", ".DE": ".DE",
                  ".TO": ".CA", ".HK": ".HK", ".AX": ".AU", ".T": ".JP"}
    for suf, stooq_suf in suffix_map.items():
        if t.endswith(suf):
            return t[: -len(suf)].lower() + stooq_suf.lower()
    if "." not in t:  # US listing
        return t.lower() + ".us"
    return None


def _try_stooq(ticker: str) -> pd.DataFrame | None:
    """Fetch daily OHLCV from Stooq as a CSV. Returns None on any failure."""
    sym = _stooq_symbol(ticker)
    if not sym:
        return None
    try:
        import io

        url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
        text = r.text.strip()
        # Stooq returns "No data" (not CSV) for unknown symbols.
        if not text or not text.lower().startswith("date"):
            return None
        df = pd.read_csv(io.StringIO(text))
        if df.empty or "Close" not in df.columns:
            return None
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")[["Open", "High", "Low", "Close", "Volume"]].dropna()
        return df if len(df) >= 30 else None
    except Exception:
        return None


def get_stock_bundle(raw_ticker: str) -> dict:
    """Everything the agents and UI need for one ticker."""
    ticker = normalize_ticker(raw_ticker)
    hist = info = None
    actions: list = []
    source = "synthetic"

    # 1. Yahoo raw chart API (browser UA) — REAL OHLCV + quote for US, NSE, BSE,
    #    and all Yahoo exchanges. Works from cloud IPs where the yfinance lib is
    #    blocked. This is the primary source and covers Indian markets.
    yc = _try_yahoo_chart(ticker)
    if yc is not None:
        hist, info, source = yc
        actions = info.get("_actions", [])  # real dividends/splits from Yahoo
        # For Indian tickers, NSE's API has the RICH set (bonus, buyback,
        # demerger, splits) that Yahoo's chart events lack — prefer it.
        nse = _nse_actions(ticker)
        if nse:
            actions = nse

    # 2. yfinance library (adds sector/industry/richer fundamentals + dividends).
    if hist is None:
        yhist, yinfo, yactions, ysrc = _try_yfinance(ticker)
        if yhist is not None:
            hist, info, actions, source = yhist, yinfo, yactions, ysrc

    # 3. Finnhub (US only, real quote/fundamentals; candles are premium so
    #    synthesize history anchored to the real price).
    if hist is None:
        fh = _try_finnhub(ticker)
        if fh is not None:
            info, actions, source = fh
            hist = _synthetic_history(ticker, end_price=info.get("currentPrice"))

    # 4. Stooq CSV (keyless) as a last real option.
    if hist is None:
        stooq_hist = _try_stooq(ticker)
        if stooq_hist is not None:
            hist, info, actions, source = stooq_hist, {}, [], "stooq"

    # 5. Fully synthetic fallback.
    if hist is None:
        hist = _synthetic_history(ticker)
        actions = _synthetic_corporate_actions(ticker)

    info = info or {}

    # Yahoo's raw chart API provides prices/candles but NO fundamentals (P/E,
    # EPS, margins etc. are all missing). Enrich with Finnhub's free metrics
    # endpoint which gives real fundamentals for US stocks.
    if not info.get("trailingPE") and not info.get("marketCap"):
        fh_info = _try_finnhub(ticker)
        if fh_info is not None:
            fh_data = fh_info[0]  # (info_dict, actions, source)
            # Merge Finnhub fundamentals into info without overwriting Yahoo's
            # price/name fields that are already populated.
            for k, v in fh_data.items():
                if k.startswith("_"):
                    continue
                if v is not None and not info.get(k):
                    info[k] = v

    currency = resolve_currency(ticker, info.get("currency"))
    indicators = compute_indicators(hist)

    close = hist["Close"]
    last = float(info.get("currentPrice") or close.iloc[-1])
    # Day change = last vs the prior trading day's close. Derive from the candle
    # series (Yahoo meta's previousClose can be a stale/range-start value).
    prev = float(close.iloc[-2]) if len(close) > 1 else last
    day_change = last - prev
    day_change_pct = (day_change / prev * 100) if prev else 0.0
    # Prefer real 52-week range when the data source provided it.
    hi52 = float(info.get("fiftyTwoWeekHigh") or close.tail(252).max())
    lo52 = float(info.get("fiftyTwoWeekLow") or close.tail(252).min())
    vol = float(close.pct_change().tail(30).std() * math.sqrt(252) * 100)

    fundamentals = {
        "name": _num(info, "longName", "shortName") or ticker,
        "sector": _num(info, "sector"),
        "industry": _num(info, "industry"),
        "marketCap": _num(info, "marketCap"),
        "peRatio": _num(info, "trailingPE"),
        "forwardPE": _num(info, "forwardPE"),
        "pbRatio": _num(info, "priceToBook"),
        "eps": _num(info, "trailingEps"),
        "revenueGrowth": _num(info, "revenueGrowth"),
        "debtToEquity": _num(info, "debtToEquity"),
        "roe": _num(info, "returnOnEquity"),
        "profitMargin": _num(info, "profitMargins"),
        "dividendYield": _num(info, "dividendYield"),
        "beta": _num(info, "beta"),
        "targetMeanPrice": _num(info, "targetMeanPrice"),
        "recommendationKey": _num(info, "recommendationKey"),
    }

    return {
        "ticker": ticker,
        "input": raw_ticker,
        "source": source,
        "currency": currency,
        "price": {
            "last": round(last, 2),
            "dayChange": round(day_change, 2),
            "dayChangePct": round(day_change_pct, 2),
            "week52High": round(hi52, 2),
            "week52Low": round(lo52, 2),
            "annualizedVolatilityPct": round(vol, 1),
        },
        "fundamentals": fundamentals,
        "corporateActions": actions,
        "technicals": indicators,
    }
