import { JIRA_URL_RE, EPIC_KEYWORD_RE, PROJECT_KEY_RE, TICKET_KEY_RE } from "./constants";

function detectAnalyzeIntent(text) {
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
  return content.split("\n").map((line, i) => {
    if (line.startsWith("- ")) {
      const text = line.slice(2);
      return text.length <= 40
        ? <div key={i} className="msg-bullet">{text}</div>
        : <div key={i} className="msg-list-item">{text}</div>;
    }
    if (line.trim() === "") return <br key={i} />;
    return <p key={i}>{line}</p>;
  });
}

export { detectAnalyzeIntent, renderContent };
