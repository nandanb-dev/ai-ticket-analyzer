from textwrap import shorten
from typing import Any, List, Tuple
import logging

from agents.chat.models import ChatState

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
    bugs = ticket_data.get("bugs", [])
    sample_titles = [item["summary"] for item in (epics + stories + tasks + bugs)[:6]]
    preview_lines = "\n".join(f"- {title}" for title in sample_titles) if sample_titles else "- No ticket titles generated"
    
    # Build dynamic count message
    counts = []
    if len(epics) > 0:
        counts.append(f"{len(epics)} epic{'s' if len(epics) != 1 else ''}")
    if len(stories) > 0:
        counts.append(f"{len(stories)} stor{'ies' if len(stories) != 1 else 'y'}")
    if len(tasks) > 0:
        counts.append(f"{len(tasks)} task{'s' if len(tasks) != 1 else ''}")
    if len(bugs) > 0:
        counts.append(f"{len(bugs)} bug{'s' if len(bugs) != 1 else ''}")
    
    if counts:
        count_text = ", ".join(counts)
        intro = f"I drafted {count_text} based on the chat context."
    else:
        intro = "No tickets were generated."
    
    return (
        f"{intro}\n\n"
        f"Preview:\n{preview_lines}\n\n"
        "Review the draft below. When it looks right, confirm to create the tickets in Jira."
    )


def summarize_pending_tickets(pending: dict[str, Any]) -> str:
    """Build a summary of pending tickets for the edit_draft chain."""
    lines = []
    for ticket_type in ["epics", "stories", "tasks", "bugs"]:
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
        from rag.retrieval import retrieve
        from rag.context_builder import build_context
        
        # Retrieve relevant chunks
        # Note: project_key filtering can be added when MetadataFilter supports it
        results = retrieve(
            query=query,
            top_k=30,
            rerank_top_n=10,
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