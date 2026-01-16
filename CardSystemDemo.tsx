/**
 * WS2 — Card Component System (Sprint 1)
 *
 * What this file gives you:
 * - A calm, reusable card UI + mini state model that ingests JSON card events.
 * - No duplicates: same card_id updates in-place (no duplicate renders).
 * - Actions: Copy / Mark Used (toggle) / Dismiss (hide).
 * - Calm list rules: max visible cards + stable ordering (no reflow spikes).
 * - Lock window: when enabled, incoming updates are buffered and applied every N seconds,
 *   with a visible countdown: “Updates in Xs…”
 *
 * How to demo:
 * - Render <CardSystemDemoPage /> anywhere (e.g. App.tsx)
 * - Click “Start Demo” to simulate a stream of events (including repeats)
 * - Verify behavior: no duplicates, Used toggles, Dismiss hides, Lock buffers updates.
 *
 * Integration:
 * - Emmanuel/Amanuel can call ingestEvent(event) from the real stream.
 */

import React from "react";

/** -----------------------------
 * Types
 * ------------------------------*/

export type CardType =
  | "Objection"
  | "Next-Best-Question"
  | "Summary"
  | "Risk"
  | "CTA"
  | string;

export type CardEvent = {
  card_id?: string; // unique key
  type?: CardType;
  title?: string;
  body?: string; // 1–4 lines
  bullets?: string[];
  confidence?: number; // 0..1
  priority?: number; // higher = more important (adjust if your team uses rank differently)
  timestamp_ms?: number;
  source?: any;
};

export type CardModel = {
  card_id: string;
  type: CardType;
  title: string;
  body: string;
  bullets?: string[];
  confidence?: number;
  priority?: number;
  timestamp_ms: number;

  // UI state owned by user interactions
  used: boolean;
  dismissed: boolean;

  // bookkeeping
  first_seen_ms: number;
  last_updated_ms: number;
};

/** -----------------------------
 * State + Actions
 * ------------------------------*/

type CardState = {
  // Map for fast dedupe + update-in-place
  byId: Record<string, CardModel>;

  // Stable ordering list of ids.
  // IMPORTANT: We insert new cards at the front but DO NOT reorder on updates.
  // That “no reorder on update” is a big part of calmness/no-flicker.
  order: string[];

  // UI rule: only show top N visible cards
  maxVisible: number;

  // Lock window: buffer updates and apply every lockEveryMs
  lockOn: boolean;
  lockEveryMs: number;
  nextApplyAtMs: number | null;

  // Latest pending event per card_id (latest wins)
  bufferedEvents: Record<string, CardEvent>;
};

type Action =
  | { type: "INGEST_EVENT"; event: CardEvent; now: number }
  | { type: "INGEST_EVENTS"; events: CardEvent[]; now: number }
  | { type: "TOGGLE_USED"; cardId: string; now: number }
  | { type: "DISMISS"; cardId: string; now: number }
  | { type: "SET_MAX_VISIBLE"; maxVisible: number }
  | { type: "SET_LOCK"; lockOn: boolean; lockEveryMs: number; now: number }
  | { type: "APPLY_BUFFER"; now: number }
  | { type: "CLEAR_ALL" };

const initialState: CardState = {
  byId: {},
  order: [],
  maxVisible: 4,

  lockOn: false,
  lockEveryMs: 3000,
  nextApplyAtMs: null,

  bufferedEvents: {},
};

/** -----------------------------
 * Helpers (safe rendering + dedupe)
 * ------------------------------*/

/**
 * Returns a safe id or null (if missing/empty).
 * If card_id is missing, we ignore the event (safe behavior).
 */
function safeId(e: CardEvent): string | null {
  const id = e.card_id?.trim();
  return id && id.length > 0 ? id : null;
}

/** Clamp numbers into [0,1] for confidence. */
function clamp01(x: number): number {
  if (Number.isNaN(x)) return 0;
  return Math.max(0, Math.min(1, x));
}

/**
 * Create a new card model from an event, with safe defaults
 * so missing fields never crash rendering.
 */
