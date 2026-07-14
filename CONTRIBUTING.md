# Contributing to AlphaCouncil

Thanks for your interest! AlphaCouncil is a multi-agent stock-debate analyzer —
contributions of new agents, data sources, markets, or UI improvements are welcome.

## Getting started
1. Fork and clone the repo.
2. Run it locally in **mock mode** (no API keys needed):
   ```bash
   cd backend && python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt && cp .env.example .env
   uvicorn app.main:app --port 8000
   # in another terminal:
   cd frontend && npm install && npm run dev
   ```
3. Open http://localhost:5173 and run a debate.

## Where things live
- **Add / edit an agent** → `backend/app/agents/personas.py`
- **Change the debate flow / weighting** → `backend/app/agents/orchestrator.py`
- **Add a data source** → `backend/app/data/` (market, news, technicals)
- **Add an LLM provider** → `backend/app/llm/provider.py`
- **UI** → `frontend/src/components/`

See `ARCHITECTURE.md` for the full design.

## Guidelines
- Keep the app runnable in **mock mode** (no keys) — that's how contributors test.
- Match the existing code style; keep functions small and documented.
- New data sources must **degrade gracefully** (fall back, never crash the app).
- Don't commit secrets — use `.env` (gitignored) and update `.env.example`.

## Ideas
See the "What to Build Next" section in `COURSE.md` — the multi-agent pattern
generalizes to code review, hiring, travel planning, and more.

## Disclaimer
This project is for educational purposes only and is not financial advice.
