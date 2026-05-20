"use client";

import { useState } from "react";
import { CheckCircle, AlertTriangle, HelpCircle, ChevronRight } from "lucide-react";

/**
 * Displays clarification questions with intelligent suggestions
 * Users can click suggestions or type custom answers
 */
function ClarificationCard({ 
  analysis, 
  onAnswer, 
  onProceedWithAssumptions,
  isSubmitting 
}) {
  const [answers, setAnswers] = useState({});
  const [customInputs, setCustomInputs] = useState({});

  if (!analysis) return null;

  const { readiness_score, summary, questions, can_proceed_with_assumptions, assumptions_if_proceed } = analysis;

  const handleSuggestionClick = (questionIndex, suggestion) => {
    setAnswers(prev => ({
      ...prev,
      [questionIndex + 1]: suggestion
    }));
  };

  const handleCustomInput = (questionIndex, value) => {
    setCustomInputs(prev => ({
      ...prev,
      [questionIndex]: value
    }));
    if (value.trim()) {
      setAnswers(prev => ({
        ...prev,
        [questionIndex + 1]: value
      }));
    }
  };

  const handleSubmitAnswers = () => {
    if (Object.keys(answers).length === 0) return;
    onAnswer(answers);
    setAnswers({});
    setCustomInputs({});
  };

  const getScoreColor = (score) => {
    if (score >= 8) return "text-green-500";
    if (score >= 5) return "text-yellow-500";
    return "text-red-500";
  };

  const getScoreIcon = (score) => {
    if (score >= 8) return <CheckCircle className="w-5 h-5 text-green-500" />;
    if (score >= 5) return <AlertTriangle className="w-5 h-5 text-yellow-500" />;
    return <AlertTriangle className="w-5 h-5 text-red-500" />;
  };

  return (
    <div className="clarification-card">
      {/* Readiness Score Header */}
      <div className="clarification-header">
        <div className="score-display">
          {getScoreIcon(readiness_score)}
          <span className={`score-value ${getScoreColor(readiness_score)}`}>
            Development Readiness: {readiness_score}/10
          </span>
        </div>
        {summary && <p className="clarification-summary">{summary}</p>}
      </div>

      {/* Questions Section */}
      {questions && questions.length > 0 && (
        <div className="questions-section">
          <h4 className="questions-title">
            <HelpCircle className="w-4 h-4" />
            Clarification Questions
          </h4>
          
          {questions.map((q, index) => (
            <div key={index} className="question-item">
              <div className="question-header">
                <span className="question-number">{index + 1}</span>
                <span className="question-text">{q.question}</span>
                <span className={`question-category category-${q.category}`}>
                  {q.category.replace(/_/g, ' ')}
                </span>
              </div>

              {/* Suggestions as clickable chips */}
              {q.suggestions && q.suggestions.length > 0 && (
                <div className="suggestions-list">
                  {q.suggestions.map((suggestion, sIndex) => (
                    <button
                      key={sIndex}
                      type="button"
                      className={`suggestion-chip ${answers[index + 1] === suggestion ? 'selected' : ''}`}
                      onClick={() => handleSuggestionClick(index, suggestion)}
                    >
                      <ChevronRight className="w-3 h-3" />
                      {suggestion}
                    </button>
                  ))}
                </div>
              )}

              {/* Custom input */}
              <input
                type="text"
                placeholder="Or type your own answer..."
                className="custom-answer-input"
                value={customInputs[index] || ''}
                onChange={(e) => handleCustomInput(index, e.target.value)}
              />

              {/* Show selected answer */}
              {answers[index + 1] && (
                <div className="selected-answer">
                  <CheckCircle className="w-4 h-4 text-green-500" />
                  <span>{answers[index + 1]}</span>
                </div>
              )}

              {/* Follow-up hint */}
              {q.follow_up_hint && (
                <p className="follow-up-hint">
                  <em>Follow-up: {q.follow_up_hint}</em>
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Action Buttons */}
      <div className="clarification-actions">
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleSubmitAnswers}
          disabled={Object.keys(answers).length === 0 || isSubmitting}
        >
          {isSubmitting ? 'Submitting...' : `Submit Answers (${Object.keys(answers).length})`}
        </button>

        {can_proceed_with_assumptions && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onProceedWithAssumptions}
            disabled={isSubmitting}
          >
            Proceed with Assumptions
          </button>
        )}
      </div>

      {/* Assumptions Preview */}
      {can_proceed_with_assumptions && assumptions_if_proceed && assumptions_if_proceed.length > 0 && (
        <div className="assumptions-preview">
          <h5>If you proceed, I'll assume:</h5>
          <ul>
            {assumptions_if_proceed.map((assumption, index) => (
              <li key={index}>{assumption}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default ClarificationCard;
