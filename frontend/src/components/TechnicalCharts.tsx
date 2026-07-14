import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceDot,
  ReferenceArea,
  Legend,
  Area,
} from "recharts";
import type { StockBundle } from "../types";
import { biasColor, fmtNum } from "../utils";

/**
 * "Technical Charts for Further Analysis" section.
 * Renders multiple charts the Chartist referred to and DRAWS the detected
 * patterns (double top/bottom, head & shoulders, trendline, squeeze) on the
 * price chart, plus RSI, MACD, and Bollinger sub-charts.
 */
export default function TechnicalCharts({ stock }: { stock: StockBundle }) {
  const t = stock.technicals;
  const sym = stock.currency.symbol;

  // Build a unified row set indexed by date. Show the last ~180 bars for clarity.
  const N = t.candles.length;
  const start = Math.max(0, N - 180);
  const rows = t.candles.slice(start).map((c, i) => {
    const gi = start + i; // global index into series arrays
    return {
      idx: gi,
      date: c.date,
      close: c.close,
      high: c.high,
      low: c.low,
      volume: c.volume,
      sma50: t.series.sma50[gi],
      sma200: t.series.sma200[gi],
      ema20: t.series.ema20[gi],
      bbUpper: t.series.bb_upper[gi],
      bbLower: t.series.bb_lower[gi],
      bbMid: t.series.bb_mid[gi],
      rsi: t.series.rsi[gi],
      macd: t.series.macd[gi],
      macdSignal: t.series.macd_signal[gi],
      macdHist: t.series.macd_hist[gi],
    };
  });

  const support = t.levels.support;
  const resistance = t.levels.resistance;

  // Only draw pattern points that fall within the visible window.
  const visiblePatternPoints = t.patterns.flatMap((p) =>
    p.points
      .filter((pt) => pt.index >= start)
      .map((pt) => ({ ...pt, name: p.name, bias: p.bias, type: p.type }))
  );

  return (
    <div className="space-y-8">
      {/* ---- Price + overlays + drawn patterns ---- */}
      <ChartCard
        title="Price, Moving Averages & Detected Patterns"
        subtitle="Candlestick close with 20 EMA, 50/200 DMA, support & resistance, and drawn chart patterns"
      >
        <ResponsiveContainer width="100%" height={360}>
          <ComposedChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fontSize: 10 }}
              tickFormatter={(v) => `${sym}${fmtNum(v, 0)}`}
              width={64}
            />
            <Tooltip formatter={(v: any) => `${sym}${fmtNum(v)}`} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="close" name="Close" stroke="#0f172a" dot={false} strokeWidth={1.6} />
            <Line type="monotone" dataKey="ema20" name="EMA20" stroke="#0891b2" dot={false} strokeWidth={1} />
            <Line type="monotone" dataKey="sma50" name="SMA50" stroke="#d97706" dot={false} strokeWidth={1} />
            <Line type="monotone" dataKey="sma200" name="SMA200" stroke="#7c3aed" dot={false} strokeWidth={1} />

            {support != null && (
              <ReferenceLine y={support} stroke="#16a34a" strokeDasharray="6 4"
                label={{ value: `Support ${sym}${fmtNum(support)}`, position: "insideBottomLeft", fontSize: 10, fill: "#16a34a" }} />
            )}
            {resistance != null && (
              <ReferenceLine y={resistance} stroke="#dc2626" strokeDasharray="6 4"
                label={{ value: `Resistance ${sym}${fmtNum(resistance)}`, position: "insideTopLeft", fontSize: 10, fill: "#dc2626" }} />
            )}

            {/* Draw pattern line segments (trendline, double top/bottom, H&S) */}
            {t.patterns.map((p, pi) => {
              const pts = p.points.filter((pt) => pt.index >= start);
              if (pts.length < 2) return null;
              return pts.slice(0, -1).map((pt, k) => {
                const next = pts[k + 1];
                return (
                  <ReferenceLine
                    key={`pat-${pi}-${k}`}
                    stroke={biasColor(p.bias)}
                    strokeWidth={2}
                    strokeDasharray="2 2"
                    segment={[
                      { x: pt.date, y: pt.price },
                      { x: next.date, y: next.price },
                    ]}
                  />
                );
              });
            })}

            {/* Mark pattern anchor points */}
            {visiblePatternPoints.map((pt, i) => (
              <ReferenceDot
                key={`dot-${i}`}
                x={pt.date}
                y={pt.price}
                r={5}
                fill={biasColor(pt.bias)}
                stroke="#fff"
                strokeWidth={1.5}
                label={{ value: pt.name, position: "top", fontSize: 9, fill: biasColor(pt.bias) }}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
        <PatternLegend patterns={t.patterns} />
      </ChartCard>

      {/* ---- Bollinger Bands ---- */}
      <ChartCard title="Bollinger Bands (20, 2σ)" subtitle="Volatility envelope around the 20-period mean">
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
            <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${sym}${fmtNum(v, 0)}`} width={64} domain={["auto", "auto"]} />
            <Tooltip formatter={(v: any) => `${sym}${fmtNum(v)}`} />
            <Area type="monotone" dataKey="bbUpper" name="Upper" stroke="#94a3b8" fill="#e2e8f0" fillOpacity={0.5} />
            <Area type="monotone" dataKey="bbLower" name="Lower" stroke="#94a3b8" fill="#ffffff" fillOpacity={1} />
            <Line type="monotone" dataKey="close" name="Close" stroke="#0f172a" dot={false} strokeWidth={1.4} />
            <Line type="monotone" dataKey="bbMid" name="Mid (SMA20)" stroke="#d97706" dot={false} strokeWidth={1} />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* ---- RSI ---- */}
      <ChartCard title="Relative Strength Index (14)" subtitle="Overbought > 70, oversold < 30">
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} width={40} />
            <Tooltip formatter={(v: any) => fmtNum(v)} />
            <ReferenceArea y1={70} y2={100} fill="#fee2e2" fillOpacity={0.5} />
            <ReferenceArea y1={0} y2={30} fill="#dcfce7" fillOpacity={0.5} />
            <ReferenceLine y={70} stroke="#dc2626" strokeDasharray="4 4" />
            <ReferenceLine y={30} stroke="#16a34a" strokeDasharray="4 4" />
            <Line type="monotone" dataKey="rsi" name="RSI" stroke="#7c3aed" dot={false} strokeWidth={1.4} />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* ---- MACD ---- */}
      <ChartCard title="MACD (12, 26, 9)" subtitle="MACD line vs signal, with histogram">
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
            <YAxis tick={{ fontSize: 10 }} width={48} />
            <Tooltip formatter={(v: any) => fmtNum(v)} />
            <ReferenceLine y={0} stroke="#94a3b8" />
            <Bar dataKey="macdHist" name="Histogram" fill="#cbd5e1" />
            <Line type="monotone" dataKey="macd" name="MACD" stroke="#2563eb" dot={false} strokeWidth={1.4} />
            <Line type="monotone" dataKey="macdSignal" name="Signal" stroke="#dc2626" dot={false} strokeWidth={1.2} />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* ---- Volume ---- */}
      <ChartCard title="Volume" subtitle="Traded volume per bar">
        <ResponsiveContainer width="100%" height={160}>
          <ComposedChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
            <YAxis tick={{ fontSize: 10 }} width={56} tickFormatter={(v) => `${(v / 1e6).toFixed(1)}M`} />
            <Tooltip formatter={(v: any) => fmtNum(v, 0)} />
            <Bar dataKey="volume" name="Volume" fill="#93c5fd" />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}

function ChartCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-card rounded-2xl shadow-soft p-5">
      <h4 className="font-semibold text-ink">{title}</h4>
      <p className="text-xs text-subtle mb-3">{subtitle}</p>
      {children}
    </div>
  );
}

function PatternLegend({ patterns }: { patterns: StockBundle["technicals"]["patterns"] }) {
  if (!patterns.length) return null;
  return (
    <div className="mt-4 space-y-2">
      <div className="text-xs font-semibold text-subtle uppercase tracking-wide">
        Patterns observed on this chart
      </div>
      {patterns.map((p, i) => (
        <div key={i} className="flex gap-2 text-sm items-start">
          <span
            className="mt-0.5 inline-block w-3 h-3 rounded-full flex-shrink-0"
            style={{ background: biasColor(p.bias) }}
          />
          <div>
            <span className="font-medium text-ink">{p.name}</span>{" "}
            <span
              className="text-xs px-1.5 py-0.5 rounded-full"
              style={{ background: biasColor(p.bias) + "22", color: biasColor(p.bias) }}
            >
              {p.bias}
            </span>
            <p className="text-subtle text-xs mt-0.5">{p.description}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
