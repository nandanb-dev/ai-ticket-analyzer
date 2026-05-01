"""
routes/analyze.py
─────────────────
Ticket Analyzer API routes.

Workflow:
  1. POST /analyze-tickets          → fetch + analyze; returns session_id + analysis
  2. POST /analyze-tickets/{id}/feedback → refine analysis with user feedback
  3. POST /analyze-tickets/{id}/apply    → write approved suggestions to JIRA
  4. GET  /analyze-tickets/{id}          → retrieve current analysis for a session
"""

import anyio
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from agents.analyzer_agent import run_analyzer_agent, run_apply_agent, run_refine_agent
from services.analysis_sessions import analysis_sessions

router = APIRouter(prefix="/analyze-tickets", tags=["analyze"])


# ── Request / Response models ─────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    project_key: str | None = Field(
        default=None,
        description="JIRA project key (e.g. PROJ). Provide exactly one of project_key, epic_key, or ticket_key.",
    )
    epic_key: str | None = Field(
        default=None,
        description="JIRA epic key (e.g. PROJ-42). Provide exactly one of project_key, epic_key, or ticket_key.",
    )
    ticket_key: str | None = Field(
        default=None,
        description="Single JIRA ticket key (e.g. PROJ-123). Provide exactly one of project_key, epic_key, or ticket_key.",
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
    ticket_keys: list[str] | None = Field(
        default=None,
        description=(
            "List of JIRA ticket keys whose suggested_updates should be applied. "
            "Leave null / omit to apply updates for ALL tickets in the analysis."
        ),
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

    A `session_id` is returned so you can later `/feedback` or `/apply` updates.
    """
    provided_scopes = [bool(req.project_key), bool(req.epic_key), bool(req.ticket_key)]
    if sum(provided_scopes) != 1:
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of project_key, epic_key, or ticket_key.",
        )

    # Create session before running the agent so we always have an id to return
    session = analysis_sessions.create_session(
        project_key=req.project_key or "",
        epic_key=req.epic_key or "",
        ticket_key=req.ticket_key or "",
        user_context=req.context,
    )

    try:
        result = await anyio.to_thread.run_sync(
            lambda: run_analyzer_agent(
                project_key=req.project_key,
                epic_key=req.epic_key,
                ticket_key=req.ticket_key,
                user_context=req.context,
            )
        )
    except RuntimeError as exc:
        analysis_sessions.delete_session(session.session_id)
        raise HTTPException(status_code=500, detail=str(exc))

    analysis_sessions.set_analysis(session.session_id, result["analysis"])

    return {
        "session_id": session.session_id,
        "ticket_count": result.get("ticket_count", 0),
        "source": result.get("source", ""),
        "project_key": session.project_key,
        "epic_key": session.epic_key,
        "ticket_key": session.ticket_key,
        "analysis": result["analysis"],
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
        raise HTTPException(status_code=500, detail=str(exc))

    updated_session = analysis_sessions.set_analysis(session_id, result["analysis"])

    return {
        "session_id": session_id,
        "revision": len(updated_session.revision_history),
        "analysis": result["analysis"],
    }


@router.post(
    "/{session_id}/apply",
    summary="Apply approved suggestions to JIRA tickets",
    response_description="List of JIRA ticket keys that were updated",
)
async def apply_suggestions(session_id: str, req: ApplyRequest = Body(default=ApplyRequest())):
    """
    Write the `suggested_updates` from the current analysis back to JIRA.

    - Pass `ticket_keys` to apply updates only to specific tickets.
    - Omit `ticket_keys` (or pass `null`) to apply updates to **all** tickets in the analysis.
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
            lambda: run_apply_agent(
                analysis=session.analysis,
                apply_keys=req.ticket_keys,
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
