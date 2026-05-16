"""
rag/ingestion/jira_ingestion.py
───────────────────────────────
Ingest Jira tickets (issues, comments, resolutions, labels, metadata)
into the RAG knowledge base.

For each ticket we:
  1. Build a rich text representation (summary, description, AC, comments …)
  2. Clean and chunk it
  3. Generate embeddings
  4. Store in rag_documents + rag_chunks

Metadata extracted per chunk:
  - ticket_type  → issue_type (bug / story / task / epic)
  - severity     → priority   (critical / high / medium / low)
  - component    → first component or label that looks like a component
  - team         → assignee team or sprint name
  - service      → labels / components matching known services
  - source_id    → Jira ticket key (e.g. PROJ-123)
  - source_url   → {JIRA_URL}/browse/{key}
"""

import logging
from typing import Any, Dict, List, Optional

import requests
from fastapi import HTTPException

from config import JIRA_API_TOKEN, JIRA_URL, JIRA_USERNAME
from rag.cleaning import clean_document
from rag.ingestion.base import ingest_document
from rag.models import DocumentRecord

logger = logging.getLogger(__name__)

_PRIORITY_MAP = {
    "blocker": "critical",
    "critical": "critical",
    "highest": "critical",
    "high": "high",
    "major": "high",
    "medium": "medium",
    "normal": "medium",
    "low": "low",
    "minor": "low",
    "lowest": "low",
    "trivial": "low",
}


# ── Public API ────────────────────────────────────────────────────────────────

def ingest_project(project_key: str) -> List[dict]:
    """
    Ingest all tickets for a Jira project.

    Args:
        project_key: e.g. "PROJ"

    Returns:
        List of per-ticket ingestion result dicts.
    """
    from services.jira import fetch_project_tickets
    tickets = fetch_project_tickets(project_key)
    return _ingest_tickets(tickets)


def ingest_epic(epic_key: str) -> List[dict]:
    """
    Ingest an epic and all its child tickets.

    Args:
        epic_key: e.g. "PROJ-42"

    Returns:
        List of per-ticket ingestion result dicts.
    """
    from services.jira import fetch_epic_tickets
    tickets = fetch_epic_tickets(epic_key)
    return _ingest_tickets(tickets)


def ingest_ticket(ticket_key: str) -> List[dict]:
    """
    Ingest a single Jira ticket.

    Args:
        ticket_key: e.g. "PROJ-123"

    Returns:
        List containing one ingestion result dict.
    """
    from services.jira import fetch_ticket_by_key
    tickets = fetch_ticket_by_key(ticket_key)
    return _ingest_tickets(tickets)


def ingest_tickets_list(tickets: List[Dict[str, Any]]) -> List[dict]:
    """
    Ingest an already-fetched list of simplified Jira ticket dicts.

    Useful when the caller already has the ticket data (e.g. after running
    an analysis) and wants to add it to the knowledge base without a
    second round-trip to Jira.
    """
    return _ingest_tickets(tickets)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ingest_tickets(tickets: List[Dict[str, Any]]) -> List[dict]:
    results = []
    for ticket in tickets:
        try:
            doc = _ticket_to_document(ticket)
            result = ingest_document(doc)
            result["source_id"] = ticket.get("key", "")
            results.append(result)
        except Exception as exc:
            key = ticket.get("key", "unknown")
            logger.error("Failed to ingest ticket %s: %s", key, exc)
            results.append({"source_id": key, "error": str(exc)})
    return results


