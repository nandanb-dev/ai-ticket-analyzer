from textwrap import shorten
from typing import Any

from agents.chat.models import ChatState


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