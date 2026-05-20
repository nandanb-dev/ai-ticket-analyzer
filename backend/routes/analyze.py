"""
routes/analyze.py
─────────────────
Ticket Analyzer API routes.

Workflow:
  1. POST /analyze-tickets          → fetch + analyze; returns session_id + analysis + clarification
  2. POST /analyze-tickets/{id}/feedback → refine analysis with user feedback
  3. POST /analyze-tickets/{id}/apply    → write approved suggestions to JIRA
  4. GET  /analyze-tickets/{id}          → retrieve current analysis for a session
"""

import re
from typing import List, Optional
import json
import logging

import anyio
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from agents.analyzer_agent import run_analyzer_agent, run_apply_agent, run_refine_agent
from agents.chat.chains import get_clarification_chain
from agents.chat.utils import retrieve_rag_context, format_rag_context
from services.analysis_sessions import analysis_sessions
from services.confluence import get_page_content_as_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze-tickets", tags=["analyze"])


# ── Request / Response models ─────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    project_key: Optional[str] = Field(
        default=None,
        description="JIRA project key (e.g. PROJ). Provide exactly one of project_key, epic_key, or ticket_key.",
    )
    epic_key: Optional[str] = Field(
        default=None,
        description="JIRA epic key (e.g. PROJ-42). Provide exactly one of project_key, epic_key, or ticket_key.",
    )
    ticket_key: Optional[str] = Field(
        default=None,
        description="Single JIRA ticket key (e.g. PROJ-123). Provide exactly one of project_key, epic_key, or ticket_key.",
    )
    confluence_page: Optional[str] = Field(
        default=None,
        description=(
            "Confluence page URL or page ID to fetch as additional context. "
            "Supports URLs like https://domain.atlassian.net/wiki/spaces/SPACE/pages/123456/Title "
            "or just the page ID (e.g. '123456')."
        ),
    )
    context: str = Field(
        default="",
        description=(
            "Additional context to help the analyzer: SRS document text, product goals, "
            "domain notes, or any information that clarifies what the tickets should do."
        ),
    )

    model_config = {"json_schema_extra": {
        "examples": [{
            "project_key": "SHOP",
            "confluence_page": "https://mycompany.atlassian.net/wiki/spaces/PROJ/pages/123456/Product+Requirements",
            "context": "This is an e-commerce platform. The checkout flow must support guest checkout, promo codes, and PayPal."
        }]
    }}


class FeedbackRequest(BaseModel):
    feedback: str = Field(
        description=(
            "Natural language feedback on the current analysis. You can: approve specific "
            "suggestions, reject them with reasons, add new context, ask for deeper checks "
            "on certain tickets, or request a different priority."
        )
    )


