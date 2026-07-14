import { useEffect, useState } from "react";
import { getAgents, getHealth } from "./api";
import { captureSsoFragment } from "./auth";
import type { AgentMeta } from "./types";
import { useDebate } from "./useDebate";
import ControlPanel from "./components/ControlPanel";
import StockOverview from "./components/StockOverview";
import DebateFeed from "./components/DebateFeed";
import ConsensusPanel from "./components/ConsensusPanel";
import TechnicalCharts from "./components/TechnicalCharts";
import {
  CorporateActionsPanel,
  NewsPanel,
  SignalsPanel,
} from "./components/SidePanels";
import { exportPdf } from "./pdf";

export default function App() {
  const [agents, setAgents] = useState<AgentMeta[]>([]);
  const [health, setHealth] = useState<any>(null);
  const debate = useDebate();

  useEffect(() => {
    captureSsoFragment(); // capture OIDC id_token if returned from an SSO redirect
    getAgents().then((d) => setAgents(d.agents || [])).catch(() => {});
    getHealth().then(setHealth).catch(() => {});
  }, []);

  const { stock, consensus } = debate;

  return (
    <div className="min-h-full">
      {/* header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-ink">
              🏛️ AlphaCouncil — Stock Debate
            </h1>
            <p className="text-xs text-subtle">
              8 AI personas independently analyze, debate, and reach a consensus
            </p>
          </div>
          {consensus && stock && (
            <button
              onClick={() => exportPdf(stock, consensus)}
              className="text-sm bg-slate-100 hover:bg-slate-200 px-4 py-2 rounded-xl font-medium text-ink"
            >
              ⬇ Export PDF
            </button>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-5 grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* left column: controls */}
        <div className="lg:col-span-1 space-y-5">
          <ControlPanel
            agents={agents}
            running={debate.running}
            onStart={debate.start}
            health={health}
          />
          {stock && <SignalsPanel stock={stock} />}
          {stock && <CorporateActionsPanel stock={stock} />}
        </div>

        {/* right columns */}
        <div className="lg:col-span-2 space-y-5">
          {debate.error && (
            <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
              {debate.error}
            </div>
          )}

          {stock && <StockOverview stock={stock} />}

          {consensus && stock && (
            <ConsensusPanel consensus={consensus} stock={stock} />
          )}

          <DebateFeed
            messages={debate.messages}
            status={debate.status}
            running={debate.running}
          />

          {stock && (
            <div className="grid sm:grid-cols-2 gap-5">
              <NewsPanel
                title="Company News"
                items={debate.companyNews}
                emptyHint="No company news loaded."
              />
              <NewsPanel
                title="World / Macro Headlines"
                items={debate.macroNews}
                emptyHint="No macro headlines loaded."
              />
            </div>
          )}
        </div>

        {/* full-width technical charts section */}
        {stock && (
          <div className="lg:col-span-3">
            <div className="flex items-center gap-3 mt-2 mb-4">
              <h2 className="text-xl font-bold text-ink">
                Technical Charts for Further Analysis
              </h2>
              <span className="text-xs text-subtle">
                Charts and patterns the Technical Chartist referred to
              </span>
            </div>
            <TechnicalCharts stock={stock} />
          </div>
        )}
      </main>

      <footer className="max-w-7xl mx-auto px-4 py-6 text-center text-xs text-subtle">
        Not financial advice · For educational purposes only ·
        {health ? ` LLM: ${health.llmProvider}` : ""}
      </footer>
    </div>
  );
}
