"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { detectAnalyzeIntent } from "./utils";
import { ANALYZE_INTENT_RE } from "./constants";
import API_BASE_URL from "./config";
import MessageBubble from "./components/MessageBubble";
import DraftPanel from "./components/DraftPanel";
import AnalysisCard from "./components/AnalysisCard";

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

  function pushChatMessage(role, content, id = null) {
    setChatMessages((prev) => [...prev, { role, content, ...(id && { id }) }]);
  }

  async function handleAnalyze(sentMessage, intent) {
    const source = intent.ticket_key || intent.epic_key || intent.project_key;
    const scopeLabel = intent.ticket_key ? `ticket ${source}` : intent.epic_key ? `epic ${source}` : `project ${source}`;
    pushChatMessage("user", sentMessage);
    const tempMsgId = Date.now();
    pushChatMessage("assistant", `Analyzing ${scopeLabel}…`, tempMsgId);

    try {
      const res = await fetch(`${API_BASE_URL}/analyze-tickets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(intent),
        signal: abortRef.current?.signal,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Analysis failed.");

      // Remove the temporary analyzing message
      setChatMessages((prev) => prev.filter((m) => m.id !== tempMsgId));
      setAnalyzeSession(data);
      const a = data.analysis || {};
      const tickets = a.tickets || [];
      const critical = tickets.flatMap((t) => t.issues_found || []).filter((i) => i.severity === "critical").length;
      const major = tickets.flatMap((t) => t.issues_found || []).filter((i) => i.severity === "major").length;
      pushChatMessage(
        "assistant",
        `Analysis complete. Overall score: ${a.overall_score ?? "—"}/10 across ${data.ticket_count} ticket(s).\n- ${critical} critical issue(s)\n- ${major} major issue(s)\n\n${a.analysis_summary || ""}\n\nReview the details in the panel. You can approve and apply changes per ticket, or type feedback below to refine the analysis.`
      );
    } catch (e) {
      // Remove the temporary analyzing message on error too
      setChatMessages((prev) => prev.filter((m) => m.id !== tempMsgId));
      if (e.name !== "AbortError") {
        pushChatMessage("assistant", `Analysis failed: ${e.message}`);
        setError(e.message);
      }
    }
  }

  async function handleFeedback(sentMessage) {
    pushChatMessage("user", sentMessage);
    const tempMsgId = Date.now();
    pushChatMessage("assistant", "Refining analysis…", tempMsgId);

    try {
      const res = await fetch(`${API_BASE_URL}/analyze-tickets/${analyzeSession.session_id}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback: sentMessage }),
        signal: abortRef.current?.signal,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Feedback failed.");

      // Remove the temporary refining message
      setChatMessages((prev) => prev.filter((m) => m.id !== tempMsgId));
      setAnalyzeSession((prev) => ({ ...prev, analysis: data.analysis }));
      pushChatMessage("assistant", `Analysis revised (revision ${data.revision}). Review the updated panel.`);
    } catch (e) {
      // Remove the temporary refining message on error
      setChatMessages((prev) => prev.filter((m) => m.id !== tempMsgId));
      if (e.name !== "AbortError") {
        pushChatMessage("assistant", `Feedback failed: ${e.message}`);
        setError(e.message);
      }
    }
  }

  function handleApplied(ticketKey) {
    pushChatMessage("assistant", `Applied suggestions to ${ticketKey} in JIRA.`);
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
      
      // Extract project key from message if mentioned
      const projectKeyMatch = sentMessage.match(/(?:project|in project|project key|project:)\s*([A-Z][A-Z0-9]{1,9})/i);
      if (projectKeyMatch) {
        formData.append("project_key", projectKeyMatch[1].toUpperCase());
      }

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
    const tempMsgId = Date.now();
    pushChatMessage("assistant", "Creating tickets in JIRA…", tempMsgId);

    try {
      const response = await fetch(`${API_BASE_URL}/chat/sessions/${session.session_id}/confirm`, {
        method: "POST",
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Failed to confirm Jira creation.");
      }

      setSession(data);
      
      // Remove temporary message and show success feedback
      setChatMessages((prev) => prev.filter((m) => m.id !== tempMsgId));
      const created = data.last_created || [];
      if (created.length > 0) {
        const createdList = created.map(t => `  • ${t.key}: ${t.summary}`).join('\n');
        pushChatMessage("assistant", `Successfully created ${created.length} ticket(s) in JIRA:\n${createdList}`);
      } else {
        pushChatMessage("assistant", "Tickets have been created in JIRA.");
      }
    } catch (nextError) {
      setChatMessages((prev) => prev.filter((m) => m.id !== tempMsgId));
      setError(nextError.message);
      pushChatMessage("assistant", `Failed to create tickets: ${nextError.message}`);
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
      <header className="app-header">
        <div className="app-header-left">
          <span className="app-name">Ticket Analyzer</span>
        </div>
      </header>

      <section className="workspace-grid">
        <section className="conversation-panel glass-panel">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Conversation {session?.project_key && <span className="project-badge">Project: {session.project_key}</span>}</p>
              <h2>Context-friendly ticket shaping</h2>
            </div>
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
                placeholder={analyzeSession
                  ? "Type feedback to refine the analysis..."
                  : "Enter a JIRA ticket key (e.g., PROJ-123) or ask me to analyze your tickets..."
                }
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

            {!analyzeSession && (
              <div className="quick-actions">
                <button type="button" className="quick-chip" onClick={() => setMessage("Analyze ticket ")}>
                  🔍 Analyze ticket
                </button>
                <button type="button" className="quick-chip" onClick={() => setMessage("Review epic ")}>
                  📋 Review epic
                </button>
                <button type="button" className="quick-chip" onClick={() => setMessage("Check project ")}>
                  📁 Check project
                </button>
              </div>
            )}

            {error ? <p className="error-banner">{error}</p> : null}
          </form>
        </section>

        <aside className="inspector-column">
          {analyzeSession ? (
            <section className="glass-panel side-panel analysis-panel">
              <div className="panel-header slim">
                <div>
                  <p className="panel-kicker">🔍 Analysis</p>
                  <h3>{analyzeSession.source || 'Ticket Review'}</h3>
                </div>
                <button className="exit-btn" onClick={() => setAnalyzeSession(null)} title="Exit analysis mode">✕</button>
              </div>

              <div className="analysis-metrics">
                <div className="metric">
                  <span className="metric-value">{analyzeSession.analysis?.overall_score ?? '—'}</span>
                  <span className="metric-label">Overall Score</span>
                </div>
                <div className="metric">
                  <span className="metric-value">{analyzeSession.ticket_count || 0}</span>
                  <span className="metric-label">Tickets</span>
                </div>
                <div className="metric critical">
                  <span className="metric-value">
                    {(analyzeSession.analysis?.tickets || []).flatMap(t => t.issues_found || []).filter(i => i.severity === 'critical').length}
                  </span>
                  <span className="metric-label">Critical</span>
                </div>
                <div className="metric major">
                  <span className="metric-value">
                    {(analyzeSession.analysis?.tickets || []).flatMap(t => t.issues_found || []).filter(i => i.severity === 'major').length}
                  </span>
                  <span className="metric-label">Major</span>
                </div>
              </div>

              {analyzeSession.analysis?.analysis_summary && (
                <p className="analysis-summary-text">{analyzeSession.analysis.analysis_summary}</p>
              )}

              <div className="analysis-list">
                {(analyzeSession.analysis?.tickets || []).map((ticket, index) => (
                  <AnalysisCard
                    key={`${ticket.key}-${analyzeSession.analysis?.overall_score}-${index}`}
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
            <section className="glass-panel side-panel draft-section">
              <DraftPanel
                tickets={pendingTickets}
                onUpdate={(updatedTickets) => {
                  setSession(prev => prev ? { ...prev, pending_tickets: updatedTickets } : prev);
                }}
                onDelete={() => {}}
                onCreate={handleConfirm}
                isCreating={isConfirming}
                canCreate={session?.awaiting_confirmation && session?.project_key}
                projectKey={session?.project_key || ''}
                onProjectKeyChange={async (key) => {
                  if (!session?.session_id || !key) return;
                  try {
                    const res = await fetch(`${API_BASE_URL}/chat/sessions/${session.session_id}/project-key`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ project_key: key })
                    });
                    if (res.ok) {
                      const data = await res.json();
                      setSession(data);
                    }
                  } catch (e) {
                    console.error('Failed to update project key:', e);
                  }
                }}
              />
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