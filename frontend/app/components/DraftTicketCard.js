import { useState } from "react";

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

export default DraftTicketCard;
