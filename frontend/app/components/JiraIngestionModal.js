import { useState } from "react";
import { X } from "lucide-react";

export default function JiraIngestionModal({ isOpen, onClose, onSubmit }) {
  const [ingestionType, setIngestionType] = useState("project");
  const [inputValue, setInputValue] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!inputValue.trim()) return;

    setIsSubmitting(true);
    try {
      const params = {};
      if (ingestionType === "project") params.project_key = inputValue.trim();
      else if (ingestionType === "epic") params.epic_key = inputValue.trim();
      else params.ticket_key = inputValue.trim();

      await onSubmit(params);
      setInputValue("");
      onClose();
    } catch (error) {
      console.error("Jira ingestion failed:", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const getPlaceholder = () => {
    if (ingestionType === "project") return "e.g., PROJ or SHOP";
    if (ingestionType === "epic") return "e.g., PROJ-42";
    return "e.g., PROJ-123";
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add Jira Tickets to Knowledge Base</h3>
          <button className="icon-btn" onClick={onClose} title="Close">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <p style={{ marginBottom: "16px", color: "var(--text-secondary)", fontSize: "0.9rem" }}>
              Ingest Jira tickets into the RAG knowledge base for enhanced context.
            </p>

            <div style={{ marginBottom: "16px" }}>
              <label style={{ display: "block", marginBottom: "8px", fontWeight: "500" }}>
                Ingestion Type
              </label>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <label style={{ display: "flex", alignItems: "center", cursor: "pointer" }}>
                  <input
                    type="radio"
                    name="ingestionType"
                    value="project"
                    checked={ingestionType === "project"}
                    onChange={(e) => setIngestionType(e.target.value)}
                    style={{ marginRight: "8px" }}
                  />
                  <span>Project - Ingest all tickets in a project</span>
                </label>
                <label style={{ display: "flex", alignItems: "center", cursor: "pointer" }}>
                  <input
                    type="radio"
                    name="ingestionType"
                    value="epic"
                    checked={ingestionType === "epic"}
                    onChange={(e) => setIngestionType(e.target.value)}
                    style={{ marginRight: "8px" }}
                  />
                  <span>Epic - Ingest an epic and its child tickets</span>
                </label>
                <label style={{ display: "flex", alignItems: "center", cursor: "pointer" }}>
                  <input
                    type="radio"
                    name="ingestionType"
                    value="ticket"
                    checked={ingestionType === "ticket"}
                    onChange={(e) => setIngestionType(e.target.value)}
                    style={{ marginRight: "8px" }}
                  />
                  <span>Single Ticket - Ingest one specific ticket</span>
                </label>
              </div>
            </div>

            <div>
              <label htmlFor="jira-input" style={{ display: "block", marginBottom: "8px", fontWeight: "500" }}>
                {ingestionType === "project" ? "Project Key" : ingestionType === "epic" ? "Epic Key" : "Ticket Key"}
              </label>
              <input
                id="jira-input"
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder={getPlaceholder()}
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "6px",
                  fontSize: "0.95rem",
                  backgroundColor: "var(--bg-primary)",
                  color: "var(--text-primary)",
                }}
                autoFocus
                disabled={isSubmitting}
              />
            </div>
          </div>

          <div className="modal-footer">
            <button
              type="button"
              className="btn-secondary"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={!inputValue.trim() || isSubmitting}
            >
              {isSubmitting ? "Ingesting..." : "Ingest Tickets"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
