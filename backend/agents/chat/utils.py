from textwrap import shorten
from typing import Any, List, Tuple
import logging

from agents.chat.models import ChatState, ClarificationAnalysis, ClarificationQuestion

logger = logging.getLogger(__name__)


def format_messages(messages: list[dict[str, str]]) -> str:
    if not messages:
        return "No previous conversation yet."
    return "\n".join(
        f"{message['role'].upper()}: {message['content']}"
        for message in messages[-12:]
    )


def format_attachments(attachments: list[dict[str, str]]) -> str:
    if not attachments:
        return "No uploaded documents yet."
    parts = []
    for attachment in attachments[-8:]:
        preview = shorten(attachment["content"].replace("\n", " "), width=2500, placeholder=" ...")
        parts.append(f"Document: {attachment['name']}\n{preview}")
    return "\n\n".join(parts)


def build_generation_context(state: ChatState) -> str:
    sections = [
        "Conversation context:\n" + format_messages(state["conversation_history"]),
        "Uploaded context:\n" + format_attachments(state["attachments"]),
    ]
    if state["context_text"].strip():
        sections.append("Additional context from this turn:\n" + state["context_text"].strip())
    sections.append("Latest instruction:\n" + state["latest_user_message"].strip())
    return "\n\n".join(sections)


def summarize_ticket_preview(ticket_data: dict[str, Any]) -> str:
    epics = ticket_data.get("epics", [])
    stories = ticket_data.get("stories", [])
    tasks = ticket_data.get("tasks", [])
    sample_titles = [item["summary"] for item in (epics + stories + tasks)[:6]]
    preview_lines = "\n".join(f"- {title}" for title in sample_titles) if sample_titles else "- No ticket titles generated"
    return (
        f"I drafted {len(epics)} epics, {len(stories)} stories, and {len(tasks)} tasks based on the chat context.\n\n"
        f"Preview:\n{preview_lines}\n\n"
        "Review the draft below. When it looks right, confirm to create the tickets in Jira."
    )


def summarize_pending_tickets(pending: dict[str, Any]) -> str:
    """Build a summary of pending tickets for the edit_draft chain."""
    lines = []
    for ticket_type in ["epics", "stories", "tasks"]:
        ticket_list = pending.get(ticket_type, [])
        if ticket_list:
            singular = ticket_type.rstrip("s")
            for i, ticket in enumerate(ticket_list):
                summary = ticket.get("summary", "Untitled")
                priority = ticket.get("priority", "Medium")
                lines.append(f"{singular} {i + 1}: \"{summary}\" (priority: {priority})")
    return "\n".join(lines) if lines else "No pending tickets"


def retrieve_rag_context(query: str, project_key: str = "") -> Tuple[str, List[dict]]:
    """
    Retrieve relevant context from the RAG knowledge base.
    
    Args:
        query: The search query (user message + context)
        project_key: Optional project key (reserved for future filtering)
    
    Returns:
        Tuple of (context_text, citations)
    """
    try:
        from rag.retrieval import retrieve, retrieve_keyword_first
        from rag.context_builder import build_context

        cleaned_query = (query or "").strip()
        if not cleaned_query:
            return "", []
        
        # Fast path: lexical keyword retrieval first to reduce latency and improve
        # deterministic citation hits when terms appear in ingested docs.
        results = retrieve_keyword_first(
            query=cleaned_query,
            top_n=8,
            metadata_filter=None,
        )

        # Fallback path: hybrid semantic retrieval only when keyword retrieval finds nothing.
        if not results:
            results = retrieve(
                query=cleaned_query,
                top_k=12,
                rerank_top_n=6,
                metadata_filter=None,
            )
        
        if not results:
            return "", []
        
        # Build context string and citations
        context_text, citations = build_context(results, token_budget=2000)
        
        # Convert citations to dicts for JSON serialization
        citation_dicts = [
            {
                "source_type": c.source_type,
                "source_id": c.source_id,
                "title": c.title,
                "source_url": c.source_url,
                "excerpt": c.excerpt,
                "score": c.score,
            }
            for c in citations
        ]
        
        return context_text, citation_dicts
        
    except ImportError:
        logger.warning("RAG module not available, skipping RAG retrieval")
        return "", []
    except Exception as exc:
        logger.warning(f"RAG retrieval failed: {exc}")
        return "", []