class ApplyRequest(BaseModel):
    ticket_keys: Optional[List[str]] = Field(
        default=None,
        description=(
            "List of JIRA ticket keys whose suggested_updates should be applied. "
            "Leave null / omit to apply updates for ALL tickets in the analysis."
        ),
    )
    only_approved: bool = Field(
        default=False,
        description=(
            "If true, apply only tickets with suggested_updates.approved=true. "
            "If false (default), apply all suggested updates in scope."
        ),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_confluence_page_id(url_or_id: str) -> str:
    """
    Extract Confluence page ID from a URL or return as-is if already an ID.
    
    Supports URLs like:
    - https://domain.atlassian.net/wiki/spaces/SPACE/pages/123456/Page+Title
    - https://domain.atlassian.net/wiki/pages/viewpage.action?pageId=123456
    """
    # If it's just digits, assume it's already a page ID
    if url_or_id.isdigit():
        return url_or_id
    
    # Try to extract from /pages/{id}/ pattern
    match = re.search(r'/pages/(\d+)', url_or_id)
    if match:
        return match.group(1)
    
    # Try to extract from pageId= query param
    match = re.search(r'pageId=(\d+)', url_or_id)
    if match:
        return match.group(1)
    
    raise HTTPException(
        status_code=422,
        detail=f"Could not extract page ID from Confluence URL: {url_or_id}"
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "",
    summary="Analyze tickets for a project, epic, or individual ticket",
    response_description="session_id + full multi-role analysis with suggested improvements",
)
async def analyze_tickets(req: AnalyzeRequest):
    """
    Fetch all tickets for the given **project_key**, **epic_key**, or **ticket_key** from JIRA,
    then run a multi-role AI analysis (PM, Dev, QA, Security, DevOps, UX) and
    return per-ticket findings with concrete suggested updates.

    Optionally provide a **confluence_page** URL or page ID to include as additional context
    (e.g., SRS, PRD, or design specs) for more accurate analysis.

    A `session_id` is returned so you can later `/feedback` or `/apply` updates.
    """
    provided_scopes = [bool(req.project_key), bool(req.epic_key), bool(req.ticket_key)]
    if sum(provided_scopes) != 1:
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of project_key, epic_key, or ticket_key.",
        )

    # Build combined context from user input and optional Confluence page
    combined_context = req.context or ""
    confluence_title = None
    
    if req.confluence_page and req.confluence_page.strip():
        try:
            page_id = _extract_confluence_page_id(req.confluence_page.strip())
            page_data = get_page_content_as_text(page_id)
            confluence_title = page_data.get("title", "Confluence Page")
            confluence_content = page_data.get("content", "")
            
            if confluence_content.strip():
                if combined_context:
                    combined_context += f"\n\n--- Confluence: {confluence_title} ---\n{confluence_content}"
                else:
                    combined_context = f"--- Confluence: {confluence_title} ---\n{confluence_content}"
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch Confluence page: {str(e)}"
            )

    # Create session before running the agent so we always have an id to return
    session = analysis_sessions.create_session(
        project_key=req.project_key or "",
        epic_key=req.epic_key or "",
        ticket_key=req.ticket_key or "",
        user_context=combined_context,
    )

    try:
        result = await anyio.to_thread.run_sync(
            lambda: run_analyzer_agent(
                project_key=req.project_key,
                epic_key=req.epic_key,
                ticket_key=req.ticket_key,
                user_context=combined_context,
            )
        )
    except RuntimeError as exc:
        analysis_sessions.delete_session(session.session_id)
        raise HTTPException(status_code=500, detail=str(exc))

    try:
        analysis_sessions.set_analysis(session.session_id, result["analysis"])
    except KeyError:
        raise HTTPException(status_code=410, detail="Analysis session expired before results could be stored.")

    # Run clarification analysis on the fetched ticket content
    clarification_analysis = None
    try:
        # Build context from analyzed tickets for clarification
        tickets = result.get("analysis", {}).get("tickets", [])
        if tickets:
            ticket_context_parts = []
            for t in tickets[:5]:  # Limit to first 5 tickets
                ticket_context_parts.append(
                    f"Ticket: {t.get('key', 'Unknown')}\n"
                    f"Summary: {t.get('summary', '')}\n"
                    f"Description: {t.get('description', '')[:500]}"
                )
            ticket_context = "\n\n".join(ticket_context_parts)
            
            # Reuse RAG context from analysis (same citations)
            rag_citations = result.get("rag_citations", [])
            if rag_citations:
                rag_text = "\n\n".join([
                    f"[Source: {c.get('source', 'unknown')}]\n{c.get('content', '')}"
                    for c in rag_citations[:5]
                ])
            else:
                rag_text = ""
            
            # Run clarification chain with same RAG context as analysis
            clarification_result = await anyio.to_thread.run_sync(
                lambda: get_clarification_chain().invoke({
                    "history_text": "",
                    "attachment_text": "",
                    "context_text": ticket_context,
                    "latest_user_message": f"Analyze completeness of these ticket requirements",
                    "rag_context": format_rag_context(rag_text),
                })
            )
            clarification_analysis = clarification_result.model_dump()
    except Exception as e:
        logger.warning(f"Clarification analysis failed (non-fatal): {e}")

    return {
        "session_id": session.session_id,
        "ticket_count": result.get("ticket_count", 0),
        "source": result.get("source", ""),
        "project_key": session.project_key,
        "epic_key": session.epic_key,
        "ticket_key": session.ticket_key,
        "analysis": result["analysis"],
        "clarification_analysis": clarification_analysis,
        "rag_citations": result.get("rag_citations", []),
        "rag_used": bool(result.get("rag_citations")),
    }


