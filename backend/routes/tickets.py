import re
from typing import Optional

import anyio
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from agents.ticket_agent import run_ticket_agent
from services.document import extract_text
from services.confluence import get_page_content_as_text

router = APIRouter()


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


@router.post("/generate-tickets", summary="Generate JIRA tickets from PRD")
async def generate_tickets_endpoint(
    file: Optional[UploadFile] = File(None, description="PRD file (PDF / DOCX / TXT / MD)"),
    confluence_page: Optional[str] = Form(None, description="Confluence page URL or page ID"),
    prd_text: Optional[str] = Form(None, description="Plain text PRD content"),
    project_key: str = Form(..., description="JIRA project key e.g. PROJ"),
    dry_run: bool = Form(False, description="Return generated tickets without creating them in JIRA"),
):
    """
    Generate JIRA tickets from a Product Requirements Document.
    
    Accepts ONE of:
    - `file`: Upload PDF, DOCX, TXT, or MD file
    - `confluence_page`: Confluence page URL or page ID
    - `prd_text`: Plain text PRD content
    
    Required:
    - `project_key`: JIRA project key
    
    Optional:
    - `dry_run`: If true, return generated tickets without pushing to JIRA
    
    Returns generated tickets (epics, stories, tasks) optionally pushed to JIRA.
    """
    # Validate input - need exactly one source
    has_file = file is not None and bool(file.filename)
    has_confluence = confluence_page is not None and bool(confluence_page.strip())
    has_text = prd_text is not None and bool(prd_text.strip())
    
    sources_provided = sum([has_file, has_confluence, has_text])
    
    if sources_provided == 0:
        raise HTTPException(
            status_code=422,
            detail="Provide one of: file, confluence_page, or prd_text"
        )
    
    if sources_provided > 1:
        raise HTTPException(
            status_code=422,
            detail="Provide only one source: file, confluence_page, or prd_text"
        )
    
    # Extract text from source
    text_content = ""
    source = ""
    
    if has_file:
        try:
            content = await file.read()
            text_content = extract_text(content, file.filename or "")
            source = f"file ({file.filename})"
            
            if not text_content.strip():
                raise HTTPException(
                    status_code=422,
                    detail=f"Could not extract text from {source}"
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to extract content from file: {str(e)}"
            )
    
    elif has_confluence:
        try:
            page_id = _extract_confluence_page_id(confluence_page.strip())
            page_data = get_page_content_as_text(page_id)
            text_content = page_data["content"]
            source = f"confluence ({page_data['title']})"
            
            if not text_content.strip():
                raise HTTPException(
                    status_code=422,
                    detail=f"Confluence page '{page_data['title']}' has no text content"
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch Confluence page: {str(e)}"
            )
    
    elif has_text:
        text_content = prd_text.strip()
        source = "text input"
    
    # Generate tickets
    try:
        result = await anyio.to_thread.run_sync(
            lambda: run_ticket_agent(prd_text=text_content, project_key=project_key, dry_run=dry_run)
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    
    return {
        "source": source,
        "project_key": project_key,
        "dry_run": dry_run,
        **result
    }

