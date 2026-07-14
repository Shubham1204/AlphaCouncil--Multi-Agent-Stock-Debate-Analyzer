import { useState } from "react";
import type { AgentMeta, Profile } from "../types";

const EXAMPLES = ["NSE:TCS", "AAPL", "NSE:RELIANCE", "MSFT", "BHP.AX", "TSLA"];

export default function ControlPanel({
  agents,
  running,
  onStart,
  health,
}: {
  agents: AgentMeta[];
  running: boolean;
  onStart: (a: { ticker: string; profile: Profile; agents: string[]; rounds: number }) => void;
  health: any;
}) {
  const [ticker, setTicker] = useState("NSE:TCS");
  const [profile, setProfile] = useState<Profile>("long_term");
  const [rounds, setRounds] = useState(2);
  const [selected, setSelected] = useState<Record<string, boolean>>({});

  // initialize selection from defaults once agents load
  if (agents.length && Object.keys(selected).length === 0) {
    const init: Record<string, boolean> = {};
    agents.forEach((a) => (init[a.id] = a.defaultSelected));
    setSelected(init);
  }

  const toggle = (id: string) =>
    setSelected((s) => ({ ...s, [id]: !s[id] }));

  const chosen = agents.filter((a) => a.selectable && selected[a.id]).map((a) => a.id);
  // moderator is non-selectable but always participates
  const moderatorIds = agents.filter((a) => !a.selectable).map((a) => a.id);

  const submit = () => {
    if (!ticker.trim() || running) return;
    onStart({
      ticker: ticker.trim(),
      profile,
      agents: [...chosen, ...moderatorIds],
      rounds,
    });
  };

  return (
    <div className="bg-card rounded-2xl shadow-soft p-5 space-y-5">
      {/* ticker input */}
      <div>
        <label className="text-xs font-semibold text-subtle uppercase tracking-wide">
          Stock Ticker
        </label>
        <div className="flex gap-2 mt-1.5">
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="e.g. NSE:TCS, AAPL, BHP.AX"
            className="flex-1 border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <button
            onClick={submit}
            disabled={running}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-5 py-2 rounded-xl text-sm font-semibold"
          >
            {running ? "Debating…" : "Run Debate"}
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5 mt-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => setTicker(ex)}
              className="text-xs bg-slate-100 hover:bg-slate-200 text-subtle px-2 py-1 rounded-lg"
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      {/* investor profile */}
      <div>
        <label className="text-xs font-semibold text-subtle uppercase tracking-wide">
          Investor Profile
        </label>
        <div className="grid grid-cols-2 gap-2 mt-1.5">
          <ProfileButton
            active={profile === "long_term"}
            onClick={() => setProfile("long_term")}
            title="Long-Term Investor"
            desc="6 months – 5-10 years · buy low, hold, compound"
          />
          <ProfileButton
            active={profile === "short_term"}
            onClick={() => setProfile("short_term")}
            title="Short-Term / Swing"
            desc="1 week – 3-5 months · momentum & catalysts"
          />
        </div>
      </div>

      {/* rounds */}
      <div>
        <label className="text-xs font-semibold text-subtle uppercase tracking-wide">
          Debate Rounds: <span className="text-ink">{rounds}</span>
        </label>
        <input
          type="range"
          min={1}
          max={2}
          value={rounds}
          onChange={(e) => setRounds(Number(e.target.value))}
          className="w-full mt-1 accent-blue-600"
        />
      </div>

      {/* agent selection */}
      <div>
        <label className="text-xs font-semibold text-subtle uppercase tracking-wide">
          Agents in the Debate ({chosen.length + moderatorIds.length})
        </label>
        <div className="space-y-1.5 mt-1.5">
          {agents.map((a) => {
            const on = a.selectable ? selected[a.id] : true;
            return (
              <button
                key={a.id}
                onClick={() => a.selectable && toggle(a.id)}
                disabled={!a.selectable}
                className={`w-full flex items-center gap-2 text-left px-3 py-2 rounded-xl border transition ${
                  on
                    ? "border-transparent"
                    : "border-slate-200 opacity-55 hover:opacity-80"
                }`}
                style={on ? { background: a.color + "14" } : {}}
              >
                <span className="text-lg">{a.emoji}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-ink flex items-center gap-1.5">
                    {a.name}
                    {!a.selectable && (
                      <span className="text-[10px] bg-slate-200 text-subtle px-1.5 rounded-full">
                        always on
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-subtle truncate">{a.tagline}</div>
                </div>
                <span
                  className="w-4 h-4 rounded-md border flex-shrink-0"
                  style={{
                    background: on ? a.color : "#fff",
                    borderColor: on ? a.color : "#cbd5e1",
                  }}
                />
              </button>
            );
          })}
        </div>
      </div>

      {/* model info */}
      {health && (
        <div className="text-[11px] text-subtle border-t border-slate-100 pt-3 leading-relaxed">
          <div>
            LLM provider: <span className="font-semibold text-ink">{health.llmProvider}</span>
          </div>
          <div className="truncate">Model: {health.defaultModel}</div>
          {health.moderatorModel !== health.defaultModel && (
            <div className="truncate">Moderator: {health.moderatorModel}</div>
          )}
        </div>
      )}
    </div>
  );
}

function ProfileButton({
  active,
  onClick,
  title,
  desc,
}: {
  active: boolean;
  onClick: () => void;
  title: string;
  desc: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`text-left px-3 py-2 rounded-xl border text-sm transition ${
        active
          ? "border-blue-500 bg-blue-50 text-blue-800"
          : "border-slate-200 text-subtle hover:border-slate-300"
      }`}
    >
      <div className="font-semibold">{title}</div>
      <div className="text-[11px] mt-0.5 opacity-80">{desc}</div>
    </button>
  );
}
