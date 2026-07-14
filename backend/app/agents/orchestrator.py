"""Multi-agent debate orchestrator.

Flow:
  1. INDEPENDENT ANALYSIS  - each selected agent analyzes in isolation.
  2. DEBATE ROUNDS (N)     - each agent sees the public transcript and may
                             challenge/support/refine, updating its verdict.
  3. CONSENSUS             - the moderator synthesizes a weighted final call.

Each agent call is an independent LLM invocation with its own system prompt and
a fresh message list that contains only (a) the shared data context and (b) the
public transcript. Agents never see each other's hidden chain-of-thought — only
what was said on the record. That is what makes this a genuine debate rather
than one prompt role-playing. See llm/provider.py for the model-per-agent note.

Events are emitted via an async callback so the WebSocket layer can stream them.
"""
from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable

from ..data.market import get_stock_bundle
from ..data.news import get_company_news, get_macro_news
from ..llm.provider import get_provider
from .personas import PERSONA_BY_ID, PERSONAS

Emit = Callable[[dict], Awaitable[None]]

# Weighting for the final consensus, tuned per investor profile.
PROFILE_WEIGHTS = {
    "long_term": {
        "fundamental": 1.6, "researcher": 1.3, "macro": 1.1, "corpaction": 1.0,
        "price": 0.9, "chartist": 0.7, "synthesizer": 1.0, "moderator": 1.0,
    },
    "short_term": {
        "chartist": 1.6, "price": 1.4, "macro": 1.2, "corpaction": 1.0,
        "researcher": 0.9, "fundamental": 0.7, "synthesizer": 1.0, "moderator": 1.0,
    },
}

VERDICT_SCORE = {
    "Strong Buy": 2, "Buy": 1, "Hold": 0, "Sell": -1, "Strong Sell": -2,
}
SCORE_VERDICT = [
    (1.3, "Strong Buy"), (0.4, "Buy"), (-0.4, "Hold"), (-1.3, "Sell"),
    (-99, "Strong Sell"),
]


def _score_to_verdict(score: float) -> str:
    for threshold, verdict in SCORE_VERDICT:
        if score >= threshold:
            return verdict
    return "Strong Sell"


def _parse_json(text: str) -> dict:
    """Extract the JSON object from an LLM response, tolerating stray prose."""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return {
        "verdict": "Hold", "conviction": 5,
        "summary": text[:400] or "No structured response.",
        "bullish": [], "bearish": [], "evidence": [],
        "price_target": None, "stop_loss": None,
    }


def _context_block(bundle: dict, company_news: list, macro_news: list, role: str) -> str:
    """Build the shared data context each agent sees. Chartist/researcher/macro/
    corpaction get their specialized slices emphasized."""
    cur = bundle["currency"]
    f = bundle["fundamentals"]
    p = bundle["price"]
    t = bundle["technicals"]
    lines = [
        f"TICKER: {bundle['ticker']} ({f.get('name')})",
        f"EXCHANGE/CURRENCY: {cur['exchange']} — prices are in {cur['code']} ({cur['symbol']}).",
        f"DATA SOURCE: {bundle['source']}"
        + (" (SYNTHETIC demo data — flag this uncertainty)" if bundle["source"] == "synthetic" else ""),
        "",
        "PRICE:",
        f"  last={cur['symbol']}{p['last']}, dayChange={p['dayChangePct']}%, "
        f"52wHigh={cur['symbol']}{p['week52High']}, 52wLow={cur['symbol']}{p['week52Low']}, "
        f"annualizedVol={p['annualizedVolatilityPct']}%",
        "",
        "FUNDAMENTALS:",
        f"  sector={f.get('sector')}, PE={f.get('peRatio')}, fwdPE={f.get('forwardPE')}, "
        f"PB={f.get('pbRatio')}, EPS={f.get('eps')}, revGrowth={f.get('revenueGrowth')}, "
        f"D/E={f.get('debtToEquity')}, ROE={f.get('roe')}, margin={f.get('profitMargin')}, "
        f"divYield={f.get('dividendYield')}, beta={f.get('beta')}, "
        f"analystTarget={f.get('targetMeanPrice')}",
    ]
    if role in ("chartist", "price", "synthesizer", "moderator"):
        lines += [
            "",
            "TECHNICALS (latest):",
            f"  close={t['latest']['close']}, RSI={t['latest']['rsi']}, "
            f"MACD={t['latest']['macd']} vs signal={t['latest']['macd_signal']}, "
            f"50DMA={t['latest']['sma50']}, 200DMA={t['latest']['sma200']}, "
            f"cross={t['latest']['cross']}",
            f"  support={t['levels']['support']}, resistance={t['levels']['resistance']}",
            "  signals: " + "; ".join(
                f"{s['name']}={s['reading']}({s['signal']})" for s in t["signals"]),
            "  detected chart patterns: " + (
                "; ".join(f"{pt['name']}[{pt['bias']}]" for pt in t["patterns"]) or "none"),
        ]
    if role in ("researcher", "moderator", "synthesizer"):
        lines += ["", "RECENT COMPANY NEWS (cite url):"]
        for n in company_news[:6]:
            lines.append(f"  - {n['publishedAt']} | {n['title']} | {n['source']} | {n['url']}")
    if role in ("macro", "moderator", "synthesizer"):
        lines += ["", "WORLD / MACRO HEADLINES (cite url):"]
        for n in macro_news[:6]:
            lines.append(f"  - {n['publishedAt']} | {n['title']} | {n['source']} | {n['url']}")
    if role in ("corpaction", "moderator", "synthesizer"):
        lines += ["", "CORPORATE ACTIONS:"]
        for a in bundle["corporateActions"][:8]:
            lines.append(f"  - {a['date']} | {a['type']} | {a['detail']}")
        if not bundle["corporateActions"]:
            lines.append("  none on record")
    return "\n".join(lines)


