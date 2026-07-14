import {
  AreaChart,
  Area,
  ResponsiveContainer,
  YAxis,
  Tooltip,
} from "recharts";
import type { StockBundle } from "../types";
import { fmtLargeNum, fmtMoney, fmtNum, fmtPct } from "../utils";

export default function StockOverview({ stock }: { stock: StockBundle }) {
  const { currency: cur, price, fundamentals: f } = stock;
  const up = price.dayChangePct >= 0;
  const mini = stock.technicals.candles.slice(-90).map((c) => ({ date: c.date, close: c.close }));

  const metrics: [string, string][] = [
    ["Market Cap", fmtLargeNum(f.marketCap)],
    ["P/E", fmtNum(f.peRatio)],
    ["Fwd P/E", fmtNum(f.forwardPE)],
    ["P/B", fmtNum(f.pbRatio)],
    ["EPS", fmtNum(f.eps)],
    ["ROE", f.roe != null ? fmtPct(f.roe * 100) : "—"],
    ["Debt/Eq", fmtNum(f.debtToEquity)],
    ["Div Yield", f.dividendYield != null ? fmtPct(f.dividendYield * 100) : "—"],
    ["Beta", fmtNum(f.beta)],
    ["52w High", fmtMoney(cur.symbol, price.week52High)],
    ["52w Low", fmtMoney(cur.symbol, price.week52Low)],
    ["Ann. Vol", fmtPct(price.annualizedVolatilityPct)],
  ];

  return (
    <div className="bg-card rounded-2xl shadow-soft p-5">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-ink">{f.name || stock.ticker}</h2>
            <span className="text-xs bg-slate-100 text-subtle px-2 py-0.5 rounded-full">
              {stock.ticker}
            </span>
            <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">
              {cur.exchange} · {cur.code}
            </span>
          </div>
          <div className="text-sm text-subtle mt-0.5">
            {f.sector || "—"} {f.industry ? `· ${f.industry}` : ""}
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold text-ink">
            {fmtMoney(cur.symbol, price.last)}
          </div>
          <div className={`text-sm font-semibold ${up ? "text-green-600" : "text-red-600"}`}>
            {fmtMoney(cur.symbol, price.dayChange)} ({fmtPct(price.dayChangePct)})
          </div>
        </div>
      </div>

      {stock.source === "synthetic" && (
        <div className="mt-3 text-xs bg-amber-50 text-amber-700 border border-amber-200 rounded-lg px-3 py-2">
          ⚠️ Live market data was unavailable (offline or rate-limited) — showing
          <b> synthetic demo data</b>. Numbers are illustrative only.
        </div>
      )}
      {stock.source === "finnhub" && (
        <div className="mt-3 text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded-lg px-3 py-2">
          ℹ️ Live price &amp; fundamentals from Finnhub. Historical chart shape is
          simulated (real intraday history requires a premium feed) but is
          anchored to the true current price.
        </div>
      )}

      <div className="mt-4 h-24">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={mini}>
            <defs>
              <linearGradient id="miniGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={up ? "#22c55e" : "#ef4444"} stopOpacity={0.3} />
                <stop offset="100%" stopColor={up ? "#22c55e" : "#ef4444"} stopOpacity={0} />
              </linearGradient>
            </defs>
            <YAxis domain={["auto", "auto"]} hide />
            <Tooltip formatter={(v: any) => fmtMoney(cur.symbol, v)} labelFormatter={() => ""} />
            <Area
              type="monotone"
              dataKey="close"
              stroke={up ? "#16a34a" : "#dc2626"}
              fill="url(#miniGrad)"
              strokeWidth={1.6}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-3 sm:grid-cols-4 gap-x-4 gap-y-2 mt-4">
        {metrics.map(([k, v]) => (
          <div key={k}>
            <div className="text-[11px] text-subtle">{k}</div>
            <div className="text-sm font-semibold text-ink">{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