def _ticket_to_document(ticket: Dict[str, Any]) -> DocumentRecord:
    """Convert a simplified Jira ticket dict to a DocumentRecord."""
    key = ticket.get("key", "")
    summary = ticket.get("summary", "")
    description = ticket.get("description", "") or ""
    issue_type = (ticket.get("issue_type") or "").lower()
    priority = (ticket.get("priority") or "").lower()
    status = ticket.get("status", "")
    labels = ticket.get("labels") or []
    assignee = ticket.get("assignee", "") or ""
    story_points = ticket.get("story_points")
    parent_key = ticket.get("parent_key", "") or ""
    parent_summary = ticket.get("parent_summary", "") or ""
    comments = ticket.get("comments") or []
    resolution = ticket.get("resolution") or ""
    components = ticket.get("components") or []
    sprint = ticket.get("sprint") or ""
    reporter = ticket.get("reporter") or ""

    # ── Build rich text content ──
    lines = [
        f"# {key}: {summary}",
        "",
        f"Type: {issue_type.title()}  |  Priority: {priority.title()}  |  Status: {status}",
    ]

    if story_points is not None:
        lines.append(f"Story Points: {story_points}")

    if assignee:
        lines.append(f"Assignee: {assignee}")

    if reporter:
        lines.append(f"Reporter: {reporter}")

    if parent_key:
        lines.append(f"Parent: {parent_key}" + (f" — {parent_summary}" if parent_summary else ""))

    if sprint:
        lines.append(f"Sprint: {sprint}")

    if components:
        lines.append(f"Components: {', '.join(components)}")

    if labels:
        lines.append(f"Labels: {', '.join(labels)}")

    if resolution:
        lines.append(f"Resolution: {resolution}")

    lines.append("")

    if description.strip():
        lines.append("## Description")
        lines.append(description.strip())
        lines.append("")

    # Acceptance criteria / test cases from description (if structured)
    ac_text = _extract_section(description, ["acceptance criteria", "ac:", "given/when/then"])
    if ac_text:
        lines.append("## Acceptance Criteria")
        lines.append(ac_text)
        lines.append("")

    test_cases_text = _extract_section(description, ["test cases", "testing:", "test scenarios"])
    if test_cases_text:
        lines.append("## Test Cases")
        lines.append(test_cases_text)
        lines.append("")

    # Comments (only non-empty, up to 10)
    if comments:
        lines.append("## Comments")
        for comment in comments[:10]:
            author = comment.get("author", "")
            body = comment.get("body", "").strip()
            if body:
                if author:
                    lines.append(f"**{author}:** {body}")
                else:
                    lines.append(body)
        lines.append("")

    raw_content = "\n".join(lines)
    raw_content = clean_document(raw_content, source_type="jira")

    # ── Extract structured metadata ──
    severity = _normalize_priority(priority)
    component = _extract_component(components, labels)
    service = _extract_service(labels, components)

    metadata = {
        "ticket_type": issue_type,
        "severity": severity,
        "component": component,
        "team": assignee,
        "service": service,
        "labels": labels,
        "status": status,
        "story_points": story_points,
        "parent_key": parent_key,
    }

    source_url = f"{JIRA_URL}/browse/{key}" if JIRA_URL and key else None

    return DocumentRecord(
        source_type="jira",
        source_id=key,
        title=f"{key}: {summary}",
        raw_content=raw_content,
        source_url=source_url,
        metadata=metadata,
    )


def _normalize_priority(priority: str) -> str:
    return _PRIORITY_MAP.get(priority.lower(), "medium")


def _extract_component(components: List[str], labels: List[str]) -> Optional[str]:
    """Return the most relevant component name."""
    if components:
        return components[0]
    # Fall back to first label that looks like a component (not a generic word)
    generic = {"frontend", "backend", "api", "ui", "ux", "test", "testing", "bug", "feature"}
    for label in labels:
        if label.lower() not in generic:
            return label
    return None


def _extract_service(labels: List[str], components: List[str]) -> Optional[str]:
    """Extract service name from labels / components."""
    service_keywords = [
        "service", "svc", "worker", "consumer", "producer", "gateway",
        "proxy", "handler", "processor",
    ]
    all_terms = [l.lower() for l in labels] + [c.lower() for c in components]
    for term in all_terms:
        for kw in service_keywords:
            if kw in term:
                return term
    return None


def _extract_section(text: str, keywords: List[str]) -> str:
    """
    Extract a named section from free-form description text.
    Returns the section content if found, empty string otherwise.
    """
    import re
    lower = text.lower()
    for kw in keywords:
        idx = lower.find(kw)
        if idx != -1:
            # Find the section from this keyword to the next heading or end
            start = idx
            rest = text[start:]
            # Next heading starts with a line that begins with ** or ## or ALL CAPS
            match = re.search(r"\n(?=\*\*|##|[A-Z]{3,}:)", rest[len(kw):])
            if match:
                return rest[: len(kw) + match.start()].strip()
            return rest.strip()
    return ""


# ── Fetch comments (if not already in the ticket dict) ───────────────────────

def fetch_ticket_comments(ticket_key: str) -> List[Dict[str, Any]]:
    """Fetch comments for a Jira ticket via the REST API."""
    if not all([JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN]):
        return []
    try:
        resp = requests.get(
            f"{JIRA_URL}/rest/api/3/issue/{ticket_key}/comment",
            params={"maxResults": 50},
            auth=(JIRA_USERNAME, JIRA_API_TOKEN),
            headers={"Accept": "application/json"},
            timeout=15,
        )
        if not resp.ok:
            return []
        data = resp.json()
        comments = []
        for c in data.get("comments", []):
            author = (c.get("author") or {}).get("displayName", "")
            body_adf = c.get("body") or {}
            from services.jira import _adf_to_text
            body_text = _adf_to_text(body_adf) if isinstance(body_adf, dict) else str(body_adf)
            comments.append({"author": author, "body": body_text})
        return comments
    except Exception as exc:
        logger.warning("Failed to fetch comments for %s: %s", ticket_key, exc)
        return []
