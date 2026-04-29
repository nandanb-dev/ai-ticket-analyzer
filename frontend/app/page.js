"use client";

import { useEffect, useMemo, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

function MessageBubble({ role, content }) {
  return (
    <article className={`message-card ${role === "assistant" ? "assistant" : "user"}`}>
      <span className="message-role">{role}</span>
      <p>{content}</p>
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

export default function HomePage() {
  const [session, setSession] = useState(null);
  const [projectKey, setProjectKey] = useState("SCRUM");
  const [message, setMessage] = useState("");
  const [contextText, setContextText] = useState("");
  const [files, setFiles] = useState([]);
  const [isSending, setIsSending] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function bootstrap() {
      try {
        const response = await fetch(`${API_BASE_URL}/chat/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_key: projectKey }),
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
  }, []);

  const pendingTickets = useMemo(() => session?.pending_tickets || {}, [session]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!session?.session_id) {
      return;
    }

    setIsSending(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("message", message);
      formData.append("context_text", contextText);
      formData.append("project_key", projectKey);

      files.forEach((file) => {
        formData.append("files", file);
      });

      const response = await fetch(`${API_BASE_URL}/chat/sessions/${session.session_id}/messages`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Failed to send message.");
      }

      setSession(data);
      setMessage("");
      setContextText("");
      setFiles([]);
    } catch (nextError) {
      setError(nextError.message);
    } finally {
      setIsSending(false);
    }
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

        <div className="hero-metrics">
          <div className="metric-card">
            <span>Session</span>
            <strong>{session?.session_id ? session.session_id.slice(0, 8) : "Starting"}</strong>
          </div>
          <div className="metric-card">
            <span>Project</span>
            <strong>{session?.project_key || projectKey || "Unset"}</strong>
          </div>
          <div className="metric-card">
            <span>Status</span>
            <strong>{session?.awaiting_confirmation ? "Awaiting approval" : "Exploration"}</strong>
          </div>
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
            {session?.messages?.length ? (
              session.messages.map((entry, index) => (
                <MessageBubble key={`${entry.role}-${index}`} role={entry.role} content={entry.content} />
              ))
            ) : (
              <div className="empty-state">
                <strong>Start with intent, documents, or raw notes.</strong>
                <p>The agent will keep the conversation grounded in everything you upload or paste.</p>
              </div>
            )}
          </div>

          <form className="composer-panel" onSubmit={handleSubmit}>
            <div className="field-grid compact">
              <label>
                <span>Jira project key</span>
                <input value={projectKey} onChange={(event) => setProjectKey(event.target.value.toUpperCase())} placeholder="SCRUM" />
              </label>
            </div>

            <div className="field-grid">
              <label>
                <span>Ask the assistant what to do</span>
                <textarea
                  rows={4}
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                  placeholder="Example: I have a Todo app PRD and a stakeholder call transcript. Help me understand the scope and then draft Jira tickets."
                />
              </label>

              <label>
                <span>Paste supporting context</span>
                <textarea
                  rows={7}
                  value={contextText}
                  onChange={(event) => setContextText(event.target.value)}
                  placeholder="Paste transcript notes, backlog dumps, acceptance criteria, or risk notes here."
                />
              </label>
            </div>

            <label className="upload-field">
              <span>Attach files</span>
              <input
                type="file"
                multiple
                onChange={(event) => setFiles(Array.from(event.target.files || []))}
              />
            </label>

            {files.length ? <p className="muted-copy">{files.length} file(s) ready to send.</p> : null}
            {error ? <p className="error-banner">{error}</p> : null}

            <div className="composer-actions">
              <button className="send-button" type="submit" disabled={isSending}>
                {isSending ? "Sending..." : "Send into chat"}
              </button>
            </div>
          </form>
        </section>

        <aside className="inspector-column">
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