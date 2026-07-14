# Architecture & Data Sources

This document explains **every component**, **where each piece of data comes
from**, **what each module does**, and **how it does it**. For setup/run/deploy
steps see [README.md](./README.md); for AWS deployment specifics see
[DEPLOY.md](./DEPLOY.md).

---

## 1. High-level architecture

```
                    ┌───────────────────────────────────────────────┐
   Browser          │              FRONTEND (React + Vite)           │
   (user)  ───────▶ │  CloudFront-hosted static SPA (or localhost:5173) │
                    │                                                │
                    │  ControlPanel → useDebate() ──SSE/POST──┐      │
                    └─────────────────────────────────────────┼──────┘
                                                               │ HTTPS
                                                               ▼
                    ┌───────────────────────────────────────────────┐
                    │            BACKEND (FastAPI, Python)           │
                    │            AWS App Runner container            │
                    │                                                │
                    │  main.py  ── endpoints ──▶ orchestrator.py     │
                    │                              │                 │
                    │        ┌─────────────────────┼──────────────┐  │
                    │        ▼                     ▼              ▼  │
                    │   llm/provider.py       data/market.py  data/news.py
                    └────────┼─────────────────────┼──────────────┼──┘
                             ▼                     ▼              ▼
                     ┌──────────────┐   ┌────────────────┐  ┌──────────────┐
                     │ AWS Bedrock  │   │ Yahoo (chart)  │  │ Finnhub      │
                     │ Claude Opus  │   │ NSE (corp act) │  │ GNews        │
                     │ →Sonnet f/b  │   │ Finnhub/Stooq  │  │ (news)       │
                     └──────────────┘   └────────────────┘  └──────────────┘
```

**Request lifecycle:**
1. User enters a ticker, picks agents + investor profile, clicks **Run Debate**.
2. Frontend opens an **SSE** stream (`GET /api/debate/stream`) — or a single
   `POST /api/debate` if `VITE_TRANSPORT=post`.
3. Backend `orchestrator.py` fetches market data + news, then runs the 3-phase
   debate, calling Bedrock once per agent per phase.
4. Each event (stock data, agent tokens, verdicts, consensus) streams back and
   the UI renders it live.

---

## 2. Backend components (`backend/app/`)

### `main.py` — HTTP surface
FastAPI app. Endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Liveness + which LLM/model is active |
| `/api/agents` | GET | List of the 8 selectable agent personas |
| `/api/stock/{ticker}` | GET | One-shot stock bundle + news (no debate) |
| `/api/debate/stream` | GET | **SSE** — streams the whole debate live |
| `/api/debate` | POST | Non-streaming — runs debate, returns all events at once |
| `/ws/debate` | WS | WebSocket variant (local dev only) |

- **SSE** sends a `: keepalive` comment every 10s so long model "thinking" gaps
  don't drop the connection.
- CORS allows `localhost` and `*.cloudfront.net` (configurable via CORS_ORIGINS / CORS_ORIGIN_REGEX).
- `auth.py` optionally gates every request behind an OIDC JWT (`REQUIRE_AUTH`).

### `config.py` — settings
Loads all config from environment / `.env` via pydantic-settings. See the env
table in the README. Key ones: `LLM_PROVIDER`, `BEDROCK_MODEL_ID`,
`BEDROCK_MODEL_ID_MODERATOR`, `BEDROCK_MODEL_ID_FALLBACK`, `FINNHUB_API_KEY`,
`GNEWS_API_KEY`.

### `llm/provider.py` — the LLM abstraction
Three interchangeable providers behind one interface:

- **`mock`** — deterministic offline responses; no keys, for UI/dev.
- **`bedrock`** — AWS Bedrock `converse_stream`. Supports **per-role models**
  (`model_for_role`): moderator/synthesizer can use a different (stronger) model
  than the analysis agents. Includes **automatic fallback**: if the primary
  model errors before producing tokens (throttle/access/validation), it retries
  with `BEDROCK_MODEL_ID_FALLBACK`.
