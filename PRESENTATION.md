---
marp: true
theme: default
paginate: true
title: Building Multi-Agent Debate Systems — A Practical Guide
---

# Building Multi-Agent Debate Systems
### How to orchestrate multiple AI agents that genuinely debate, challenge, and converge

Workshop

---

# What is a Multi-Agent Debate System?

Multiple **independent** LLM invocations, each with a **distinct persona**, that:

1. Analyze a problem from their own angle
2. **See each other's public reasoning** (but NOT hidden chain-of-thought)
3. Challenge, support, or revise their positions
4. Converge on a weighted final answer

**Not:** one model role-playing multiple characters in a single prompt.
**Is:** genuinely separate calls where Agent A reads Agent B's published output and responds to it.

---

# Why Debate > Single Prompt?

| Single prompt | Multi-agent debate |
|---|---|
| One monolithic answer | Multiple independent perspectives |
| Can't self-challenge | Agents explicitly disagree |
| Anchoring bias (first reasoning wins) | Fresh reasoning per agent |
| "Confident but wrong" | Contradictions surface naturally |
| One-shot | Iterative refinement across rounds |

**When to use it:**
- The answer depends on **multiple lenses** (financial, technical, qualitative…)
- You need to show **why** the conclusion holds (cite the disagreements)
- You want **weighted confidence**, not binary answers

---

# Core Architecture (3 Components)

```
┌─────────────────────────────────────────────┐
│  1. PERSONAS — who debates                  │
│     system prompt + output contract + role   │
└────────────────────┬────────────────────────┘
                     ▼
┌─────────────────────────────────────────────┐
│  2. ORCHESTRATOR — how they debate          │
│     phases + concurrency + transcript +     │
│     weighted consensus                      │
└────────────────────┬────────────────────────┘
                     ▼
┌─────────────────────────────────────────────┐
│  3. TRANSPORT — how the user sees it        │
│     SSE streaming + emit() callback         │
└─────────────────────────────────────────────┘
```

Let's build each one.

---

# Component 1: Personas

### What defines an agent?
```python
@dataclass
class Persona:
    id: str           # "fundamental", "chartist", ...
    name: str         # display name
    role: str         # routes to a specific LLM model
    system: str       # THE PERSONA PROMPT — this is what makes it unique
```

### The system prompt is everything
```
"You are a seasoned Fundamental Analyst. Analyze {ticker} using
P/E, EPS, revenue growth, debt-to-equity, ROE, margins, cash flow.
Estimate intrinsic value. Be data-driven and cite specific numbers."
```

Each agent has a DIFFERENT focus → different analysis → genuine disagreement.

---

# The Output Contract (critical!)

Every agent MUST return the **same JSON shape** — otherwise the orchestrator can't compare/weight/synthesize them:

```json
{
  "verdict": "Buy",           // Strong Buy|Buy|Hold|Sell|Strong Sell
  "conviction": 7,            // 1-10
  "summary": "why...",        // 2-4 sentences
  "bullish": ["point1"],      // supports
  "bearish": ["risk1"],       // concerns
  "evidence": [{"claim":"...", "source":"...", "url":"..."}]
}
```

**Lesson:** the more structured your output contract, the more reliable your orchestration. LLMs are good at filling JSON schemas when told precisely.

---

# Injecting Context (profile, data, transcript)

Each agent's final prompt is assembled from 3 pieces:

```
SYSTEM PROMPT = persona_base + profile_guidance + output_contract

USER MESSAGE  = data_context + transcript (if debate round) + instruction
```

### Profile guidance changes the reasoning:
```python
LONG_TERM = "Time horizon 6mo–10yr. Prioritise fundamentals, moat, intrinsic value."
SHORT_TERM = "Time horizon 1wk–5mo. Prioritise momentum, catalysts, entry/exit."
```

Same agent, different profile → different verdict. That's the power.

---

# Component 2: The Orchestrator

### The 3-Phase Pattern

```python
async def run(ticker, profile, agents):
    # PHASE 1 — Independent analysis (concurrent!)
    positions = await asyncio.gather(*[
        run_agent(agent, context, transcript="")
        for agent in agents
    ])

    # PHASE 2 — Debate rounds (sequential phases, concurrent agents)
    for round in range(num_rounds):
        transcript = render_transcript(positions)
        positions = await asyncio.gather(*[
            run_agent(agent, context, transcript=transcript)
            for agent in agents
        ])

    # PHASE 3 — Consensus (moderator synthesizes)
    consensus = await run_moderator(positions)
    return consensus
```