function normalizeEvent(e: CardEvent, now: number): CardModel | null {
  const id = safeId(e);
  if (!id) return null;

  return {
    card_id: id,
    type: e.type ?? "CTA",
    title: e.title ?? "Untitled",
    body: e.body ?? "",
    bullets: e.bullets,
    confidence: typeof e.confidence === "number" ? clamp01(e.confidence) : undefined,
    priority: typeof e.priority === "number" ? e.priority : undefined,
    timestamp_ms: typeof e.timestamp_ms === "number" ? e.timestamp_ms : now,

    used: false,
    dismissed: false,

    first_seen_ms: now,
    last_updated_ms: now,
  };
}

/**
 * Merge updates into an existing card WITHOUT overriding user actions.
 * This prevents “Used” being cleared when a new event arrives.
 */
function mergeCard(prev: CardModel, e: CardEvent, now: number): CardModel {
  return {
    ...prev,
    type: e.type ?? prev.type,
    title: e.title ?? prev.title,
    body: e.body ?? prev.body,
    bullets: e.bullets ?? prev.bullets,
    confidence:
      typeof e.confidence === "number" ? clamp01(e.confidence) : prev.confidence,
    priority: typeof e.priority === "number" ? e.priority : prev.priority,
    timestamp_ms:
      typeof e.timestamp_ms === "number" ? e.timestamp_ms : prev.timestamp_ms,
    last_updated_ms: now,
  };
}

/**
 * Core ingestion: dedupe by card_id.
 * - New card: insert at front of order list.
 * - Existing card: update in place, DO NOT reorder (calmer).
 */
function ingestImmediately(state: CardState, events: CardEvent[], now: number): CardState {
  let byId = state.byId;
  let order = state.order;

  for (const e of events) {
    const id = safeId(e);
    if (!id) continue;

    const existing = byId[id];
    if (!existing) {
      const model = normalizeEvent(e, now);
      if (!model) continue;

      byId = { ...byId, [id]: model };

      // Insert at the front. Also ensure uniqueness in order.
      order = [id, ...order.filter((x) => x !== id)];
    } else {
      byId = { ...byId, [id]: mergeCard(existing, e, now) };
      // IMPORTANT: keep order stable on update (no card jumping).
    }
  }

  return { ...state, byId, order };
}

/**
 * Visible cards selector (calm UI).
 * Default sort policy:
 * 1) not dismissed
 * 2) unused first
 * 3) higher priority first
 * 4) newer timestamp first
 */
function selectVisible(state: CardState): CardModel[] {
  const cards = state.order
    .map((id) => state.byId[id])
    .filter(Boolean)
    .filter((c) => !c.dismissed);

  cards.sort((a, b) => {
    if (a.used !== b.used) return a.used ? 1 : -1;

    const ap = a.priority ?? 0;
    const bp = b.priority ?? 0;
    if (ap !== bp) return bp - ap;

    return (b.timestamp_ms ?? 0) - (a.timestamp_ms ?? 0);
  });

  return cards.slice(0, state.maxVisible);
}

/** Build copy text. */
function buildCopyText(c: CardModel): string {
  const lines: string[] = [];
  if (c.title) lines.push(c.title);
  if (c.body) lines.push(c.body);
  if (c.bullets?.length) {
    for (const b of c.bullets) lines.push(`• ${b}`);
  }
  return lines.join("\n").trim();
}

/** -----------------------------
 * Reducer
 * ------------------------------*/

