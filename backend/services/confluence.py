import re
from typing import Dict, List, Optional
from html import unescape

import requests
from fastapi import HTTPException

from config import CONFLUENCE_API_TOKEN, CONFLUENCE_URL, CONFLUENCE_USERNAME


def _validate_confluence_credentials() -> None:
    """Raise HTTPException if Confluence credentials are not configured."""
    if not all([CONFLUENCE_URL, CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN]):
        raise HTTPException(
            status_code=500,
            detail="Confluence credentials not configured in .env (CONFLUENCE_URL, CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN)"
        )


def _html_to_plain_text(html: str) -> str:
    """
    Convert HTML content to plain text.
    Strips tags and decodes HTML entities.
    """
    # Remove script and style elements
    html = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Replace <br>, <p>, <div>, <li> with newlines
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</?(p|div|li|tr|h[1-6])[^>]*>', '\n', html, flags=re.IGNORECASE)
    # Replace list items with bullet points
    html = re.sub(r'<li[^>]*>', '\n• ', html, flags=re.IGNORECASE)
    # Remove all remaining HTML tags
    html = re.sub(r'<[^>]+>', '', html)
    # Decode HTML entities
    html = unescape(html)
    # Normalize whitespace
    html = re.sub(r'\n\s*\n', '\n\n', html)
    html = re.sub(r' +', ' ', html)
    return html.strip()


def get_page_by_id(page_id: str, expand: str = "body.storage") -> Dict:
    """
    Fetch a Confluence page by its ID.
    
    Args:
        page_id: The Confluence page ID
        expand: Fields to expand (default: body.storage for HTML content)
    
    Returns:
        Dict with page metadata and content
    """
    _validate_confluence_credentials()
    
    url = f"{CONFLUENCE_URL}/wiki/rest/api/content/{page_id}"
    
    resp = requests.get(
        url,
        params={"expand": expand},
        auth=(CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    
    if not resp.ok:
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Confluence page '{page_id}' not found.")
        raise HTTPException(
            status_code=502,
            detail=f"Confluence API error: {resp.status_code} - {resp.text}"
        )
    
    return resp.json()


def get_page_by_title(space_key: str, title: str, expand: str = "body.storage") -> Dict:
    """
    Fetch a Confluence page by space key and title.
    
    Args:
        space_key: The Confluence space key (e.g., 'PROJ', 'DOCS')
        title: The exact page title
        expand: Fields to expand (default: body.storage for HTML content)
    
    Returns:
        Dict with page metadata and content
    """
    _validate_confluence_credentials()
    
    url = f"{CONFLUENCE_URL}/wiki/rest/api/content"
    
    resp = requests.get(
        url,
        params={
            "spaceKey": space_key,
            "title": title,
            "expand": expand,
        },
        auth=(CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    
    if not resp.ok:
        raise HTTPException(
            status_code=502,
            detail=f"Confluence API error: {resp.status_code} - {resp.text}"
        )
    
    data = resp.json()
    results = data.get("results", [])
    
    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"Page '{title}' not found in space '{space_key}'."
        )
    
    return results[0]


def search_pages(query: str, space_key: Optional[str] = None, limit: int = 10) -> List[Dict]:
    """
    Search for Confluence pages using CQL (Confluence Query Language).
    
    Args:
        query: Search query string
        space_key: Optional space key to limit search
        limit: Maximum number of results
    
    Returns:
        List of matching pages with metadata
    """
    _validate_confluence_credentials()
    
    # Build CQL query
    cql_parts = [f'text ~ "{query}"', 'type = "page"']
    if space_key:
        cql_parts.append(f'space = "{space_key}"')
    cql = " AND ".join(cql_parts)
    
    url = f"{CONFLUENCE_URL}/wiki/rest/api/content/search"
    
    resp = requests.get(
        url,
        params={
            "cql": cql,
            "limit": limit,
            "expand": "space,version",
        },
        auth=(CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    
    if not resp.ok:
        raise HTTPException(
            status_code=502,
            detail=f"Confluence search error: {resp.status_code} - {resp.text}"
        )
    
    data = resp.json()
    return data.get("results", [])


def get_page_content_as_text(page_id: str) -> Dict:
    """
    Fetch a Confluence page and return its content as plain text.
    
    Args:
        page_id: The Confluence page ID
    
    Returns:
        Dict with page title, id, space, and plain text content
    """
    page = get_page_by_id(page_id, expand="body.storage,space,version")
    
    html_content = page.get("body", {}).get("storage", {}).get("value", "")
    plain_text = _html_to_plain_text(html_content)
    
    return {
        "id": page.get("id"),
        "title": page.get("title"),
        "space_key": page.get("space", {}).get("key"),
        "space_name": page.get("space", {}).get("name"),
        "version": page.get("version", {}).get("number"),
        "content": plain_text,
        "url": f"{CONFLUENCE_URL}/wiki{page.get('_links', {}).get('webui', '')}",
    }


def get_space_pages(space_key: str, limit: int = 25) -> List[Dict]:
    """
    List pages in a Confluence space.
    
    Args:
        space_key: The Confluence space key
        limit: Maximum number of pages to return
    
    Returns:
        List of page summaries
    """
    _validate_confluence_credentials()
    
    url = f"{CONFLUENCE_URL}/wiki/rest/api/content"
    
    resp = requests.get(
        url,
        params={
            "spaceKey": space_key,
            "type": "page",
            "limit": limit,
            "expand": "version",
        },
        auth=(CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    
    if not resp.ok:
        raise HTTPException(
            status_code=502,
            detail=f"Confluence API error: {resp.status_code} - {resp.text}"
        )
    
    data = resp.json()
    pages = []
    
    for page in data.get("results", []):
        pages.append({
            "id": page.get("id"),
            "title": page.get("title"),
            "version": page.get("version", {}).get("number"),
        })
    
    return pages
