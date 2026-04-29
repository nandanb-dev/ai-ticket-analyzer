from typing import Any

from services.jira import push_tickets

from agents.chat.chains import get_decision_chain, get_response_chain, get_ticket_chain
from agents.chat.models import ChatState
from agents.chat.utils import (
    build_generation_context,
    format_attachments,
    format_messages,
    summarize_ticket_preview,
)


def decide_node(state: ChatState) -> dict[str, Any]:
    try:
        if state.get("forced_action"):
            return {
                "decision": {
                    "action": state["forced_action"],
                    "reason": "Action was explicitly requested by the API caller.",
                    "missing_information": [],
                }
            }

        decision = get_decision_chain().invoke({
            "forced_action": state.get("forced_action") or "none",
            "awaiting_confirmation": state["awaiting_confirmation"],
            "project_key": state["project_key"] or "not set",
            "history_text": format_messages(state["conversation_history"]),
            "attachment_text": format_attachments(state["attachments"]),
            "context_text": state["context_text"] or "",
            "latest_user_message": state["latest_user_message"],
        })
        return {"decision": decision.model_dump()}
    except Exception as exc:
        return {"error": f"Chat routing failed: {exc}"}


def respond_node(state: ChatState) -> dict[str, Any]:
    try:
        response = get_response_chain().invoke({
            "history_text": format_messages(state["conversation_history"]),
            "attachment_text": format_attachments(state["attachments"]),
            "context_text": state["context_text"] or "",
            "latest_user_message": state["latest_user_message"],
        })
        return {"reply": response.content}
    except Exception as exc:
        return {"error": f"Chat response failed: {exc}"}


def ask_for_more_context_node(state: ChatState) -> dict[str, Any]:
    missing = []
    if state.get("decision"):
        missing = state["decision"].get("missing_information", [])
    lines = "\n".join(f"- {item}" for item in missing) if missing else "- The product goal or acceptance details are missing"
    reply = (
        "I can generate tickets, but I need a bit more product context first.\n\n"
        f"Please add one or more of these details:\n{lines}"
    )
    return {"reply": reply}


def generate_tickets_node(state: ChatState) -> dict[str, Any]:
    try:
        ticket_data = get_ticket_chain().invoke({"prd_content": build_generation_context(state)})
        return {
            "generated_tickets": ticket_data,
            "reply": summarize_ticket_preview(ticket_data),
        }
    except Exception as exc:
        return {"error": f"Ticket generation failed: {exc}"}


def confirm_tickets_node(state: ChatState) -> dict[str, Any]:
    if not state.get("pending_tickets"):
        return {"reply": "There are no pending tickets to confirm yet. Ask me to draft the tickets first."}
    if not state.get("project_key"):
        return {"reply": "I have the ticket draft, but I still need the Jira project key before I can create them."}

    try:
        created = push_tickets(state["project_key"], state["pending_tickets"])
        total = sum(len(items) for items in created.values())
        return {
            "created": created,
            "reply": f"Created {total} Jira tickets in project '{state['project_key']}'.",
        }
    except Exception as exc:
        return {"error": f"JIRA creation failed: {exc}"}


def route_after_decision(state: ChatState) -> str:
    if state.get("error"):
        return "end"
    action = (state.get("decision") or {}).get("action", "respond")
    return action