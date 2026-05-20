import { renderContent } from "../utils";

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

function MessageBubble({ role, content, clarificationAnalysis, onSuggestionClick }) {
  return (
    <article className={`message-card ${role === "assistant" ? "assistant" : "user"}`}>
      <span className="message-role">{role}</span>
      <div className="msg-body">
        {role === "assistant" ? renderContent(content) : <p>{content}</p>}
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
