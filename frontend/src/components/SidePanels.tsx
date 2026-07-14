import type { NewsItem, StockBundle } from "../types";

export function NewsPanel({
  title,
  items,
  emptyHint,
}: {
  title: string;
  items: NewsItem[];
  emptyHint: string;
}) {
  return (
    <div className="bg-card rounded-2xl shadow-soft p-5">
      <h3 className="font-semibold text-ink mb-3">{title}</h3>
      {items.length === 0 ? (
        <p className="text-sm text-subtle">{emptyHint}</p>
      ) : (
        <ul className="space-y-3">
          {items.slice(0, 8).map((n, i) => (
            <li key={i} className="border-b border-slate-100 last:border-0 pb-2 last:pb-0">
              {n.url ? (
                <a
                  href={n.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm font-medium text-blue-700 hover:underline"
                >
                  {n.title} ↗
                </a>
              ) : (
                <span className="text-sm font-medium text-ink">{n.title}</span>
              )}
              <div className="text-[11px] text-subtle mt-0.5">
                {n.source} · {n.publishedAt}
              </div>
              {n.snippet && <p className="text-xs text-slate-500 mt-1">{n.snippet}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function CorporateActionsPanel({ stock }: { stock: StockBundle }) {
  const actions = stock.corporateActions;
  const icon: Record<string, string> = {
    dividend: "💰",
    split: "✂️",
    buyback: "🔄",
    bonus: "🎁",
    merger: "🤝",
    demerger: "🔀",
    rights: "📜",
    meeting: "🗓️",
    other: "📌",
  };
  return (
    <div className="bg-card rounded-2xl shadow-soft p-5">
      <h3 className="font-semibold text-ink mb-3">Corporate Actions</h3>
      {actions.length === 0 ? (
        <p className="text-sm text-subtle">No corporate actions on record.</p>
      ) : (
        <ul className="space-y-2.5">
          {actions.map((a, i) => (
            <li key={i} className="flex gap-2.5 items-start">
              <span className="text-lg">{icon[a.type] || "📌"}</span>
              <div>
                <div className="text-sm text-ink capitalize font-medium">{a.type}</div>
                <div className="text-xs text-subtle">{a.detail}</div>
                <div className="text-[11px] text-slate-400">{a.date}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function SignalsPanel({ stock }: { stock: StockBundle }) {
  const signals = stock.technicals.signals;
  const color = (s: string) =>
    s === "bullish" ? "#16a34a" : s === "bearish" ? "#dc2626" : "#a16207";
  return (
    <div className="bg-card rounded-2xl shadow-soft p-5">
      <h3 className="font-semibold text-ink mb-3">Technical Signals</h3>
      <ul className="space-y-2">
        {signals.map((s, i) => (
          <li key={i} className="flex items-center justify-between text-sm">
            <div>
              <span className="font-medium text-ink">{s.name}</span>
              <span className="text-subtle text-xs ml-2">{s.reading}</span>
            </div>
            <span
              className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
              style={{ background: color(s.signal) + "22", color: color(s.signal) }}
            >
              {s.signal}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
