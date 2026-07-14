"""In-memory TTL cache for Bedrock (LLM) responses ONLY.

Why cache Bedrock and nothing else: LLM calls are ~95% of the app's cost. An
identical prompt (same model + system + messages) produces an equivalent
response, so replaying a cached response avoids paying for another invocation.

Market data / news are intentionally NOT cached — they should stay fresh.

Keyed by a hash of the exact request (see provider._bedrock_key). Because each
agent prompt embeds the day's market data, keys are naturally scoped to the
current data; a TTL bounds staleness and memory.

Note: this lives in the App Runner instance's memory. With one warm instance
(the default) it's effectively shared across users. For a guaranteed shared
cache across many instances, back it with DynamoDB (TTL attribute) instead.
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_store: dict[str, tuple[str, float]] = {}

TTL_SECONDS = 6 * 3600   # 6 hours
MAX_ENTRIES = 2000


def bedrock_cache_get(key: str) -> str | None:
    now = time.time()
    with _lock:
        hit = _store.get(key)
        if hit and hit[1] > now:
            return hit[0]
        if hit:                      # expired
            _store.pop(key, None)
    return None


def bedrock_cache_set(key: str, text: str) -> None:
    if not text:
        return
    now = time.time()
    with _lock:
        if len(_store) >= MAX_ENTRIES:
            # evict the ~10% nearest expiry
            for k in sorted(_store, key=lambda k: _store[k][1])[: MAX_ENTRIES // 10]:
                _store.pop(k, None)
        _store[key] = (text, now + TTL_SECONDS)


def clear() -> None:
    with _lock:
        _store.clear()
