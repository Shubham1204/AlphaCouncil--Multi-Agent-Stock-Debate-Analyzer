# Building Multi-Agent Debate Systems — 8-Class Workshop

**Course goal:** Teach attendees how to build **any** multi-agent AI application
where independent agents analyze, debate, and converge — using the Stock Debate
Analyzer as the running example codebase.

**What attendees walk away with:**
- A reusable architectural pattern (personas + orchestrator + transport)
- Hands-on experience with streaming, LLM orchestration, and deployment
- Ability to swap the domain (stock → code review → hiring → travel) in an afternoon

**Format:** 8 sessions × 60–90 min. Theory → live code → exercise.

**Pre-reqs:** Basic Python, basic React/JS, curiosity.

---

## Class 1 — What is Multi-Agent Debate? (Concepts + Architecture)

### Objective
Understand WHY you'd use multiple agents instead of one prompt, and HOW the
pieces connect.

### Topics
- **Single-prompt vs multi-agent:** anchoring bias, lack of self-challenge,
  one-perspective problem
- **What "multi-agent" actually means:** separate LLM invocations, each with
  its own system prompt, seeing only the public transcript
- **The 3-component pattern:**
  1. Personas (who debates)
  2. Orchestrator (how they debate)
  3. Transport (how the user sees it)
- **Architecture walkthrough** (draw.io diagram): frontend → backend → LLM →
  data sources
