import anyio
from pydantic import BaseModel
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from agents.chat_agent import run_chat_agent
from services.chat_sessions import chat_sessions
from services.document import extract_text


router = APIRouter(prefix="/chat", tags=["chat"])


class CreateSessionRequest(BaseModel):
    project_key: str = ""


def _normalize_uploaded_files(files: list[UploadFile | str] | None) -> list[UploadFile]:
    normalized_files = []
    for file in files or []:
        if isinstance(file, UploadFile):
            normalized_files.append(file)
    return normalized_files


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


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str,
    message: str = Form(""),
    context_text: str = Form(""),
    project_key: str = Form(""),
    files: list[UploadFile | str] | None = File(None),
) -> dict:
    session = chat_sessions.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    uploaded_files = _normalize_uploaded_files(files)

    if not message.strip() and not context_text.strip() and not uploaded_files:
        raise HTTPException(status_code=422, detail="Provide a message, context text, or uploaded files.")

    if project_key.strip():
        session = chat_sessions.update_project_key(session_id, project_key)

    uploaded_names = []
    for file in uploaded_files:
        content = await file.read()
        text = extract_text(content, file.filename or "")
        if text.strip():
            chat_sessions.add_attachment(session_id, file.filename or "uploaded-file", text)
            uploaded_names.append(file.filename or "uploaded-file")

    display_message = message.strip()
    if uploaded_names and not display_message:
        display_message = f"Uploaded supporting context: {', '.join(uploaded_names)}"

    if context_text.strip() and not display_message:
        display_message = "Added extra written context for the conversation."

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