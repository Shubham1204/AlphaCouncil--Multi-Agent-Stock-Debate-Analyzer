"""FastAPI entrypoint: REST metadata endpoints + WebSocket debate stream."""
from __future__ import annotations

import asyncio
import json

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .agents.orchestrator import DebateOrchestrator
from .agents.personas import selectable_personas
from .auth import require_user, verify_token
from .config import get_settings
from .data.market import get_stock_bundle
from .data.news import get_company_news, get_macro_news
from .llm.provider import get_provider

settings = get_settings()
app = FastAPI(title="AlphaCouncil — Multi-Agent Stock Debate Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    # Also allow any CloudFront-hosted frontend origin (the SPA calls this API
    # cross-origin). Add your own domains to CORS_ORIGINS or this regex.
    allow_origin_regex=settings.cors_origin_regex or r"https://.*\.cloudfront\.net",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    # Open (no auth) so load balancers / uptime checks work.
    provider = get_provider()
    return {
        "status": "ok",
        "llmProvider": provider.name,
        "defaultModel": provider.model_for_role("fundamental"),
        "moderatorModel": provider.model_for_role("moderator"),
        "debateRounds": settings.debate_rounds,
        "requireAuth": settings.require_auth,
    }


@app.get("/api/agents")
async def agents(user: dict = Depends(require_user)):
    return {"agents": selectable_personas()}


@app.get("/api/stock/{ticker}")
async def stock(ticker: str, user: dict = Depends(require_user)):
    bundle = get_stock_bundle(ticker)
    company_news = await get_company_news(
        bundle["ticker"], bundle["fundamentals"].get("name"))
    macro_news = await get_macro_news()
    return {"stock": bundle, "companyNews": company_news, "macroNews": macro_news}


@app.websocket("/ws/debate")
async def debate_ws(ws: WebSocket):
    await ws.accept()
    try:
        # Auth gate (when enabled): token comes as ?access_token= or in the
        # first message's "token" field, since browsers can't set WS headers.
        if settings.require_auth:
            token = ws.query_params.get("access_token")
            raw0 = await ws.receive_text()
            req = json.loads(raw0)
            token = token or req.get("token")
            if not token:
                await ws.send_json({"type": "error", "message": "Authentication required"})
                await ws.close()
                return
            try:
                verify_token(token)
            except Exception as e:
                await ws.send_json({"type": "error", "message": f"Invalid token: {e}"})
                await ws.close()
                return
        else:
            raw0 = await ws.receive_text()
            req = json.loads(raw0)
        ticker = req.get("ticker", "").strip()
        profile = req.get("profile", "long_term")
        selected = req.get("agents") or [p["id"] for p in selectable_personas()]
        rounds = int(req.get("rounds", settings.debate_rounds))

        if not ticker:
            await ws.send_json({"type": "error", "message": "ticker is required"})
            await ws.close()
            return

        async def emit(event: dict):
            await ws.send_json(event)

        orch = DebateOrchestrator(emit=emit, rounds=max(1, min(rounds, 4)))
        await orch.run(ticker, profile, selected)
    except WebSocketDisconnect:
        return
    except Exception as e:  # surface errors to the client instead of silent drop
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


@app.get("/api/debate/stream")
async def debate_sse(
    request: Request,
    ticker: str,
    profile: str = "long_term",
    agents: str = "",
    rounds: int = 0,
    user: dict = Depends(require_user),
):
    """Server-Sent Events variant of the debate stream.

    Same events as the WebSocket, delivered over a plain HTTP GET so it works on
    AWS Lambda streaming Function URLs / API Gateway (no WebSocket needed).
    `agents` is a comma-separated list of agent ids; empty = all.
    """
    ticker = (ticker or "").strip()
    selected = [a for a in agents.split(",") if a] or [
        p["id"] for p in selectable_personas()
    ]
    n_rounds = rounds or settings.debate_rounds

    async def event_gen():
        if not ticker:
            yield _sse({"type": "error", "message": "ticker is required"})
            return

        queue: asyncio.Queue = asyncio.Queue()

        async def emit(event: dict):
            await queue.put(event)

        async def drive():
            try:
                orch = DebateOrchestrator(emit=emit, rounds=max(1, min(n_rounds, 4)))
                await orch.run(ticker, profile, selected)
            except Exception as e:  # surface to client
                await queue.put({"type": "error", "message": str(e)})
            finally:
                await queue.put(None)  # sentinel: done

        task = asyncio.create_task(drive())
        try:
            while True:
                # Wait for the next event, but never block silently for long:
                # emit an SSE keepalive comment every ~10s so proxies/browsers
                # don't drop the idle connection during long model "thinking"
                # gaps (common with Opus + rounds=3).
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    yield ": keepalive\n\n"
                    continue
                if event is None:
                    break
                if await request.is_disconnected():
                    break
                yield _sse(event)
        finally:
            task.cancel()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering
            "Connection": "keep-alive",
        },
    )


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.post("/api/debate")
async def debate_once(request: Request, user: dict = Depends(require_user)):
    """Non-streaming debate: run the whole thing, return ALL events at once.

    For API Gateway (which buffers responses and can't stream SSE). The frontend
    replays the returned events through the same handler it uses for streaming,
    so the UI is identical — it just fills in all at once instead of live.
    Body: {ticker, profile, agents:[...], rounds}
    """
    body = await request.json()
    ticker = (body.get("ticker") or "").strip()
    if not ticker:
        return {"events": [{"type": "error", "message": "ticker is required"}]}
    profile = body.get("profile", "long_term")
    selected = body.get("agents") or [p["id"] for p in selectable_personas()]
    n_rounds = int(body.get("rounds", settings.debate_rounds))

    events: list[dict] = []

    async def emit(event: dict):
        events.append(event)

    try:
        orch = DebateOrchestrator(emit=emit, rounds=max(1, min(n_rounds, 4)))
        await orch.run(ticker, profile, selected)
    except Exception as e:
        events.append({"type": "error", "message": str(e)})

    return {"events": events}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
