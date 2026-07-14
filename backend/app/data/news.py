"""News + macro context fetch.

Used by the Deep Researcher and the new Macro/Geopolitical News agent. Returns
articles with title, source, url, publish time and a short snippet so the UI can
render clickable references ("give a hyperlink to refer that"). Falls back to
yfinance's `.news` and finally to synthetic items if no provider is configured.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from ..config import get_settings


async def _gnews_company(symbol: str, name: str | None) -> list[dict]:
    """Company news by NAME via GNews (gnews.io). Works for any market incl.
    India (unlike Finnhub free, which is US-only). Free tier ~100 req/day."""
    s = get_settings()
    if not s.gnews_api_key:
        return []
    # Search by company name when we have it (works for NSE/BSE); else the symbol.
    # Strip corporate suffixes ("Limited", "Inc.", etc.) and DON'T quote — an
    # over-specific exact phrase returns 0 results on GNews.
    query = name or symbol.split(".")[0]
    import re
    query = re.sub(
        r"\b(Limited|Ltd|Inc|Incorporated|Corporation|Corp|Company|Co|PLC|"
        r"Holdings|Group)\b\.?", "", query, flags=re.IGNORECASE).strip(" .,&")
    url = "https://gnews.io/api/v4/search"
    params = {"q": query, "lang": "en", "max": 10,
              "sortby": "publishedAt", "apikey": s.gnews_api_key}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        return [{
            "title": a.get("title", ""),
            "source": (a.get("source") or {}).get("name", "GNews"),
            "url": a.get("url", ""),
            "publishedAt": (a.get("publishedAt", "") or "")[:10],
            "snippet": (a.get("description") or "")[:300],
            "category": "company",
        } for a in data.get("articles", []) if a.get("title")]
    except Exception:
        return []


async def _finnhub_news(symbol: str) -> list[dict]:
    s = get_settings()
    if not s.finnhub_api_key:
        return []
    today = datetime.utcnow().date()
    frm = today - timedelta(days=30)
    url = "https://finnhub.io/api/v1/company-news"
    params = {"symbol": symbol.split(".")[0], "from": frm.isoformat(),
              "to": today.isoformat(), "token": s.finnhub_api_key}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        return [{
            "title": a.get("headline", ""),
            "source": a.get("source", "Finnhub"),
            "url": a.get("url", ""),
            "publishedAt": datetime.utcfromtimestamp(a.get("datetime", 0)).strftime("%Y-%m-%d"),
            "snippet": a.get("summary", "")[:300],
            "category": a.get("category", "company"),
        } for a in data[:15]]
    except Exception:
        return []


async def _finnhub_macro() -> list[dict]:
    """Broad market/world headlines from Finnhub's general news (free tier)."""
    s = get_settings()
    if not s.finnhub_api_key:
        return []
    url = "https://finnhub.io/api/v1/news"
    params = {"category": "general", "token": s.finnhub_api_key}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        return [{
            "title": a.get("headline", ""),
            "source": a.get("source", "Finnhub"),
            "url": a.get("url", ""),
            "publishedAt": datetime.utcfromtimestamp(a.get("datetime", 0)).strftime("%Y-%m-%d"),
            "snippet": (a.get("summary", "") or "")[:300],
            "category": "macro",
        } for a in data[:15] if a.get("headline")]
    except Exception:
        return []


async def _newsapi_macro() -> list[dict]:
    """Broad world/economy headlines for the macro agent."""
    s = get_settings()
    if not s.newsapi_key:
        return []
    url = "https://newsapi.org/v2/top-headlines"
    params = {"category": "business", "language": "en", "pageSize": 15, "apiKey": s.newsapi_key}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        return [{
            "title": a.get("title", ""),
            "source": (a.get("source") or {}).get("name", "NewsAPI"),
            "url": a.get("url", ""),
            "publishedAt": (a.get("publishedAt", "") or "")[:10],
            "snippet": (a.get("description") or "")[:300],
            "category": "macro",
        } for a in data.get("articles", [])]
    except Exception:
        return []


def _yfinance_news(symbol: str) -> list[dict]:
    try:
        import yfinance as yf

        items = yf.Ticker(symbol).news or []
        out = []
        for it in items[:15]:
            content = it.get("content", it)
            title = content.get("title") or it.get("title", "")
            url = ""
            if isinstance(content.get("canonicalUrl"), dict):
                url = content["canonicalUrl"].get("url", "")
            url = url or it.get("link", "")
            provider = ""
            if isinstance(content.get("provider"), dict):
                provider = content["provider"].get("displayName", "")
            out.append({
                "title": title,
                "source": provider or it.get("publisher", "Yahoo Finance"),
                "url": url,
                "publishedAt": (content.get("pubDate", "") or "")[:10],
                "snippet": (content.get("summary", "") or "")[:300],
                "category": "company",
            })
        return [o for o in out if o["title"]]
    except Exception:
        return []


def _synthetic_news(symbol: str, macro: bool) -> list[dict]:
    base = "Global markets" if macro else symbol.split(".")[0]
    today = datetime.utcnow().date()
    kind = "macro" if macro else "company"
    samples = [
        f"{base} in focus as investors weigh rate outlook",
        f"Analysts revisit {base} estimates amid sector rotation",
        f"{base}: supply-chain and demand signals mixed this quarter",
    ]
    return [{
        "title": t,
        "source": "Synthetic Wire (demo)",
        "url": "",
        "publishedAt": (today - timedelta(days=i * 3)).strftime("%Y-%m-%d"),
        "snippet": "Synthetic placeholder article — configure FINNHUB/NEWSAPI keys "
                   "for real headlines with working links.",
        "category": kind,
    } for i, t in enumerate(samples)]


async def get_company_news(symbol: str, name: str | None = None) -> list[dict]:
    # Finnhub first (rich, but US-only on free tier).
    news = await _finnhub_news(symbol)
    # GNews by company name — covers India and every other market.
    if not news:
        news = await _gnews_company(symbol, name)
    if not news:
        news = _yfinance_news(symbol)
    if not news:
        news = _synthetic_news(symbol, macro=False)
    return news


async def get_macro_news() -> list[dict]:
    news = await _newsapi_macro()      # NewsAPI if a key is set
    if not news:
        news = await _finnhub_macro()  # Finnhub general news (free tier)
    if not news:
        news = _synthetic_news("world", macro=True)
    return news
