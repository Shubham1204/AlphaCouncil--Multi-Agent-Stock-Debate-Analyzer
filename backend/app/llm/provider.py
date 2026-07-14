"""Pluggable LLM provider.

This is the module that answers the user's question:
"Is this one model faking multi-agent, or actually multiple models debating?"

Answer: each agent is a SEPARATE invocation with its own system prompt and its
own private message history. They only observe the shared, public debate
transcript -- never each other's hidden reasoning. That makes it a genuine
multi-agent debate. By default every agent is backed by the SAME underlying
model (invoked many independent times, once per agent per turn). But you can
assign a DIFFERENT model per agent (see `model_for_role`), which turns it into
a true cross-model debate. Both modes are supported without code changes.

Three backends:
  - mock       : deterministic, offline, no credentials (runs anywhere today)
  - bedrock    : AWS Bedrock Converse / ConverseStream
  - anthropic  : Anthropic Messages API
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import AsyncIterator

from ..config import get_settings


class LLMProvider:
    """Base interface. `stream` yields text chunks; `complete` returns full text."""

    name = "base"

    def model_for_role(self, role: str) -> str:  # pragma: no cover - overridden
        return "unknown"

    async def stream(self, system: str, messages: list[dict], role: str) -> AsyncIterator[str]:
        raise NotImplementedError

    async def complete(self, system: str, messages: list[dict], role: str) -> str:
        chunks: list[str] = []
        async for c in self.stream(system, messages, role):
            chunks.append(c)
        return "".join(chunks)


# ---------------------------------------------------------------------------
# MOCK provider -- lets the whole app run with zero credentials.
# ---------------------------------------------------------------------------
class MockProvider(LLMProvider):
    name = "mock"

    def model_for_role(self, role: str) -> str:
        return "mock-model-v1"

    async def stream(self, system: str, messages: list[dict], role: str) -> AsyncIterator[str]:
        # Deterministic but context-aware canned reasoning. The debate
        # orchestrator asks agents to return JSON; we synthesize plausible JSON
        # here so the full UI works offline.
        last = messages[-1]["content"] if messages else ""
        seed = int(hashlib.sha256((role + last[:200]).encode()).hexdigest(), 16)
        text = _mock_reasoning(role, seed, last)
        # stream word by word to exercise the streaming UI
        for word in text.split(" "):
            await asyncio.sleep(0.004)
            yield word + " "


def _mock_reasoning(role: str, seed: int, prompt: str) -> str:
    verdicts = ["Buy", "Hold", "Sell"]
    verdict = verdicts[seed % 3]
    conviction = 5 + (seed % 5)
    # Detect whether orchestrator asked for JSON, and mirror the schema.
    if '"verdict"' in prompt or "JSON" in prompt or "json" in prompt:
        payload = {
            "verdict": verdict,
            "conviction": conviction,
            "summary": f"[MOCK/{role}] Preliminary read leans {verdict.upper()} "
            f"(conviction {conviction}/10). This is offline demo output; enable "
            f"a real LLM provider for live analysis.",
            "bullish": [
                f"{role}: momentum indicator is constructive",
                f"{role}: valuation not stretched vs peers",
            ],
            "bearish": [
                f"{role}: macro/sector headwinds add uncertainty",
            ],
            "evidence": [
                {"claim": "Illustrative data point", "source": "mock://offline", "url": ""}
            ],
            "price_target": None,
            "stop_loss": None,
        }
        return json.dumps(payload)
    return (
        f"[MOCK {role}] I lean {verdict} with conviction {conviction}/10. "
        "Enable LLM_PROVIDER=bedrock or =anthropic for real analysis."
    )


# ---------------------------------------------------------------------------
# BEDROCK provider -- AWS Bedrock Converse API.
# ---------------------------------------------------------------------------
class BedrockProvider(LLMProvider):
    name = "bedrock"

    def __init__(self) -> None:
        import boto3  # imported lazily so mock mode needs no boto3

        s = get_settings()
        self._client = boto3.client("bedrock-runtime", region_name=s.aws_region)
        self._default_model = s.bedrock_model_id
        self._moderator_model = s.bedrock_model_id_moderator or s.bedrock_model_id
        self._fallback_model = s.bedrock_model_id_fallback

    def model_for_role(self, role: str) -> str:
        if role in ("moderator", "synthesizer"):
            return self._moderator_model
        return self._default_model

    async def stream(self, system: str, messages: list[dict], role: str) -> AsyncIterator[str]:
        primary = self.model_for_role(role)

        # --- Bedrock response cache -----------------------------------------
        # Cache by (model, system, messages) so an identical prompt reuses a
        # prior Bedrock response instead of paying for another invocation.
        # This is the ONLY thing cached — market data / news are always fresh.
        from ..data.cache import bedrock_cache_get, bedrock_cache_set
        cache_key = _bedrock_key(primary, system, messages)
        cached_text = bedrock_cache_get(cache_key)
        if cached_text is not None:
            # Replay the cached response as chunks (keeps the streaming UI happy).
            for word in cached_text.split(" "):
                yield word + " "
            return

        # Try primary (e.g. Opus 4.8); on failure fall back (e.g. Sonnet 4.5).
        # Fallback is only safe BEFORE any tokens are yielded, so we open the
        # stream and read the first delta inside the try — if opening or the
        # first read fails, we retry with the fallback model cleanly.
        candidates = [primary]
        if self._fallback_model and self._fallback_model != primary:
            candidates.append(self._fallback_model)

        conv = [
            {"role": m["role"], "content": [{"text": m["content"]}]} for m in messages
        ]
        loop = asyncio.get_event_loop()
        accumulated: list[str] = []  # collect full text to cache on success

        last_err: Exception | None = None
        for i, model_id in enumerate(candidates):
            def _call(mid=model_id):
                return self._client.converse_stream(
                    modelId=mid,
                    system=[{"text": system}],
                    messages=conv,
                    inferenceConfig={"maxTokens": 2000},
                )
            try:
                response = await loop.run_in_executor(None, _call)
            except Exception as e:  # open failed (access/validation/throttle)
                last_err = e
                continue  # try fallback

            stream = response["stream"]
            queue: asyncio.Queue = asyncio.Queue()

            def _pump(st=stream):
                try:
                    for event in st:
                        if "contentBlockDelta" in event:
                            delta = event["contentBlockDelta"]["delta"].get("text", "")
                            if delta:
                                loop.call_soon_threadsafe(queue.put_nowait, delta)
                    loop.call_soon_threadsafe(queue.put_nowait, None)
                except Exception as err:  # mid-stream error
                    loop.call_soon_threadsafe(queue.put_nowait, err)

            loop.run_in_executor(None, _pump)
            produced = False
            errored = False
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    last_err = item
                    errored = True
                    break
                produced = True
                accumulated.append(item)
                yield item
            # If the stream errored before producing anything, try the fallback.
            if errored and not produced and i < len(candidates) - 1:
                continue
            # Cache a clean, complete response (not a mid-stream failure).
            if produced and not errored:
                bedrock_cache_set(cache_key, "".join(accumulated))
            return  # done (either success, or mid-stream failure after tokens)

        # All candidates failed to even open.
        raise RuntimeError(f"All Bedrock models failed. Last error: {last_err}")


def _bedrock_key(model: str, system: str, messages: list[dict]) -> str:
    """Stable hash of the exact Bedrock request (model + system + messages)."""
    payload = json.dumps(
        {"m": model, "s": system, "msgs": messages}, sort_keys=True
    )
    return "bedrock:" + hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# ANTHROPIC provider -- direct Messages API.
# ---------------------------------------------------------------------------
class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self) -> None:
        from anthropic import AsyncAnthropic

        s = get_settings()
        if not s.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for LLM_PROVIDER=anthropic")
        self._client = AsyncAnthropic(api_key=s.anthropic_api_key)
        self._model = s.anthropic_model_id

    def model_for_role(self, role: str) -> str:
        return self._model

    async def stream(self, system: str, messages: list[dict], role: str) -> AsyncIterator[str]:
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=2000,
            temperature=0.4,
            system=system,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        ) as stream:
            async for text in stream.text_stream:
                yield text


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is not None:
        return _provider
    provider = get_settings().llm_provider.lower()
    if provider == "bedrock":
        _provider = BedrockProvider()
    elif provider == "anthropic":
        _provider = AnthropicProvider()
    else:
        _provider = MockProvider()
    return _provider