- **`anthropic`** — direct Anthropic Messages API (needs `ANTHROPIC_API_KEY`).

> **Is it really multi-agent?** Yes. Each agent is a *separate* LLM invocation
> with its own persona system prompt and its own message list. Agents only see
> the **public debate transcript**, never each other's hidden reasoning.

### `agents/personas.py` — the 8 agents
Each persona = id, display name, emoji, color, and a system-prompt builder. The
selected **investor profile** ("long_term" | "short_term") is injected into
every prompt so agents reason for that horizon. The 8:

| id | Agent | Analyzes |
|----|-------|----------|
| `moderator` | Market Expert (Moderator) | Macro context; writes final consensus (always on) |
| `fundamental` | Fundamental Analyst | P/E, EPS, margins, debt, intrinsic value |
| `chartist` | Technical Chartist | MAs, RSI, MACD, Bollinger, patterns |
| `price` | Price Analyst | Historical performance, volatility, 52wk range |
| `researcher` | Deep Researcher | News sentiment, moat, management, catalysts |
| `macro` | Macro & Geopolitical | World/country news impact on the stock |
| `corpaction` | Corporate Actions | Dividends, splits, buybacks, bonus |
| `synthesizer` | Generalist Synthesizer | Devil's advocate; finds contradictions |

### `agents/orchestrator.py` — the debate engine
Runs the debate in **3 phases**, emitting events via a callback (SSE/WS/POST all
reuse this):

1. **Independent analysis** — every selected agent produces a verdict + reasoning.
   Agents in a phase run **concurrently** (`asyncio.gather`) to cut latency.
2. **Debate rounds (1–2)** — agents see the transcript and may challenge/revise.
3. **Consensus** — the moderator produces a **weighted** final verdict.

**Investor-profile weighting** (in `_weighted_score`): the final vote weights
agents differently per profile —
- *Long-term:* Fundamental 1.6, Researcher 1.3 dominate; Chartist 0.7.
- *Short-term:* Chartist 1.6, Price 1.4 dominate; Fundamental 0.7.

Verdicts map to scores (Strong Buy +2 … Strong Sell −2), combined as
`weight × (conviction/10) × score`, normalized to a final verdict + confidence.

### `data/market.py` — prices, fundamentals, corporate actions
Tries sources in order, falling back gracefully:

1. **Yahoo raw chart API** (`query1.finance.yahoo.com/v8/finance/chart` with a
   browser User-Agent) — **primary** for prices/candles. Real OHLCV + quote for
   **US and Indian** (`.NS`/`.BO`) and all Yahoo exchanges, incl. real historical
   candles. Works from cloud IPs where the `yfinance` *library* is blocked. Accepts
   any stock with ≥ 5 days of history (so IPOs / recently-listed stocks work).
2. **yfinance library** — fallback if the raw API fails.
3. **Finnhub** — fallback price source; also the **fundamentals** source (see below).
4. **Stooq** — keyless CSV, last real option.
5. **Synthetic** — deterministic fallback, clearly labeled in the UI.

**Fundamentals** (P/E, EPS, market cap, ROE, margins, beta, 52wk): the Yahoo
chart API returns none, so after prices are fetched, `_try_finnhub()` is called
and its metrics are **merged onto the Yahoo bundle**. Finnhub's free tier is
US-only, so Indian stocks get real prices/charts but no ratios (documented as a
known gap; a paid tier would fill it).

**Corporate actions:** for `.NS`/`.BO`, uses the **NSE public API**
(`nseindia.com/api/corporates-corporateActions`, browser UA — the nseindia.com
*home page* 403s but the `/api` endpoint answers) — the richest free source,
returning real **dividends, splits, bonus, buyback, demergers**. US uses Yahoo's
dividend/split events.