def format_rag_context(rag_text: str) -> str:
    """Format RAG context for inclusion in prompts."""
    if not rag_text:
        return "No relevant knowledge base content found."
    return f"Relevant context from knowledge base:\n\n{rag_text}"


def build_rag_query_from_state(state: ChatState) -> str:
    """Build a compact retrieval query from latest turn, recent chat, and attachment previews."""
    latest = (state.get("latest_user_message") or "").strip()
    context_text = (state.get("context_text") or "").strip()
    history = state.get("conversation_history") or []
    attachments = state.get("attachments") or []

    recent_turns = []
    for msg in history[-4:]:
        role = (msg.get("role") or "").upper()
        content = (msg.get("content") or "").strip()
        if content:
            recent_turns.append(f"{role}: {content}")

    attachment_bits = []
    for item in attachments[-3:]:
        name = item.get("name", "document")
        snippet = shorten((item.get("content") or "").replace("\n", " "), width=600, placeholder=" ...")
        if snippet:
            attachment_bits.append(f"{name}: {snippet}")

    parts = [latest, context_text]
    if recent_turns:
        parts.append("\n".join(recent_turns))
    if attachment_bits:
        parts.append("\n".join(attachment_bits))

    return "\n\n".join([p for p in parts if p]).strip()[:3000]


def _enrich_suggestion_text(question: str, suggestion: str) -> str:
    text = (suggestion or "").strip()
    if not text:
        return ""
    if len(text) >= 90:
        return text
    return (
        f"{text} Include concrete scope boundaries, measurable acceptance criteria, and at least one edge case "
        f"for '{question}' so implementation decisions are unambiguous."
    )


def _fallback_suggestions(question: str, category: str) -> list[str]:
    readable_category = (category or "requirements").replace("_", " ")
    return [
        (
            f"Define a primary option for {readable_category} with clear user impact, system behavior, ownership, "
            f"and a measurable success metric tied to '{question}'."
        ),
        (
            f"Define an alternative option with lower delivery risk, including explicit assumptions, dependency needs, "
            f"and validation criteria for '{question}'."
        ),
        (
            f"Define a phased rollout option with phase boundaries, non-goals, acceptance gates, and rollback conditions "
            f"for '{question}'."
        ),
    ]


def normalize_clarification_analysis(analysis: ClarificationAnalysis) -> ClarificationAnalysis:
    """Enforce UX-friendly clarification output: 2-3 focused questions with 3 rich suggestions each."""
    if not analysis.questions:
        return analysis

    blocking_categories = {g.category for g in analysis.gaps if g.severity == "blocking"}
    important_categories = {g.category for g in analysis.gaps if g.severity == "important"}

    def priority(question: ClarificationQuestion) -> tuple[int, int]:
        if question.category in blocking_categories:
            return (0, 0)
        if question.category in important_categories:
            return (1, 0)
        return (2, 0)

    seen = set()
    unique_questions: list[ClarificationQuestion] = []
    for question in analysis.questions:
        key = (question.question or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_questions.append(question)

    ordered = sorted(unique_questions, key=priority)
    target_count = 2 if analysis.readiness_score >= 7 else 3
    selected = ordered[: max(2, min(3, target_count))]

    for question in selected:
        suggestions = []
        for suggestion in question.suggestions or []:
            enriched = _enrich_suggestion_text(question.question, suggestion)
            if enriched and enriched not in suggestions:
                suggestions.append(enriched)

        if len(suggestions) < 3:
            for fallback in _fallback_suggestions(question.question, question.category):
                enriched = _enrich_suggestion_text(question.question, fallback)
                if enriched not in suggestions:
                    suggestions.append(enriched)
                if len(suggestions) >= 3:
                    break

        question.suggestions = suggestions[:3]

    analysis.questions = selected
    return analysis