@router.get(
    "/{session_id}",
    summary="Get the current analysis for a session",
)
async def get_analysis(session_id: str):
    """Retrieve the latest analysis (and revision count) for an existing session."""
    session = analysis_sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return {
        "session_id": session_id,
        "project_key": session.project_key,
        "epic_key": session.epic_key,
        "ticket_key": session.ticket_key,
        "revision": len(session.revision_history),
        "analysis": session.analysis,
    }


@router.post(
    "/{session_id}/feedback",
    summary="Refine analysis based on user feedback",
    response_description="Revised analysis incorporating the user's comments",
)
async def feedback_on_analysis(session_id: str, req: FeedbackRequest):
    """
    Provide free-text feedback on the current analysis and receive a revised version.

    Examples of useful feedback:
    - *"Approve all security suggestions. Reject the story-point change for PROJ-5 — it's correct."*
    - *"The payment service uses Stripe, not PayPal. Re-evaluate PROJ-12 and PROJ-15 with that in mind."*
    - *"Add more edge cases for the file upload tickets."*
    """
    session = analysis_sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    if not session.analysis:
        raise HTTPException(
            status_code=409,
            detail="No analysis found in this session. Run POST /analyze-tickets first.",
        )

    try:
        result = await anyio.to_thread.run_sync(
            lambda: run_refine_agent(
                previous_analysis=session.analysis,
                user_feedback=req.feedback,
                project_key=session.project_key or None,
                epic_key=session.epic_key or None,
                ticket_key=session.ticket_key or None,
            )
        )
    except RuntimeError as exc:
        # Fallback: recover JSON from model/parsing error text
        message = str(exc)
        if "Invalid json output" in message:
            try:
                recovered_analysis = _extract_first_json_object(message)
                updated_session = analysis_sessions.set_analysis(session_id, recovered_analysis)
                return {
                    "session_id": session_id,
                    "revision": len(updated_session.revision_history),
                    "analysis": recovered_analysis,
                }
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=message)

    try:
        updated_session = analysis_sessions.set_analysis(session_id, result["analysis"])
    except KeyError:
        raise HTTPException(status_code=410, detail=f"Session '{session_id}' expired before the revision could be stored.")

    return {
        "session_id": session_id,
        "revision": len(updated_session.revision_history),
        "analysis": result["analysis"],
    }


@router.post(
    "/{session_id}/apply",
    summary="Apply suggestions to JIRA tickets",
    response_description="List of JIRA ticket keys that were updated",
)
async def apply_suggestions(session_id: str, req: Optional[ApplyRequest] = Body(default=None)):
    """
    Write `suggested_updates` from the current analysis back to JIRA.

    - Pass `ticket_keys` to apply updates only to those tickets.
    - Set `only_approved=true` to apply only tickets whose `suggested_updates.approved` flag is true.
    - Default behavior applies all suggested updates when `ticket_keys` is omitted.
    """
    if req is None:
        req = ApplyRequest()

    session = analysis_sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    if not session.analysis:
        raise HTTPException(
            status_code=409,
            detail="No analysis found in this session. Run POST /analyze-tickets first.",
        )

    try:
        result = await anyio.to_thread.run_sync(
            lambda: run_apply_agent(
                analysis=session.analysis,
                apply_keys=req.ticket_keys,
                apply_only_approved=req.only_approved,
                project_key=session.project_key or None,
                epic_key=session.epic_key or None,
                ticket_key=session.ticket_key or None,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "session_id": session_id,
        "message": result.get("message", ""),
        "applied": result.get("applied", []),
        "skipped": result.get("skipped", []),
    }

def _extract_first_json_object(text: str) -> dict:
    """
    Best-effort recovery when model output includes preamble text before JSON.
    Example: 'Invalid json output: Revised analysis (JSON): { ... }'
    """
    cleaned = text.strip()
    cleaned = cleaned.replace("```json", "```").replace("```", "")
    start = cleaned.find("{")
    if start == -1:
        raise ValueError("No JSON object found in text.")
    obj, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    if not isinstance(obj, dict):
        raise ValueError("Recovered JSON is not an object.")
    return obj