### `data/technicals.py` — indicators + patterns
Computes from the OHLCV series (no external TA lib): SMA 50/200, EMA 20, RSI,
MACD, Bollinger Bands, support/resistance, and **detects chart patterns**
(trendline, double top/bottom, head & shoulders, Bollinger squeeze) with the
coordinates needed to *draw* them on the frontend charts.

### `data/currency.py` — exchange → currency
Maps ticker suffix to currency + symbol (`.NS`/`.BO` → ₹ INR, none → $ USD,
`.AX` → A$, `.L` → £, etc.) and normalizes inputs like `NSE:TCS` → `TCS.NS`.

### `data/news.py` — company + macro news
- **Company news:** Finnhub (US) → **GNews by company name** (covers India + all
  markets) → yfinance → synthetic.
- **Macro/world news:** NewsAPI (if key) → **Finnhub general** → synthetic.
- All items carry title, source, clickable URL, date, snippet.

---

## 3. Frontend components (`frontend/src/`)

| File | Role |
|------|------|
| `App.tsx` | Layout; wires all panels; captures OIDC SSO fragment |
| `useDebate.ts` | Core hook — opens SSE/POST/WS, parses events into state |
| `api.ts` | Resolves API base URL + transport |
| `auth.ts` | Grabs an OIDC id_token (no-op in no-auth mode) |
| `components/ControlPanel.tsx` | Ticker input, agent picker, profile, rounds |
| `components/StockOverview.tsx` | Price card, metrics, mini chart, data-source banner |
| `components/DebateFeed.tsx` | Live chat-style debate feed (auto-scrolls its own box) |
| `components/ConsensusPanel.tsx` | Final verdict, confidence, bull/bear, targets |
| `components/TechnicalCharts.tsx` | Candlestick + drawn patterns, RSI, MACD, Bollinger, volume |
| `components/SidePanels.tsx` | News lists, corporate actions, technical signals |
| `pdf.ts` | Client-side PDF export of the analysis |

**Transports** (`VITE_TRANSPORT`): `sse` (default, live streaming) · `post`
(one request, fills in at once) · `ws` (server hosts only).

---

## 4. Where every piece of data comes from (summary)

| Data | Source | US | India |
|------|--------|:--:|:--:|
| Debate reasoning | AWS Bedrock (Claude Opus 4.8 → Sonnet 4.5 fallback) | ✅ | ✅ |
| Prices / charts | Yahoo raw chart API | ✅ | ✅ |
| Fundamentals (P/E, EPS, mktcap…) | Finnhub (merged onto Yahoo prices) | ✅ | ⚠️ none (no free India source) |
| Corporate actions | NSE API (India) / Yahoo events (US) | ✅ | ✅ |
| Company news | Finnhub (US) / GNews by name (India + all) | ✅ | ✅ |
| Macro / world news | Finnhub general | ✅ | ✅ |
| Technical indicators & patterns | Computed locally from OHLCV | ✅ | ✅ |

Every external source degrades gracefully to clearly-labeled synthetic data if
temporarily unreachable, so the app is never broken.

---

## 5. Deployment topology

- **Backend:** Docker image → Amazon ECR → **AWS App Runner** (no request-time
  streaming cap; supports SSE). Instance role grants Bedrock invoke permission.
  Redeploy = rebuild image + push + `aws apprunner start-deployment`; env-only
  change = `aws apprunner update-service`.
- **Frontend:** static build → **CloudFront + private S3 (OAC)** for public
  access. Scripts:
  `frontend/deploy-cloudfront.sh` (build + deploy) and
  `deploy-cloudfront-prebuilt.sh` (deploy an existing `./build`, no npm).
- **LLM:** Amazon Bedrock (Claude Opus 4.8 → Sonnet 4.5 fallback) in `us-west-2`.
- **CORS:** backend allows `*.cloudfront.net` and anything in CORS_ORIGINS, so the
  browser-served SPA can call it cross-origin.

See README.md / DEPLOY.md for the exact commands and IAM setup.
