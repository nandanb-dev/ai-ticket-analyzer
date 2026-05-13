"""
rag/ingestion/confluence_ingestion.py
──────────────────────────────────────
Ingest Confluence pages into the RAG knowledge base.

Extracts:
  - Page title and section hierarchy (headings preserved)
  - Tables (as pipe-delimited text)
  - Code blocks (fenced)
  - Body content with structure preserved

Document structure is intentionally kept intact to give chunking the best
chance of splitting at meaningful boundaries.
"""

import logging
import re
from typing import Dict, List, Optional

from rag.cleaning import clean_document, clean_html_to_text
from rag.ingestion.base import ingest_document
from rag.models import DocumentRecord

logger = logging.getLogger(__name__)


# ── Public API ────────────────────────────────────────────────────────────────

def ingest_page_by_id(page_id: str) -> dict:
    """
    Fetch and ingest a Confluence page by its numeric page ID.

    Args:
        page_id: The Confluence page ID (e.g. "123456").

    Returns:
        Ingestion result dict: {document_id, chunk_count, embedded_count}.
    """
    from services.confluence import get_page_by_id

    page_data = get_page_by_id(page_id, expand="body.storage,ancestors,space,version")
    doc = _page_to_document(page_data)
    return ingest_document(doc)


def ingest_page_by_title(space_key: str, title: str) -> dict:
    """
    Fetch and ingest a Confluence page by space key and exact title.

    Args:
        space_key: e.g. "PROJ"
        title:     Exact page title.

    Returns:
        Ingestion result dict: {document_id, chunk_count, embedded_count}.
    """
    from services.confluence import get_page_by_title

    page_data = get_page_by_title(space_key, title, expand="body.storage,ancestors,space,version")
    doc = _page_to_document(page_data)
    return ingest_document(doc)


def ingest_space(space_key: str, max_pages: int = 50) -> List[dict]:
    """
    Ingest all pages in a Confluence space (up to max_pages).

    Args:
        space_key:  Confluence space key (e.g. "DOCS").
        max_pages:  Safety limit on the number of pages to ingest.

    Returns:
        List of per-page ingestion result dicts.
    """
    page_ids = _list_space_pages(space_key, max_pages)
    results = []
    for page_id in page_ids:
        try:
            result = ingest_page_by_id(page_id)
            result["page_id"] = page_id
            results.append(result)
        except Exception as exc:
            logger.error("Failed to ingest Confluence page %s: %s", page_id, exc)
            results.append({"page_id": page_id, "error": str(exc)})
    return results


# ── Conversion ────────────────────────────────────────────────────────────────

def _page_to_document(page_data: dict) -> DocumentRecord:
    """Convert a Confluence REST API response to a DocumentRecord."""
    page_id = str(page_data.get("id", ""))
    title = page_data.get("title", "")

    # Extract HTML body from storage format
    body_node = page_data.get("body", {})
    storage = body_node.get("storage", {})
    html_content = storage.get("value", "")

    # Convert HTML to structured plain text (preserves headings/tables/code)
    plain_text = clean_html_to_text(html_content) if html_content else ""

    # Build section hierarchy breadcrumb
    ancestors = page_data.get("ancestors", [])
    breadcrumb = " > ".join(a.get("title", "") for a in ancestors if a.get("title"))
    if breadcrumb:
        header = f"# {title}\nPath: {breadcrumb}\n\n"
    else:
        header = f"# {title}\n\n"

    raw_content = header + plain_text
    raw_content = clean_document(raw_content, source_type="confluence")

    # Build source URL
    space = page_data.get("space", {})
    space_key = space.get("key", "")
    from config import CONFLUENCE_URL
    source_url = (
        f"{CONFLUENCE_URL}/wiki/spaces/{space_key}/pages/{page_id}"
        if CONFLUENCE_URL and space_key
        else None
    )

    # Version info
    version = page_data.get("version", {})
    last_modified_by = (version.get("by") or {}).get("displayName", "")

    metadata = {
        "space_key": space_key,
        "space_name": space.get("name", ""),
        "breadcrumb": breadcrumb,
        "last_modified_by": last_modified_by,
        "version_number": version.get("number", 1),
    }

    return DocumentRecord(
        source_type="confluence",
        source_id=page_id,
        title=title,
        raw_content=raw_content,
        source_url=source_url,
        metadata=metadata,
    )


# ── Space listing ─────────────────────────────────────────────────────────────

def _list_space_pages(space_key: str, max_pages: int) -> List[str]:
    """Return a list of page IDs from a Confluence space."""
    from services.confluence import _validate_confluence_credentials
    import requests
    from config import CONFLUENCE_API_TOKEN, CONFLUENCE_URL, CONFLUENCE_USERNAME

    _validate_confluence_credentials()

    url = f"{CONFLUENCE_URL}/wiki/rest/api/content"
    page_ids: List[str] = []
    start = 0
    limit = min(25, max_pages)

    while len(page_ids) < max_pages:
        resp = requests.get(
            url,
            params={
                "spaceKey": space_key,
                "type": "page",
                "limit": limit,
                "start": start,
                "expand": "version",
            },
            auth=(CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN),
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if not resp.ok:
            logger.error("Failed to list Confluence space %s: %s", space_key, resp.text)
            break

        data = resp.json()
        results = data.get("results", [])
        if not results:
            break

        page_ids.extend(str(r["id"]) for r in results)

        links = data.get("_links", {})
        if not links.get("next"):
            break
        start += limit

    return page_ids[:max_pages]
