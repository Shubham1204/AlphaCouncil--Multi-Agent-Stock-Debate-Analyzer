import jsPDF from "jspdf";
import type { Consensus, StockBundle } from "./types";

/** Lightweight text-based PDF export of the consensus + per-agent summaries. */
export function exportPdf(stock: StockBundle, consensus: Consensus) {
  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const margin = 40;
  const width = doc.internal.pageSize.getWidth() - margin * 2;
  let y = margin;

  const line = (text: string, size = 10, bold = false, color = "#0f172a") => {
    doc.setFontSize(size);
    doc.setFont("helvetica", bold ? "bold" : "normal");
    doc.setTextColor(color);
    const lines = doc.splitTextToSize(text, width);
    for (const l of lines) {
      if (y > doc.internal.pageSize.getHeight() - margin) {
        doc.addPage();
        y = margin;
      }
      doc.text(l, margin, y);
      y += size * 1.4;
    }
  };

  const sym = stock.currency.symbol;
  line("Stock Multi-Agent Debate Analysis", 18, true);
  line(`${stock.fundamentals.name || stock.ticker} (${stock.ticker})  ·  ${stock.currency.exchange} · ${stock.currency.code}`, 11);
  line(`Price: ${sym}${stock.price.last}  ·  Day: ${stock.price.dayChangePct}%`, 10, false, "#64748b");
  y += 8;

  line(`CONSENSUS: ${consensus.verdict}  (Confidence ${consensus.confidence}%)`, 14, true, "#2563eb");
  line(`Profile: ${consensus.profile === "long_term" ? "Long-Term (6mo–5-10yr)" : "Short-Term / Swing (1wk–3-5mo)"}`, 10, false, "#64748b");
  if (consensus.priceTarget != null) line(`Price Target: ${sym}${consensus.priceTarget}`, 10);
  if (consensus.stopLoss != null) line(`Stop-Loss: ${sym}${consensus.stopLoss}`, 10);
  y += 4;
  line(consensus.moderatorSummary || "", 10);
  y += 6;

  line("Key Bullish Points", 12, true, "#16a34a");
  consensus.bullish.forEach((b) => line(`• ${b}`, 10));
  y += 4;
  line("Key Bearish Points", 12, true, "#dc2626");
  consensus.bearish.forEach((b) => line(`• ${b}`, 10));
  y += 8;

  line("Per-Agent Debate Summary", 13, true);
  consensus.agentSummaries.forEach((a) => {
    y += 4;
    line(`${a.name} — ${a.verdict} (${a.conviction}/10)`, 11, true);
    line(a.summary || "", 10);
    a.evidence.forEach((e) => line(`  - ${e.claim}${e.url ? ` (${e.url})` : ""}`, 9, false, "#64748b"));
  });

  y += 10;
  line("Not financial advice. For educational purposes only.", 9, false, "#94a3b8");

  doc.save(`${stock.ticker}-debate-analysis.pdf`);
}