---

# Why Concurrent Agents + Sequential Phases?

```
WRONG (fully sequential):
  Agent1 → Agent2 → Agent3 → Agent4 → ...
  Time: N × agent_time (slow!)

WRONG (fully parallel, no interaction):
  All agents in parallel, no transcript sharing
  Result: independent analysis, no debate

RIGHT (concurrent within phase, sequential between):
  Phase 1: [A1, A2, A3, A4] all at once → transcript
  Phase 2: [A1, A2, A3, A4] all at once, seeing Phase 1 → updated positions
  Phase 3: Moderator sees all → consensus

  Time: num_phases × one_agent_time (much faster than sequential!)
```

`asyncio.gather()` makes agents within a phase run in parallel — adding more agents costs almost no additional latency.

---

# The Transcript Pattern (how agents "see" each other)

```python
def render_transcript(positions):
    lines = []
    for agent_id, pos in positions.items():
        lines.append(
            f"[{pos['name']}] verdict={pos['verdict']} "
            f"conviction={pos['conviction']}/10 — {pos['summary']}"
        )
    return "\n".join(lines)
```

In debate rounds, this transcript is appended to the user message:
```
DEBATE TRANSCRIPT SO FAR (public):
[Fundamental Analyst] verdict=Buy conviction=8/10 — Strong margins...
[Technical Chartist] verdict=Sell conviction=7/10 — RSI overbought...

Review the panel. Challenge, support or refine. UPDATE your verdict if warranted.
```

Agents ONLY see the public summary — not each other's hidden reasoning. That's what makes it a real debate.

---

# Weighted Consensus

Not a simple majority vote. Each agent's weight depends on the **context**:

```python
WEIGHTS = {
    "long_term": {"fundamental": 1.6, "chartist": 0.7, "researcher": 1.3},
    "short_term": {"chartist": 1.6, "fundamental": 0.7, "price": 1.4},
}

def weighted_score(positions, profile):
    total = 0
    for agent_id, pos in positions.items():
        w = WEIGHTS[profile][agent_id]
        score = VERDICT_MAP[pos["verdict"]]  # Strong Buy=+2 ... Strong Sell=-2
        conviction = pos["conviction"] / 10
        total += w * score * conviction
    return total / sum_weights
```

The **moderator** then narrates the consensus with full context of who agreed/disagreed and why.

---

# Component 3: Transport — The `emit()` Pattern

The orchestrator doesn't know HOW events reach the user. It just calls `emit()`:

```python
class Orchestrator:
    def __init__(self, emit: Callable):
        self.emit = emit  # any async callback

    async def _run_agent(self, persona, ...):
        await self.emit({"type": "agent_start", "agent": persona.id})
        async for chunk in self.provider.stream(...):
            await self.emit({"type": "agent_token", "text": chunk})
        await self.emit({"type": "agent_done", "verdict": ...})
```

### Same orchestrator, multiple transports:
- **SSE:** `emit` = `yield f"data: {json.dumps(event)}\n\n"`
- **WebSocket:** `emit` = `ws.send_json(event)`
- **POST:** `emit` = `events.append(event)` (return all at end)

---

# SSE Streaming — The Server Side

```python
@app.get("/api/debate/stream")
async def debate_sse(ticker, agents, rounds):
    queue = asyncio.Queue()

    async def emit(event):
        await queue.put(event)

    async def event_gen():
        task = asyncio.create_task(
            Orchestrator(emit).run(ticker, agents, rounds))
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=10)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"  # prevent proxy drop!
                continue
            if event is None: break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
```

The **10s keepalive** prevents proxies/browsers from dropping the connection during long model "thinking" gaps.

---

# SSE Streaming — The Client Side

```typescript
function startDebate(args) {
  const es = new EventSource(`/api/debate/stream?ticker=${args.ticker}&...`);

  es.onmessage = (ev) => {
    const event = JSON.parse(ev.data);
    switch (event.type) {
      case "agent_start":  // → show "Agent X is typing..."
      case "agent_token":  // → append text to the active bubble
      case "agent_done":   // → freeze bubble, show verdict badge
      case "consensus":    // → render the final verdict panel
      case "complete":     // → stop spinner, close connection
    }
  };
}
```

