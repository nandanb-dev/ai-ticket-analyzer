"""
rag/ingestion/document_ingestion.py
────────────────────────────────────
Ingest PDFs and web URLs into the RAG knowledge base.

Supported sources:
  - PDF bytes   (parsed with pypdf)
  - DOCX bytes  (parsed with python-docx)
  - Plain text  (.txt / .md)
  - Web URLs    (fetched with httpx, cleaned with BeautifulSoup)

No files are saved to disk; all content is processed in-memory.
"""

import hashlib
import logging
import re
from typing import Optional

from rag.cleaning import clean_document, clean_html_to_text
from rag.ingestion.base import ingest_document
from rag.models import DocumentRecord

logger = logging.getLogger(__name__)


# ── Public API ────────────────────────────────────────────────────────────────

def ingest_pdf(content: bytes, filename: str, title: Optional[str] = None) -> dict:
    """
    Ingest a PDF file from raw bytes.

    Args:
        content:  Raw PDF bytes.
        filename: Original filename (used as source_id).
        title:    Human-readable title (defaults to filename).

    Returns:
        Ingestion result dict: {document_id, chunk_count, embedded_count}.
    """
    text = _extract_pdf_text(content)
    text = clean_document(text, source_type="pdf")

    source_id = _stable_id(filename)
    doc = DocumentRecord(
        source_type="pdf",
        source_id=source_id,
        title=title or filename,
        raw_content=text,
        source_url=None,
        metadata={"filename": filename},
    )
    return ingest_document(doc)


def ingest_docx(content: bytes, filename: str, title: Optional[str] = None) -> dict:
    """
    Ingest a DOCX file from raw bytes.

    Args:
        content:  Raw DOCX bytes.
        filename: Original filename.
        title:    Human-readable title (defaults to filename).

    Returns:
        Ingestion result dict: {document_id, chunk_count, embedded_count}.
    """
    text = _extract_docx_text(content)
    text = clean_document(text, source_type="pdf")

    source_id = _stable_id(filename)
    doc = DocumentRecord(
        source_type="pdf",
        source_id=source_id,
        title=title or filename,
        raw_content=text,
        source_url=None,
        metadata={"filename": filename},
    )
    return ingest_document(doc)


def ingest_text(
    text: str,
    source_id: str,
    title: str,
    source_url: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """
    Ingest arbitrary plain text.

    Args:
        text:       The raw text content.
        source_id:  A stable identifier for this document (e.g. filename or slug).
        title:      Human-readable title.
        source_url: Optional URL for attribution.
        metadata:   Optional extra metadata dict.

    Returns:
        Ingestion result dict: {document_id, chunk_count, embedded_count}.
    """
    cleaned = clean_document(text, source_type="pdf")
    doc = DocumentRecord(
        source_type="pdf",
        source_id=source_id,
        title=title,
        raw_content=cleaned,
        source_url=source_url,
        metadata=metadata or {},
    )
    return ingest_document(doc)


def ingest_url(url: str, title: Optional[str] = None) -> dict:
    """
    Fetch a web page and ingest its main content.

    Args:
        url:   The URL to fetch and parse.
        title: Optional override for the page title.

    Returns:
        Ingestion result dict: {document_id, chunk_count, embedded_count}.
    """
    html, detected_title = _fetch_url(url)
    text = clean_html_to_text(html)

    if not text.strip():
        raise ValueError(f"No usable text content found at URL: {url}")

    source_id = _url_to_id(url)
    doc = DocumentRecord(
        source_type="url",
        source_id=source_id,
        title=title or detected_title or url,
        raw_content=text,
        source_url=url,
        metadata={"original_url": url},
    )
    return ingest_document(doc)


# ── Extraction helpers ────────────────────────────────────────────────────────

def _extract_pdf_text(content: bytes) -> str:
    """Extract text from PDF bytes using pypdf."""
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(f"<!-- Page {i} -->\n{page_text}")
        return "\n\n".join(pages)
    except Exception as exc:
        logger.error("PDF extraction failed: %s", exc)
        return ""


def _extract_docx_text(content: bytes) -> str:
    """Extract text from DOCX bytes using python-docx."""
    try:
        import io
        from docx import Document
        doc = Document(io.BytesIO(content))
        paragraphs = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            # Map heading styles to markdown headings
            style_name = (para.style.name or "").lower()
            if "heading 1" in style_name:
                text = f"# {text}"
            elif "heading 2" in style_name:
                text = f"## {text}"
            elif "heading 3" in style_name:
                text = f"### {text}"
            paragraphs.append(text)
        return "\n\n".join(paragraphs)
    except Exception as exc:
        logger.error("DOCX extraction failed: %s", exc)
        return ""


def _fetch_url(url: str) -> tuple[str, str]:
    """
    Fetch a URL and return (html_content, page_title).

    Uses httpx with a reasonable timeout and common User-Agent.
    """
    try:
        import httpx
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; AI-Ticket-Analyzer/1.0; "
                "+https://github.com/nandanb-dev/ai-ticket-analyzer)"
            )
        }
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()

        html = resp.text
        title = _extract_title(html)
        return html, title
    except Exception as exc:
        logger.error("Failed to fetch URL %s: %s", url, exc)
        raise RuntimeError(f"Could not fetch URL: {exc}") from exc


def _extract_title(html: str) -> str:
    """Extract <title> text from HTML."""
    match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _stable_id(filename: str) -> str:
    """Create a stable, filesystem-safe ID from a filename."""
    # Normalise: lowercase, replace spaces with hyphens, strip special chars
    name = re.sub(r"[^A-Za-z0-9._-]", "-", filename.lower()).strip("-")
    return name[:200]  # cap length


def _url_to_id(url: str) -> str:
    """Create a stable ID from a URL using a short hash + domain."""
    short_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    domain_match = re.search(r"https?://([^/]+)", url)
    domain = domain_match.group(1).replace(".", "-") if domain_match else "url"
    return f"{domain}-{short_hash}"