function reducer(state: CardState, action: Action): CardState {
  switch (action.type) {
    case "CLEAR_ALL":
      // keep current config (maxVisible/lock settings) but clear cards
      return {
        ...state,
        byId: {},
        order: [],
        bufferedEvents: {},
        nextApplyAtMs: state.lockOn ? Date.now() + state.lockEveryMs : null,
      };

    case "SET_MAX_VISIBLE":
      return { ...state, maxVisible: Math.max(1, Math.min(8, action.maxVisible)) };

    case "SET_LOCK": {
      const nextApplyAtMs = action.lockOn ? action.now + action.lockEveryMs : null;
      return {
        ...state,
        lockOn: action.lockOn,
        lockEveryMs: action.lockEveryMs,
        nextApplyAtMs,
        bufferedEvents: action.lockOn ? state.bufferedEvents : {},
      };
    }

    case "INGEST_EVENT": {
      const e = action.event;

      // If locked, buffer updates by card_id so the latest wins
      if (state.lockOn) {
        const id = safeId(e);
        if (!id) return state;
        return {
          ...state,
          bufferedEvents: { ...state.bufferedEvents, [id]: e },
        };
      }

      // If unlocked, apply immediately
      return ingestImmediately(state, [e], action.now);
    }

    case "INGEST_EVENTS": {
      if (state.lockOn) {
        const next = { ...state.bufferedEvents };
        for (const e of action.events) {
          const id = safeId(e);
          if (id) next[id] = e;
        }
        return { ...state, bufferedEvents: next };
      }

      return ingestImmediately(state, action.events, action.now);
    }

    case "APPLY_BUFFER": {
      if (!state.lockOn) return state;

      const buffered = Object.values(state.bufferedEvents);
      const cleared: CardState = {
        ...state,
        bufferedEvents: {},
        nextApplyAtMs: action.now + state.lockEveryMs,
      };

      return ingestImmediately(cleared, buffered, action.now);
    }

    case "TOGGLE_USED": {
      const c = state.byId[action.cardId];
      if (!c || c.dismissed) return state;
      return {
        ...state,
        byId: {
          ...state.byId,
          [action.cardId]: { ...c, used: !c.used, last_updated_ms: action.now },
        },
      };
    }

    case "DISMISS": {
      const c = state.byId[action.cardId];
      if (!c || c.dismissed) return state;
      return {
        ...state,
        byId: {
          ...state.byId,
          [action.cardId]: { ...c, dismissed: true, last_updated_ms: action.now },
        },
      };
    }

    default:
      return state;
  }
}

/** -----------------------------
 * Hook: useCardSystem
 * - Provides ingestion API + state and visible selection
 * - Runs lock window ticker
 * ------------------------------*/

export function useCardSystem(options?: { maxVisible?: number; lockEveryMs?: number }) {
  const [state, dispatch] = React.useReducer(reducer, {
    ...initialState,
    maxVisible: options?.maxVisible ?? initialState.maxVisible,
    lockEveryMs: options?.lockEveryMs ?? initialState.lockEveryMs,
  });

  // Lock ticker: checks whether the buffer should be applied.
  React.useEffect(() => {
    if (!state.lockOn || !state.nextApplyAtMs) return;

    const id = window.setInterval(() => {
      const now = Date.now();
      if (state.nextApplyAtMs && now >= state.nextApplyAtMs) {
        dispatch({ type: "APPLY_BUFFER", now });
      }
    }, 150);

    return () => window.clearInterval(id);
  }, [state.lockOn, state.nextApplyAtMs, state.lockEveryMs]);

  const visible = React.useMemo(() => selectVisible(state), [state]);

  // Ingestion API — what the stream wiring will call
  const ingestEvent = React.useCallback((event: CardEvent) => {
    dispatch({ type: "INGEST_EVENT", event, now: Date.now() });
  }, []);

  const ingestEvents = React.useCallback((events: CardEvent[]) => {
    dispatch({ type: "INGEST_EVENTS", events, now: Date.now() });
  }, []);

  // UI actions
  const toggleUsed = React.useCallback((cardId: string) => {
    dispatch({ type: "TOGGLE_USED", cardId, now: Date.now() });
  }, []);

  const dismiss = React.useCallback((cardId: string) => {
    dispatch({ type: "DISMISS", cardId, now: Date.now() });
  }, []);

  const setLock = React.useCallback((lockOn: boolean, lockEveryMs: number) => {
    dispatch({ type: "SET_LOCK", lockOn, lockEveryMs, now: Date.now() });
  }, []);

  const setMaxVisible = React.useCallback((maxVisible: number) => {
    dispatch({ type: "SET_MAX_VISIBLE", maxVisible });
  }, []);

  const clearAll = React.useCallback(() => {
    dispatch({ type: "CLEAR_ALL" });
  }, []);

  return {
    state,
    visible,
    ingestEvent,
    ingestEvents,
    toggleUsed,
    dismiss,
    setLock,
    setMaxVisible,
    clearAll,
  };
}

