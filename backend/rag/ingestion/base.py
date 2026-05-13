"""
rag/ingestion/base.py
─────────────────────
Shared ingestion utilities: persist DocumentRecord + ChunkRecords to PostgreSQL,
then generate and store embeddings.
"""

import json
import logging
from typing import List, Optional
from uuid import UUID

from database import get_connection
from rag.chunking import chunk_document
from rag.embeddings import embed_texts
from rag.models import ChunkRecord, DocumentRecord

logger = logging.getLogger(__name__)


# ── Document persistence ──────────────────────────────────────────────────────

def upsert_document(doc: DocumentRecord) -> UUID:
    """
    Insert or update a document record.

    Uses (source_type, source_id) as the natural key — existing records are
    overwritten so re-ingesting a source always reflects the latest content.

    Returns:
        The UUID of the persisted document row.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rag_documents
                    (source_type, source_id, source_url, title, raw_content, metadata, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (source_type, source_id)
                DO UPDATE SET
                    source_url  = EXCLUDED.source_url,
                    title       = EXCLUDED.title,
                    raw_content = EXCLUDED.raw_content,
                    metadata    = EXCLUDED.metadata,
                    updated_at  = NOW()
                RETURNING id
                """,
                (
                    doc.source_type,
                    doc.source_id,
                    doc.source_url,
                    doc.title,
                    doc.raw_content,
                    json.dumps(doc.metadata),
                ),
            )
            row = cur.fetchone()
    return row[0]


def delete_chunks_for_document(document_id: UUID) -> None:
    """Remove all existing chunks for a document before re-chunking."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rag_chunks WHERE document_id = %s", (document_id,))


def insert_chunks(chunks: List[ChunkRecord]) -> List[UUID]:
    """
    Batch-insert chunk records (without embeddings).

    Returns:
        List of new chunk UUIDs in insertion order.
    """
    if not chunks:
        return []

    chunk_ids: List[UUID] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for chunk in chunks:
                cur.execute(
                    """
                    INSERT INTO rag_chunks
                        (document_id, chunk_index, content,
                         source_type, source_id,
                         ticket_type, severity, component, team, service,
                         labels, heading_context, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        chunk.document_id,
                        chunk.chunk_index,
                        chunk.content,
                        chunk.source_type,
                        chunk.source_id,
                        chunk.ticket_type,
                        chunk.severity,
                        chunk.component,
                        chunk.team,
                        chunk.service,
                        chunk.labels or [],
                        chunk.heading_context,
                        json.dumps(chunk.metadata),
                    ),
                )
                row = cur.fetchone()
                chunk_ids.append(row[0])

    return chunk_ids


def update_chunk_embeddings(chunk_ids: List[UUID], embeddings: List[List[float]]) -> None:
    """Persist computed embeddings back to the DB in a single transaction."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            for chunk_id, embedding in zip(chunk_ids, embeddings):
                cur.execute(
                    "UPDATE rag_chunks SET embedding = %s WHERE id = %s",
                    (embedding, chunk_id),
                )


# ── Full ingestion pipeline ───────────────────────────────────────────────────

def ingest_document(doc: DocumentRecord) -> dict:
    """
    Full ingestion pipeline for a single DocumentRecord:
      1. Upsert document row
      2. Delete existing chunks (for re-ingestion)
      3. Chunk the document
      4. Insert chunks
      5. Generate + store embeddings

    Args:
        doc: Populated DocumentRecord with raw_content.

    Returns:
        Summary dict: {document_id, chunk_count, embedded_count}
    """
    # Step 1: Upsert document
    document_id = upsert_document(doc)
    doc.id = document_id

    # Step 2: Clear old chunks
    delete_chunks_for_document(document_id)

    # Step 3: Chunk
    chunks = chunk_document(doc)
    if not chunks:
        logger.warning("No chunks produced for document %s / %s", doc.source_type, doc.source_id)
        return {"document_id": str(document_id), "chunk_count": 0, "embedded_count": 0}

    # Step 4: Insert chunks (without embeddings)
    chunk_ids = insert_chunks(chunks)

    # Step 5: Embed + store
    texts = [c.content for c in chunks]
    try:
        embeddings = embed_texts(texts)
        update_chunk_embeddings(chunk_ids, embeddings)
        embedded_count = sum(1 for e in embeddings if not all(v == 0.0 for v in e))
    except Exception as exc:
        logger.error("Embedding failed for document %s: %s", doc.source_id, exc)
        embedded_count = 0

    logger.info(
        "Ingested %s/%s → %d chunks, %d embedded",
        doc.source_type, doc.source_id, len(chunks), embedded_count,
    )
    return {
        "document_id": str(document_id),
        "chunk_count": len(chunks),
        "embedded_count": embedded_count,
    }
