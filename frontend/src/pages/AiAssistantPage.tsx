import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ChatMessageDto, Currency } from "../types";

const GOAL_PRESETS = ["Long-term investing", "A big purchase", "Building a cash reserve"];

export function AiAssistantPage({ currency }: { currency: Currency }) {
  const [goal, setGoal] = useState<string | null>(null);
  const [customGoal, setCustomGoal] = useState("");
  const [messages, setMessages] = useState<ChatMessageDto[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notConfigured, setNotConfigured] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  async function send(nextMessages: ChatMessageDto[], nextGoal: string) {
    setLoading(true);
    setError(null);
    try {
      const res = await api.assistantChat(currency, nextGoal, nextMessages);
      setMessages([...nextMessages, { role: "assistant", content: res.reply }]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setNotConfigured(err.message);
      } else {
        setError(err instanceof ApiError ? err.message : "Something went wrong");
      }
    } finally {
      setLoading(false);
    }
  }

  function startWithGoal(chosenGoal: string) {
    setGoal(chosenGoal);
    const opening: ChatMessageDto = { role: "user", content: `My goal: ${chosenGoal}.` };
    setMessages([opening]);
    send([opening], chosenGoal);
  }

  function handleSend() {
    if (!input.trim() || goal === null) return;
    const next: ChatMessageDto[] = [...messages, { role: "user", content: input.trim() }];
    setInput("");
    setMessages(next);
    send(next, goal);
  }

  function reset() {
    setGoal(null);
    setCustomGoal("");
    setMessages([]);
    setError(null);
    setNotConfigured(null);
  }

  return (
    <div className="card">
      <p className="card-title">AI Assistant</p>
      <p className="stat-sub">
        Chat about your portfolio and what to do next. It reads a snapshot of your current
        numbers — nothing is written or changed. General, educational information only, not
        financial advice: it has no access to live prices or rates, so verify anything specific
        before acting on it.
      </p>

      {notConfigured && (
        <div className="warning-list" style={{ marginTop: 12 }}>
          <strong>The AI Assistant isn't enabled.</strong>
          <p style={{ margin: "6px 0 0" }}>{notConfigured}</p>
        </div>
      )}

      {goal === null ? (
        <div style={{ marginTop: 16 }}>
          <p className="stat-sub">What's your goal?</p>
          <div className="form-row" style={{ marginTop: 8 }}>
            {GOAL_PRESETS.map((g) => (
              <button key={g} className="secondary" onClick={() => startWithGoal(g)}>
                {g}
              </button>
            ))}
          </div>
          <div className="form-row">
            <input
              placeholder="Or describe it in your own words…"
              value={customGoal}
              onChange={(e) => setCustomGoal(e.target.value)}
              style={{ minWidth: 260 }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && customGoal.trim()) startWithGoal(customGoal.trim());
              }}
            />
            <button
              className="primary"
              disabled={!customGoal.trim()}
              onClick={() => startWithGoal(customGoal.trim())}
            >
              Start
            </button>
          </div>
        </div>
      ) : (
        <div style={{ marginTop: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span className="stat-sub" style={{ margin: 0 }}>
              Goal: {goal}
            </span>
            <button
              className="secondary"
              style={{ padding: "4px 10px", fontSize: 12 }}
              onClick={reset}
            >
              Change goal
            </button>
          </div>

          <div className="chat-log" ref={logRef}>
            {messages.map((m, i) => (
              <div key={i} className={`chat-bubble chat-bubble-${m.role}`}>
                {m.content}
              </div>
            ))}
            {loading && <div className="chat-bubble chat-bubble-assistant">…</div>}
          </div>

          {error && <div className="warning-list">{error}</div>}

          <div className="chat-input-row">
            <textarea
              rows={2}
              value={input}
              placeholder="Ask a follow-up…"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
            />
            <button className="primary" disabled={loading || !input.trim()} onClick={handleSend}>
              Send
            </button>
          </div>
          <p className="chat-disclaimer">
            AI-generated, general information only — not financial advice. Verify anything
            specific (prices, rates, tax rules) independently.
          </p>
        </div>
      )}
    </div>
  );
}
