"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "react-toastify";
import { Paperclip, FileText, X, Send, Search, Square, Trash2 } from "lucide-react";
import { detectAnalyzeIntent } from "./utils";
import { ANALYZE_INTENT_RE } from "./constants";
import API_BASE_URL from "./config";
import MessageBubble from "./components/MessageBubble";
import DraftPanel from "./components/DraftPanel";
import AnalysisCard from "./components/AnalysisCard";
import ConfirmModal from "./components/ConfirmModal";
import { normalizeRagCitations } from "./utils";

function buildPendingTicketsFromAnalysis(analysis) {
  const grouped = { epics: [], stories: [], tasks: [] };
  const tickets = analysis?.tickets || [];

  for (const t of tickets) {
    const su = t?.suggested_updates || {};
    const issueType = String(su.issue_type || t.issue_type || "Task").toLowerCase();

    const draft = {
      summary: su.summary || t.current_summary || "",
      description: su.description || "",
      priority: su.priority || "Medium",
      story_points: su.story_points ?? "",
      labels: Array.isArray(su.labels) ? su.labels : [],
      acceptance_criteria: Array.isArray(su.acceptance_criteria) ? su.acceptance_criteria : [],
    };

    if (issueType === "epic") grouped.epics.push(draft);
    else if (issueType === "story") grouped.stories.push(draft);
    else grouped.tasks.push(draft);
  }

  return grouped;
}

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
  const [editingAttachment, setEditingAttachment] = useState(null);
  const [editedContent, setEditedContent] = useState("");
  const [appliedTickets, setAppliedTickets] = useState(new Set());
  const [confirmModal, setConfirmModal] = useState({ isOpen: false, title: "", message: "", onConfirm: null });
  const [ragFiles, setRagFiles] = useState([]);
  const [isUploadingToRag, setIsUploadingToRag] = useState(false);
  const [ragIngestionStatus, setRagIngestionStatus] = useState({});
  const [ingestionHistory, setIngestionHistory] = useState([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [inspectorTab, setInspectorTab] = useState("analysis");
  const fileInputRef = useRef(null);
  const ragFileInputRef = useRef(null);
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

  useEffect(() => {
    async function loadRagDocuments() {
      setIsLoadingHistory(true);
      try {
        const response = await fetch(`${API_BASE_URL}/rag/documents?page=1&page_size=50`);
        if (response.ok) {
          const data = await response.json();
          setIngestionHistory(data.documents || []);
        }
      } catch (error) {
        console.error("Failed to load RAG documents:", error);
      } finally {
        setIsLoadingHistory(false);
      }
    }

    loadRagDocuments();
  }, []);

  const pendingTickets = useMemo(() => session?.pending_tickets || {}, [session]);

  function pushChatMessage(role, content, id = null) {
    setChatMessages((prev) => [...prev, { role, content, ...(id && { id }) }]);
  }

  function logRagDebug(stage, payload) {
    const citations = normalizeRagCitations(payload);
    const tickets = payload?.analysis?.tickets || [];
    const perTicketSourceCounts = tickets.map((ticket) => {
      const count = [
        ticket?.rag_citations,
        ticket?.citations,
        ticket?.sources,
        ticket?.retrieval_context?.sources,
      ].find(Array.isArray)?.length || 0;
      return { key: ticket?.key || "unknown", sourceCount: count };
    });

    console.groupCollapsed(`[RAG][UI] ${stage}`);
    console.log("API rag_used:", payload?.rag_used);
    console.log("API rag_citations count:", Array.isArray(payload?.rag_citations) ? payload.rag_citations.length : 0);
    console.log("Normalized citations count:", citations.length);
    console.log("Ticket-level source counts:", perTicketSourceCounts);
    console.log("Normalized citations preview:", citations.slice(0, 3));
    if (citations.length === 0) {
      console.warn("[RAG][UI] No citations found in response payload. Analysis may be ungrounded or retrieval returned no matches.");
    }
    console.groupEnd();

    return citations;
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

      const ragCitations = logRagDebug("analyze-response", data);
      setAnalyzeSession({
        ...data,
        rag_citations: ragCitations,
      });
      setInspectorTab("analysis");

      setSession((prev) =>
        prev
          ? {
              ...prev,
              pending_tickets: buildPendingTicketsFromAnalysis(data.analysis),
              awaiting_confirmation: true,
            }
          : prev
      );

      // Remove the temporary analyzing message
      setChatMessages((prev) => prev.filter((m) => m.id !== tempMsgId));
      setAppliedTickets(new Set()); // Reset applied tickets for new analysis
      const a = data.analysis || {};
      const tickets = a.tickets || [];
      const critical = tickets.flatMap((t) => t.issues_found || []).filter((i) => i.severity === "critical").length;
      const major = tickets.flatMap((t) => t.issues_found || []).filter((i) => i.severity === "major").length;
      pushChatMessage(
        "assistant",
        `Analysis complete. ${ragCitations.length} source(s) retrieved from RAG.`
      );
      toast.success(`Analysis complete — score ${a.overall_score ?? "—"}/10 across ${data.ticket_count} ticket(s)`);
    } catch (e) {
      // Remove the temporary analyzing message on error too
      setChatMessages((prev) => prev.filter((m) => m.id !== tempMsgId));
      if (e.name !== "AbortError") {
        pushChatMessage("assistant", `Analysis failed: ${e.message}`);
        setError(e.message);
        toast.error(`Analysis failed: ${e.message}`);
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

      const nextCitations = logRagDebug("feedback-response", data);
      setAnalyzeSession((prev) => ({
        ...(prev || {}),
        analysis: data.analysis,
        // keep previous citations if feedback response does not return fresh ones
        rag_citations: nextCitations.length ? nextCitations : prev?.rag_citations || [],
      }));

      setSession((prev) =>
        prev
          ? {
              ...prev,
              pending_tickets: buildPendingTicketsFromAnalysis(data.analysis),
              awaiting_confirmation: true,
            }
          : prev
      );

      // Remove the temporary refining message
      setChatMessages((prev) => prev.filter((m) => m.id !== tempMsgId));
      pushChatMessage("assistant", `Analysis revised (revision ${data.revision}). Review the updated panel.`);
      toast.success(`Analysis revised (revision ${data.revision})`);
    } catch (e) {
      // Remove the temporary refining message on error
      setChatMessages((prev) => prev.filter((m) => m.id !== tempMsgId));
      if (e.name !== "AbortError") {
        pushChatMessage("assistant", `Feedback failed: ${e.message}`);
        setError(e.message);
        toast.error(`Feedback failed: ${e.message}`);
      }
    }
  }

  function handleApplied(ticketKey, data) {
    pushChatMessage("assistant", `Applied suggestions to ${ticketKey} in JIRA.`);
    
    // Track applied ticket
    setAppliedTickets((prev) => {
      const updated = new Set(prev);
      updated.add(ticketKey);
      
      // Check if all tickets have been applied
      const totalTickets = analyzeSession?.analysis?.tickets?.length || 0;
      if (updated.size >= totalTickets && totalTickets > 0) {
        // All tickets applied - close the analysis panel
        setTimeout(() => {
          setAnalyzeSession(null);
          setAppliedTickets(new Set());
        }, 1500); // Small delay so user sees the success state
      }
      
      return updated;
    });
  }

  async function handleSaveAttachment(index) {
    try {
      const response = await fetch(`${API_BASE_URL}/chat/sessions/${session.session_id}/attachments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index, content: editedContent }),
      });
      
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Failed to update attachment");
      }
      
      setSession(data);
      setEditingAttachment(null);
      setEditedContent("");
      toast.success("Attachment updated");
    } catch (error) {
      toast.error(`Failed to update attachment: ${error.message}`);
    }
  }

  function handleDeleteAttachment(index, filename) {
    setConfirmModal({
      isOpen: true,
      title: "Remove Attachment",
      message: `Are you sure you want to remove "${filename}" from context? This action cannot be undone.`,
      onConfirm: async () => {
        setConfirmModal({ isOpen: false, title: "", message: "", onConfirm: null });
        
        try {
          const response = await fetch(`${API_BASE_URL}/chat/sessions/${session.session_id}/attachments`, {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ index }),
          });
          
          const data = await response.json();
          if (!response.ok) {
            throw new Error(data.detail || "Failed to remove attachment");
          }
          
          setSession(data);
          setEditingAttachment(null);
          setEditedContent("");
          toast.success("Attachment removed");
        } catch (error) {
          toast.error(`Failed to remove attachment: ${error.message}`);
        }
      }
    });
  }

  async function handleDeleteRagDocument(docId, docTitle) {
    setConfirmModal({
      isOpen: true,
      title: "Delete RAG Document",
      message: `Are you sure you want to delete "${docTitle}" from the knowledge base? This action cannot be undone.`,
      onConfirm: async () => {
        setConfirmModal({ isOpen: false, title: "", message: "", onConfirm: null });
        
        try {
          const response = await fetch(`${API_BASE_URL}/rag/documents/${docId}`, {
            method: "DELETE",
          });
          
          const data = await response.json();
          if (!response.ok) {
            throw new Error(data.detail || "Failed to delete document");
          }
          
          // Remove from ingestion history
          setIngestionHistory((prev) => prev.filter((doc) => doc.id !== docId));
          toast.success(`Deleted "${docTitle}" from knowledge base`);
        } catch (error) {
          toast.error(`Failed to delete document: ${error.message}`);
        }
      }
    });
  }

  async function handleUploadRagDocuments(event) {
    const selectedFiles = Array.from(event.target.files || []);
    if (!selectedFiles.length) return;

    setIsUploadingToRag(true);
    setRagFiles((prev) => [...prev, ...selectedFiles]);

    try {
      // Upload files one at a time
      let totalChunks = 0;
      for (const file of selectedFiles) {
        const formData = new FormData();
        formData.append("file", file); // Backend expects "file", not "documents"

        const response = await fetch(`${API_BASE_URL}/rag/ingest/document`, {
          method: "POST",
          body: formData,
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Failed to ingest documents to RAG");
        }

        totalChunks += data.chunks_created || 0;

        // Update ingestion status for this file
        setRagIngestionStatus((prev) => ({
          ...prev,
          [file.name]: { status: "completed", chunks: data.chunks_created || 0 },
        }));
      }

      toast.success(
        `Ingested ${selectedFiles.length} document(s) to knowledge base (${totalChunks} chunks created)`
      );

      // Reload ingestion history to show newly added documents
      const historyResponse = await fetch(`${API_BASE_URL}/rag/documents?page=1&page_size=50`);
      if (historyResponse.ok) {
        const historyData = await historyResponse.json();
        setIngestionHistory(historyData.documents || []);
      }

      // Clear uploading files and status
      setRagFiles([]);
      setRagIngestionStatus({});
    } catch (error) {
      selectedFiles.forEach((file) => {
        setRagIngestionStatus((prev) => ({
          ...prev,
          [file.name]: { status: "failed", error: error.message },
        }));
      });
      toast.error(`Failed to ingest documents: ${error.message}`);
    } finally {
      setIsUploadingToRag(false);
      if (ragFileInputRef.current) ragFileInputRef.current.value = "";
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!message.trim() && files.length === 0) return;
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
      
      // Show warning for failed file extractions
      if (data.failed_files && data.failed_files.length > 0) {
        const fileList = data.failed_files.join(", ");
        toast.error(`Could not extract text from: ${fileList}. Only text-based (non-scanned) PDFs are supported.`);
      }
    } catch (nextError) {
      if (nextError.name !== "AbortError") {
        setError(nextError.message);
        toast.error(nextError.message);
      }
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
      const createdTickets = data.last_created
        ? Object.values(data.last_created).flat()
        : [];
      if (createdTickets.length > 0) {
        const createdList = createdTickets.map(t => `  • ${t.key}: ${t.summary}`).join('\n');
        pushChatMessage("assistant", `Successfully created ${createdTickets.length} ticket(s) in JIRA:\n${createdList}`);
        toast.success(`Created ${createdTickets.length} ticket(s) in JIRA`);
      } else {
        pushChatMessage("assistant", "Tickets have been created in JIRA.");
        toast.success("Tickets have been created in JIRA.");
      }
    } catch (nextError) {
      setChatMessages((prev) => prev.filter((m) => m.id !== tempMsgId));
      setError(nextError.message);
      pushChatMessage("assistant", `Failed to create tickets: ${nextError.message}`);
      toast.error(`Failed to create tickets: ${nextError.message}`);
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
            {files.length > 0 && (
              <div className="attached-files">
                {files.map((file, index) => (
                  <div key={`${file.name}-${index}`} className="file-chip">
                    <FileText size={16} className="file-icon" />
                    <span className="file-name">{file.name}</span>
                    <button
                      type="button"
                      className="remove-file-btn"
                      onClick={() => {
                        setFiles((prev) => prev.filter((_, i) => i !== index));
                      }}
                      title="Remove file"
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="composer-bar">
              <button
                type="button"
                className="icon-btn"
                title="Attach files"
                onClick={() => fileInputRef.current?.click()}
              >
                <Paperclip size={20} />
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
                  <Square size={20} fill="currentColor" />
                </button>
              ) : (
                <button className="icon-btn send-icon-btn" type="submit" title="Send">
                  <Send size={20} />
                </button>
              )}
            </div>

            {error ? <p className="error-banner">{error}</p> : null}
          </form>
        </section>

        <aside className="inspector-column">
          {analyzeSession ? (
            <section className="glass-panel side-panel">
              <div className="panel-header slim">
                <div
                  style={{
                    display: "flex",
                    gap: 10,
                    flexWrap: "wrap",
                    alignItems: "center",
                    marginRight: 12,
                    marginLeft: 12,
                    padding: "6px",
                    borderRadius: 12,
                    background: "rgba(255, 255, 255, 0.06)",
                    border: "1px solid rgba(255, 255, 255, 0.12)",
                  }}
                >
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={() => setInspectorTab("analysis")}
                    style={{
                      padding: "15px 45px",
                      background: inspectorTab === "analysis" ? "rgba(58, 134, 255, 0.16)" : "transparent",
                      border: inspectorTab === "analysis" ? "1px solid rgba(58, 134, 255, 0.35)" : "1px solid transparent",
                      borderRadius: 8,
                      color: inspectorTab === "analysis" ? "var(--text-primary)" : "var(--text-secondary)",
                      fontWeight: inspectorTab === "analysis" ? 700 : 500,
                      textDecoration: inspectorTab === "analysis" ? "underline" : "none",
                      textUnderlineOffset: "5px",
                      boxShadow: "none",
                      cursor: "pointer",
                    }}
                  >
                    Analysis
                  </button>
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={() => setInspectorTab("draft")}
                    style={{
                      padding: "15px 45px",
                      background: inspectorTab === "draft" ? "rgba(58, 134, 255, 0.16)" : "transparent",
                      border: inspectorTab === "draft" ? "1px solid rgba(58, 134, 255, 0.35)" : "1px solid transparent",
                      borderRadius: 8,
                      color: inspectorTab === "draft" ? "var(--text-primary)" : "var(--text-secondary)",
                      fontWeight: inspectorTab === "draft" ? 700 : 500,
                      textDecoration: inspectorTab === "draft" ? "underline" : "none",
                      textUnderlineOffset: "5px",
                      boxShadow: "none",
                      cursor: "pointer",
                    }}
                  >
                    Draft
                  </button>
                </div>
                <button
                  className="exit-btn"
                  onClick={() => {
                    setAnalyzeSession(null);
                    setInspectorTab("analysis");
                  }}
                  title="Exit analysis mode"
                >
                  <X size={16} />
                </button>
              </div>

              {inspectorTab === "analysis" ? (
                <section className="analysis-panel" style={{ marginTop: 8 }}>
                  <div className="panel-header slim" style={{ padding: 0, marginBottom: 10 }}>
                    <div>
                      <p className="panel-kicker"><Search size={14} style={{display: 'inline', verticalAlign: 'middle', marginRight: '4px'}} /> Analysis</p>
                      <h3>{analyzeSession.source || 'Ticket Review'}</h3>
                    </div>
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

                  {analyzeSession?.rag_citations?.length > 0 && (
                    <p className="muted-copy" style={{ marginBottom: 10 }}>
                      RAG evidence loaded: <strong>{analyzeSession.rag_citations.length}</strong> source(s)
                    </p>
                  )}

                  <div className="analysis-list">
                    {(analyzeSession.analysis?.tickets || []).map((ticket, index) => (
                      <AnalysisCard
                        key={`${ticket.key}-${analyzeSession.analysis?.overall_score}-${index}`}
                        ticket={ticket}
                        sessionId={analyzeSession.session_id}
                        onApplied={handleApplied}
                        globalSources={analyzeSession.rag_citations || []}
                      />
                    ))}
                    {!(analyzeSession.analysis?.tickets?.length) && (
                      <p className="muted-copy">No tickets in analysis.</p>
                    )}
                  </div>
                </section>
              ) : (
                <section className="draft-section" style={{ marginTop: 8 }}>
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
                        toast.error('Failed to update project key');
                      }
                    }}
                  />
                </section>
              )}
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
                    toast.error('Failed to update project key');
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

            {/* Chat attachments section */}
            <div style={{ marginBottom: "24px" }}>
              <p style={{ fontSize: "0.85rem", fontWeight: "600", marginBottom: "12px", color: "var(--text-secondary)" }}>
                Chat Context
              </p>
              {session?.attachments?.length ? (
                <div 
                  className="summary-list"
                  style={{
                    maxHeight: "180px",
                    overflowY: "auto",
                    paddingRight: "4px",
                  }}
                >
                  {session.attachments.map((attachment, index) => (
                    <div className="summary-card attachment-card" key={`${attachment.name}-${index}`}>
                      <div className="attachment-header">
                        <strong>{attachment.name}</strong>
                        {editingAttachment === index ? (
                          <div className="attachment-actions">
                            <button
                              className="attachment-action-btn save"
                              onClick={() => handleSaveAttachment(index)}
                              title="Save changes"
                            >
                              Save
                            </button>
                            <button
                              className="attachment-action-btn cancel"
                              onClick={() => {
                                setEditingAttachment(null);
                                setEditedContent("");
                              }}
                              title="Cancel"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : editingAttachment === null ? (
                          <div className="attachment-actions">
                            <button
                              className="attachment-action-btn delete"
                              onClick={() => handleDeleteAttachment(index, attachment.name)}
                              title="Remove attachment"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        ) : null}
                      </div>
                      {editingAttachment === index ? (
                        <textarea
                          className="attachment-editor"
                          value={editedContent}
                          onChange={(e) => setEditedContent(e.target.value)}
                          rows={10}
                        />
                      ) : (
                        <p>{attachment.preview}</p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted-copy">No chat attachments yet.</p>
              )}
            </div>

            {/* RAG documents section */}
            <div>
              <p style={{ fontSize: "0.85rem", fontWeight: "600", marginBottom: "12px", color: "var(--text-secondary)" }}>
                Knowledge Base
              </p>
              <div style={{ marginBottom: "12px" }}>
                <button
                  type="button"
                  className="icon-btn"
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    fontSize: "0.9rem",
                    marginBottom: "8px",
                    border: "1px dashed var(--border-subtle)",
                    borderRadius: "6px",
                    cursor: "pointer",
                    backgroundColor: "rgba(58, 134, 255, 0.05)",
                    color: "var(--text-primary)",
                    transition: "all 0.2s",
                  }}
                  onClick={() => ragFileInputRef.current?.click()}
                  disabled={isUploadingToRag}
                >
                  {isUploadingToRag ? "Uploading..." : "➕ Add documents to RAG"}
                </button>
                <input
                  ref={ragFileInputRef}
                  type="file"
                  multiple
                  style={{ display: "none" }}
                  onChange={handleUploadRagDocuments}
                />
              </div>

              {/* Display already-ingested documents */}
              {ingestionHistory.length > 0 && (
                <div style={{ marginBottom: "16px" }}>
                  <p style={{ fontSize: "0.75rem", fontWeight: "500", marginBottom: "8px", color: "var(--text-secondary)", textTransform: "uppercase" }}>
                    Ingested ({ingestionHistory.length})
                  </p>
                  <div 
                    className="summary-list"
                    style={{
                      maxHeight: "200px",
                      overflowY: "auto",
                      paddingRight: "4px",
                    }}
                  >
                    {ingestionHistory.map((doc) => (
                      <div className="summary-card" key={doc.id}>
                        <div className="attachment-header">
                          <div style={{ flex: 1 }}>
                            <strong>{doc.title || doc.source_id}</strong>
                            <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "4px" }}>
                              <span style={{ textTransform: "capitalize" }}>{doc.source_type}</span>
                              {doc.chunk_count && ` • ${doc.chunk_count} chunks`}
                              {doc.created_at && ` • ${new Date(doc.created_at).toLocaleDateString()}`}
                            </p>
                          </div>
                          <div className="attachment-actions">
                            <button
                              className="attachment-action-btn delete"
                              onClick={() => handleDeleteRagDocument(doc.id, doc.title || doc.source_id)}
                              title="Delete from knowledge base"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Display currently uploading files */}
              {ragFiles.length > 0 && (
                <div>
                  <p style={{ fontSize: "0.75rem", fontWeight: "500", marginBottom: "8px", color: "var(--text-secondary)", textTransform: "uppercase" }}>
                    Uploading ({ragFiles.length})
                  </p>
                  <div 
                    className="summary-list"
                    style={{
                      maxHeight: "150px",
                      overflowY: "auto",
                      paddingRight: "4px",
                    }}
                  >
                    {ragFiles.map((file, index) => {
                      const status = ragIngestionStatus[file.name];
                      const isCompleted = status?.status === "completed";
                      const isFailed = status?.status === "failed";

                      return (
                        <div
                          className="summary-card"
                          key={`${file.name}-${index}`}
                          style={{
                            opacity: isFailed ? 0.6 : 1,
                            borderColor: isFailed ? "var(--error-color, #ff5757)" : "var(--border-subtle)",
                          }}
                        >
                          <div className="attachment-header">
                            <div style={{ flex: 1 }}>
                              <strong>{file.name}</strong>
                              <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "4px" }}>
                                {!status ? (
                                  "⏳ Queued..."
                                ) : isCompleted ? (
                                  <>✓ {status.chunks} chunks created</>
                                ) : isFailed ? (
                                  <>✗ {status.error}</>
                                ) : null}
                              </p>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Empty state */}
              {ingestionHistory.length === 0 && ragFiles.length === 0 && (
                <p className="muted-copy">No documents added to knowledge base yet.</p>
              )}
            </div>
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

      <ConfirmModal
        isOpen={confirmModal.isOpen}
        title={confirmModal.title}
        message={confirmModal.message}
        onConfirm={confirmModal.onConfirm}
        onCancel={() => setConfirmModal({ isOpen: false, title: "", message: "", onConfirm: null })}
        confirmText="Remove"
        cancelText="Cancel"
        variant="danger"
      />
    </main>
  );
}