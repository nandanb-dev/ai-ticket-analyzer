import { useState } from "react";
import { X } from "lucide-react";

export default function ConfluenceIngestionModal({ isOpen, onClose, onSubmit }) {
  const [ingestionType, setIngestionType] = useState("page");
  const [pageId, setPageId] = useState("");
  const [spaceKey, setSpaceKey] = useState("");
  const [title, setTitle] = useState("");
  const [maxPages, setMaxPages] = useState(20);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (ingestionType === "page" && !pageId.trim()) return;
    if (ingestionType === "space" && !spaceKey.trim()) return;

    setIsSubmitting(true);
    try {
      const params = {};
      
      if (ingestionType === "page") {
        params.page_id = pageId.trim();
      } else if (ingestionType === "space") {
        params.space_key = spaceKey.trim();
        if (title.trim()) params.title = title.trim();
        params.max_pages = maxPages;
      } else {
        params.space_key = spaceKey.trim();
        params.title = title.trim();
      }

      await onSubmit(params);
      
      setPageId("");
      setSpaceKey("");
      setTitle("");
      setMaxPages(20);
      onClose();
    } catch (error) {
      console.error("Confluence ingestion failed:", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add Confluence Pages to Knowledge Base</h3>
          <button className="icon-btn" onClick={onClose} title="Close">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <p style={{ marginBottom: "16px", color: "var(--text-secondary)", fontSize: "0.9rem" }}>
              Ingest Confluence pages or spaces into the RAG knowledge base.
            </p>

            <div style={{ marginBottom: "16px" }}>
              <label style={{ display: "block", marginBottom: "8px", fontWeight: "500" }}>
                Ingestion Type
              </label>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <label style={{ display: "flex", alignItems: "center", cursor: "pointer" }}>
                  <input
                    type="radio"
                    name="confluenceType"
                    value="page"
                    checked={ingestionType === "page"}
                    onChange={(e) => setIngestionType(e.target.value)}
                    style={{ marginRight: "8px" }}
                  />
                  <span>Single Page - Ingest by page ID</span>
                </label>
                <label style={{ display: "flex", alignItems: "center", cursor: "pointer" }}>
                  <input
                    type="radio"
                    name="confluenceType"
                    value="space"
                    checked={ingestionType === "space"}
                    onChange={(e) => setIngestionType(e.target.value)}
                    style={{ marginRight: "8px" }}
                  />
                  <span>Entire Space - Ingest multiple pages from a space</span>
                </label>
                <label style={{ display: "flex", alignItems: "center", cursor: "pointer" }}>
                  <input
                    type="radio"
                    name="confluenceType"
                    value="space-page"
                    checked={ingestionType === "space-page"}
                    onChange={(e) => setIngestionType(e.target.value)}
                    style={{ marginRight: "8px" }}
                  />
                  <span>Page by Title - Ingest specific page from a space</span>
                </label>
              </div>
            </div>

            {ingestionType === "page" && (
              <div>
                <label htmlFor="page-id" style={{ display: "block", marginBottom: "8px", fontWeight: "500" }}>
                  Page ID
                </label>
                <input
                  id="page-id"
                  type="text"
                  value={pageId}
                  onChange={(e) => setPageId(e.target.value)}
                  placeholder="e.g., 123456"
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
                <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "4px" }}>
                  Find the page ID in the URL or page info
                </p>
              </div>
            )}

            {ingestionType === "space" && (
              <>
                <div style={{ marginBottom: "16px" }}>
                  <label htmlFor="space-key" style={{ display: "block", marginBottom: "8px", fontWeight: "500" }}>
                    Space Key
                  </label>
                  <input
                    id="space-key"
                    type="text"
                    value={spaceKey}
                    onChange={(e) => setSpaceKey(e.target.value)}
                    placeholder="e.g., PROJ or DOCS"
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
                <div>
                  <label htmlFor="max-pages" style={{ display: "block", marginBottom: "8px", fontWeight: "500" }}>
                    Max Pages to Ingest
                  </label>
                  <input
                    id="max-pages"
                    type="number"
                    min="1"
                    max="200"
                    value={maxPages}
                    onChange={(e) => setMaxPages(parseInt(e.target.value) || 20)}
                    style={{
                      width: "100%",
                      padding: "10px 12px",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "6px",
                      fontSize: "0.95rem",
                      backgroundColor: "var(--bg-primary)",
                      color: "var(--text-primary)",
                    }}
                    disabled={isSubmitting}
                  />
                  <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "4px" }}>
                    Maximum: 200 pages
                  </p>
                </div>
              </>
            )}

            {ingestionType === "space-page" && (
              <>
                <div style={{ marginBottom: "16px" }}>
                  <label htmlFor="space-key-2" style={{ display: "block", marginBottom: "8px", fontWeight: "500" }}>
                    Space Key
                  </label>
                  <input
                    id="space-key-2"
                    type="text"
                    value={spaceKey}
                    onChange={(e) => setSpaceKey(e.target.value)}
                    placeholder="e.g., PROJ or DOCS"
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
                <div>
                  <label htmlFor="page-title" style={{ display: "block", marginBottom: "8px", fontWeight: "500" }}>
                    Page Title
                  </label>
                  <input
                    id="page-title"
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g., Product Requirements"
                    style={{
                      width: "100%",
                      padding: "10px 12px",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "6px",
                      fontSize: "0.95rem",
                      backgroundColor: "var(--bg-primary)",
                      color: "var(--text-primary)",
                    }}
                    disabled={isSubmitting}
                  />
                </div>
              </>
            )}
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
              disabled={
                (ingestionType === "page" && !pageId.trim()) ||
                (ingestionType === "space" && !spaceKey.trim()) ||
                (ingestionType === "space-page" && (!spaceKey.trim() || !title.trim())) ||
                isSubmitting
              }
            >
              {isSubmitting ? "Ingesting..." : "Ingest Pages"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
