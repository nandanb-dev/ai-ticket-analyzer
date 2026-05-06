import os
from datetime import datetime, timezone
from uuid import uuid4

import anyio
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from motor.motor_asyncio import AsyncIOMotorClient

from agents.ticket_agent import run_ticket_agent
from services.document import extract_text

router = APIRouter()
MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "ai_ticket")


async def _store_ticket_session(                  # Shift to service layer later
    session_id: str, 
    project_key: str,
    dry_run: bool,
    document_text: str,
    final_response: dict,
) -> None:
    """Persist request + final LLM response when MongoDB is configured."""
    if not MONGODB_URI:
        return

    client = AsyncIOMotorClient(MONGODB_URI)
    try:
        await client[MONGODB_DB_NAME]["ticket_generations"].insert_one(
            {
                "_id": session_id,
                "session_id": session_id,
                "project_key": project_key,
                "dry_run": dry_run,
                "document_text": document_text,
                "final_response": final_response,
                "created_at": datetime.now(timezone.utc),
            }
        )
    finally:
        client.close()

@router.post("/generate-tickets", summary="Upload PRD → generate & create JIRA tickets")
async def generate_tickets_endpoint(
    file: UploadFile = File(..., description="PRD file (PDF / DOCX / TXT / MD)"),
    project_key: str = Form(..., description="JIRA project key e.g. PROJ"),
    dry_run: bool = Form(False, description="Return generated tickets without creating them in JIRA"),
):
    session_id = str(uuid4())

    # Read file bytes asynchronously to avoid blocking the event loop
    content = await file.read()
    prd_text = extract_text(content, file.filename or "")
    if not prd_text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from the uploaded file.")

    try:
        # Run the synchronous LangGraph agent in a thread to avoid blocking
        result = await anyio.to_thread.run_sync(
            lambda: run_ticket_agent(prd_text=prd_text, project_key=project_key, dry_run=dry_run)
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    await _store_ticket_session(
        session_id=session_id,
        project_key=project_key,
        dry_run=dry_run,
        document_text=prd_text,
        final_response=result,
    )

    return {"session_id": session_id, **result}

