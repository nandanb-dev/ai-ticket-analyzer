import anyio
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from agents.ticket_agent import run_ticket_agent
from services.document import extract_text

router = APIRouter()


@router.post("/generate-tickets", summary="Upload PRD → generate & create JIRA tickets")
async def generate_tickets_endpoint(
    file: UploadFile = File(..., description="PRD file (PDF / DOCX / TXT / MD)"),
    project_key: str = Form(..., description="JIRA project key e.g. PROJ"),
    dry_run: bool = Form(False, description="Return generated tickets without creating them in JIRA"),
):
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

    return result

