"""Map an exchange / ticker suffix to its trading currency and symbol.

Answers the user's requirement: NSE/BSE -> INR (Rupee), NASDAQ/NYSE -> USD,
ASX -> AUD, etc. yfinance also reports the currency on `.info`, which we prefer
when available; this table is the offline fallback and the source for symbols.
"""
from __future__ import annotations

# Yahoo Finance ticker suffix -> (currency code, symbol, exchange label)
SUFFIX_MAP: dict[str, tuple[str, str, str]] = {
    ".NS": ("INR", "₹", "NSE"),
    ".BO": ("INR", "₹", "BSE"),
    ".AX": ("AUD", "A$", "ASX"),
    ".L": ("GBP", "£", "LSE"),
    ".TO": ("CAD", "C$", "TSX"),
    ".V": ("CAD", "C$", "TSXV"),
    ".HK": ("HKD", "HK$", "HKEX"),
    ".T": ("JPY", "¥", "TSE"),
    ".SS": ("CNY", "¥", "SSE"),
    ".SZ": ("CNY", "¥", "SZSE"),
    ".DE": ("EUR", "€", "XETRA"),
    ".PA": ("EUR", "€", "Euronext Paris"),
    ".MI": ("EUR", "€", "Borsa Italiana"),
    ".SW": ("CHF", "CHF", "SIX"),
    ".SI": ("SGD", "S$", "SGX"),
    ".NZ": ("NZD", "NZ$", "NZX"),
    ".SA": ("BRL", "R$", "B3"),
    ".JO": ("ZAR", "R", "JSE"),
    ".KS": ("KRW", "₩", "KRX"),
    ".TW": ("TWD", "NT$", "TWSE"),
}

CURRENCY_SYMBOL: dict[str, str] = {
    "USD": "$", "INR": "₹", "AUD": "A$", "GBP": "£", "EUR": "€",
    "CAD": "C$", "HKD": "HK$", "JPY": "¥", "CNY": "¥", "CHF": "CHF",
    "SGD": "S$", "NZD": "NZ$", "BRL": "R$", "ZAR": "R", "KRW": "₩",
    "TWD": "NT$",
}


def normalize_ticker(raw: str) -> str:
    """Accept forms like 'NSE:TCS', 'TCS.NS', 'AAPL' and return a yfinance symbol."""
    t = raw.strip().upper()
    if ":" in t:
        exch, sym = t.split(":", 1)
        exch = exch.strip()
        sym = sym.strip()
        prefix_map = {
            "NSE": ".NS", "BSE": ".BO", "ASX": ".AX", "LSE": ".L", "TSX": ".TO",
            "HKEX": ".HK", "TSE": ".T", "SSE": ".SS", "SZSE": ".SZ",
            "NASDAQ": "", "NYSE": "", "NYSEARCA": "", "AMEX": "",
        }
        suffix = prefix_map.get(exch, "")
        return f"{sym}{suffix}"
    return t


def resolve_currency(ticker: str, info_currency: str | None = None) -> dict:
    """Return {code, symbol, exchange} for a normalized yfinance ticker."""
    for suffix, (code, symbol, exch) in SUFFIX_MAP.items():
        if ticker.endswith(suffix):
            return {"code": code, "symbol": symbol, "exchange": exch}
    # No suffix -> assume a US listing unless yfinance told us otherwise.
    if info_currency and info_currency in CURRENCY_SYMBOL:
        return {"code": info_currency, "symbol": CURRENCY_SYMBOL[info_currency], "exchange": "US"}
    return {"code": "USD", "symbol": "$", "exchange": "NASDAQ/NYSE"}
