import { useCallback, useRef, useState } from "react";
import { API_BASE, WS_BASE } from "./api";
import { getAuthToken } from "./auth";
import type {
  Consensus,
  DebateMessage,
  NewsItem,
  Profile,
  StockBundle,
} from "./types";

interface StartArgs {
  ticker: string;
  profile: Profile;
  agents: string[];
  rounds: number;
}

// Transport options:
//   sse  (default) - live token streaming over SSE. Works locally (Vite proxy)
//                    and on servers that don't buffer (App Runner/ECS).
//   post           - single POST that returns ALL events at once. Use behind
//                    API Gateway, which buffers responses and can't stream.
//                    The UI replays events, so it looks the same but fills in
//                    all at once (no live token-by-token).
//   ws             - WebSocket (server-based backends only).
const TRANSPORT = (import.meta as any).env?.VITE_TRANSPORT || "sse";

export function useDebate() {
  const [running, setRunning] = useState(false);
  const [phase, setPhase] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [stock, setStock] = useState<StockBundle | null>(null);
  const [companyNews, setCompanyNews] = useState<NewsItem[]>([]);
  const [macroNews, setMacroNews] = useState<NewsItem[]>([]);
  const [messages, setMessages] = useState<DebateMessage[]>([]);
  const [consensus, setConsensus] = useState<Consensus | null>(null);
  const [error, setError] = useState<string>("");
  const wsRef = useRef<WebSocket | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const counter = useRef(0);

  const reset = useCallback(() => {
    setPhase("");
    setStatus("");
    setStock(null);
    setCompanyNews([]);
    setMacroNews([]);
    setMessages([]);
    setConsensus(null);
    setError("");
  }, []);

  // Shared event handler for both transports.
  const handle = useCallback((e: any, done: () => void) => {
    switch (e.type) {
      case "status":
        setStatus(e.message);
        break;
      case "phase":
        setPhase(e.phase);
        break;
      case "stock":
        setStock(e.data);
        setCompanyNews(e.companyNews || []);
        setMacroNews(e.macroNews || []);
        break;
      case "agent_start": {
        const id = `${e.agent}-${e.phase}-${counter.current++}`;
        setMessages((m) => [
          ...m,
          {
            id,
            agent: e.agent,
            name: e.name,
            emoji: e.emoji,
            color: e.color,
            phase: e.phase,
            streaming: true,
            text: "",
          },
        ]);
        break;
      }
      case "agent_token":
        setMessages((m) => {
          const copy = [...m];
          for (let i = copy.length - 1; i >= 0; i--) {
            if (copy[i].agent === e.agent && copy[i].streaming) {
              copy[i] = { ...copy[i], text: copy[i].text + e.text };
              break;
            }
          }
          return copy;
        });
        break;
      case "agent_done":
        setMessages((m) => {
          const copy = [...m];
          for (let i = copy.length - 1; i >= 0; i--) {
            if (copy[i].agent === e.agent && copy[i].streaming) {
              copy[i] = {
                ...copy[i],
                streaming: false,
                parsed: {
                  agent: e.agent,
                  name: e.name,
                  emoji: e.emoji,
                  color: e.color,
                  verdict: e.verdict,
                  conviction: e.conviction,
                  summary: e.summary,
                  bullish: e.bullish || [],
                  bearish: e.bearish || [],
                  evidence: e.evidence || [],
                  priceTarget: e.price_target ?? null,
                  stopLoss: e.stop_loss ?? null,
                },
              };
              break;
            }
          }
          return copy;
        });
        break;
      case "consensus":
        setConsensus(e as Consensus);
        break;
      case "complete":
        setRunning(false);
        done();
        break;
      case "error":
        setError(e.message);
        setRunning(false);
        done();
        break;
    }
  }, []);

  const startSse = useCallback(
    async (args: StartArgs) => {
      const params = new URLSearchParams({
        ticker: args.ticker,
        profile: args.profile,
        agents: args.agents.join(","),
        rounds: String(args.rounds),
      });
      // EventSource can't set an Authorization header, so pass the auth token
      // as a query param (the backend accepts ?access_token=). Harmless/no-op
      // when the backend is in no-auth mode.
      const token = await getAuthToken();
      if (token) params.set("access_token", token);
      const es = new EventSource(`${API_BASE}/api/debate/stream?${params}`);
      esRef.current = es;
      const close = () => {
        es.close();
        esRef.current = null;
      };
      es.onmessage = (ev) => {
        try {
          handle(JSON.parse(ev.data), close);
        } catch {
          /* ignore keep-alive/parse noise */
        }
      };
      es.onerror = () => {
        // EventSource fires onerror on normal close too; only surface if we
        // never completed.
        if (esRef.current) {
          setError(
            "Debate stream connection failed. Is the backend reachable?"
          );
          setRunning(false);
          close();
        }
      };
    },
    [handle]
  );

  const startWs = useCallback(
    async (args: StartArgs) => {
      const token = await getAuthToken();
      const ws = new WebSocket(`${WS_BASE}/ws/debate`);
      wsRef.current = ws;
      const close = () => {
        ws.close();
        wsRef.current = null;
      };
      // Browsers can't set WS headers, so include the auth token in the first
      // message (backend reads req.token). No-op in no-auth mode.
      ws.onopen = () => ws.send(JSON.stringify({ ...args, token }));
      ws.onmessage = (ev) => handle(JSON.parse(ev.data), close);
      ws.onerror = () => {
        setError("WebSocket connection failed. Is the backend running on :8000?");
        setRunning(false);
      };
      ws.onclose = () => setRunning(false);
    },
    [handle]
  );

  const startPost = useCallback(
    async (args: StartArgs) => {
      // One POST; backend runs the whole debate and returns all events. We
      // replay them through the same handler so the UI renders identically
      // (just not live token-by-token). Correct for API Gateway (buffered).
      try {
        const token = await getAuthToken();
        const res = await fetch(`${API_BASE}/api/debate`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(args),
        });
        if (!res.ok) {
          setError(
            res.status === 401
              ? "Authentication required (auth token missing or invalid)."
              : `Backend returned ${res.status}.`
          );
          setRunning(false);
          return;
        }
        const data = await res.json();
        const done = () => {};
        for (const e of data.events || []) handle(e, done);
        setRunning(false);
      } catch {
        setError("Could not reach the backend. Check VITE_API_BASE.");
        setRunning(false);
      }
    },
    [handle]
  );

  const start = useCallback(
    (args: StartArgs) => {
      reset();
      setRunning(true);
      if (TRANSPORT === "ws") startWs(args);
      else if (TRANSPORT === "post") startPost(args);
      else startSse(args);
    },
    [reset, startWs, startSse, startPost]
  );

  const stop = useCallback(() => {
    wsRef.current?.close();
    esRef.current?.close();
    esRef.current = null;
    setRunning(false);
  }, []);

  return {
    running,
    phase,
    status,
    stock,
    companyNews,
    macroNews,
    messages,
    consensus,
    error,
    start,
    stop,
  };
}
