import { JIRA_URL_RE, EPIC_KEYWORD_RE, PROJECT_KEY_RE, TICKET_KEY_RE } from "./constants";

function detectAnalyzeIntent(text) {
  const lowerText = text.toLowerCase();
  
  // If user wants to CREATE a ticket, don't route to analyze
  // Even if the message contains a ticket key pattern (e.g., in JSON)
  if (/^(create|generate|make|draft|build|add)\s+(a\s+)?(ticket|story|task|epic|issue)/i.test(text)) {
    return null;
  }
  
  // If text contains JSON-like structure with "key", it's likely a create request
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

/**
 * Detect if a message looks like feedback for an analysis.
 * Returns true if the message should be treated as analysis feedback.
 */
function detectAnalysisFeedback(text) {
  const lowerText = text.toLowerCase().trim();
  
  // FIRST: Check if this is a NEW create request (not feedback)
  // "create ticket for X" or "create a story" etc. should NOT be feedback
  if (/^(create|generate|make|draft|build|add)\s+(a\s+)?(new\s+)?(ticket|story|task|epic|issue|bug)/i.test(text)) {
    return false;
  }
  
  // Feedback keywords that indicate the user is responding to analysis
  const feedbackPatterns = [
    // Explicit feedback/revision requests
    /\b(change|update|revise|modify|fix|correct|adjust|edit)\b.*\b(score|severity|priority|description|summary|analysis|ticket|issue)/i,
    /\b(score|severity|priority|description|summary)\b.*\b(should be|is wrong|incorrect|too high|too low)/i,
    // Agreement/approval
    /^(yes|no|ok|okay|correct|right|wrong|agree|disagree|approved?|reject|looks good|lgtm|ship it)\b/i,
    // References to the analysis
    /\b(the analysis|your analysis|this analysis|the score|the severity|the suggestion|the recommendation)\b/i,
    // Explicit feedback markers
    /^(feedback|comment|suggestion|note|correction|change request):/i,
    // Apply/confirm actions - but NOT "create ticket" (that's a new request)
    /\b(apply|confirm|push|submit)\b.*\b(changes?|updates?|to jira)/i,
    /\b(create|push)\b.*\b(in jira|to jira)\b/i,
    // Short affirmations (less than 15 chars and common responses)
    /^(yes|no|ok|okay|sure|fine|good|great|thanks|done|next)\.?$/i,
  ];
  
  for (const pattern of feedbackPatterns) {
    if (pattern.test(lowerText)) {
      return true;
    }
  }
  
  // If the message is very short (under 30 chars) and doesn't look like a question or new topic,
  // it's more likely to be feedback
  if (lowerText.length < 30 && !lowerText.includes("?") && !lowerText.startsWith("i want") && !lowerText.startsWith("create") && !lowerText.startsWith("build")) {
    // Check if it contains any ticket-related words
    if (/\b(ticket|story|epic|task|bug|issue|priority|severity|score)\b/i.test(lowerText)) {
      return true;
    }
  }
  
  return false;
}

export { detectAnalyzeIntent, renderContent, detectAnalysisFeedback };

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