- **When multi-agent makes sense** (and when it doesn't)

### Demo
- Open the live app, run a debate, watch agents disagree and refine
- Point out: different agents give different verdicts; the transcript shows
  how they challenge each other; the consensus reflects weighted disagreement

### Exercise
- Sketch (on paper/whiteboard) a multi-agent system for a domain you care about:
  what are the 3–5 personas? what would their system prompts emphasize?

---

## Class 2 — Personas: Defining Who Debates

### Objective
Learn to design agent personas that produce genuinely different perspectives.

### Topics
- **Anatomy of a persona:** id, name, role, system prompt, output contract
- **The system prompt is everything:** same LLM, different persona = different
  reasoning. Show two agents given the same data → opposite conclusions.
- **The output contract:** why every agent MUST return the same JSON shape
  (enables weighting, comparison, display)
- **Context injection:** how profile guidance ("long-term" / "short-term")
  changes the reasoning without changing the persona
- **Role-specific data slicing:** the Chartist sees indicators; the Researcher
  sees news; everyone sees prices. Why not dump everything on everyone.

### Code walkthrough
```python
# personas.py
PROFILE_GUIDANCE = {"long_term": "...", "short_term": "..."}
OUTPUT_CONTRACT = '{"verdict": ..., "conviction": ..., "summary": ...}'

@dataclass
class Persona:
    id: str; name: str; role: str
    system: Callable[[str], str]  # builds the prompt given a profile

# 8 personas, each with a distinct focus in their base prompt
```

### Key patterns
- Prompt = base (persona focus) + profile (context) + contract (output format)
- The stricter the contract, the more reliable the downstream parsing
- "Role" routes to a specific model (moderator → stronger model)

### Exercise
- Write 3 personas for a **Code Review Debate** system:
  "Correctness Reviewer", "Performance Reviewer", "Security Reviewer"
- Define the output contract they'd share

---

## Class 3 — The Orchestrator: How Agents Debate

### Objective
Build the engine that runs independent analysis → debate → consensus.

### Topics
- **The 3-phase pattern:**
  1. Independent analysis (no cross-contamination)
  2. Debate rounds (see transcript, challenge/revise)
  3. Consensus (weighted synthesis)
- **Concurrency within phases:** `asyncio.gather` — adding agents is nearly
  free in wall-clock time
- **Sequential between phases:** each phase needs the previous one's output
- **The transcript:** how agents "see" each other (only public summary, not
  hidden reasoning) — this is what makes it a real debate vs role-play
- **Weighted consensus:** not a majority vote. Weights reflect expertise
  relevance per context (investor profile, review type, etc.)

### Code walkthrough
```python
# orchestrator.py
# Phase 1: concurrent independent analysis
results = await asyncio.gather(*[
    self._run_agent(persona, context, transcript="")
    for persona in selected_agents
])

# Phase 2: debate rounds (transcript-aware)
for round in range(num_rounds):
    transcript = self._render_transcript(positions)
    results = await asyncio.gather(*[
        self._run_agent(persona, context, transcript=transcript)
        for persona in selected_agents
    ])

# Phase 3: weighted consensus
score = sum(weight * conviction * verdict_score) / sum(weights)
```

### Key patterns
- The `emit()` callback: the orchestrator doesn't know about SSE/WS/POST —
  it just calls `await self.emit(event)` for every event
- The transcript is a SUMMARY (name + verdict + 1-line reason), not the full
  agent output — keeps context windows manageable
- `_parse_json()` — tolerant extraction of JSON from LLM output that may
  include stray prose

### Exercise
- Implement a 2-agent debate: "Optimist" vs "Pessimist" that argue about a
  topic. Use mock mode. Make them run 2 rounds and show how their verdicts change.

---

## Class 4 — The LLM Provider: Abstraction & Resilience

### Objective
Talk to any LLM without coupling your app to one provider.

### Topics
- **The provider interface:** `stream(system, messages, role) → AsyncIterator[str]`
- **Mock mode:** why it's essential (fast dev, no cost, deterministic tests)
- **Per-role model routing:** `model_for_role("moderator")` → Opus;
  `model_for_role("chartist")` → Sonnet. Match capability to importance.
- **Automatic fallback:** try primary → catch error → try secondary → raise
  only if all fail. Makes the system resilient to throttling/model-access issues.
- **Streaming bridge:** AWS Bedrock SDK is synchronous (blocking). How to bridge
  it into async Python using `asyncio.Queue` + `loop.run_in_executor()`.
- **Model quirks:** Opus 4.8 rejects `temperature`; some models have different
  token limits. Handle per-model config.

### Code walkthrough
```python
# provider.py
class BedrockProvider(LLMProvider):
    async def stream(self, system, messages, role):
        for model in [self.primary, self.fallback]:
            try:
                response = await self._call_bedrock(model, system, messages)
                async for chunk in self._stream_response(response):
                    yield chunk
                return
            except Exception:
                continue
        raise RuntimeError("All models failed")
```

### Key patterns
- Singleton factory (`get_provider()`) — one provider instance for the app
- The queue-based async bridge for blocking SDKs
- Fallback only fires before any tokens are yielded (user never sees a half-response)

### Exercise
- Add a "logging provider" wrapper that logs every call + response length
- Implement a simple rate-limiter in the provider (max N calls/minute)

---

## Class 5 — Real-Time Streaming: SSE, Keepalive, and Event Design

### Objective
Stream a long-running multi-agent debate to the browser live.

### Topics
- **Why streaming matters:** a 60–90s debate with no output = "is it broken?"
  Streaming = the user sees progress token-by-token.
- **SSE vs WebSocket vs POST:**
  - SSE: simplest, works through proxies, one-way (server → client)
  - WebSocket: bidirectional, but complex with proxies/load-balancers
  - POST: simplest but no live feedback (spinner for 90s)
- **Event design:** define a small set of event types that cover the whole lifecycle
  (`agent_start`, `agent_token`, `agent_done`, `consensus`, `complete`, `error`)
- **The keepalive problem:** LLMs "think" for 30–60s with no output. Proxies drop
  "idle" connections. Solution: emit `: keepalive\n\n` (SSE comment) every 10s.
- **The `emit()` pattern revisited:** the orchestrator is transport-agnostic; the
  endpoint wires `emit` to the appropriate transport.

### Code walkthrough
```python
# Server: SSE endpoint with keepalive
async def event_gen():
    queue = asyncio.Queue()
    task = asyncio.create_task(orchestrator.run(...))
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=10)
        except asyncio.TimeoutError:
            yield ": keepalive\n\n"
            continue
        if event is None: break
        yield f"data: {json.dumps(event)}\n\n"
```

```typescript
// Client: EventSource
const es = new EventSource(url);
es.onmessage = (ev) => {
    const event = JSON.parse(ev.data);
    // route to UI based on event.type
};
```

### Key patterns
- `asyncio.wait_for` with timeout for the keepalive loop
- SSE comment lines (`: ...`) are ignored by the client — perfect for heartbeats
- One event handler function shared across all three transports (SSE/POST/WS)
- "Event replay" for POST: call the same handler for each event in the array

### Exercise
- Add a `progress` event type that emits "Phase 1 of 3: 40% complete"
- Implement a client-side reconnection (EventSource auto-reconnects, but handle
  the "resume from where we left off" logic)

---

## Class 6 — Frontend: Rendering a Live Debate

### Objective
Build a React UI that renders streaming events as a chat-style debate feed.

### Topics
- **The `useDebate()` hook:** managing streaming state in React
  - `running`, `messages`, `stock`, `consensus` — all updated by event handler
  - Three transports in one hook (SSE / POST / WS)
- **The event handler pattern:** one `handle(event, done)` function
  - `agent_start` → add a new message bubble (streaming: true)
  - `agent_token` → append text to the latest streaming bubble
  - `agent_done` → freeze the bubble, parse verdict, show badge
  - `consensus` → render the consensus panel
- **Auto-scroll without hijacking:** `stickToBottom` ref — only auto-scroll
  when the user is already near the bottom. If they scroll up, leave them alone.
- **Rendering structured agent output:** verdict badges (color-coded), bull/bear
  lists, evidence links (clickable URLs), per-agent expandable summaries

### Code walkthrough
```typescript
// useDebate.ts — the core state machine
const handle = useCallback((e, done) => {
  switch (e.type) {
    case "agent_start":   // create bubble
    case "agent_token":   // append to active bubble
    case "agent_done":    // parse + freeze
    case "consensus":     // set consensus state
    case "complete":      // stop spinner
  }
}, []);

// The scroll pattern
const stickToBottom = useRef(true);
const onScroll = () => {
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottom.current = distFromBottom < 80;
};
useEffect(() => {
    if (stickToBottom.current) el.scrollTop = el.scrollHeight;
}, [messages]);
```

### Key patterns
- Custom hooks for complex async state (cleaner than Redux for streaming)
- `useRef` for mutable state that doesn't trigger re-renders
- Immutable state updates: `setMessages(m => [...m, newMsg])` — React needs new
  array references to detect changes

### Exercise
- Add a "typing" animation (three dots) while an agent is streaming
- Add a "pin message" feature that highlights a specific agent's output

---

## Class 7 — Data Grounding: Giving Agents Real Facts

### Objective
Agents are only as good as the data you give them. Learn to build a resilient
data layer with graceful fallback.

### Topics
- **Why data grounding matters:** without it, agents "hallucinate" financials.
  With it, they cite real numbers and URLs.
- **The waterfall pattern:** try sources in priority order
  (Yahoo → Finnhub → Stooq → synthetic). First success wins.
- **Source-specific tricks:**
  - Yahoo blocks the *library* but not the raw API (User-Agent trick)
  - NSE blocks the *home page* but not `/api/` endpoints
  - Finnhub free = US only; GNews searches by company *name* (covers India)
- **Merging from multiple sources:** Yahoo for prices, Finnhub for fundamentals,
  NSE for corporate actions — combine into one bundle.
- **Graceful degradation:** always show SOMETHING, labeled honestly. The app is
  never "broken" — just sometimes "synthetic (demo data)".
- **Context block assembly:** give each agent only the data relevant to its role
  (Chartist doesn't need news; Researcher doesn't need RSI values).

### Code walkthrough
```python
# The waterfall
yc = _try_yahoo_chart(ticker)       # prices + candles
if not yc: yf = _try_yfinance(...)  # fallback
if still none: fh = _try_finnhub()  # fundamentals (US)
if still none: synthetic()          # labeled honestly

# Merge fundamentals onto prices
if not info.get("trailingPE"):
    fh_info = _try_finnhub(ticker)
    for key, val in fh_info.items():
        if val and not info.get(key):
            info[key] = val
```

### Key patterns
- Waterfall with early return (don't call expensive sources if cheap one worked)
- Merge without overwrite (`if not info.get(key)`)
- Role-specific data slicing in `_context_block()`
- Always tag the source (`source: "yahoo" | "finnhub" | "synthetic"`) so the
  UI can show an honest banner

### Exercise
- Add a new data source for your domain (e.g. a code repository API for a code
  review debate, or a travel API for a trip planner)
- Implement a caching layer (in-memory, 5 min TTL) to avoid re-fetching the same
  ticker within a session

---

## Class 8 — Deployment & Productionizing

### Objective
Ship your multi-agent app to real users on AWS.

### Topics
- **Why App Runner over Lambda:** the 30s API Gateway timeout kills multi-agent
  debates. App Runner has no request timeout + supports SSE streaming.
- **The Docker → ECR → App Runner pipeline:**
  ```
  docker build → docker push → aws apprunner start-deployment
  ```
- **IAM roles:** instance role (Bedrock invoke) + ECR access role. Least privilege.
- **Frontend hosting:** CloudFront + S3 (private bucket, OAC) for public;
  any other static host. One-script deploy.
- **Environment variables as the config plane:** all secrets in env vars, never
  in code. `.env.example` template committed; `.env` gitignored.
- **The redeploy rules:**
  - Code change → rebuild image + push + `start-deployment`
  - Env-only change → `update-service` (no rebuild needed)
- **Lessons learned (the hard way):**
  - Small build environments cant `pip install` pandas — build in Docker instead
  - Some managed AWS accounts block public Lambda Function URLs via SCP — App Runner avoids this
  - `start-deployment` ≠ `update-service` (one pulls image, other sets env)
  - CloudFront DNS takes 10–30 min to propagate (brand-new distributions)
  - `python -m uvicorn` (not bare `uvicorn`) in a `pip install -t` package

### Code walkthrough
- `Dockerfile` + `run.sh` — the container entrypoint
- `frontend/deploy-cloudfront.sh` — full S3 + OAC + CloudFront script
- `.gitignore` — what stays out of version control

### Key patterns
- "Build where you have room, deploy just the artifact"
- OAC for private S3 (the bucket isn't publicly readable)
- SPA routing via CloudFront custom error responses (403/404 → /index.html)
- Cache strategy: hashed assets = forever; index.html = never

### Exercise
- Deploy the app to your own AWS account end-to-end
- Add a health-check alert (CloudWatch alarm on App Runner 5xx rate)

---

## What to Build Next (Adapt the Pattern)

The recipe is always the same:
```
Personas + Orchestrator + Transport + Data grounding
```

Swap the domain, keep the architecture:

| Domain | Personas | Data grounding |
|--------|----------|---------------|
| **Code Review** | Correctness, Perf, Security, Readability | Git diff + AST |
| **Hiring Decision** | Technical, Culture, Growth-potential | Resume + interview notes |
| **Travel Planning** | Budget, Adventure, Comfort, Safety | Flight/hotel APIs |
| **Architecture Review** | Scalability, Cost, Security, Simplicity | System diagram + metrics |
| **Research Synthesis** | Domain experts (3–5 perspectives) | Papers + citations |

The debate pattern generalizes to **any** problem where multiple perspectives improve the answer.

---

## Resources

- **Live app:** your CloudFront URL after deploy
- **Source code:** your repository
- **Architecture diagram:** `architecture.drawio` (open at app.diagrams.net)
- **Presentation slides:** `PRESENTATION.md` (render with `marp --pptx`)
- **Contact:** the project maintainer
