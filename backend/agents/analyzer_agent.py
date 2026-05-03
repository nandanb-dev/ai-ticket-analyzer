"""
analyzer_agent.py
─────────────────
LangGraph-based agent that:
  1. Fetches tickets from JIRA (project or epic scope)
  2. Analyses every ticket with the multi-role analysis prompt
  3. Can refine the analysis based on user feedback
  4. Applies approved suggested updates back to JIRA
"""

import json
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.output_parsers import JsonOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph

from config import CHAT_MODEL, JIRA_API_TOKEN, JIRA_URL, JIRA_USERNAME, GOOGLE_API_KEY
from prompts.ticket_analysis import TICKET_ANALYSIS_PROMPT, TICKET_REFINEMENT_PROMPT
from services.jira import fetch_epic_tickets, fetch_project_tickets, fetch_ticket_by_key, update_issue


# ── State ─────────────────────────────────────────────────────────────────────

class AnalyzerState(TypedDict):
    # Inputs
    project_key: Optional[str]
    epic_key: Optional[str]
    ticket_key: Optional[str]
    user_context: str          # SRS / additional description from the user
    user_feedback: Optional[str]
    previous_analysis: Optional[dict]

    # Internal
    raw_tickets: Optional[List[Dict]]
    analysis: Optional[dict]
    apply_keys: Optional[List[str]]   # ticket keys the user wants to apply updates to
    apply_only_approved: bool

    # Output
    result: Optional[dict]
    error: Optional[str]


# ── LLM chains (lazy-init) ────────────────────────────────────────────────────

_analysis_chain = None
_refinement_chain = None


def _get_analysis_chain():
    global _analysis_chain
    if _analysis_chain is not None:
        return _analysis_chain
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not configured in .env")
    llm = ChatGoogleGenerativeAI(model=CHAT_MODEL, temperature=0.1, api_key=GOOGLE_API_KEY)
    _analysis_chain = TICKET_ANALYSIS_PROMPT | llm | JsonOutputParser()
    return _analysis_chain


def _get_refinement_chain():
    global _refinement_chain
    if _refinement_chain is not None:
        return _refinement_chain
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not configured in .env")
    llm = ChatGoogleGenerativeAI(model=CHAT_MODEL, temperature=0.1, api_key=GOOGLE_API_KEY)
    _refinement_chain = TICKET_REFINEMENT_PROMPT | llm | JsonOutputParser()
    return _refinement_chain


# ── Nodes ─────────────────────────────────────────────────────────────────────

def _fetch_tickets_node(state: AnalyzerState) -> dict:
    """Fetch tickets from JIRA based on project_key, epic_key, or ticket_key."""
    try:
        if not all([JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN]):
            return {"error": "JIRA credentials not configured in .env"}

        epic_key = state.get("epic_key")
        project_key = state.get("project_key")
        ticket_key = state.get("ticket_key")

        if ticket_key:
            tickets = fetch_ticket_by_key(ticket_key)
        elif epic_key:
            tickets = fetch_epic_tickets(epic_key)
        elif project_key:
            tickets = fetch_project_tickets(project_key)
        else:
            return {"error": "Provide exactly one of project_key, epic_key, or ticket_key."}

        if not tickets:
            source = (
                f"ticket {ticket_key}" if ticket_key
                else f"epic {epic_key}" if epic_key
                else f"project {project_key}"
            )
            return {"error": f"No tickets found for {source}."}

        return {"raw_tickets": tickets}
    except Exception as exc:
        return {"error": f"Failed to fetch tickets: {exc}"}


def _analyze_node(state: AnalyzerState) -> dict:
    """Run the multi-role analysis against all fetched tickets."""
    try:
        tickets_json = json.dumps(state["raw_tickets"], indent=2, ensure_ascii=False)
        analysis = _get_analysis_chain().invoke({
            "tickets_json": tickets_json,
            "user_context": state.get("user_context") or "No additional context provided.",
        })
        return {"analysis": analysis}
    except Exception as exc:
        return {"error": f"Analysis failed: {exc}"}


def _refine_node(state: AnalyzerState) -> dict:
    """Refine an existing analysis using user feedback."""
    try:
        previous = state.get("previous_analysis") or {}
        feedback = state.get("user_feedback") or ""
        if not previous:
            return {"error": "No previous analysis to refine."}
        if not feedback.strip():
            return {"error": "User feedback is empty — nothing to refine."}

        revised = _get_refinement_chain().invoke({
            "previous_analysis_json": json.dumps(previous, indent=2, ensure_ascii=False),
            "user_feedback": feedback,
        })
        return {"analysis": revised}
    except Exception as exc:
        return {"error": f"Refinement failed: {exc}"}


def _apply_node(state: AnalyzerState) -> dict:
    """Apply approved suggested updates to JIRA tickets."""
    try:
        if not all([JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN]):
            return {"error": "JIRA credentials not configured in .env"}

        analysis = state.get("analysis") or state.get("previous_analysis") or {}
        apply_keys_filter = state.get("apply_keys")  # None means apply all
        apply_only_approved = bool(state.get("apply_only_approved", False))

        tickets_analysis = analysis.get("tickets", [])
        applied = []
        skipped = []

        for ticket in tickets_analysis:
            key = ticket.get("key")
            if not key:
                continue
            if apply_keys_filter and key not in apply_keys_filter:
                skipped.append(key)
                continue

            updates = ticket.get("suggested_updates", {})
            if not updates:
                skipped.append(key)
                continue
            if apply_only_approved and not apply_keys_filter and not updates.get("approved"):
                skipped.append(key)
                continue

            result = update_issue(
                issue_key=key,
                summary=updates.get("summary"),
                description=updates.get("description"),
                priority=updates.get("priority"),
                labels=updates.get("labels"),
                story_points=updates.get("story_points"),
                acceptance_criteria=updates.get("acceptance_criteria"),
                test_cases=updates.get("test_cases"),
                edge_cases=updates.get("edge_cases"),
            )
            applied.append(result)

        return {
            "result": {
                "message": f"Applied updates to {len(applied)} ticket(s). Skipped {len(skipped)}.",
                "applied": applied,
                "skipped": skipped,
            }
        }
    except Exception as exc:
        return {"error": f"Apply failed: {exc}"}


