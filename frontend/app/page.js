"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

const TICKET_KEY_RE = /\b([A-Za-z][A-Za-z0-9]+-\d+)\b/i;
const JIRA_URL_RE = /atlassian\.net\/browse\/([A-Za-z][A-Za-z0-9]+-\d+)/i;
const PROJECT_KEY_RE = /\bproject[:\s]+([A-Za-z][A-Za-z0-9]+)\b/i;
const EPIC_KEYWORD_RE = /\bepic[:\s]+([A-Za-z][A-Za-z0-9]+-\d+)\b/i;
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

function DraftTicketCard({ ticket, type, index, onUpdate, onDelete }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [edited, setEdited] = useState({ ...ticket });

  const issueTypes = ["Epic", "Story", "Task", "Bug"];
  const priorities = ["Highest", "High", "Medium", "Low", "Lowest"];

  const handleChange = (field, value) => {
    const updated = { ...edited, [field]: value };
    setEdited(updated);
    onUpdate(index, type, updated);
  };

  const handleACChange = (acIndex, field, value) => {
    const updatedAC = [...(edited.acceptance_criteria || [])];
    updatedAC[acIndex] = { ...updatedAC[acIndex], [field]: value };
    handleChange('acceptance_criteria', updatedAC);
  };

  return (
    <div className={`draft-ticket-card ${type.toLowerCase()} ${isExpanded ? 'expanded' : ''}`}>
      <div className="draft-ticket-header" onClick={() => setIsExpanded(!isExpanded)}>
        <div className="draft-ticket-type-badge">{type}</div>
        <div className="draft-ticket-title">
          <input
            type="text"
            value={edited.summary || ''}
            onChange={(e) => handleChange('summary', e.target.value)}
            onClick={(e) => e.stopPropagation()}
            placeholder="Ticket summary..."
          />
        </div>
        <div className="draft-ticket-actions">
          <select
            value={edited.priority || 'Medium'}
            onChange={(e) => handleChange('priority', e.target.value)}
            onClick={(e) => e.stopPropagation()}
            className={`priority-select priority-${(edited.priority || 'medium').toLowerCase()}`}
          >
            {priorities.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <button className="expand-toggle" onClick={(e) => { e.stopPropagation(); setIsExpanded(!isExpanded); }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              {isExpanded ? <path d="m18 15-6-6-6 6"/> : <path d="m9 18 6-6-6-6"/>}
            </svg>
          </button>
          <button className="delete-btn" onClick={(e) => { e.stopPropagation(); onDelete(index, type); }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6 6 18"/><path d="m6 6 12 12"/>
            </svg>
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="draft-ticket-body">
          <div className="draft-field-row">
            <label>Issue Type</label>
            <select value={type} onChange={(e) => handleChange('issue_type', e.target.value)}>
              {issueTypes.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          
          <div className="draft-field">
            <label>Description</label>
            <textarea
              value={edited.description || ''}
              onChange={(e) => handleChange('description', e.target.value)}
              placeholder="Add a description..."
              rows={3}
            />
          </div>

          <div className="draft-field-row">
            <div className="draft-field">
              <label>Story Points</label>
              <input
                type="number"
                value={edited.story_points || ''}
                onChange={(e) => handleChange('story_points', e.target.value)}
                placeholder="0"
                min="0"
              />
            </div>
            <div className="draft-field">
              <label>Labels</label>
              <input
                type="text"
                value={(edited.labels || []).join(', ')}
                onChange={(e) => handleChange('labels', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                placeholder="label1, label2"
              />
            </div>
          </div>

          {edited.acceptance_criteria && edited.acceptance_criteria.length > 0 && (
            <div className="draft-field">
              <label>Acceptance Criteria ({edited.acceptance_criteria.length})</label>
              <div className="ac-list editable">
                {edited.acceptance_criteria.map((ac, i) => (
                  <div key={i} className="ac-item editable">
                    <span className="ac-num">{i + 1}.</span>
                    <div className="ac-fields">
                      <input 
                        type="text" 
                        value={ac.given || ''} 
                        onChange={(e) => handleACChange(i, 'given', e.target.value)}
                        placeholder="GIVEN..."
                        className="ac-input"
                      />
                      <input 
                        type="text" 
                        value={ac.when || ''} 
                        onChange={(e) => handleACChange(i, 'when', e.target.value)}
                        placeholder="WHEN..."
                        className="ac-input"
                      />
                      <input 
                        type="text" 
                        value={ac.then || ''} 
                        onChange={(e) => handleACChange(i, 'then', e.target.value)}
                        placeholder="THEN..."
                        className="ac-input"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DraftPanel({ tickets, onUpdate, onDelete, onCreate, isCreating, canCreate, projectKey, onProjectKeyChange }) {
  const handleUpdate = (index, type, updatedTicket) => {
    const key = type.toLowerCase() + 's';
    const list = [...(tickets[key] || [])];
    list[index] = updatedTicket;
    onUpdate({ ...tickets, [key]: list });
  };

  const handleDelete = (index, type) => {
    const key = type.toLowerCase() + 's';
    const list = (tickets[key] || []).filter((_, i) => i !== index);
    onUpdate({ ...tickets, [key]: list });
  };

  const epicCount = (tickets.epics || []).length;
  const storyCount = (tickets.stories || []).length;
  const taskCount = (tickets.tasks || []).length;
  const totalCount = epicCount + storyCount + taskCount;

  return (
    <div className="draft-panel">
      <div className="draft-panel-header">
        <div>
          <p className="panel-kicker">Draft</p>
          <h3>Pending ticket overview</h3>
        </div>
        <div className="draft-stats">
          <span className="stat-pill epic">{epicCount} Epics</span>
          <span className="stat-pill story">{storyCount} Stories</span>
          <span className="stat-pill task">{taskCount} Tasks</span>
        </div>
      </div>

      <div className="project-key-row">
        <label>JIRA Project Key</label>
        <div className="project-key-input-group">
          <input
            type="text"
            value={projectKey || ''}
            onChange={(e) => onProjectKeyChange(e.target.value.toUpperCase())}
            placeholder="e.g., KAN"
            className="project-key-input"
          />
          {!projectKey && <span className="project-key-hint">Required to create tickets</span>}
        </div>
      </div>

      {totalCount === 0 ? (
        <p className="muted-copy">No tickets drafted yet. Start a conversation to create tickets.</p>
      ) : (
        <div className="draft-ticket-list">
          {(tickets.epics || []).map((ticket, i) => (
            <DraftTicketCard
              key={`epic-${i}`}
              ticket={ticket}
              type="Epic"
              index={i}
              onUpdate={handleUpdate}
              onDelete={handleDelete}
            />
          ))}
          {(tickets.stories || []).map((ticket, i) => (
            <DraftTicketCard
              key={`story-${i}`}
              ticket={ticket}
              type="Story"
              index={i}
              onUpdate={handleUpdate}
              onDelete={handleDelete}
            />
          ))}
          {(tickets.tasks || []).map((ticket, i) => (
            <DraftTicketCard
              key={`task-${i}`}
              ticket={ticket}
              type="Task"
              index={i}
              onUpdate={handleUpdate}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      <div className="draft-panel-footer">
        <button
          className="create-tickets-btn"
          onClick={onCreate}
          disabled={!canCreate || isCreating || totalCount === 0}
        >
          {isCreating ? "Creating in JIRA..." : `Create ${totalCount} ticket(s) in JIRA`}
        </button>
        {!canCreate && totalCount > 0 && (
          <p className="draft-hint">Specify a project key (e.g., "in project KAN") to enable creation</p>
        )}
      </div>
    </div>
  );
}

function AnalysisCard({ ticket, sessionId, onApplied }) {
  const [cardState, setCardState] = useState("idle");
  const [expanded, setExpanded] = useState(false);
  const [showingUpdates, setShowingUpdates] = useState(false);
  const [error, setError] = useState("");
  const [showingRoleFindings, setShowingRoleFindings] = useState(false);

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

  const roleNames = {
    product_manager: "Product Manager",
    developer: "Developer",
    qa_engineer: "QA Engineer",
    security_engineer: "Security",
    devops_sre: "DevOps/SRE",
    ux_accessibility: "UX/Accessibility",
    scrum_master: "Scrum Master"
  };

  const hasRoleFindings = Object.keys(ticket.role_findings || {}).length > 0;
  const hasUpdates = Object.keys(ticket.suggested_updates || {}).length > 0;

  // Compact inline metrics
  const criticalCount = (ticket.issues_found || []).filter(i => i.severity === "critical").length;
  const majorCount = (ticket.issues_found || []).filter(i => i.severity === "major").length;
  const minorCount = (ticket.issues_found || []).filter(i => i.severity === "minor").length;

  return (
    <div className={`analysis-card ${cardState} ${expanded ? 'expanded' : ''}`}>
      <div className="analysis-card-header">
        <div className="analysis-card-title">
          <span className="analysis-key">{ticket.key}</span>
          {ticket.issue_type && (
            <span className="analysis-type">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                {ticket.issue_type === 'Epic' ? <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/> : 
                 ticket.issue_type === 'Story' ? <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/> :
                 <circle cx="12" cy="12" r="10"/>}
              </svg>
              {ticket.issue_type}
            </span>
          )}
        </div>
        <div className="analysis-card-meta">
          <div className={`score-bar score-${ticket.quality_score >= 8 ? "good" : ticket.quality_score >= 5 ? "mid" : "bad"}`}>
            <div className="score-fill" style={{ width: `${ticket.quality_score * 10}%` }} />
            <span className="score-text">{ticket.quality_score}/10</span>
          </div>
        </div>
      </div>

      <p className="analysis-summary">{ticket.current_summary}</p>

      {/* Inline Metrics Row */}
      <div className="analysis-metrics-row">
        {criticalCount > 0 && (
          <span className="metric-pill critical">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 22h20L12 2zm0 3l7.5 15h-15L12 5z"/></svg>
            {criticalCount} Critical
          </span>
        )}
        {majorCount > 0 && (
          <span className="metric-pill major">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"/></svg>
            {majorCount} Major
          </span>
        )}
        {minorCount > 0 && (
          <span className="metric-pill minor">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/></svg>
            {minorCount} Minor
          </span>
        )}
        {(ticket.issues_found || []).length === 0 && (
          <span className="metric-pill good">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 6L9 17l-5-5"/></svg>
            No issues
          </span>
        )}
      </div>

      {/* Collapsed Issues Preview (first 2 only) */}
      {(ticket.issues_found || []).length > 0 && (
        <div className="issues-preview">
          {(ticket.issues_found || []).slice(0, 2).map((issue, i) => (
            <div key={i} className={`issue-chip-mini sev-${issue.severity}`}>
              <span className="issue-sev-mini">{issue.severity}</span>
              <span className="issue-desc-mini">{issue.description.substring(0, 60)}{issue.description.length > 60 ? '…' : ''}</span>
            </div>
          ))}
          {(ticket.issues_found || []).length > 2 && (
            <button className="issues-more-btn" onClick={() => setExpanded(!expanded)}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                {expanded ? <path d="m18 15-6-6-6 6"/> : <path d="m9 18 6-6-6-6"/>}
              </svg>
              {(ticket.issues_found || []).length - 2} more issues
            </button>
          )}
        </div>
      )}

      {/* Expanded Issues */}
      {expanded && (ticket.issues_found || []).length > 0 && (
        <div className="issues-list-expanded">
          {(ticket.issues_found || []).map((issue, i) => (
            <div key={i} className={`issue-chip sev-${issue.severity}`}>
              <div className="issue-header">
                <span className="issue-sev">{issue.severity}</span>
                {issue.category && <span className="issue-cat">{issue.category}</span>}
              </div>
              <span className="issue-desc">{issue.description}</span>
              {issue.suggestion && (
                <span className="issue-suggestion">Suggestion: {issue.suggestion}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {hasRoleFindings && (
        <div className="role-findings-section">
          <button className="expand-btn compact" onClick={() => setShowingRoleFindings(!showingRoleFindings)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              {showingRoleFindings ? <path d="m18 15-6-6-6 6"/> : <path d="m9 18 6-6-6-6"/>}
            </svg>
            Role Findings ({Object.keys(ticket.role_findings || {}).length})
          </button>
          {showingRoleFindings && (
            <div className="role-findings-list">
              {Object.entries(ticket.role_findings || {}).map(([role, finding]) => (
                <div key={role} className="role-finding">
                  <span className="role-name">{roleNames[role] || role}</span>
                  <span className="role-text">{finding}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {hasUpdates && cardState !== "applied" && (
        <div className="suggested-updates-section">
          <button className="expand-btn compact" onClick={() => setShowingUpdates(!showingUpdates)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              {showingUpdates ? <path d="m18 15-6-6-6 6"/> : <path d="m9 18 6-6-6-6"/>}
            </svg>
            Suggested Updates
          </button>
          {showingUpdates && (
            <div className="updates-detail">
              {(ticket.suggested_updates || {}).summary && (
                <div className="update-field">
                  <span className="update-label">Summary</span>
                  <p className="update-value">{(ticket.suggested_updates || {}).summary}</p>
                </div>
              )}
              {(ticket.suggested_updates || {}).description && (
                <div className="update-field">
                  <span className="update-label">Description</span>
                  <p className="update-value">{(ticket.suggested_updates || {}).description}</p>
                </div>
              )}
              <div className="update-fields-row">
                {(ticket.suggested_updates || {}).priority && (
                  <span className="update-priority">{(ticket.suggested_updates || {}).priority}</span>
                )}
                {(ticket.suggested_updates || {}).story_points && (
                  <span className="update-points">{(ticket.suggested_updates || {}).story_points} pts</span>
                )}
              </div>
              {(ticket.suggested_updates || {}).labels && (ticket.suggested_updates || {}).labels.length > 0 && (
                <div className="update-field">
                  <span className="update-label">Labels</span>
                  <div className="update-labels">
                    {(ticket.suggested_updates || {}).labels.map((label, i) => (
                      <span key={i} className="update-label-tag">{label}</span>
                    ))}
                  </div>
                </div>
              )}
              {(ticket.suggested_updates || {}).acceptance_criteria && (ticket.suggested_updates || {}).acceptance_criteria.length > 0 && (
                <div className="update-field">
                  <span className="update-label">Acceptance Criteria</span>
                  <div className="update-ac-list">
                    {(ticket.suggested_updates || {}).acceptance_criteria.map((ac, i) => (
                      <div key={i} className="ac-item">
                        <strong>GIVEN</strong> {ac.given}<br/>
                        <strong>WHEN</strong> {ac.when}<br/>
                        <strong>THEN</strong> {ac.then}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {(ticket.suggested_updates || {}).test_cases && (ticket.suggested_updates || {}).test_cases.length > 0 && (
                <div className="update-field">
                  <span className="update-label">Test Cases ({(ticket.suggested_updates || {}).test_cases.length})</span>
                  <div className="update-test-list">
                    {(ticket.suggested_updates || {}).test_cases.slice(0, 3).map((tc, i) => (
                      <div key={i} className="test-item">
                        <span className="test-type">{tc.type}</span>
                        <strong>{tc.title}</strong>
                        <p>{tc.expected}</p>
                      </div>
                    ))}
                    {(ticket.suggested_updates || {}).test_cases.length > 3 && (
                      <p className="muted-copy">+{(ticket.suggested_updates || {}).test_cases.length - 3} more test cases</p>
                    )}
                  </div>
                </div>
              )}
              {(ticket.suggested_updates || {}).edge_cases && (ticket.suggested_updates || {}).edge_cases.length > 0 && (
                <div className="update-field">
                  <span className="update-label">Edge Cases ({(ticket.suggested_updates || {}).edge_cases.length})</span>
                  <ul className="update-edge-list">
                    {(ticket.suggested_updates || {}).edge_cases.map((edge, i) => (
                      <li key={i}>{edge}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="analysis-card-footer">
        {cardState === "idle" && hasUpdates && (
          <button className="action-btn primary" onClick={() => setCardState("approved")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 6L9 17l-5-5"/></svg>
            Approve
          </button>
        )}
        {cardState === "approved" && (
          <>
            <button className="action-btn primary" onClick={handleApply}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14"/></svg>
              Apply to JIRA
            </button>
            <button className="action-btn secondary" onClick={() => setCardState("idle")}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
              Cancel
            </button>
          </>
        )}
        {cardState === "applying" && (
          <span className="status-text">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            Applying…
          </span>
        )}
        {cardState === "applied" && (
          <span className="status-text success">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 6L9 17l-5-5"/></svg>
            Applied to JIRA
          </span>
        )}
        {error && (
          <span className="status-text error">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>
            {error}
          </span>
        )}
      </div>
    </div>
  );
}

function HomePage() {
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

export default HomePage;