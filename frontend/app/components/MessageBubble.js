import { renderContent } from "../utils";
import { useEffect, useMemo, useState } from "react";

function ClarificationInline({ analysis, onSuggestionClick }) {
  if (!analysis) return null;

  const { readiness_score, summary, questions = [], gaps = [], can_proceed_with_assumptions, assumptions_if_proceed = [] } = analysis;

  return (
    <div className="clarification-inline">
      {/* Readiness Score */}
      <div className="clarification-score-row">
        <span className="score-badge" data-score={readiness_score <= 3 ? 'low' : readiness_score <= 6 ? 'medium' : 'high'}>
          Readiness: {readiness_score}/10
        </span>
        {can_proceed_with_assumptions && (
          <span className="can-proceed-badge">Can proceed with assumptions</span>
        )}
      </div>

      {/* Summary */}
      {summary && <p className="clarification-summary">{summary}</p>}

      {/* Gaps */}
      {gaps.length > 0 && (
        <div className="clarification-gaps">
          <span className="gaps-label">Missing information:</span>
          <div className="gaps-list">
            {gaps.map((gap, i) => (
              <span key={i} className="gap-tag" data-severity={gap.severity}>
                {gap.category.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Questions */}
      {questions.length > 0 && (
        <div className="clarification-questions">
          {questions.map((q, i) => (
            <div key={i} className="clarification-question">
              <div className="question-header">
                <span className="question-number">{i + 1}.</span>
                <span className="question-text">{q.question}</span>
              </div>
              {q.suggestions && q.suggestions.length > 0 && (
                <div className="suggestion-chips">
                  {q.suggestions.map((suggestion, j) => (
                    <button
                      key={j}
                      type="button"
                      className="suggestion-chip"
                      onClick={() => onSuggestionClick && onSuggestionClick(q.question, suggestion)}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              )}
              {q.follow_up_hint && (
                <span className="followup-hint">{q.follow_up_hint}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Assumptions if proceed */}
      {assumptions_if_proceed.length > 0 && (
        <div className="assumptions-section">
          <span className="assumptions-label">Assumptions if proceeding:</span>
          <ul className="assumptions-list">
            {assumptions_if_proceed.map((assumption, i) => (
              <li key={i}>{assumption}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function getPrimaryAssistantContent(content, clarificationAnalysis) {
  if (!clarificationAnalysis || !content) return content;

  const markers = [
    "**Development Readiness",
    "Development Readiness:",
    "I have a few questions to ensure we build the right thing:",
    "The requirements look solid! I can proceed with ticket generation.",
  ];

  const cutPositions = markers
    .map((marker) => content.indexOf(marker))
    .filter((idx) => idx >= 0);

  if (!cutPositions.length) return content;

  const cutAt = Math.min(...cutPositions);
  const head = content.slice(0, cutAt).trim();
  return head || "I analyzed your requirements. See the structured clarification details below.";
}

function MessageBubble({ role, content, clarificationAnalysis, ragCitations = [], onSuggestionClick, stream = false, onStreamEnd = null }) {
  const displayBaseContent = useMemo(
    () => (role === "assistant" ? getPrimaryAssistantContent(content, clarificationAnalysis) : content),
    [role, content, clarificationAnalysis]
  );

  const [renderedContent, setRenderedContent] = useState(
    role === "assistant" && stream ? "" : displayBaseContent
  );

  useEffect(() => {
    if (role !== "assistant") {
      setRenderedContent(displayBaseContent);
      return;
    }

    if (!stream) {
      setRenderedContent(displayBaseContent);
      return;
    }

    let idx = 0;
    const text = displayBaseContent || "";
    const chunkSize = 3;
    const timer = setInterval(() => {
      idx = Math.min(idx + chunkSize, text.length);
      setRenderedContent(text.slice(0, idx));
      if (idx >= text.length) {
        clearInterval(timer);
        if (onStreamEnd) onStreamEnd();
      }
    }, 16);

    return () => clearInterval(timer);
  }, [role, displayBaseContent, stream, onStreamEnd]);

  return (
    <article className={`message-card ${role === "assistant" ? "assistant" : "user"}`}>
      <span className="message-role">{role}</span>
      <div className="msg-body">
        {role === "assistant" ? renderContent(renderedContent) : <p>{content}</p>}
        {role === "assistant" && Array.isArray(ragCitations) && ragCitations.length > 0 && (
          <div className="clarification-inline" style={{ marginTop: 10 }}>
            <div className="clarification-gaps">
              <span className="gaps-label">Sources:</span>
              <div className="gaps-list">
                {ragCitations.slice(0, 5).map((source, i) => (
                  <a
                    key={`${source.source_id || source.title || i}`}
                    href={source.source_url || "#"}
                    target={source.source_url ? "_blank" : undefined}
                    rel={source.source_url ? "noreferrer" : undefined}
                    className="gap-tag"
                    style={{ textDecoration: "none" }}
                  >
                    {source.title || source.source_id || `Source ${i + 1}`}
                  </a>
                ))}
              </div>
            </div>
          </div>
        )}
        {role === "assistant" && clarificationAnalysis && (
          <ClarificationInline 
            analysis={clarificationAnalysis} 
            onSuggestionClick={onSuggestionClick}
          />
        )}
      </div>
    </article>
  );
}

export default MessageBubble;
