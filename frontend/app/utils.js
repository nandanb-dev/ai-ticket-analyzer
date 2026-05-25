import { JIRA_URL_RE, EPIC_KEYWORD_RE, PROJECT_KEY_RE, TICKET_KEY_RE } from "./constants";

function detectAnalyzeIntent(text) {
  const lowerText = text.toLowerCase();

  // If user wants to create/draft tickets, don't treat this as analyze intent.
  if (/^(create|generate|make|draft|build|add)\s/i.test(text)) {
    return null;
  }

  // If text looks like ticket JSON payload, don't auto-route to analyze.
  if (text.includes('"key"') || text.includes('"issue_type"') || text.includes('"summary"')) {
    return null;
  }

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
  // Parse inline markdown: **bold**, *italic*, _italic_, `code`
  const parseInlineMarkdown = (text) => {
    // Replace **bold** and __bold__
    let parsed = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    parsed = parsed.replace(/__(.+?)__/g, '<strong>$1</strong>');
    // Replace *italic* and _italic_ (but not inside words)
    parsed = parsed.replace(/(?<!\w)\*([^*]+)\*(?!\w)/g, '<em>$1</em>');
    parsed = parsed.replace(/(?<!\w)_([^_]+)_(?!\w)/g, '<em>$1</em>');
    // Replace `code`
    parsed = parsed.replace(/`([^`]+)`/g, '<code>$1</code>');
    return parsed;
  };

  return content.split("\n").map((line, i) => {
    // Handle headers
    if (line.startsWith("### ")) {
      return <h4 key={i} dangerouslySetInnerHTML={{ __html: parseInlineMarkdown(line.slice(4)) }} />;
    }
    if (line.startsWith("## ")) {
      return <h3 key={i} dangerouslySetInnerHTML={{ __html: parseInlineMarkdown(line.slice(3)) }} />;
    }
    if (line.startsWith("# ")) {
      return <h2 key={i} dangerouslySetInnerHTML={{ __html: parseInlineMarkdown(line.slice(2)) }} />;
    }
    // Handle numbered lists (1. 2. 3.)
    const numberedMatch = line.match(/^(\d+)\.\s+(.+)/);
    if (numberedMatch) {
      return (
        <div key={i} className="msg-numbered-item">
          <span className="msg-number">{numberedMatch[1]}.</span>
          <span dangerouslySetInnerHTML={{ __html: parseInlineMarkdown(numberedMatch[2]) }} />
        </div>
      );
    }
    // Handle bullet points
    if (line.startsWith("- ")) {
      const text = line.slice(2);
      return (
        <div key={i} className={text.length <= 40 ? "msg-bullet" : "msg-list-item"}>
          <span dangerouslySetInnerHTML={{ __html: parseInlineMarkdown(text) }} />
        </div>
      );
    }
    if (line.trim() === "") return <br key={i} />;
    return <p key={i} dangerouslySetInnerHTML={{ __html: parseInlineMarkdown(line) }} />;
  });
}

export { detectAnalyzeIntent, renderContent };

export function normalizeRagCitations(payload) {
  const raw =
    payload?.rag_citations ||
    payload?.analysis?.rag_citations ||
    payload?.rag?.citations ||
    payload?.citations ||
    [];

  if (!Array.isArray(raw)) return [];

  return raw.map((item, idx) => ({
    id: item?.id || item?.chunk_id || item?.doc_id || `src-${idx + 1}`,
    title: item?.title || item?.document_title || item?.source || "Untitled source",
    url: item?.url || item?.uri || item?.link || "",
    snippet: item?.snippet || item?.excerpt || item?.text || "",
    score: typeof item?.score === "number" ? item.score : null,
    sourceType: item?.source_type || item?.type || "document",
  }));
}