**One handler, all events.** The same handler works for SSE, POST (replay), and WebSocket — just the connection setup differs.

---

# The LLM Provider Abstraction

```python
class LLMProvider:
    def model_for_role(self, role: str) -> str: ...
    async def stream(self, system, messages, role) -> AsyncIterator[str]: ...

class BedrockProvider(LLMProvider):
    async def stream(self, system, messages, role):
        primary = self.model_for_role(role)
        for model in [primary, self.fallback]:
            try:
                response = await call_bedrock(model, system, messages)
                async for chunk in response:
                    yield chunk
                return  # success
            except Exception:
                continue  # try fallback
        raise RuntimeError("All models failed")
```

**Key ideas:**
- Per-role model routing (stronger model for moderator)
- Automatic fallback (Opus → Sonnet if throttled)
- Same interface for mock/bedrock/anthropic (swap without changing app)

---

# Putting It All Together — The Full Flow

```
1. User enters ticker + picks agents + profile
2. Frontend opens SSE connection
3. Backend:
   a. Fetches market data (Yahoo/Finnhub/NSE)
   b. Phase 1: all agents analyze concurrently
      → each streams tokens → frontend shows typing
   c. Phase 2: agents see transcript, debate
      → challenges, revisions, updated verdicts
   d. Phase 3: moderator synthesizes
      → weighted consensus + confidence
4. Frontend renders:
   - Live debate feed (chat bubbles per agent)
   - Consensus panel (verdict + bull/bear + targets)
   - Charts with drawn patterns
```

Total time: ~60–90s for 7 agents × 2 rounds (Opus). Streams live — user watches it unfold.

---

# Design Decisions That Matter

| Decision | Why |
|----------|-----|
| Separate LLM calls (not one prompt) | Genuine independence; no anchoring |
| Structured JSON output contract | Reliable parsing; enables weighting |
| Concurrent agents within a phase | Latency = 1 agent, not N agents |
| Sequential phases (not all-parallel) | Agents NEED to see prior round |
| `emit()` callback (not hardcoded SSE) | Transport-agnostic; testable |
| Keepalive heartbeat | Prevents proxy/browser timeout |
| Weighted consensus (not majority) | Domain expertise matters more in some contexts |
| Profile injection in prompt | Same system, tailored reasoning |

---

# How to Adapt This to YOUR Domain

### Recipe:
1. **Define your personas** — what angles matter for YOUR problem?
2. **Define the output contract** — what must every agent return?
3. **Choose the weighting** — which perspectives dominate in which context?
4. **Pick your data sources** — what factual grounding do agents need?
5. **Keep the orchestrator + transport unchanged** — they're domain-agnostic

### Examples:
- **Code review:** correctness, perf, security, readability agents → verdict: approve/request-changes
- **Hiring decision:** technical, culture, growth-potential agents → hire/pass
- **Architecture review:** scalability, cost, security, simplicity → recommend/concerns

---

# Common Pitfalls & How We Solved Them

| Pitfall | Solution |
|---------|----------|
| Agents agree too easily | Add a "devil's advocate" / synthesizer persona |
| Output parsing fails | Strict JSON contract + tolerant `_parse_json()` |
| Debate takes too long | Concurrent agents (asyncio.gather) + round cap |
| Connection drops mid-debate | SSE keepalive every 10s |
| Same verdict regardless of context | Profile-specific prompt injection + weighting |
| "Hallucinated" data | Give agents REAL data in context; prompt says "cite from provided" |
| Model errors mid-debate | Auto-fallback in provider (Opus → Sonnet) |

---

# Live Demo

**Try it:** your deployed CloudFront URL

1. Enter `NSE:TCS` or `AAPL`
2. Select 3–4 agents
3. Pick "Long-Term" profile
4. Click **Run Debate**
5. Watch the debate stream live
6. Scroll up while it runs — it won't drag you back
7. See the consensus + charts at the end

---

# Questions & Next Steps

### Want to build your own multi-agent app?
1. Clone the repo — runs in mock mode immediately (no keys)
2. Change the personas and prompts → new domain
3. Swap the data layer → new grounding
4. Deploy (App Runner + CloudFront)

### Source & docs:
- **Source:** your repository
- **Course curriculum:** `COURSE.md` in the repo (8-class breakdown)
- **Architecture:** `ARCHITECTURE.md` + `architecture.drawio`

**Looking for collaborators** — DM me or reply in the channel.

Questions welcome.
