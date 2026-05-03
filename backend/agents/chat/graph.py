from typing import Any, Dict, List, Optional

from langgraph.graph import END, StateGraph

from agents.chat.models import ChatState
from agents.chat.nodes import (
    ask_for_more_context_node,
    confirm_tickets_node,
    decide_node,
    generate_tickets_node,
    respond_node,
    route_after_decision,
)


_graph = StateGraph(ChatState)
_graph.add_node("decide", decide_node)
_graph.add_node("respond", respond_node)
_graph.add_node("ask_for_more_context", ask_for_more_context_node)
_graph.add_node("generate_tickets", generate_tickets_node)
_graph.add_node("confirm_tickets", confirm_tickets_node)
_graph.set_entry_point("decide")
_graph.add_conditional_edges(
    "decide",
    route_after_decision,
    {
        "respond": "respond",
        "generate_tickets": "generate_tickets",
        "confirm_tickets": "confirm_tickets",
        "ask_for_more_context": "ask_for_more_context",
        "end": END,
    },
)
_graph.add_edge("respond", END)
_graph.add_edge("ask_for_more_context", END)
_graph.add_edge("generate_tickets", END)
_graph.add_edge("confirm_tickets", END)

_agent = _graph.compile()


def run_chat_agent(
    *,
    session_id: str,
    latest_user_message: str,
    context_text: str,
    project_key: str,
    pending_tickets: Optional[Dict[str, Any]],
    awaiting_confirmation: bool,
    conversation_history: List[Dict[str, str]],
    attachments: List[Dict[str, str]],
    forced_action: Optional[str] = None,
) -> Dict[str, Any]:
    final_state = _agent.invoke({
        "session_id": session_id,
        "latest_user_message": latest_user_message,
        "context_text": context_text,
        "project_key": project_key,
        "pending_tickets": pending_tickets,
        "awaiting_confirmation": awaiting_confirmation,
        "conversation_history": conversation_history,
        "attachments": attachments,
        "forced_action": forced_action,
        "decision": None,
        "reply": None,
        "generated_tickets": None,
        "created": None,
        "error": None,
    })

    if final_state.get("error"):
        raise RuntimeError(final_state["error"])

    return {
        "assistant_message": final_state.get("reply") or "",
        "decision": final_state.get("decision") or {"action": "respond", "reason": "No decision returned."},
        "generated_tickets": final_state.get("generated_tickets"),
        "created": final_state.get("created"),
    }