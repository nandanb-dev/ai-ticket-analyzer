"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

const TICKET_KEY_RE = /\b([A-Z][A-Z0-9]+-\d+)\b/;
const JIRA_URL_RE = /atlassian\.net\/browse\/([A-Z][A-Z0-9]+-\d+)/i;
const PROJECT_KEY_RE = /\bproject[:\s]+([A-Z][A-Z0-9]+)\b/i;
const EPIC_KEYWORD_RE = /\bepic[:\s]+([A-Z][A-Z0-9]+-\d+)\b/i;
const ANALYZE_INTENT_RE = /\b(analyz[e]?|review|inspect|check|audit|improve|fix|assess)\b.*\b(ticket|issue|story|task|epic|jira)\b|\b(ticket|issue|story|task|epic|jira)\b.*\b(analyz[e]?|review|inspect|check|audit|improve|fix|assess)\b/i;

function detectAnalyzeIntent(text) {
  const urlMatch = text.match(JIRA_URL_RE);
  if (urlMatch) return { ticket_key: urlMatch[1], context: text.replace(JIRA_URL_RE, "").trim() };

  const epicMatch = text.match(EPIC_KEYWORD_RE);
  if (epicMatch) return { epic_key: epicMatch[1], context: text.replace(EPIC_KEYWORD_RE, "").trim() };

  const projectMatch = text.match(PROJECT_KEY_RE);
  if (projectMatch) return { project_key: projectMatch[1], context: text.replace(PROJECT_KEY_RE, "").trim() };

  const ticketMatch = text.match(TICKET_KEY_RE);
  if (ticketMatch) return { ticket_key: ticketMatch[1], context: text.replace(TICKET_KEY_RE, "").trim() };

  return null;
}

function renderContent(content) {
  return content.split("\n").map((line, i) => {
    if (line.startsWith("- ")) {
      const text = line.slice(2);
      return text.length <= 40
        ? <div key={i} className="msg-bullet">{text}</div>
        : <div key={i} className="msg-list-item">{text}</div>;
    }
    if (line.trim() === "") return <br key={i} />;
    return <p key={i}>{line}</p>;
  });
}

function MessageBubble({ role, content }) {
  return (
    <article className={`message-card ${role === "assistant" ? "assistant" : "user"}`}>
      <span className="message-role">{role}</span>
      <div className="msg-body">
        {role === "assistant" ? renderContent(content) : <p>{content}</p>}
      </div>
    </article>
  );
}

