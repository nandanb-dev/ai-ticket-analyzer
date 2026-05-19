"""
routes/rag.py
─────────────
RAG (Retrieval-Augmented Generation) API routes.

Endpoints:

  POST /rag/ingest/jira         — Ingest Jira tickets
  POST /rag/ingest/confluence   — Ingest a Confluence page or space
  POST /rag/ingest/document     — Ingest PDF, DOCX, TXT, MD, or URL
  POST /rag/search              — Semantic + keyword hybrid search
  GET  /rag/documents           — List ingested documents (paginated)
  GET  /rag/documents/{id}      — Get a single document's metadata
  DELETE /rag/documents/{id}    — Delete a document and all its chunks
  GET  /rag/status              — Database statistics
"""

import json
import logging
from typing import List, Optional
from uuid import UUID

import anyio
from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from database import get_connection, is_db_available
from rag.context_builder import format_citations_for_response
from rag.models import MetadataFilter
from rag.retrieval import retrieve

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    """Normalize optional form text values coming from multipart Swagger forms."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    # Swagger UI often posts untouched optional fields as literal "string".
    if cleaned.lower() in {"null", "none", "undefined", "string", "<string>"}:
        return None
    return cleaned


# ── Request / Response models ──────────────────────────────────────────────────

class IngestJiraRequest(BaseModel):
    project_key: Optional[str] = Field(
        default=None,
        description="Ingest all tickets for a project (e.g. PROJ).",
    )
    epic_key: Optional[str] = Field(
        default=None,
        description="Ingest an epic and all its child tickets (e.g. PROJ-42).",
    )
    ticket_key: Optional[str] = Field(
        default=None,
        description="Ingest a single Jira ticket (e.g. PROJ-123).",
    )

    model_config = {"json_schema_extra": {
        "examples": [
            {"project_key": "SHOP"},
            {"epic_key": "SHOP-42"},
            {"ticket_key": "SHOP-123"},
        ]
    }}


class IngestConfluenceRequest(BaseModel):
    page_id: Optional[str] = Field(
        default=None,
        description="Numeric Confluence page ID (e.g. '123456').",
    )
    space_key: Optional[str] = Field(
        default=None,
        description="Confluence space key — ingests up to max_pages pages.",
    )
    title: Optional[str] = Field(
        default=None,
        description="Page title (required when using space_key without page_id).",
    )
    max_pages: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Max pages to ingest when ingesting an entire space.",
    )

    model_config = {"json_schema_extra": {
        "examples": [
            {"page_id": "123456"},
            {"space_key": "PROJ", "max_pages": 50},
        ]
    }}


class SearchRequest(BaseModel):
    query: str = Field(description="Natural language search query.")
    top_k: int = Field(default=50, ge=1, le=200, description="Candidate pool size before reranking.")
    top_n: int = Field(default=8, ge=1, le=50, description="Final results after reranking.")
    ticket_type: Optional[str] = Field(default=None, description="Filter: bug | story | task | epic")
    severity: Optional[str] = Field(default=None, description="Filter: critical | high | medium | low")
    component: Optional[str] = Field(default=None, description="Filter: component/module name (partial match).")
    team: Optional[str] = Field(default=None, description="Filter: team or assignee name (partial match).")
    service: Optional[str] = Field(default=None, description="Filter: service name (partial match).")
    source_type: Optional[str] = Field(default=None, description="Filter: jira | confluence | pdf | url")
    labels: Optional[List[str]] = Field(default=None, description="Filter: any of these labels must be present.")

    model_config = {"json_schema_extra": {
        "examples": [{
            "query": "payment gateway integration timeout issues",
            "top_n": 8,
            "ticket_type": "bug",
            "severity": "high",
            "component": "payments",
        }]
    }}


# ── Ingest: Jira ──────────────────────────────────────────────────────────────

@router.post(
    "/ingest/jira",
    summary="Ingest Jira tickets into the knowledge base",
    response_description="List of per-ticket ingestion results",
)
async def ingest_jira(req: IngestJiraRequest):
    """
    Fetch Jira tickets and ingest them into the RAG knowledge base.

    Provide exactly **one** of:
    - `project_key` — ingest all tickets in the project
    - `epic_key` — ingest an epic and its child tickets
    - `ticket_key` — ingest a single ticket

    Each ticket is cleaned, chunked, embedded, and stored with metadata
    (type, severity, component, team, service, labels) for metadata filtering.
    """
    _require_db()
    provided = [bool(req.project_key), bool(req.epic_key), bool(req.ticket_key)]
    if sum(provided) != 1:
        raise HTTPException(status_code=422, detail="Provide exactly one of: project_key, epic_key, ticket_key.")

    from rag.ingestion.jira_ingestion import ingest_epic, ingest_project, ingest_ticket

    try:
        if req.ticket_key:
            results = await anyio.to_thread.run_sync(lambda: ingest_ticket(req.ticket_key))
        elif req.epic_key:
            results = await anyio.to_thread.run_sync(lambda: ingest_epic(req.epic_key))
        else:
            results = await anyio.to_thread.run_sync(lambda: ingest_project(req.project_key))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    total_chunks = sum(r.get("chunk_count", 0) for r in results)
    total_embedded = sum(r.get("embedded_count", 0) for r in results)

    return {
        "message": f"Ingested {len(results)} ticket(s) → {total_chunks} chunks, {total_embedded} embedded.",
        "tickets_ingested": len(results),
        "total_chunks": total_chunks,
        "total_embedded": total_embedded,
        "results": results,
    }


# ── Ingest: Confluence ────────────────────────────────────────────────────────

@router.post(
    "/ingest/confluence",
    summary="Ingest a Confluence page or space into the knowledge base",
    response_description="Ingestion result(s)",
)
async def ingest_confluence(req: IngestConfluenceRequest):
    """
    Fetch Confluence content and ingest it into the RAG knowledge base.

    Provide one of:
    - `page_id` — ingest a specific page by numeric ID
    - `space_key` + optional `title` — ingest all pages in a space (up to `max_pages`)
    - `space_key` + `title` — ingest a specific page by space and title

    Document structure (headings, tables, code blocks) is preserved through
    the ingestion pipeline to maintain semantic boundaries.
    """
    _require_db()

    has_page_id = bool(req.page_id)
    has_space = bool(req.space_key)

    if not has_page_id and not has_space:
        raise HTTPException(status_code=422, detail="Provide page_id or space_key.")

    from rag.ingestion.confluence_ingestion import (
        ingest_page_by_id,
        ingest_page_by_title,
        ingest_space,
    )

    try:
        if has_page_id:
            result = await anyio.to_thread.run_sync(lambda: ingest_page_by_id(req.page_id))
            return {
                "message": f"Ingested page {req.page_id} → {result.get('chunk_count', 0)} chunks.",
                "results": [result],
            }
        elif has_space and req.title:
            result = await anyio.to_thread.run_sync(
                lambda: ingest_page_by_title(req.space_key, req.title)
            )
            return {
                "message": f"Ingested '{req.title}' → {result.get('chunk_count', 0)} chunks.",
                "results": [result],
            }
        else:
            results = await anyio.to_thread.run_sync(
                lambda: ingest_space(req.space_key, req.max_pages)
            )
            total_chunks = sum(r.get("chunk_count", 0) for r in results)
            return {
                "message": f"Ingested {len(results)} pages from space '{req.space_key}' → {total_chunks} chunks.",
                "pages_ingested": len(results),
                "total_chunks": total_chunks,
                "results": results,
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Ingest: Document / URL ────────────────────────────────────────────────────

@router.post(
    "/ingest/document",
    summary="Ingest a PDF, DOCX, plain text, or URL into the knowledge base",
    response_description="Ingestion result",
)
@router.post(
    "/inject/document",
    summary="Alias for ingest document endpoint",
    include_in_schema=False,
)
async def ingest_document_endpoint(
    file: Optional[UploadFile] = File(
        default=None,
        description="PDF / DOCX / TXT / MD file to ingest.",
    ),
    url: Optional[str] = Form(
        default=None,
        description="Web URL to fetch and ingest.",
    ),
    title: Optional[str] = Form(
        default=None,
        description="Human-readable title for the document (optional override).",
    ),
    prd_text: Optional[str] = Form(
        default=None,
        description="Plain text content to ingest directly.",
    ),
    source_id: Optional[str] = Form(
        default=None,
        description="Stable identifier for plain text content (required with prd_text).",
    ),
):
    """
    Ingest a document into the RAG knowledge base.

    Accepts **one** of:
    - `file` — upload a PDF, DOCX, TXT, or MD file
    - `url` — a web URL to fetch and parse
    - `prd_text` + `source_id` — raw plain text

    Supported priorities: Jira > Confluence > PDFs > URLs
    """
    _require_db()

    normalized_url = _normalize_optional_text(url)
    normalized_text = _normalize_optional_text(prd_text)
    normalized_source_id = _normalize_optional_text(source_id)
    normalized_title = _normalize_optional_text(title)

    has_file = file is not None and bool((file.filename or "").strip())
    has_url = bool(normalized_url)
    has_text = bool(normalized_text) and bool(normalized_source_id)

    sources_provided = sum([has_file, has_url, has_text])
    if sources_provided == 0:
        raise HTTPException(
            status_code=422,
            detail="Provide one of: file, url, or (prd_text + source_id).",
        )
    if sources_provided > 1:
        raise HTTPException(
            status_code=422,
            detail="Provide only one source: file, url, or (prd_text + source_id).",
        )

    from rag.ingestion.document_ingestion import (
        ingest_docx,
        ingest_pdf,
        ingest_text,
        ingest_url,
    )

    try:
        if has_file:
            content = await file.read()
            filename = file.filename or "upload"
            name_lower = filename.lower()
            if name_lower.endswith(".pdf"):
                result = await anyio.to_thread.run_sync(
                    lambda: ingest_pdf(content, filename, title=normalized_title)
                )
            elif name_lower.endswith(".docx"):
                result = await anyio.to_thread.run_sync(
                    lambda: ingest_docx(content, filename, title=normalized_title)
                )
            elif name_lower.endswith((".txt", ".md")):
                text = content.decode("utf-8", errors="ignore")
                sid = filename.replace(" ", "-").lower()
                result = await anyio.to_thread.run_sync(
                    lambda: ingest_text(text, sid, normalized_title or filename)
                )
            else:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unsupported file type: {filename}. Use PDF, DOCX, TXT, or MD.",
                )
            return {
                "message": f"Ingested '{filename}' → {result.get('chunk_count', 0)} chunks.",
                "source": f"file ({filename})",
                **result,
            }

        elif has_url:
            result = await anyio.to_thread.run_sync(lambda: ingest_url(normalized_url, title=normalized_title))
            return {
                "message": f"Ingested URL → {result.get('chunk_count', 0)} chunks.",
                "source": f"url ({normalized_url})",
                **result,
            }

        else:
            result = await anyio.to_thread.run_sync(
                lambda: ingest_text(normalized_text, normalized_source_id, normalized_title or normalized_source_id)
            )
            return {
                "message": f"Ingested text '{normalized_source_id}' → {result.get('chunk_count', 0)} chunks.",
                "source": "text",
                **result,
            }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Semantic Search ───────────────────────────────────────────────────────────

@router.post(
    "/search",
    summary="Hybrid semantic search over the knowledge base",
    response_description="Ranked list of relevant chunks with citations",
)
async def search_knowledge_base(req: SearchRequest):
    """
    Search the knowledge base using **hybrid retrieval**:

    1. **Dense retrieval** — cosine similarity via pgvector (HNSW)
    2. **BM25 keyword search** — PostgreSQL full-text search
    3. **Reciprocal Rank Fusion** — merges both ranked lists
    4. **Cross-encoder reranking** — ms-marco-MiniLM reranker refines top-50 → top-N

    Supports **metadata filtering** on: `ticket_type`, `severity`, `component`,
    `team`, `service`, `source_type`, `labels`.

    Returns ranked results with full content, source attribution, and relevance score.
    """
    _require_db()

    metadata_filter = MetadataFilter(
        ticket_type=req.ticket_type,
        severity=req.severity,
        component=req.component,
        team=req.team,
        service=req.service,
        source_type=req.source_type,
        labels=req.labels,
    )

    results = await anyio.to_thread.run_sync(
        lambda: retrieve(req.query, top_k=req.top_k, rerank_top_n=req.top_n, metadata_filter=metadata_filter)
    )

    citations = format_citations_for_response(
        [
            type("Citation", (), {
                "source_type": r.source_type,
                "source_id": r.source_id,
                "title": r.title or r.source_id,
                "source_url": r.source_url,
                "excerpt": r.content[:200],
                "score": r.score,
            })()
            for r in results
        ]
    )

    return {
        "query": req.query,
        "result_count": len(results),
        "results": [
            {
                "chunk_id": str(r.chunk_id),
                "document_id": str(r.document_id),
                "source_type": r.source_type,
                "source_id": r.source_id,
                "title": r.title,
                "source_url": r.source_url,
                "relevance_score": round(r.score, 4),
                "ticket_type": r.ticket_type,
                "severity": r.severity,
                "component": r.component,
                "team": r.team,
                "service": r.service,
                "heading_context": r.heading_context,
                "content": r.content,
            }
            for r in results
        ],
        "citations": citations,
    }


# ── Document management ───────────────────────────────────────────────────────

@router.get(
    "/documents",
    summary="List all ingested documents",
    response_description="Paginated list of document records",
)
async def list_documents(
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page."),
    source_type: Optional[str] = Query(default=None, description="Filter by source_type: jira | confluence | pdf | url"),
):
    """
    List all documents currently in the knowledge base, with pagination.

    Returns document metadata (id, source_type, source_id, title, chunk count,
    timestamps) without the raw content.
    """
    _require_db()

    offset = (page - 1) * page_size

    type_filter = " WHERE d.source_type = %s" if source_type else ""
    params: list = ([source_type] if source_type else []) + [page_size, offset]

    sql = f"""
        SELECT
            d.id,
            d.source_type,
            d.source_id,
            d.title,
            d.source_url,
            d.metadata,
            d.created_at,
            d.updated_at,
            COUNT(c.id) AS chunk_count
        FROM rag_documents d
        LEFT JOIN rag_chunks c ON c.document_id = d.id
        {type_filter}
        GROUP BY d.id
        ORDER BY d.updated_at DESC
        LIMIT %s OFFSET %s
    """

    count_sql = f"SELECT COUNT(*) FROM rag_documents d {type_filter}"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql, [source_type] if source_type else [])
            total = cur.fetchone()[0]
            cur.execute(sql, params)
            rows = cur.fetchall()

    documents = [
        {
            "id": str(row[0]),
            "source_type": row[1],
            "source_id": row[2],
            "title": row[3],
            "source_url": row[4],
            "metadata": row[5],
            "created_at": row[6].isoformat() if row[6] else None,
            "updated_at": row[7].isoformat() if row[7] else None,
            "chunk_count": row[8],
        }
        for row in rows
    ]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "documents": documents,
    }


@router.get(
    "/documents/{document_id}",
    summary="Get a document by ID",
    response_description="Document metadata and chunk count",
)
async def get_document(document_id: UUID):
    """
    Retrieve metadata for a single ingested document.

    Does **not** return chunk content or embeddings — use `/rag/search` to
    perform a semantic search over chunks.
    """
    _require_db()

    sql = """
        SELECT
            d.id, d.source_type, d.source_id, d.title, d.source_url,
            d.metadata, d.created_at, d.updated_at,
            COUNT(c.id)                                   AS chunk_count,
            COUNT(c.id) FILTER (WHERE c.embedding IS NOT NULL) AS embedded_count
        FROM rag_documents d
        LEFT JOIN rag_chunks c ON c.document_id = d.id
        WHERE d.id = %s
        GROUP BY d.id
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (document_id,))
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")

    return {
        "id": str(row[0]),
        "source_type": row[1],
        "source_id": row[2],
        "title": row[3],
        "source_url": row[4],
        "metadata": row[5],
        "created_at": row[6].isoformat() if row[6] else None,
        "updated_at": row[7].isoformat() if row[7] else None,
        "chunk_count": row[8],
        "embedded_count": row[9],
    }


