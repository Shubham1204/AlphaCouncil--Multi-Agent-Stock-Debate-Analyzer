# 🏛️ AlphaCouncil — Multi-Agent Stock Debate Analyzer

Enter a stock ticker → **8 AI agents** independently analyze it, **debate** over
1–2 rounds, then reach a **consensus** (Strong Buy → Strong Sell) with a
confidence score, price targets, live charts, and cited news. Streams live.

Works for **US (NASDAQ/NYSE)** and **Indian (NSE/BSE)** markets, with the
correct currency per exchange (₹ / $ / A$ / £ …). Tailored for **long-term**
and **short-term / swing** investors.

> ⚠️ Not financial advice. For educational purposes only.

---

## Table of contents
1. [What it does](#what-it-does)
2. [Architecture](#architecture)
3. [The 8 agents](#the-8-agents)
4. [How the debate works](#how-the-debate-works)
5. [Data sources](#data-sources)
6. [Run locally](#run-locally)
7. [Deploy the backend (AWS App Runner)](#deploy-the-backend-aws-app-runner)
8. [Deploy the frontend (CloudFront + S3)](#deploy-the-frontend-cloudfront--s3)
9. [Environment variables](#environment-variables)
10. [Troubleshooting](#troubleshooting)

---

## What it does

- **8 selectable AI personas** independently analyze a stock, then debate.
- **Real LLM debate** on AWS Bedrock (Claude Opus 4.8, falls back to Sonnet 4.5),
  or the Anthropic API, or a zero-dependency mock mode.
- **Two investor profiles** — Long-Term (6mo–10yr) and Short-Term/Swing (1wk–5mo)
  — that change both each agent's reasoning *and* the consensus weighting.
- **Live streaming** (SSE): the debate unfolds token-by-token in the browser.
- **Real market data + charts** for US and Indian stocks.
- **Cited news** (company + macro/world) with clickable source links.
- **Technical charts** with drawn patterns (double top/bottom, head & shoulders,
  trendlines, Bollinger squeeze), RSI, MACD, Bollinger Bands, volume.
- **PDF export** of the consensus + per-agent summaries.

---

## Architecture

```
┌─────────────────────────────┐        ┌──────────────────────────────────────┐
│  Frontend (React + Vite)    │        │  Backend (FastAPI, Python)            │
│  CloudFront + S3 (or any     │  HTTPS │  AWS App Runner (Docker container)    │
│  static host / localhost)   │ ─────▶ │                                       │
│                             │  SSE   │  GET  /api/health                     │
│  • Search + agent picker    │        │  GET  /api/agents                     │
│  • Live debate feed         │        │  GET  /api/stock/{ticker}             │
│  • Consensus panel          │        │  GET  /api/debate/stream  (SSE)       │
│  • Technical charts         │        │  POST /api/debate         (buffered)  │
│  • PDF export               │        │  WS   /ws/debate          (local dev) │
└─────────────────────────────┘        └───────────────┬──────────────────────┘
                                                        │
             ┌──────────────────────┬──────────────────┼────────────────────────┐
             ▼                      ▼                   ▼                        ▼
    ┌──────────────────┐  ┌──────────────────┐ ┌──────────────────┐  ┌────────────────────┐
    │  AWS Bedrock     │  │  Prices/charts   │ │ Corporate actions│  │  News              │
    │  Claude Opus 4.8 │  │  Yahoo chart API │ │ NSE API (India:  │  │  Finnhub (US news  │
    │  → Sonnet 4.5    │  │  + Finnhub (US   │ │ bonus/buyback/   │  │  + fundamentals +  │
    │  (fallback)      │  │  fundamentals)   │ │ split) · Yahoo   │  │  macro), GNews     │
    └──────────────────┘  │  Stooq (fallback)│ │ events (US)      │  │  (company by name) │
                          └──────────────────┘ └──────────────────┘  └────────────────────┘
```

**Why App Runner (not Lambda)?** A full 7-agent × 2-round debate takes 60–90s.
Serverless request/response gateways typically cap at ~30s and buffer responses
(breaking SSE). App Runner has no request timeout and streams SSE — the right fit
for a long, streaming, multi-agent workload.

### Repository layout
```
alphacouncil/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI: REST + SSE + WebSocket endpoints
│   │   ├── config.py            # env-driven settings (pydantic-settings)
│   │   ├── auth.py              # optional OIDC/JWT verification
│   │   ├── llm/provider.py      # mock | bedrock | anthropic; Opus→Sonnet fallback; response cache
│   │   ├── data/
│   │   │   ├── market.py        # Yahoo/Finnhub/Stooq prices + NSE corp actions
│   │   │   ├── news.py          # Finnhub/GNews company + macro news
│   │   │   ├── technicals.py    # indicators + chart-pattern detection
│   │   │   ├── cache.py         # in-memory TTL cache for Bedrock responses
│   │   │   └── currency.py      # exchange → currency/symbol
│   │   └── agents/
│   │       ├── personas.py      # 8 persona prompts + profile guidance
│   │       └── orchestrator.py  # 3-phase debate, weighting, consensus
│   ├── Dockerfile               # container image
│   ├── requirements.txt
│   ├── run.sh                   # container entrypoint (uvicorn)
│   ├── deploy-apprunner.sh      # one-shot backend deploy to App Runner
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── App.tsx, useDebate.ts, api.ts, types.ts, utils.ts, pdf.ts, auth.ts
    │   └── components/          # ControlPanel, StockOverview, DebateFeed,
    │                            # ConsensusPanel, TechnicalCharts, SidePanels
    ├── deploy-cloudfront.sh     # build + deploy to S3 + CloudFront
    ├── vite.config.ts
    └── package.json
```

---

## The 8 agents

| Agent | Focus |
|-------|-------|
| 🎓 **Market Expert (Moderator)** | Macro context; moderates and writes the final consensus (always on) |
| 📊 **Fundamental Analyst** | P/E, EPS, margins, debt, cash flow, intrinsic value |
| 📈 **Technical Chartist** | MAs, RSI, MACD, Bollinger, patterns, support/resistance |
| 💹 **Price Analyst** | Historical performance, volatility, 52wk range, risk/reward |
| 🔬 **Deep Researcher** | News sentiment, moat, management, regulation, catalysts |
| 🌍 **Macro & Geopolitical** | World/country news impact on the stock/sector |
| 🏛️ **Corporate Actions** | Dividends, splits, buybacks and their price impact |
| 🧩 **Generalist Synthesizer** | Devil's advocate — finds contradictions across the panel |

All are selectable in the UI except the Moderator (always participates for the
final synthesis).

---

## How the debate works

**Is it one model faking multi-agent, or a real debate?** Real debate. Each
agent is a **separate LLM invocation** with its own persona system prompt and
its own private message list; it sees only the **public debate transcript**,
never another agent's hidden reasoning. Agents within a phase run concurrently
(`asyncio.gather`) to keep latency down.

**Three phases** (`app/agents/orchestrator.py`):
1. **Independent analysis** — each agent produces a preliminary verdict + reasoning.
2. **Debate rounds (1–2)** — agents see the transcript and may challenge, support,
   or revise their verdict. (Agents within a phase run concurrently, so adding
   agents costs little time; each extra *round* is a full sequential pass.)
3. **Consensus** — the Moderator synthesizes a weighted final verdict, confidence,
   bull/bear points, price target, and stop-loss.

### Investor profiles
The chosen profile shapes the debate at **two levels**:

1. **Prompt** — profile guidance is injected into *every* agent's system prompt,
   so a long-term profile reasons over multi-year fundamentals while a short-term
   profile reasons over technical setups/catalysts.
2. **Consensus weighting** — the final weighted vote flips the agent weights:
   - **Long-term:** Fundamental 1.6, Researcher 1.3 dominate; Chartist 0.7.
   - **Short-term:** Chartist 1.6, Price 1.4 dominate; Fundamental 0.7.

So the *same* ticker can yield a different verdict per profile.

---

## Data sources

| Data | Primary | Fallbacks | US | India |
|------|---------|-----------|:--:|:--:|
| Debate reasoning | Bedrock Opus 4.8 | Sonnet 4.5 | ✅ | ✅ |
| Prices / charts | Yahoo chart API | yfinance → Finnhub → Stooq → synthetic | ✅ | ✅ |
| Fundamentals | Finnhub (merged onto prices) | — | ✅ | ⚠️ none free |
| Corporate actions | NSE API (India) / Yahoo events (US) | synthetic | ✅ | ✅ |
| Company news | Finnhub (US) | GNews (by name, all markets) → synthetic | ✅ | ✅ |
| Macro / world news | Finnhub general | NewsAPI → synthetic | ✅ | ✅ |

- **Yahoo** works from cloud IPs via the raw `query1.finance.yahoo.com/v8/finance/chart`
  endpoint with a browser User-Agent (the `yfinance` *library* is often blocked; the
  raw API is not). Real prices + real historical candles for both markets. Any stock
  with ≥ 5 days of history is accepted (IPOs / recently-listed stocks work).
- **Fundamentals** come from **Finnhub** (free tier is US-only). Indian stocks show
  prices/charts/news/corporate actions but not P/E-style ratios (no free source
  provides parsed Indian fundamentals; a paid feed would fill the gap).
- **Corporate actions:** Indian tickers use the NSE public API for real dividends,
  splits, bonus, buyback, demergers; US uses Yahoo's dividend/split events.
- **GNews** searches by company *name*, covering markets Finnhub's free tier doesn't.
- Everything degrades gracefully to clearly-labeled synthetic data if a source is
  unreachable, so the app is never broken.

Free API keys: [finnhub.io](https://finnhub.io), [gnews.io](https://gnews.io).
Yahoo and NSE need no key.

---

## Run locally

Prerequisites: **Python 3.12+**, **Node 18+**.

### 1. Backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # runs in mock mode with no keys
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Visit http://localhost:8000/api/health → `{"status":"ok",...}`.

- **Mock mode (default):** `LLM_PROVIDER=mock` — no API keys, deterministic
  offline debate. Great for UI work.
- **Real LLM:** set `LLM_PROVIDER=bedrock` with AWS creds that can invoke Bedrock,
  or `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`.
- **Real data:** add `FINNHUB_API_KEY` and `GNEWS_API_KEY` to `.env` (Yahoo/NSE
  need no key).

### 2. Frontend
```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173
```
Vite proxies `/api` and `/ws` to `localhost:8000`, so the browser stays on one
origin. Open http://localhost:5173, enter a ticker (`AAPL`, `NSE:TCS`), pick
agents + profile, click **Run Debate**.

Transports (`VITE_TRANSPORT`): `sse` (default, live streaming), `post` (single
request, for buffered hosts), `ws` (WebSocket, server hosts only).

---

## Deploy the backend (AWS App Runner)

One-shot script (needs AWS CLI + Docker configured):
```bash
cd backend
FINNHUB_API_KEY=xxx GNEWS_API_KEY=yyy ./deploy-apprunner.sh
```
It creates the IAM roles, ECR repo, builds + pushes the image, creates the App
Runner service (or updates it), waits for `RUNNING`, and prints the URL + the
`VITE_API_BASE` to set for the frontend.

Prerequisite (one-time): enable **Anthropic Claude model access** in the Bedrock
console for your region (Model access page), or the debate falls back / fails.

Redeploy after a code change: rebuild + push the image, then
`aws apprunner start-deployment --service-arn <arn>`. Env-only change:
`aws apprunner update-service`. See `DEPLOY.md` for full detail.

---

## Deploy the frontend (CloudFront + S3)

```bash
cd frontend
VITE_API_BASE=https://<your-apprunner-url> ./deploy-cloudfront.sh
```
Builds the SPA, uploads to a private S3 bucket, fronts it with CloudFront (Origin
Access Control — bucket stays private), configures SPA routing (403/404 →
index.html), and prints the CloudFront URL. First deploy takes ~5–15 min to
propagate.

Any other static host (Netlify, nginx, plain S3): `npm run build`, serve the
`build/` folder, and set `VITE_API_BASE` to your backend URL.

---

## Environment variables

Backend (`backend/.env` or App Runner env):

| Var | Default | Purpose |
|-----|---------|---------|
| `LLM_PROVIDER` | `mock` | `mock` \| `bedrock` \| `anthropic` |
| `AWS_REGION` | `us-west-2` | Bedrock region |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-opus-4-8` | Primary model |
| `BEDROCK_MODEL_ID_FALLBACK` | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | Used if primary errors |
| `BEDROCK_MODEL_ID_MODERATOR` | (blank) | Optional distinct model for moderator |
| `ANTHROPIC_API_KEY` | (blank) | For `LLM_PROVIDER=anthropic` |
| `FINNHUB_API_KEY` | (blank) | US fundamentals + US/macro news |
| `GNEWS_API_KEY` | (blank) | Company news by name incl. India |
| `DEBATE_ROUNDS` | `2` | Default debate rounds |
| `REQUIRE_AUTH` | `false` | Gate all requests behind an OIDC JWT |
| `OIDC_ISSUER` / `OIDC_JWKS_URL` | (blank) | Your OIDC provider (if auth on) |
| `CORS_ORIGINS` | localhost:5173 | Allowed frontend origins |
| `CORS_ORIGIN_REGEX` | (blank) | Regex for a family of origins (default `*.cloudfront.net`) |

Frontend (`frontend/.env.production`):

| Var | Purpose |
|-----|---------|
| `VITE_API_BASE` | Backend base URL (empty = same origin via dev proxy) |
| `VITE_TRANSPORT` | `sse` (default) \| `post` \| `ws` |

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| News shows "Synthetic Wire (demo)" | `FINNHUB_API_KEY` / `GNEWS_API_KEY` not set, or the deployed image is stale (rebuild + redeploy). |
| `source":"synthetic"` for prices | Yahoo temporarily throttled; retry. Recently-listed stocks now work (min 5 candles). |
| US stock shows "—" for P/E / EPS | `FINNHUB_API_KEY` not set (fundamentals come from Finnhub). |
| Indian stock shows "—" for fundamentals | Expected — no free source for parsed Indian fundamentals. Prices/charts/news/corp-actions are still real. |
| Debate stream "connection failed" on 2 rounds | Long model gaps dropped the idle SSE; a 10s keepalive is built in. On a gateway with a request timeout, reduce rounds or use Sonnet for agents. |
| Every agent uses Sonnet, never Opus | Opus model access not enabled in the Bedrock console → falls back to Sonnet. Enable it. |
| CloudFront URL `ERR_NAME_NOT_RESOLVED` | New distribution still propagating DNS (up to ~30 min). Wait, then flush local DNS. |

---

## Disclaimer
Not financial advice. For educational purposes only. Multi-agent AI analysis can
be confidently wrong — always do your own research.
