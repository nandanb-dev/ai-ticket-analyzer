import { useState } from "react";
import API_BASE_URL from "../config";

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

export default AnalysisCard;
