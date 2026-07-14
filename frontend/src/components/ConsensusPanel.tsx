import type { Consensus, StockBundle } from "../types";
import { fmtMoney, verdictColor } from "../utils";
import { EvidenceList } from "./DebateFeed";

export default function ConsensusPanel({
  consensus,
  stock,
}: {
  consensus: Consensus;
  stock: StockBundle;
}) {
  const vc = verdictColor(consensus.verdict);
  const sym = stock.currency.symbol;
  const profileLabel =
    consensus.profile === "long_term"
      ? "Long-Term Investor (6mo–5-10yr)"
      : "Short-Term / Swing (1wk–3-5mo)";

  return (
    <div className="bg-card rounded-2xl shadow-lift p-6 border-t-4" style={{ borderColor: vc.ring }}>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs text-subtle uppercase tracking-wider">Final Consensus</div>
          <div className="text-xs text-subtle">{profileLabel}</div>
        </div>
        <span
          className="text-lg font-bold px-4 py-1.5 rounded-full"
          style={{ background: vc.bg, color: vc.text }}
        >
          {consensus.verdict}
        </span>
      </div>

      {/* confidence meter */}
      <div className="mt-4">
        <div className="flex justify-between text-xs text-subtle mb-1">
          <span>Confidence</span>
          <span className="font-semibold text-ink">{consensus.confidence}%</span>
        </div>
        <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${consensus.confidence}%`,
              background: `linear-gradient(90deg, ${vc.ring}, ${vc.text})`,
            }}
          />
        </div>
      </div>

      {consensus.moderatorSummary && (
        <p className="text-sm text-ink mt-4 leading-relaxed">{consensus.moderatorSummary}</p>
      )}

      {/* price targets */}
      {(consensus.priceTarget != null || consensus.stopLoss != null) && (
        <div className="flex gap-3 mt-4">
          {consensus.priceTarget != null && (
            <div className="flex-1 bg-green-50 rounded-xl px-4 py-3">
              <div className="text-[11px] text-green-700 uppercase tracking-wide">Price Target</div>
              <div className="text-lg font-bold text-green-700">
                {fmtMoney(sym, consensus.priceTarget)}
              </div>
            </div>
          )}
          {consensus.stopLoss != null && (
            <div className="flex-1 bg-red-50 rounded-xl px-4 py-3">
              <div className="text-[11px] text-red-700 uppercase tracking-wide">Suggested Stop-Loss</div>
              <div className="text-lg font-bold text-red-700">
                {fmtMoney(sym, consensus.stopLoss)}
              </div>
            </div>
          )}
        </div>
      )}

      {/* bull vs bear */}
      <div className="grid sm:grid-cols-2 gap-4 mt-5">
        <div className="bg-green-50/60 rounded-xl p-4">
          <div className="text-sm font-semibold text-green-700 mb-1">🐂 Key Bullish Points</div>
          <ul className="list-disc list-inside text-sm text-slate-700 space-y-0.5">
            {consensus.bullish.length ? (
              consensus.bullish.map((b, i) => <li key={i}>{b}</li>)
            ) : (
              <li className="text-subtle list-none">None highlighted</li>
            )}
          </ul>
        </div>
        <div className="bg-red-50/60 rounded-xl p-4">
          <div className="text-sm font-semibold text-red-700 mb-1">🐻 Key Bearish Points</div>
          <ul className="list-disc list-inside text-sm text-slate-700 space-y-0.5">
            {consensus.bearish.length ? (
              consensus.bearish.map((b, i) => <li key={i}>{b}</li>)
            ) : (
              <li className="text-subtle list-none">None highlighted</li>
            )}
          </ul>
        </div>
      </div>

      {consensus.evidence.length > 0 && (
        <div className="mt-4 bg-slate-50 rounded-xl p-4">
          <EvidenceList evidence={consensus.evidence} />
        </div>
      )}

      {/* per-agent debate summary */}
      <div className="mt-6">
        <h4 className="font-semibold text-ink mb-2">Per-Agent Debate Summary</h4>
        <div className="space-y-2">
          {consensus.agentSummaries.map((a) => {
            const c = verdictColor(a.verdict);
            return (
              <details key={a.agent} className="bg-slate-50 rounded-xl px-4 py-2.5 group">
                <summary className="flex items-center gap-2 cursor-pointer list-none">
                  <span className="text-base">{a.emoji}</span>
                  <span className="text-sm font-medium text-ink flex-1">{a.name}</span>
                  <span
                    className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
                    style={{ background: c.bg, color: c.text }}
                  >
                    {a.verdict} · {a.conviction}/10
                  </span>
                  <span className="text-subtle text-xs group-open:rotate-90 transition">▶</span>
                </summary>
                <div className="mt-2 text-sm text-slate-700 space-y-2">
                  <p>{a.summary}</p>
                  {a.evidence.length > 0 && <EvidenceList evidence={a.evidence} />}
                </div>
              </details>
            );
          })}
        </div>
      </div>

      <p className="text-[11px] text-subtle mt-5 border-t border-slate-100 pt-3">
        ⚠️ Not financial advice. For educational purposes only. Multi-agent AI
        analysis can be wrong; always do your own research.
      </p>
    </div>
  );
}
