export type Verdict =
  | "Strong Buy"
  | "Buy"
  | "Hold"
  | "Sell"
  | "Strong Sell";

export type Profile = "long_term" | "short_term";

export interface AgentMeta {
  id: string;
  name: string;
  emoji: string;
  color: string;
  tagline: string;
  selectable: boolean;
  defaultSelected: boolean;
}

export interface Evidence {
  claim: string;
  source: string;
  url: string;
}

export interface Currency {
  code: string;
  symbol: string;
  exchange: string;
}

export interface Candle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Pattern {
  type: string;
  name: string;
  bias: "bullish" | "bearish" | "neutral";
  description: string;
  points: { index: number; date: string; price: number }[];
  neckline?: number;
}

export interface Technicals {
  candles: Candle[];
  dates: string[];
  series: Record<string, (number | null)[]>;
  levels: { support: number | null; resistance: number | null };
  latest: Record<string, number | string | null>;
  signals: { name: string; reading: string; signal: string; note: string }[];
  patterns: Pattern[];
}

export interface StockBundle {
  ticker: string;
  input: string;
  source: string;
  currency: Currency;
  price: {
    last: number;
    dayChange: number;
    dayChangePct: number;
    week52High: number;
    week52Low: number;
    annualizedVolatilityPct: number;
  };
  fundamentals: Record<string, any>;
  corporateActions: { type: string; date: string; detail: string; value: number | null }[];
  technicals: Technicals;
}

export interface NewsItem {
  title: string;
  source: string;
  url: string;
  publishedAt: string;
  snippet: string;
  category: string;
}

export interface AgentPosition {
  agent: string;
  name: string;
  emoji: string;
  color: string;
  verdict: Verdict;
  conviction: number;
  summary: string;
  bullish: string[];
  bearish: string[];
  evidence: Evidence[];
  priceTarget: number | null;
  stopLoss: number | null;
}

export interface Consensus {
  verdict: Verdict;
  confidence: number;
  profile: Profile;
  moderatorSummary: string;
  bullish: string[];
  bearish: string[];
  evidence: Evidence[];
  priceTarget: number | null;
  stopLoss: number | null;
  weightedScore: number;
  agentSummaries: AgentPosition[];
}

export interface DebateMessage {
  id: string;
  agent: string;
  name: string;
  emoji: string;
  color: string;
  phase: string;
  streaming: boolean;
  text: string;
  parsed?: AgentPosition;
}