def _build_analysis_result(state: AnalyzerState) -> dict:
    """Wrap the analysis into the final result payload."""
    analysis = state.get("analysis", {})
    return {
        "result": {
            "analysis": analysis,
            "ticket_count": len((state.get("raw_tickets") or [])),
            "source": (
                f"ticket:{state['ticket_key']}" if state.get("ticket_key")
                else f"epic:{state['epic_key']}" if state.get("epic_key")
                else f"project:{state['project_key']}"
            ),
        }
    }


# ── Routing ───────────────────────────────────────────────────────────────────

def _route_initial(state: AnalyzerState) -> str:
    if state.get("error"):
        return "end"
    return "analyze"


def _route_after_analyze(state: AnalyzerState) -> str:
    if state.get("error"):
        return "end"
    return "build_result"


# ── Graph: Analyze flow ───────────────────────────────────────────────────────

_analyze_graph = StateGraph(AnalyzerState)
_analyze_graph.add_node("fetch", _fetch_tickets_node)
_analyze_graph.add_node("analyze", _analyze_node)
_analyze_graph.add_node("build_result", _build_analysis_result)
_analyze_graph.set_entry_point("fetch")
_analyze_graph.add_conditional_edges("fetch", _route_initial, {"analyze": "analyze", "end": END})
_analyze_graph.add_conditional_edges("analyze", _route_after_analyze, {"build_result": "build_result", "end": END})
_analyze_graph.add_edge("build_result", END)
_analyze_agent = _analyze_graph.compile()


# ── Graph: Refine flow ────────────────────────────────────────────────────────

def _route_after_refine(state: AnalyzerState) -> str:
    if state.get("error"):
        return "end"
    return "build_result"


_refine_graph = StateGraph(AnalyzerState)
_refine_graph.add_node("refine", _refine_node)
_refine_graph.add_node("build_result", _build_analysis_result)
_refine_graph.set_entry_point("refine")
_refine_graph.add_conditional_edges("refine", _route_after_refine, {"build_result": "build_result", "end": END})
_refine_graph.add_edge("build_result", END)
_refine_agent = _refine_graph.compile()


# ── Graph: Apply flow ─────────────────────────────────────────────────────────

def _route_apply(state: AnalyzerState) -> str:
    if state.get("error"):
        return "end"
    return "apply"


_apply_graph = StateGraph(AnalyzerState)
_apply_graph.add_node("apply", _apply_node)
_apply_graph.set_entry_point("apply")
_apply_graph.add_edge("apply", END)
_apply_agent = _apply_graph.compile()


# ── Public entrypoints ────────────────────────────────────────────────────────

def run_analyzer_agent(
    *,
    project_key: Optional[str],
    epic_key: Optional[str],
    ticket_key: Optional[str],
    user_context: str,
) -> Dict[str, Any]:
    """Fetch + analyze tickets. Returns analysis result dict."""
    final = _analyze_agent.invoke({
        "project_key": project_key,
        "epic_key": epic_key,
        "ticket_key": ticket_key,
        "user_context": user_context,
        "user_feedback": None,
        "previous_analysis": None,
        "raw_tickets": None,
        "analysis": None,
        "apply_keys": None,
        "apply_only_approved": False,
        "result": None,
        "error": None,
    })
    if final.get("error"):
        raise RuntimeError(final["error"])
    return final["result"]


def run_refine_agent(
    *,
    previous_analysis: Dict,
    user_feedback: str,
    project_key: Optional[str] = None,
    epic_key: Optional[str] = None,
    ticket_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Refine an existing analysis using user feedback."""
    final = _refine_agent.invoke({
        "project_key": project_key,
        "epic_key": epic_key,
        "ticket_key": ticket_key,
        "user_context": "",
        "user_feedback": user_feedback,
        "previous_analysis": previous_analysis,
        "raw_tickets": None,
        "analysis": None,
        "apply_keys": None,
        "apply_only_approved": False,
        "result": None,
        "error": None,
    })
    if final.get("error"):
        raise RuntimeError(final["error"])
    return final["result"]


def run_apply_agent(
    *,
    analysis: Dict,
    apply_keys: Optional[List[str]],
    apply_only_approved: bool = False,
    project_key: Optional[str] = None,
    epic_key: Optional[str] = None,
    ticket_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply suggestions from an analysis back to JIRA."""
    final = _apply_agent.invoke({
        "project_key": project_key,
        "epic_key": epic_key,
        "ticket_key": ticket_key,
        "user_context": "",
        "user_feedback": None,
        "previous_analysis": analysis,
        "raw_tickets": None,
        "analysis": analysis,
        "apply_keys": apply_keys,
        "apply_only_approved": apply_only_approved,
        "result": None,
        "error": None,
    })
    if final.get("error"):
        raise RuntimeError(final["error"])
    return final["result"]