class DebateOrchestrator:
    def __init__(self, emit: Emit, rounds: int = 2):
        self.emit = emit
        self.rounds = rounds
        self.provider = get_provider()

    async def _run_agent(self, persona, profile, context, transcript, phase) -> dict:
        """One independent, streamed agent invocation."""
        await self.emit({"type": "agent_start", "phase": phase, "agent": persona.id,
                         "name": persona.name, "emoji": persona.emoji,
                         "color": persona.color,
                         "model": self.provider.model_for_role(persona.role)})
        system = persona.system(profile)
        user = context
        if transcript:
            user += "\n\nDEBATE TRANSCRIPT SO FAR (public):\n" + transcript
            user += ("\n\nReview the panel. Challenge, support or refine your position and "
                     "UPDATE your verdict/conviction if warranted. Return the JSON object.")
        else:
            user += "\n\nProduce your independent preliminary analysis now as the JSON object."

        messages = [{"role": "user", "content": user}]
        buffer = []
        async for chunk in self.provider.stream(system, messages, persona.role):
            buffer.append(chunk)
            await self.emit({"type": "agent_token", "agent": persona.id, "text": chunk})
        raw = "".join(buffer)
        parsed = _parse_json(raw)
        result = {
            "agent": persona.id, "name": persona.name, "emoji": persona.emoji,
            "color": persona.color, "role": persona.role, "phase": phase,
            **parsed,
        }
        await self.emit({"type": "agent_done", "phase": phase, **result})
        return result

    async def run(self, raw_ticker: str, profile: str, selected_ids: list[str]) -> dict:
        await self.emit({"type": "status", "message": f"Fetching market data for {raw_ticker}…"})
        bundle = get_stock_bundle(raw_ticker)
        symbol = bundle["ticker"]
        company_news = await get_company_news(
            symbol, bundle["fundamentals"].get("name"))
        macro_news = await get_macro_news()

        await self.emit({"type": "stock", "data": bundle,
                         "companyNews": company_news, "macroNews": macro_news})

        # Resolve participating agents. Moderator always participates for consensus.
        selected = [p for p in PERSONAS if p.id in selected_ids and p.id != "moderator"]
        moderator = PERSONA_BY_ID["moderator"]

        # ---- Phase 1: independent analysis --------------------------------
        # Agents in a phase are independent, so run them CONCURRENTLY. This is
        # what keeps the whole debate under the API Gateway 30s timeout.
        await self.emit({"type": "phase", "phase": "analysis",
                         "label": "Independent Analysis"})
        positions: dict[str, dict] = {}
        results = await asyncio.gather(*[
            self._run_agent(
                persona, profile,
                _context_block(bundle, company_news, macro_news, persona.role),
                "", "analysis")
            for persona in selected
        ])
        for persona, res in zip(selected, results):
            positions[persona.id] = res

        # ---- Phase 2: debate rounds ---------------------------------------
        for rnd in range(1, self.rounds + 1):
            await self.emit({"type": "phase", "phase": f"debate_{rnd}",
                             "label": f"Debate Round {rnd}"})
            transcript = self._render_transcript(positions)
            round_results = await asyncio.gather(*[
                self._run_agent(
                    persona, profile,
                    _context_block(bundle, company_news, macro_news, persona.role),
                    transcript, f"debate_{rnd}")
                for persona in selected
            ])
            for persona, res in zip(selected, round_results):
                positions[persona.id] = res

        # ---- Phase 3: consensus -------------------------------------------
        await self.emit({"type": "phase", "phase": "consensus", "label": "Final Consensus"})
        consensus = await self._consensus(
            moderator, profile, bundle, company_news, macro_news, positions)
        await self.emit({"type": "consensus", **consensus})
        await self.emit({"type": "complete"})
        return {"stock": bundle, "positions": positions, "consensus": consensus}

    def _render_transcript(self, positions: dict[str, dict]) -> str:
        out = []
        for pid, pos in positions.items():
            out.append(
                f"[{pos['name']}] verdict={pos.get('verdict')} "
                f"conviction={pos.get('conviction')}/10 — {pos.get('summary')}")
        return "\n".join(out)

    def _weighted_score(self, positions: dict[str, dict], profile: str) -> tuple[float, float]:
        weights = PROFILE_WEIGHTS.get(profile, PROFILE_WEIGHTS["long_term"])
        num = den = 0.0
        for pid, pos in positions.items():
            w = weights.get(pid, 1.0)
            conv = float(pos.get("conviction", 5)) / 10.0
            score = VERDICT_SCORE.get(pos.get("verdict", "Hold"), 0)
            num += w * conv * score
            den += w * conv
        raw = (num / den) if den else 0.0
        # confidence: agreement strength + average conviction
        avg_conv = sum(float(p.get("conviction", 5)) for p in positions.values()) / max(len(positions), 1)
        return raw, avg_conv

    async def _consensus(self, moderator, profile, bundle, company_news, macro_news, positions) -> dict:
        raw_score, avg_conv = self._weighted_score(positions, profile)
        verdict = _score_to_verdict(raw_score)
        # confidence blends conviction with how far the weighted score is from Hold
        confidence = round(min(100, max(0, 50 + raw_score * 22 + (avg_conv - 5) * 4)))
        if verdict in ("Sell", "Strong Sell"):
            confidence = round(min(100, max(0, 50 - raw_score * 22 + (avg_conv - 5) * 4)))

        transcript = self._render_transcript(positions)
        ctx = _context_block(bundle, company_news, macro_news, "moderator")
        system = moderator.system(profile)
        user = (
            ctx + "\n\nFULL PANEL POSITIONS:\n" + transcript +
            f"\n\nThe weighted algorithmic verdict is '{verdict}' at ~{confidence}% confidence "
            f"(profile={profile}). As moderator, synthesize the debate. Return the JSON object "
            "where 'summary' explains the consensus reasoning, 'bullish'/'bearish' list the key "
            "points raised, 'evidence' cites the most important data/news the panel relied on, "
            "and set 'price_target'/'stop_loss' appropriate to the investor profile."
        )
        buffer = []
        await self.emit({"type": "agent_start", "phase": "consensus", "agent": "moderator",
                         "name": moderator.name, "emoji": moderator.emoji,
                         "color": moderator.color,
                         "model": self.provider.model_for_role("moderator")})
        async for chunk in self.provider.stream(system, [{"role": "user", "content": user}], "moderator"):
            buffer.append(chunk)
            await self.emit({"type": "agent_token", "agent": "moderator", "text": chunk})
        parsed = _parse_json("".join(buffer))
        await self.emit({"type": "agent_done", "phase": "consensus", "agent": "moderator",
                         "name": moderator.name, "emoji": moderator.emoji,
                         "color": moderator.color, **parsed})

        # Build per-agent debate summary for the UI
        agent_summaries = [{
            "agent": pid, "name": pos["name"], "emoji": pos["emoji"], "color": pos["color"],
            "verdict": pos.get("verdict"), "conviction": pos.get("conviction"),
            "summary": pos.get("summary"), "bullish": pos.get("bullish", []),
            "bearish": pos.get("bearish", []), "evidence": pos.get("evidence", []),
            "priceTarget": pos.get("price_target"), "stopLoss": pos.get("stop_loss"),
        } for pid, pos in positions.items()]

        return {
            "verdict": verdict,
            "confidence": confidence,
            "profile": profile,
            "moderatorSummary": parsed.get("summary"),
            "bullish": parsed.get("bullish", []),
            "bearish": parsed.get("bearish", []),
            "evidence": parsed.get("evidence", []),
            "priceTarget": parsed.get("price_target"),
            "stopLoss": parsed.get("stop_loss"),
            "weightedScore": round(raw_score, 3),
            "agentSummaries": agent_summaries,
        }
