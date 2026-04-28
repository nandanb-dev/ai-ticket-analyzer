from typing import Optional, TypedDict

from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from config import JIRA_API_TOKEN, JIRA_URL, JIRA_USERNAME, OPENAI_API_KEY
from prompts.ticket_generation import TICKET_GENERATION_PROMPT
from services.jira import push_tickets


# ── Agent state ───────────────────────────────────────────────────────────────

class TicketState(TypedDict):
    prd_text: str
    project_key: str
    dry_run: bool
    ticket_data: Optional[dict]
    result: Optional[dict]
    error: Optional[str]


# ── LLM + chain (lazy-initialized on first request) ─────────────────────────

_chain = None


def _get_chain():
    global _chain
    if _chain is not None:
        return _chain
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured in .env")
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2, api_key=OPENAI_API_KEY)
    _chain = TICKET_GENERATION_PROMPT | llm | JsonOutputParser()
    return _chain


# ── Nodes ─────────────────────────────────────────────────────────────────────

def _generate_node(state: TicketState) -> dict:
    """Call GPT-4o to produce structured ticket JSON from PRD text."""
    try:
        ticket_data = _get_chain().invoke({"prd_content": state["prd_text"]})
        return {"ticket_data": ticket_data}
    except Exception as exc:
        return {"error": f"AI generation failed: {exc}"}


def _dry_run_node(state: TicketState) -> dict:
    """Return the generated tickets without pushing to JIRA."""
    td = state["ticket_data"]
    return {
        "result": {
            "dry_run": True,
            "project_key": state["project_key"],
            "generated": {
                "epics":   len(td.get("epics", [])),
                "stories": len(td.get("stories", [])),
                "tasks":   len(td.get("tasks", [])),
            },
            "tickets": td,
        }
    }


def _create_node(state: TicketState) -> dict:
    """Push generated tickets to JIRA."""
    try:
        if not all([JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN]):
            return {"error": "JIRA credentials not configured in .env"}

        created = push_tickets(state["project_key"], state["ticket_data"])
        total = sum(len(v) for v in created.values())
        return {
            "result": {
                "message": f"Created {total} tickets in project '{state['project_key']}'",
                "project_key": state["project_key"],
                "created": created,
            }
        }
    except Exception as exc:
        return {"error": f"JIRA creation failed: {exc}"}


# ── Routing ───────────────────────────────────────────────────────────────────

def _route_after_generate(state: TicketState) -> str:
    if state.get("error"):
        return "end"
    return "dry_run" if state["dry_run"] else "create"


# ── Graph ─────────────────────────────────────────────────────────────────────

_graph = StateGraph(TicketState)

_graph.add_node("generate", _generate_node)
_graph.add_node("dry_run",  _dry_run_node)
_graph.add_node("create",   _create_node)

_graph.set_entry_point("generate")
_graph.add_conditional_edges(
    "generate",
    _route_after_generate,
    {"dry_run": "dry_run", "create": "create", "end": END},
)
_graph.add_edge("dry_run", END)
_graph.add_edge("create",  END)

_agent = _graph.compile()


# ── Public interface ──────────────────────────────────────────────────────────

def run_ticket_agent(prd_text: str, project_key: str, dry_run: bool) -> dict:
    """Run the ticket generation agent and return the final result."""
    final_state = _agent.invoke({
        "prd_text":    prd_text,
        "project_key": project_key,
        "dry_run":     dry_run,
        "ticket_data": None,
        "result":      None,
        "error":       None,
    })

    if final_state.get("error"):
        raise RuntimeError(final_state["error"])

    return final_state["result"]
