const TICKET_KEY_RE = /\b([A-Za-z][A-Za-z0-9]+-\d+)\b/i;
const JIRA_URL_RE = /atlassian\.net\/browse\/([A-Za-z][A-Za-z0-9]+-\d+)/i;
const PROJECT_KEY_RE = /\bproject[:\s]+([A-Za-z][A-Za-z0-9]+)\b/i;
const EPIC_KEYWORD_RE = /\bepic[:\s]+([A-Za-z][A-Za-z0-9]+-\d+)\b/i;
const ANALYZE_INTENT_RE = /\b(analyz[e]?|review|inspect|check|audit|improve|fix|assess)\b.*\b(ticket|issue|story|task|epic|jira)\b|\b(ticket|issue|story|task|epic|jira)\b.*\b(analyz[e]?|review|inspect|check|audit|improve|fix|assess)\b/i;

export {
  TICKET_KEY_RE,
  JIRA_URL_RE,
  PROJECT_KEY_RE,
  EPIC_KEYWORD_RE,
  ANALYZE_INTENT_RE
};
