import anyio
from pydantic import BaseModel
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from agents.chat_agent import run_chat_agent
from services.chat_sessions import chat_sessions
from services.document import extract_text


router = APIRouter(prefix="/chat", tags=["chat"])


class CreateSessionRequest(BaseModel):
    project_key: str = ""


def _session_response(session) -> dict:
    pending = session.pending_tickets or {}
    return {
        "session_id": session.session_id,
        "project_key": session.project_key,
        "awaiting_confirmation": session.awaiting_confirmation,
        "messages": session.messages,
        "attachments": [
            {"name": item["name"], "preview": item["content"][:800]}
            for item in session.attachments
        ],
        "pending_tickets": pending,
        "pending_counts": {
            "epics": len(pending.get("epics", [])),
            "stories": len(pending.get("stories", [])),
            "tasks": len(pending.get("tasks", [])),
        },
        "last_created": session.last_created,
    }


@router.post("/sessions")
async def create_session(payload: CreateSessionRequest) -> dict:
    session = chat_sessions.create_session(project_key=payload.project_key)
    return _session_response(session)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    session = chat_sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return _session_response(session)


class ProjectKeyUpdate(BaseModel):
    project_key: str

@router.post("/sessions/{session_id}/project-key")
async def update_project_key(session_id: str, payload: ProjectKeyUpdate) -> dict:
    session = chat_sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    updated = chat_sessions.update_project_key(session_id, payload.project_key)
    return _session_response(updated)


class AttachmentUpdate(BaseModel):
    index: int
    content: str

@router.post("/sessions/{session_id}/attachments")
async def update_attachment(session_id: str, payload: AttachmentUpdate) -> dict:
    session = chat_sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    if payload.index < 0 or payload.index >= len(session.attachments):
        raise HTTPException(status_code=400, detail="Invalid attachment index")
    
    updated = chat_sessions.update_attachment(session_id, payload.index, payload.content)
    return _session_response(updated)


class AttachmentDelete(BaseModel):
    index: int