function SummarySection({ title, items, emptyLabel }) {
  return (
    <section className="summary-section">
      <div className="summary-heading-row">
        <h4>{title}</h4>
        <span>{items.length}</span>
      </div>
      {items.length ? (
        <div className="summary-list">
          {items.map((item, index) => (
            <div className="summary-card" key={`${title}-${index}-${item.summary}`}>
              <strong>{item.summary}</strong>
              {item.priority ? <span>{item.priority}</span> : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted-copy">{emptyLabel}</p>
      )}
    </section>
  );
}

function AnalysisCard({ ticket, sessionId, onApplied }) {
  const [cardState, setCardState] = useState("idle");
  const [error, setError] = useState("");

  const issues = ticket.issues_found || [];
  const updates = ticket.suggested_updates || {};
  const score = ticket.quality_score;

  async function handleApply() {
    setCardState("applying");
    setError("");
    try {
      const res = await fetch(`${API_BASE_URL}/analyze-tickets/${sessionId}/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket_keys: [ticket.key] }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Apply failed.");
      setCardState("applied");
      onApplied(ticket.key, data);
    } catch (e) {
      setError(e.message);
      setCardState("approved");
    }
  }

  return (
    <div className={`analysis-card ${cardState}`}>
      <div className="analysis-card-header">
        <div className="analysis-card-title">
          <span className="analysis-key">{ticket.key}</span>
          {ticket.issue_type && <span className="analysis-type">{ticket.issue_type}</span>}
        </div>
        <span className={`score-badge score-${score >= 8 ? "good" : score >= 5 ? "mid" : "bad"}`}>{score}/10</span>
      </div>
      <p className="analysis-summary">{ticket.current_summary}</p>

      {issues.length > 0 && (
        <div className="issues-list">
          {issues.map((issue, i) => (
            <div key={i} className={`issue-chip sev-${issue.severity}`}>
              <span className="issue-sev">{issue.severity}</span>
              <span className="issue-desc">{issue.description}</span>
            </div>
          ))}
        </div>
      )}

      {Object.keys(updates).length > 0 && cardState !== "applied" && (
        <div className="analysis-card-actions">
          {cardState === "idle" && (
            <button className="approve-btn" onClick={() => setCardState("approved")}>✓ Approve</button>
          )}
          {cardState === "approved" && (
            <>
              <button className="apply-btn" onClick={handleApply}>Apply to JIRA →</button>
              <button className="skip-btn" onClick={() => setCardState("idle")}>✗ Cancel</button>
            </>
          )}
          {cardState === "applying" && <span className="muted-copy">Applying…</span>}
        </div>
      )}

      {cardState === "applied" && <p className="applied-label">✓ Applied to JIRA</p>}
      {error && <p className="error-banner">{error}</p>}
    </div>
  );
}

export default function HomePage() {
  const [session, setSession] = useState(null);
  const [analyzeSession, setAnalyzeSession] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const [message, setMessage] = useState("");
  const [files, setFiles] = useState([]);
  const [isSending, setIsSending] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [optimisticMessage, setOptimisticMessage] = useState("");
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);
  const textareaRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    if (session) return;

    async function bootstrap() {
      try {
        const response = await fetch(`${API_BASE_URL}/chat/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_key: "" }),
        });

        if (!response.ok) {
          throw new Error("Failed to create chat session.");
        }

        const data = await response.json();
        setSession(data);
      } catch (nextError) {
        setError(nextError.message);
      }
    }

    bootstrap();
  }, [session]);

  const pendingTickets = useMemo(() => session?.pending_tickets || {}, [session]);

  function pushChatMessage(role, content) {
    setChatMessages((prev) => [...prev, { role, content }]);
  }

  async function handleAnalyze(sentMessage, intent) {
    const source = intent.ticket_key || intent.epic_key || intent.project_key;
    const scopeLabel = intent.ticket_key ? `ticket ${source}` : intent.epic_key ? `epic ${source}` : `project ${source}`;
    pushChatMessage("user", sentMessage);
    pushChatMessage("assistant", `Analyzing ${scopeLabel}… this may take a moment.`);

    try {
      const res = await fetch(`${API_BASE_URL}/analyze-tickets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(intent),
        signal: abortRef.current?.signal,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Analysis failed.");

      setAnalyzeSession(data);
      const a = data.analysis || {};
      const tickets = a.tickets || [];
      const critical = tickets.flatMap((t) => t.issues_found || []).filter((i) => i.severity === "critical").length;
      const major = tickets.flatMap((t) => t.issues_found || []).filter((i) => i.severity === "major").length;
      pushChatMessage(
        "assistant",
        `Analysis complete. Overall score: ${a.overall_score ?? "—"}/10 across ${data.ticket_count} ticket(s).\n- ${critical} critical issue(s)\n- ${major} major issue(s)\n\n${a.analysis_summary || ""}\n\nReview the details in the panel → You can approve and apply changes per ticket, or type feedback below to refine the analysis.`
      );
    } catch (e) {
      if (e.name !== "AbortError") {
        pushChatMessage("assistant", `Analysis failed: ${e.message}`);
        setError(e.message);
      }
    }
  }

  async function handleFeedback(sentMessage) {
    pushChatMessage("user", sentMessage);
    pushChatMessage("assistant", "Refining analysis based on your feedback…");

    try {
      const res = await fetch(`${API_BASE_URL}/analyze-tickets/${analyzeSession.session_id}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback: sentMessage }),
        signal: abortRef.current?.signal,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Feedback failed.");

      setAnalyzeSession((prev) => ({ ...prev, analysis: data.analysis }));
      pushChatMessage("assistant", `Analysis revised (revision ${data.revision}). Review the updated panel →`);
    } catch (e) {
      if (e.name !== "AbortError") {
        pushChatMessage("assistant", `Feedback failed: ${e.message}`);
        setError(e.message);
      }
    }
  }

  function handleApplied(ticketKey) {
    pushChatMessage("assistant", `✓ Applied suggestions to ${ticketKey} in JIRA.`);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!message.trim()) return;
    if (!session?.session_id) return;

    const sentMessage = message.trim();
    setMessage("");
    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    setIsSending(true);
    setError("");

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const intent = detectAnalyzeIntent(sentMessage);

      if (analyzeSession) {
        await handleFeedback(sentMessage);
        return;
      }

      if (intent) {
        await handleAnalyze(sentMessage, intent);
        return;
      }

      if (ANALYZE_INTENT_RE.test(sentMessage)) {
        pushChatMessage("user", sentMessage);
        pushChatMessage("assistant", "Sure! Please share the JIRA ticket key, epic key, or project key you'd like me to analyze (e.g. PROJ-123 or project: SCRUM). You can also paste the full JIRA URL.");
        return;
      }

      setOptimisticMessage(sentMessage);
      const formData = new FormData();
      formData.append("message", sentMessage);
      files.forEach((file) => formData.append("files", file));

      const response = await fetch(`${API_BASE_URL}/chat/sessions/${session.session_id}/messages`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Failed to send message.");
      }

      setSession(data);
    } catch (nextError) {
      if (nextError.name !== "AbortError") setError(nextError.message);
    } finally {
      setOptimisticMessage("");
      setIsSending(false);
      abortRef.current = null;
    }
  }

  function handleStop() {
    abortRef.current?.abort();
  }

  async function handleConfirm() {
    if (!session?.session_id) {
      return;
    }

    setIsConfirming(true);
    setError("");

    try {
      const response = await fetch(`${API_BASE_URL}/chat/sessions/${session.session_id}/confirm`, {
        method: "POST",
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Failed to confirm Jira creation.");
      }

      setSession(data);
    } catch (nextError) {
      setError(nextError.message);
    } finally {
      setIsConfirming(false);
    }
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit(event);
    }
  }

  function handleTextareaInput(event) {
    const el = event.target;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
    setMessage(el.value);
  }

  return (
    <main className="page-shell">
      <section className="hero-band">
        <div className="hero-copy-block">
          <span className="eyebrow">Next.js Chat Workspace</span>
          <h1>Shape product noise into Jira-ready execution through one guided conversation.</h1>
          <p>
            Upload docs, paste notes, keep the discussion grounded in context, preview structured ticket drafts,
            and only create Jira items after human approval.
          </p>
        </div>
      </section>

      <section className="workspace-grid">
        <section className="conversation-panel glass-panel">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Conversation</p>
              <h2>Context-friendly ticket shaping</h2>
            </div>
            <button
              className="confirm-button"
              type="button"
              disabled={!session?.awaiting_confirmation || isConfirming}
              onClick={handleConfirm}
            >
              {isConfirming ? "Creating..." : "Approve and create Jira tickets"}
            </button>
          </div>

          <div className="message-stream">
            {(session?.messages?.length || chatMessages.length || optimisticMessage) ? (
              <>
                {session?.messages?.map((entry, index) => (
                  <MessageBubble key={`session-${index}`} role={entry.role} content={entry.content} />
                ))}
                {chatMessages.map((entry, index) => (
                  <MessageBubble key={`chat-${index}`} role={entry.role} content={entry.content} />
                ))}
                {optimisticMessage && <MessageBubble role="user" content={optimisticMessage} />}
                {isSending && (
                  <article className="message-card assistant">
                    <span className="message-role">assistant</span>
                    <p className="typing-indicator"><span /><span /><span /></p>
                  </article>
                )}
              </>
            ) : (
              <div className="empty-state">
                <strong>Start with intent, documents, or raw notes.</strong>
                <p>Type a message, paste a JIRA key (e.g. PROJ-42) or URL to analyze existing tickets.</p>
              </div>
            )}
          </div>

          <form className="composer-panel" onSubmit={handleSubmit}>
            <div className="composer-bar">
              <button
                type="button"
                className="icon-btn"
                title={files.length ? `${files.length} file(s) ready` : "Attach files"}
                onClick={() => fileInputRef.current?.click()}
              >
                📎{files.length > 0 && <span className="attach-badge">{files.length}</span>}
              </button>

              <input
                ref={fileInputRef}
                type="file"
                multiple
                style={{ display: "none" }}
                onChange={(event) => setFiles(Array.from(event.target.files || []))}
              />

              <textarea
                ref={textareaRef}
                rows={1}
                value={message}
                onInput={handleTextareaInput}
                onKeyDown={handleKeyDown}
                placeholder="Message the assistant… (Enter to send, Shift+Enter for new line)"
              />

              {isSending ? (
                <button className="icon-btn stop-btn" type="button" onClick={handleStop} title="Stop">
                  ⏹
                </button>
              ) : (
                <button className="icon-btn send-icon-btn" type="submit" title="Send">
                  ➤
                </button>
              )}
            </div>

            {error ? <p className="error-banner">{error}</p> : null}
          </form>
        </section>

        <aside className="inspector-column">
          {analyzeSession ? (
            <section className="glass-panel side-panel">
              <div className="panel-header slim">
                <div>
                  <p className="panel-kicker">Analysis</p>
                  <h3>Ticket review</h3>
                </div>
                <button className="skip-btn" onClick={() => setAnalyzeSession(null)} title="Exit analysis mode">✕ Exit</button>
              </div>
              <div className="analysis-list">
                {(analyzeSession.analysis?.tickets || []).map((ticket) => (
                  <AnalysisCard
                    key={ticket.key}
                    ticket={ticket}
                    sessionId={analyzeSession.session_id}
                    onApplied={handleApplied}
                  />
                ))}
                {!(analyzeSession.analysis?.tickets?.length) && (
                  <p className="muted-copy">No tickets in analysis.</p>
                )}
              </div>
            </section>
          ) : (
            <section className="glass-panel side-panel">
              <div className="panel-header slim">
                <div>
                  <p className="panel-kicker">Draft</p>
                  <h3>Pending ticket overview</h3>
                </div>
              </div>
              <SummarySection title="Epics" items={pendingTickets.epics || []} emptyLabel="No epics drafted yet." />
              <SummarySection title="Stories" items={pendingTickets.stories || []} emptyLabel="No stories drafted yet." />
              <SummarySection title="Tasks" items={pendingTickets.tasks || []} emptyLabel="No tasks drafted yet." />
            </section>
          )}

          <section className="glass-panel side-panel">
            <div className="panel-header slim">
              <div>
                <p className="panel-kicker">Context</p>
                <h3>Uploaded material</h3>
              </div>
            </div>

            {session?.attachments?.length ? (
              <div className="summary-list">
                {session.attachments.map((attachment, index) => (
                  <div className="summary-card attachment-card" key={`${attachment.name}-${index}`}>
                    <strong>{attachment.name}</strong>
                    <p>{attachment.preview}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted-copy">No uploaded files yet.</p>
            )}
          </section>

          <section className="glass-panel side-panel">
            <div className="panel-header slim">
              <div>
                <p className="panel-kicker">Result</p>
                <h3>Last Jira creation output</h3>
              </div>
            </div>
            <pre className="result-panel">{session?.last_created ? JSON.stringify(session.last_created, null, 2) : "Nothing created yet."}</pre>
          </section>
        </aside>
      </section>
    </main>
  );
}