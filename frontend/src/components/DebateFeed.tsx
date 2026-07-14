import { useEffect, useRef } from "react";
import type { DebateMessage, Evidence } from "../types";
import { PHASE_LABELS, verdictColor } from "../utils";

export default function DebateFeed({
  messages,
  status,
  running,
}: {
  messages: DebateMessage[];
  status: string;
  running: boolean;
}) {
  const feedRef = useRef<HTMLDivElement>(null);
  // Only auto-scroll the feed's OWN box (never the page), and only when the
  // user is already near the bottom — so scrolling up to read is respected and
  // never yanked back down.
  const stickToBottom = useRef(true);

  const onScroll = () => {
    const el = feedRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottom.current = distanceFromBottom < 80;
  };

  useEffect(() => {
    const el = feedRef.current;
    if (el && stickToBottom.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  // group messages by phase, preserving order
  const phases: { phase: string; msgs: DebateMessage[] }[] = [];
  for (const m of messages) {
    let g = phases.find((p) => p.phase === m.phase);
    if (!g) {
      g = { phase: m.phase, msgs: [] };
      phases.push(g);
    }
    g.msgs.push(m);
  }

  return (
    <div className="bg-card rounded-2xl shadow-soft p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-ink">Live Debate</h3>
        {running && (
          <span className="text-xs text-blue-600 flex items-center gap-1">
            <span className="typing">
              <span>●</span>
              <span>●</span>
              <span>●</span>
            </span>
            {status || "in progress"}
          </span>
        )}
      </div>

      {messages.length === 0 && (
        <div className="text-sm text-subtle py-10 text-center">
          Enter a ticker and run the debate to watch the agents analyze and
          argue in real time.
        </div>
      )}

      <div
        ref={feedRef}
        onScroll={onScroll}
        className="feed space-y-5 max-h-[70vh] overflow-y-auto pr-1"
      >
        {phases.map((g) => (
          <div key={g.phase}>
            <div className="sticky top-0 bg-card/90 backdrop-blur py-1 z-10">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-subtle">
                {PHASE_LABELS[g.phase] || g.phase}
              </span>
            </div>
            <div className="space-y-3 mt-1">
              {g.msgs.map((m) => (
                <Bubble key={m.id} m={m} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Bubble({ m }: { m: DebateMessage }) {
  const vc = verdictColor(m.parsed?.verdict);
  return (
    <div className="flex gap-2.5">
      <div
        className="w-9 h-9 rounded-full flex items-center justify-center text-lg flex-shrink-0"
        style={{ background: m.color + "1f" }}
      >
        {m.emoji}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold" style={{ color: m.color }}>
            {m.name}
          </span>
          {m.parsed && (
            <span
              className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
              style={{ background: vc.bg, color: vc.text }}
            >
              {m.parsed.verdict} · {m.parsed.conviction}/10
            </span>
          )}
        </div>
        <div
          className="mt-1 rounded-2xl rounded-tl-sm px-3.5 py-2.5 text-sm text-ink"
          style={{ background: m.color + "10" }}
        >
          {m.parsed ? (
            <ParsedBody m={m} />
          ) : (
            <span className="whitespace-pre-wrap break-words text-subtle">
              {m.text || "…"}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function ParsedBody({ m }: { m: DebateMessage }) {
  const p = m.parsed!;
  return (
    <div className="space-y-2">
      <p>{p.summary}</p>
      {(p.bullish.length > 0 || p.bearish.length > 0) && (
        <div className="grid sm:grid-cols-2 gap-2">
          {p.bullish.length > 0 && (
            <div>
              <div className="text-[11px] font-semibold text-green-700">Bullish</div>
              <ul className="list-disc list-inside text-xs text-slate-600">
                {p.bullish.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </div>
          )}
          {p.bearish.length > 0 && (
            <div>
              <div className="text-[11px] font-semibold text-red-700">Bearish</div>
              <ul className="list-disc list-inside text-xs text-slate-600">
                {p.bearish.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {p.evidence.length > 0 && <EvidenceList evidence={p.evidence} />}
      {(p.priceTarget != null || p.stopLoss != null) && (
        <div className="text-xs text-subtle">
          {p.priceTarget != null && <>🎯 Target: {p.priceTarget} </>}
          {p.stopLoss != null && <>· 🛑 Stop: {p.stopLoss}</>}
        </div>
      )}
    </div>
  );
}

export function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  return (
    <div>
      <div className="text-[11px] font-semibold text-subtle uppercase tracking-wide">
        Why / referenced
      </div>
      <ul className="space-y-1 mt-1">
        {evidence.map((e, i) => (
          <li key={i} className="text-xs text-slate-600">
            <span>• {e.claim}</span>{" "}
            {e.url ? (
              <a
                href={e.url}
                target="_blank"
                rel="noreferrer"
                className="text-blue-600 hover:underline"
              >
                [{e.source || "source"} ↗]
              </a>
            ) : (
              e.source && <span className="text-slate-400">({e.source})</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