/** -----------------------------
 * UI components
 * ------------------------------*/

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        fontSize: 12,
        padding: "2px 8px",
        borderRadius: 999,
        border: "1px solid rgba(255,255,255,0.15)",
        opacity: 0.9,
      }}
    >
      {children}
    </span>
  );
}

/**
 * Displays the lock countdown:
 * "Updates in Xs…"
 *
 * NOTE: It re-renders based on Date.now() at render time,
 * so it will update whenever parent renders (which happens
 * frequently due to the lock interval).
 */
function LockBanner({
  lockOn,
  nextApplyAtMs,
}: {
  lockOn: boolean;
  nextApplyAtMs: number | null;
}) {
  if (!lockOn || !nextApplyAtMs) return null;
  const remainingMs = Math.max(0, nextApplyAtMs - Date.now());
  const secs = Math.ceil(remainingMs / 1000);
  return <div style={{ fontSize: 12, opacity: 0.7 }}>Updates in {secs}s…</div>;
}

/**
 * Single Card UI.
 * - Copy copies suggested text (title + body + bullets)
 * - Used toggles a visual state
 * - Dismiss hides it from view (but remains in state)
 */
function CardItem({
  card,
  onCopy,
  onToggleUsed,
  onDismiss,
}: {
  card: CardModel;
  onCopy: (c: CardModel) => void;
  onToggleUsed: (id: string) => void;
  onDismiss: (id: string) => void;
}) {
  const usedStyle = card.used
    ? { opacity: 0.65, borderColor: "rgba(60,255,180,0.35)" }
    : {};

  return (
    <div
      style={{
        border: "1px solid rgba(255,255,255,0.15)",
        borderRadius: 14,
        padding: 12,
        background: "rgba(255,255,255,0.06)",
        boxShadow: "0 6px 18px rgba(0,0,0,0.18)",
        ...usedStyle,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <Badge>{card.type}</Badge>

          {typeof card.confidence === "number" && (
            <span style={{ fontSize: 12, opacity: 0.75 }}>
              Conf: {(card.confidence * 100).toFixed(0)}%
            </span>
          )}

          {typeof card.priority === "number" && (
            <span style={{ fontSize: 12, opacity: 0.75 }}>P: {card.priority}</span>
          )}

          {card.used && <Badge>Used</Badge>}
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button style={btnStyle} onClick={() => onCopy(card)}>
            Copy
          </button>
          <button style={btnStyle} onClick={() => onToggleUsed(card.card_id)}>
            {card.used ? "Unuse" : "Used"}
          </button>
          <button
            style={{ ...btnStyle, opacity: 0.85 }}
            onClick={() => onDismiss(card.card_id)}
          >
            Dismiss
          </button>
        </div>
      </div>

      <div style={{ marginTop: 10 }}>
        <div style={{ fontWeight: 650, fontSize: 14, lineHeight: 1.25 }}>
          {card.title}
        </div>

        {card.body ? (
          <div style={{ marginTop: 6, fontSize: 13, opacity: 0.9, lineHeight: 1.3 }}>
            {card.body}
          </div>
        ) : null}

        {card.bullets?.length ? (
          <ul style={{ marginTop: 8, marginBottom: 0, paddingLeft: 18, opacity: 0.9 }}>
            {card.bullets.slice(0, 6).map((b, idx) => (
              <li key={idx} style={{ fontSize: 13, lineHeight: 1.25, marginTop: 4 }}>
                {b}
              </li>
            ))}
          </ul>
        ) : null}

        <div style={{ marginTop: 10, fontSize: 11, opacity: 0.6 }}>
          id: {card.card_id} • updated: {new Date(card.last_updated_ms).toLocaleTimeString()}
        </div>
      </div>
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  fontSize: 12,
  padding: "6px 10px",
  borderRadius: 10,
  border: "1px solid rgba(255,255,255,0.15)",
  background: "rgba(255,255,255,0.08)",
  color: "white",
  cursor: "pointer",
};

/** -----------------------------
 * CardListOverlay (the component you ship for WS2)
 * - In Sprint 1 it includes demo controls.
 * - In real integration, you’d remove demo buttons and call ingestEvent from the stream.
 * ------------------------------*/

export function CardListOverlay({
  maxVisible = 4,
  lockEveryMs = 3000,
}: {
  maxVisible?: number;
  lockEveryMs?: number;
}) {
  const {
    state,
    visible,
    ingestEvent,
    toggleUsed,
    dismiss,
    setLock,
    setMaxVisible,
    clearAll,
  } = useCardSystem({ maxVisible, lockEveryMs });

  // Simple toast for copy success
  const [toast, setToast] = React.useState<string | null>(null);

  const handleCopy = React.useCallback(async (c: CardModel) => {
    const text = buildCopyText(c);
    try {
      await navigator.clipboard.writeText(text);
      setToast("Copied!");
      window.setTimeout(() => setToast(null), 900);
    } catch {
      setToast("Copy failed (clipboard blocked).");
      window.setTimeout(() => setToast(null), 1200);
    }
  }, []);

  // DEMO STREAM: mock event generator (you can remove later)
  const [demoOn, setDemoOn] = React.useState(false);

  React.useEffect(() => {
    if (!demoOn) return;

    const interval = window.setInterval(() => {
      const e = makeRandomDemoEvent();
      ingestEvent(e);

      // intentionally re-send same id sometimes to prove: update-in-place, not duplicate
      if (Math.random() < 0.35) {
        const e2: CardEvent = {
          ...e,
          title: (e.title ?? "Untitled") + " (updated)",
          body: (e.body ?? "") + " — new detail",
          confidence: Math.random(),
          timestamp_ms: Date.now(),
        };
        ingestEvent(e2);
      }
    }, 900);

    return () => window.clearInterval(interval);
  }, [demoOn, ingestEvent]);

  return (
    <div
      style={{
        width: 420,
        fontFamily:
          '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
        color: "white",
      }}
    >
      {/* Header controls */}
      <div
        style={{
          padding: 12,
          borderRadius: 14,
          border: "1px solid rgba(255,255,255,0.15)",
          background: "rgba(0,0,0,0.35)",
          marginBottom: 10,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 10,
        }}
      >
        <div>
          <div style={{ fontWeight: 700 }}>Battle Cards</div>
          <LockBanner lockOn={state.lockOn} nextApplyAtMs={state.nextApplyAtMs} />
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ fontSize: 12, opacity: 0.85 }}>
            Max
            <input
              type="number"
              value={state.maxVisible}
              min={1}
              max={8}
              onChange={(e) => setMaxVisible(Number(e.target.value))}
              style={{
                marginLeft: 6,
                width: 54,
                padding: "4px 6px",
                borderRadius: 8,
                border: "1px solid rgba(255,255,255,0.15)",
                background: "rgba(255,255,255,0.08)",
                color: "white",
              }}
            />
          </label>

          <button
            style={btnStyle}
            onClick={() => setLock(!state.lockOn, state.lockEveryMs)}
            title="Lock window buffers updates"
          >
            {state.lockOn ? "Unlock" : "Lock"}
          </button>

          <button style={btnStyle} onClick={clearAll}>
            Clear
          </button>
        </div>
      </div>

      {/* Demo buttons */}
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <button style={btnStyle} onClick={() => ingestEvent(makeSampleEvent())}>
          Inject Sample
        </button>
        <button style={btnStyle} onClick={() => setDemoOn((v) => !v)}>
          {demoOn ? "Stop Demo" : "Start Demo"}
        </button>
      </div>

      {/* Toast */}
      {toast ? (
        <div
          style={{
            fontSize: 12,
            marginBottom: 10,
            padding: "6px 10px",
            borderRadius: 10,
            border: "1px solid rgba(255,255,255,0.15)",
            background: "rgba(255,255,255,0.08)",
            display: "inline-block",
          }}
        >
          {toast}
        </div>
      ) : null}

      {/* List */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {visible.length === 0 ? (
          <div style={{ fontSize: 13, opacity: 0.7, padding: 12 }}>
            No cards yet. Inject sample or start demo.
          </div>
        ) : (
          visible.map((c) => (
            <CardItem
              key={c.card_id} // stable key prevents duplicate/flicker
              card={c}
              onCopy={handleCopy}
              onToggleUsed={toggleUsed}
              onDismiss={dismiss}
            />
          ))
        )}
      </div>
    </div>
  );
}

/** -----------------------------
 * Demo helpers (mock simulator)
 * - You can delete these when real stream wiring exists.
 * ------------------------------*/

function makeSampleEvent(): CardEvent {
  return {
    card_id: "card-001",
    type: "Objection",
    title: "Handle pricing concern",
    body: "Try: “Totally fair — can I ask what you’re comparing us to?”",
    bullets: ["Anchor value", "Ask budget range", "Offer 2 options"],
    confidence: 0.78,
    priority: 5,
    timestamp_ms: Date.now(),
  };
}

function makeRandomDemoEvent(): CardEvent {
  const types: CardType[] = ["Objection", "Next-Best-Question", "Summary", "Risk", "CTA"];
  const t = types[Math.floor(Math.random() * types.length)];
  const id = `card-${String(Math.floor(Math.random() * 6) + 1).padStart(3, "0")}`; // repeats intentionally
  const now = Date.now();

  const titles: Record<string, string[]> = {
    Objection: ["Price pushback", "Not interested", "Need to think", "Already have a vendor"],
    "Next-Best-Question": ["Clarify goals", "Confirm decision process", "Uncover timeline"],
    Summary: ["Quick recap", "What they said", "Key needs summary"],
    Risk: ["Risk: unclear champion", "Risk: timeline mismatch", "Risk: missing pain"],
    CTA: ["Suggest next step", "Ask for meeting", "Propose trial"],
  };

  const pool = titles[t] ?? ["New card"];
  const title = pool[Math.floor(Math.random() * pool.length)];

  return {
    card_id: id,
    type: t,
    title,
    body:
      t === "Summary"
        ? "User mentioned speed, reliability, and easy onboarding."
        : "Suggested line you can use right now.",
    bullets: Math.random() < 0.5 ? ["Keep it short", "Ask one question", "Confirm next step"] : undefined,
    confidence: Math.random(),
    priority: Math.floor(Math.random() * 6), // 0..5
    timestamp_ms: now,
  };
}

/** -----------------------------
 * Demo page you can render in App.tsx
 * ------------------------------*/

export default function CardSystemDemoPage() {
  return (
    <div
      style={{
        minHeight: "100vh",
        padding: 24,
        background:
          "radial-gradient(1200px 700px at 30% 20%, rgba(80,120,255,0.22), transparent 60%), radial-gradient(900px 600px at 70% 80%, rgba(60,255,180,0.12), transparent 55%), #0b0f1a",
      }}
    >
      <div style={{ maxWidth: 900, margin: "0 auto", display: "flex", gap: 24 }}>
        <div style={{ flex: "0 0 auto" }}>
          <CardListOverlay maxVisible={4} lockEveryMs={3000} />
        </div>

        <div style={{ maxWidth: 420, opacity: 0.85 }}>
          <h2 style={{ margin: 0, marginBottom: 10 }}>How to verify it works</h2>
          <ol style={{ marginTop: 0, lineHeight: 1.6 }}>
            <li>Click <b>Start Demo</b> (cards stream in)</li>
            <li>Notice repeating ids like <code>card-002</code> update (no duplicates)</li>
            <li>Click <b>Used</b> → card fades and badge appears (not removed)</li>
            <li>Click <b>Dismiss</b> → card disappears (kept in state as dismissed)</li>
            <li>Click <b>Lock</b> → “Updates in Xs…” appears</li>
            <li>While locked, updates buffer and apply every ~3 seconds</li>
          </ol>

          <div style={{ fontSize: 13, opacity: 0.9 }}>
            Integration: call <code>ingestEvent(cardEvent)</code> from the real stream.
          </div>
        </div>
      </div>
    </div>
  );
}