@router.delete("/sessions/{session_id}/attachments")
async def delete_attachment(session_id: str, payload: AttachmentDelete) -> dict:
    session = chat_sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    if payload.index < 0 or payload.index >= len(session.attachments):
        raise HTTPException(status_code=400, detail="Invalid attachment index")
    
    updated = chat_sessions.remove_attachment(session_id, payload.index)
    return _session_response(updated)


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str,
    message: str = Form(""),
    context_text: str = Form(""),
    project_key: str = Form(""),
    files: list[UploadFile] = File([]),
) -> dict:
    session = chat_sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    if not message.strip() and not context_text.strip() and not files:
        raise HTTPException(status_code=422, detail="Provide a message, context text, or uploaded files.")

    if project_key.strip():
        session = chat_sessions.update_project_key(session_id, project_key)

    uploaded_names = []
    failed_files = []
    for file in files:
        content = await file.read()
        text = await anyio.to_thread.run_sync(
            extract_text, content, file.filename or ""
        )
        if text.strip():
            chat_sessions.add_attachment(session_id, file.filename or "uploaded-file", text)
            uploaded_names.append(file.filename or "uploaded-file")
        else:
            failed_files.append(file.filename or "uploaded-file")

    display_message = message.strip()
    if uploaded_names and not display_message:
        display_message = f"Uploaded supporting context: {', '.join(uploaded_names)}"

    if context_text.strip() and not display_message:
        display_message = "Added extra written context for the conversation."

    if not display_message:
        raise HTTPException(
            status_code=422,
            detail="No usable text could be extracted from the uploaded files.",
        )

    session = chat_sessions.append_message(session_id, "user", display_message)

    try:
        result = await anyio.to_thread.run_sync(
            lambda: run_chat_agent(
                session_id=session_id,
                latest_user_message=display_message,
                context_text=context_text,
                project_key=session.project_key,
                pending_tickets=session.pending_tickets,
                awaiting_confirmation=session.awaiting_confirmation,
                conversation_history=session.messages,
                attachments=session.attachments,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if result.get("generated_tickets"):
        chat_sessions.set_pending_tickets(session_id, result["generated_tickets"], awaiting_confirmation=True)

    if result.get("created"):
        chat_sessions.set_last_created(session_id, result["created"])
        chat_sessions.set_pending_tickets(session_id, None, awaiting_confirmation=False)

    session = chat_sessions.append_message(session_id, "assistant", result["assistant_message"])

    response = _session_response(session)
    response["decision"] = result["decision"]
    if failed_files:
        response["failed_files"] = failed_files
    return response


@router.post("/sessions/{session_id}/confirm")
async def confirm_tickets(session_id: str) -> dict:
    session = chat_sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    try:
        result = await anyio.to_thread.run_sync(
            lambda: run_chat_agent(
                session_id=session_id,
                latest_user_message="I confirm the drafted tickets are correct. Create them in Jira now.",
                context_text="",
                project_key=session.project_key,
                pending_tickets=session.pending_tickets,
                awaiting_confirmation=session.awaiting_confirmation,
                conversation_history=session.messages,
                attachments=session.attachments,
                forced_action="confirm_tickets",
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if result.get("created"):
        chat_sessions.set_last_created(session_id, result["created"])
        chat_sessions.set_pending_tickets(session_id, None, awaiting_confirmation=False)

    session = chat_sessions.append_message(session_id, "assistant", result["assistant_message"])

    response = _session_response(session)
    response["decision"] = result["decision"]
    return response


# ── Clarification Flow Endpoints ─────────────────────────────────────────────


class AnalyzeReadinessRequest(BaseModel):
    message: str = ""
    context_text: str = ""


@router.post("/sessions/{session_id}/analyze-readiness")
async def analyze_readiness(session_id: str, payload: AnalyzeReadinessRequest) -> dict:
    """
    Analyze requirements and return clarification questions without generating tickets.
    
    Use this endpoint when you want to check if requirements are complete enough
    for development before proceeding with ticket generation.
    """
    session = chat_sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    user_message = payload.message.strip() or "Analyze these requirements for development readiness"
    
    # Add user message to history
    session = chat_sessions.append_message(session_id, "user", user_message)

    try:
        result = await anyio.to_thread.run_sync(
            lambda: run_chat_agent(
                session_id=session_id,
                latest_user_message=user_message,
                context_text=payload.context_text,
                project_key=session.project_key,
                pending_tickets=session.pending_tickets,
                awaiting_confirmation=session.awaiting_confirmation,
                conversation_history=session.messages,
                attachments=session.attachments,
                forced_action="clarify_requirements",
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    session = chat_sessions.append_message(session_id, "assistant", result["assistant_message"])

    response = _session_response(session)
    response["clarification_analysis"] = result.get("clarification_analysis")
    response["decision"] = result["decision"]
    return response


class AnswerClarificationRequest(BaseModel):
    answers: dict = {}  # Maps question number/category to answer
    additional_context: str = ""


@router.post("/sessions/{session_id}/answer-clarification")
async def answer_clarification(session_id: str, payload: AnswerClarificationRequest) -> dict:
    """
    Submit answers to clarification questions and get follow-up questions or proceed.
    
    The system will either:
    - Ask additional clarifying questions if more info is needed
    - Indicate readiness to generate tickets if requirements are now complete
    """
    session = chat_sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    # Build a message from the answers
    answer_parts = []
    for key, value in payload.answers.items():
        answer_parts.append(f"**{key}**: {value}")
    
    if payload.additional_context:
        answer_parts.append(f"\nAdditional context: {payload.additional_context}")
    
    user_message = "\n".join(answer_parts) if answer_parts else "Here are my answers to your questions."

    session = chat_sessions.append_message(session_id, "user", user_message)

    try:
        # Let the decision chain determine if we need more clarification or can proceed
        result = await anyio.to_thread.run_sync(
            lambda: run_chat_agent(
                session_id=session_id,
                latest_user_message=user_message,
                context_text=payload.additional_context,
                project_key=session.project_key,
                pending_tickets=session.pending_tickets,
                awaiting_confirmation=session.awaiting_confirmation,
                conversation_history=session.messages,
                attachments=session.attachments,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if result.get("generated_tickets"):
        chat_sessions.set_pending_tickets(session_id, result["generated_tickets"], awaiting_confirmation=True)

    session = chat_sessions.append_message(session_id, "assistant", result["assistant_message"])

    response = _session_response(session)
    response["clarification_analysis"] = result.get("clarification_analysis")
    response["decision"] = result["decision"]
    return response


@router.post("/sessions/{session_id}/proceed-with-assumptions")
async def proceed_with_assumptions(session_id: str) -> dict:
    """
    Generate tickets even with incomplete requirements, documenting assumptions.
    
    Use this when the user acknowledges that some requirements are incomplete
    but wants to proceed anyway. The generated tickets will include documented
    assumptions for areas that weren't fully specified.
    """
    session = chat_sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    # Append acknowledgment message
    session = chat_sessions.append_message(
        session_id, "user",
        "Proceed with generating tickets. Document any assumptions made."
    )

    try:
        result = await anyio.to_thread.run_sync(
            lambda: run_chat_agent(
                session_id=session_id,
                latest_user_message="Generate tickets with documented assumptions for unclear areas. "
                                   "Mark any assumptions clearly in the ticket descriptions.",
                context_text="User acknowledged that some requirements are incomplete and wants to proceed. "
                           "Document all assumptions made during ticket generation.",
                project_key=session.project_key,
                pending_tickets=session.pending_tickets,
                awaiting_confirmation=session.awaiting_confirmation,
                conversation_history=session.messages,
                attachments=session.attachments,
                forced_action="generate_tickets",
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if result.get("generated_tickets"):
        chat_sessions.set_pending_tickets(session_id, result["generated_tickets"], awaiting_confirmation=True)

    session = chat_sessions.append_message(session_id, "assistant", result["assistant_message"])

    response = _session_response(session)
    response["decision"] = result["decision"]
    return response