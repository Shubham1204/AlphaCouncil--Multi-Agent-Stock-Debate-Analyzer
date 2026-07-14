import type { Verdict } from "./types";

export function verdictColor(v?: string): { bg: string; text: string; ring: string } {
  switch (v) {
    case "Strong Buy":
      return { bg: "#dcfce7", text: "#15803d", ring: "#22c55e" };
    case "Buy":
      return { bg: "#ecfdf5", text: "#16a34a", ring: "#4ade80" };
    case "Hold":
      return { bg: "#fef9c3", text: "#a16207", ring: "#eab308" };
    case "Sell":
      return { bg: "#ffedd5", text: "#c2410c", ring: "#f97316" };
    case "Strong Sell":
      return { bg: "#fee2e2", text: "#b91c1c", ring: "#ef4444" };
    default:
      return { bg: "#f1f5f9", text: "#475569", ring: "#cbd5e1" };
  }
}

export function biasColor(bias: string): string {
  if (bias === "bullish") return "#16a34a";
  if (bias === "bearish") return "#dc2626";
  return "#a16207";
}

export function fmtMoney(symbol: string, v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${symbol}${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function fmtLargeNum(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e12) return (v / 1e12).toFixed(2) + "T";
  if (abs >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (abs >= 1e6) return (v / 1e6).toFixed(2) + "M";
  return v.toLocaleString();
}

export const PHASE_LABELS: Record<string, string> = {
  analysis: "Independent Analysis",
  debate_1: "Debate Round 1",
  debate_2: "Debate Round 2",
  debate_3: "Debate Round 3",
  consensus: "Final Consensus",
};