@router.delete(
    "/documents/{document_id}",
    summary="Delete a document and all its chunks",
    response_description="Deletion confirmation",
)
async def delete_document(document_id: UUID):
    """
    Delete a document record and **all its associated chunks** from the
    knowledge base. This operation is irreversible.

    Re-ingest the source to restore it.
    """
    _require_db()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT source_type, source_id FROM rag_documents WHERE id = %s", (document_id,))
            row = cur.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
            source_type, source_id = row[0], row[1]
            # Chunks are deleted via ON DELETE CASCADE on the FK
            cur.execute("DELETE FROM rag_documents WHERE id = %s", (document_id,))

    return {
        "message": f"Deleted document '{source_type}/{source_id}' and all its chunks.",
        "document_id": str(document_id),
    }


# ── Status ────────────────────────────────────────────────────────────────────

@router.get(
    "/status",
    summary="RAG knowledge base status and statistics",
    response_description="Database availability and document/chunk counts",
)
async def rag_status():
    """
    Return the health and statistics of the RAG knowledge base.

    Includes:
    - Database availability
    - Total documents and chunks
    - Breakdown by source_type
    - Embedding coverage (% of chunks with embeddings)
    """
    if not is_db_available():
        return {
            "available": False,
            "message": "Database is not configured or unreachable. Set DATABASE_URL in .env.",
        }

    stats_sql = """
        SELECT
            d.source_type,
            COUNT(DISTINCT d.id)                                    AS doc_count,
            COUNT(c.id)                                             AS chunk_count,
            COUNT(c.id) FILTER (WHERE c.embedding IS NOT NULL)      AS embedded_count
        FROM rag_documents d
        LEFT JOIN rag_chunks c ON c.document_id = d.id
        GROUP BY d.source_type
        ORDER BY doc_count DESC
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM rag_documents")
            total_docs = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM rag_chunks")
            total_chunks = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM rag_chunks WHERE embedding IS NOT NULL")
            embedded_chunks = cur.fetchone()[0]
            cur.execute(stats_sql)
            breakdown_rows = cur.fetchall()

    breakdown = [
        {
            "source_type": row[0],
            "documents": row[1],
            "chunks": row[2],
            "embedded": row[3],
        }
        for row in breakdown_rows
    ]

    return {
        "available": True,
        "total_documents": total_docs,
        "total_chunks": total_chunks,
        "embedded_chunks": embedded_chunks,
        "embedding_coverage_pct": round(
            (embedded_chunks / total_chunks * 100) if total_chunks > 0 else 0, 1
        ),
        "breakdown_by_source": breakdown,
    }


# ── Helper ────────────────────────────────────────────────────────────────────

def _require_db():
    """Raise 503 if the database is not available."""
    if not is_db_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "RAG knowledge base is unavailable. "
                "Configure DATABASE_URL in your .env and ensure pgvector is installed."
            ),
        )
