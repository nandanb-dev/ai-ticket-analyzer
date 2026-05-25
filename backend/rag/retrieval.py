"""
rag/retrieval.py
────────────────
Hybrid semantic retrieval layer combining:

  1. Dense retrieval   — cosine similarity via pgvector (HNSW index)
  2. BM25 retrieval    — PostgreSQL full-text search (ts_rank_cd)
  3. Metadata filtering — ticket_type, severity, component, team, service, source_type
  4. Reciprocal Rank Fusion (RRF) — merges dense + BM25 ranked lists
  5. Cross-encoder reranking — final pass via flashrank (top-50 → top-N)

Returns a list of RetrievalResult objects with fused/reranked scores.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from config import BM25_WEIGHT, DENSE_WEIGHT, RERANK_TOP_N, RETRIEVAL_TOP_K, RRF_K
from database import get_connection
from rag.embeddings import embed_query
from rag.models import MetadataFilter, RetrievalResult
from rag.reranker import rerank

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he", "in", "is",
    "it", "its", "of", "on", "that", "the", "to", "was", "were", "will", "with", "i", "we", "you",
    "they", "them", "this", "these", "those", "or", "if", "then", "than", "can", "could", "should",
    "would", "need", "want", "about", "into", "our", "your", "my", "me", "do", "does", "did",
}


# ── Public API ────────────────────────────────────────────────────────────────

def retrieve(
    query: str,
    top_k: int = RETRIEVAL_TOP_K,
    rerank_top_n: int = RERANK_TOP_N,
    metadata_filter: Optional[MetadataFilter] = None,
) -> List[RetrievalResult]:
    """
    Hybrid retrieval: dense + BM25 + metadata filtering + cross-encoder reranking.

    Args:
        query:           Natural language query or ticket text.
        top_k:           Number of candidates to fetch before reranking.
        rerank_top_n:    Final number of results to return after reranking.
        metadata_filter: Optional metadata constraints (ticket_type, severity, etc.).

    Returns:
        List of RetrievalResult sorted by relevance (best first).
        Returns [] if the database is unavailable.
    """
    try:
        query_embedding = embed_query(query)
        dense_hits = _dense_search(query_embedding, top_k, metadata_filter)
        bm25_hits = _bm25_search(query, top_k, metadata_filter)
        fused = _reciprocal_rank_fusion(dense_hits, bm25_hits)
        # Take top_k candidates before reranking
        candidates = fused[:top_k]
        if not candidates:
            return []
        reranked = rerank(query, candidates, top_n=rerank_top_n)
        return reranked
    except RuntimeError as exc:
        logger.warning("Retrieval skipped (DB unavailable): %s", exc)
        return []
    except Exception as exc:
        logger.error("Retrieval failed: %s", exc)
        return []


def retrieve_keyword_first(
    query: str,
    top_n: int = 8,
    metadata_filter: Optional[MetadataFilter] = None,
) -> List[RetrievalResult]:
    """
    Fast lexical retrieval used for chat turns.

    This avoids embedding + cross-encoder latency and returns BM25-ranked hits
    when query keywords exist in ingested documents.
    """
    try:
        bm25_hits = _bm25_search(query, limit=max(top_n * 2, top_n), metadata_filter=metadata_filter)
        if not bm25_hits:
            return []

        ordered_ids = [chunk_id for chunk_id, _score in bm25_hits]
        score_map = {chunk_id: float(score) for chunk_id, score in bm25_hits}
        chunk_data = _fetch_chunks_by_ids(ordered_ids)

        results: List[RetrievalResult] = []
        for chunk_id in ordered_ids:
            row = chunk_data.get(chunk_id)
            if not row:
                continue
            results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    document_id=row["document_id"],
                    content=row["content"],
                    score=score_map.get(chunk_id, 0.0),
                    source_type=row["source_type"] or "",
                    source_id=row["source_id"] or "",
                    title=row["title"] or "",
                    source_url=row["source_url"],
                    ticket_type=row["ticket_type"],
                    severity=row["severity"],
                    component=row["component"],
                    team=row["team"],
                    service=row["service"],
                    heading_context=row["heading_context"],
                    metadata=row["metadata"] or {},
                )
            )
            if len(results) >= top_n:
                break

        return results
    except RuntimeError as exc:
        logger.warning("Keyword retrieval skipped (DB unavailable): %s", exc)
        return []
    except Exception as exc:
        logger.error("Keyword retrieval failed: %s", exc)
        return []


# ── Dense retrieval ───────────────────────────────────────────────────────────

def _dense_search(
    embedding: List[float],
    limit: int,
    metadata_filter: Optional[MetadataFilter],
) -> List[Tuple[UUID, float]]:
    """
    Query rag_chunks by cosine similarity.

    Returns list of (chunk_id, similarity_score) sorted best-first.
    """
    where_clause, params = _build_where_clause(metadata_filter)

    sql = f"""
        SELECT
            c.id,
            1 - (c.embedding <=> %s::vector) AS similarity
        FROM rag_chunks c
        WHERE c.embedding IS NOT NULL
          {where_clause}
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [embedding] + params + [embedding, limit])
            rows = cur.fetchall()

    return [(row[0], float(row[1])) for row in rows]


# ── BM25 / full-text retrieval ────────────────────────────────────────────────

def _bm25_search(
    query: str,
    limit: int,
    metadata_filter: Optional[MetadataFilter],
) -> List[Tuple[UUID, float]]:
    """
    Query rag_chunks using PostgreSQL full-text search (ts_rank_cd).

    Returns list of (chunk_id, bm25_score) sorted best-first.
    """
    ts_query = _text_to_tsquery(query)
    if not ts_query:
        return []

    where_clause, params = _build_where_clause(metadata_filter)

    sql = f"""
        SELECT
            c.id,
            ts_rank_cd(
                COALESCE(c.content_tsv, to_tsvector('english', COALESCE(c.content, ''))),
                to_tsquery('english', %s)
            ) AS bm25_score
        FROM rag_chunks c
        WHERE COALESCE(c.content_tsv, to_tsvector('english', COALESCE(c.content, '')))
              @@ to_tsquery('english', %s)
          {where_clause}
        ORDER BY bm25_score DESC
        LIMIT %s
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [ts_query, ts_query] + params + [limit])
            rows = cur.fetchall()

    return [(row[0], float(row[1])) for row in rows]


def _text_to_tsquery(text: str) -> str:
    """Convert a plain text query to a PostgreSQL tsquery string."""
    tokens = _extract_keywords(text)
    if not tokens:
        return ""
    # Use OR to maximize recall in short chat prompts and surface doc citations quickly.
    safe_tokens = [re.sub(r"[^A-Za-z0-9_]", "", t) for t in tokens[:20]]
    safe_tokens = [t for t in safe_tokens if t]
    return " | ".join(f"{t}:*" for t in safe_tokens) if safe_tokens else ""


def _extract_keywords(text: str) -> List[str]:
    """Extract lexical keywords for BM25/FTS matching."""
    raw_tokens = re.findall(r"[A-Za-z0-9_]{2,}", (text or "").lower())
    filtered = [t for t in raw_tokens if t not in _STOPWORDS]

    # Preserve order and keep the query compact for fast FTS.
    seen = set()
    keywords: List[str] = []
    for token in filtered:
        if token in seen:
            continue
        seen.add(token)
        keywords.append(token)
        if len(keywords) >= 16:
            break
    return keywords


# ── Reciprocal Rank Fusion ────────────────────────────────────────────────────

def _reciprocal_rank_fusion(
    dense_hits: List[Tuple[UUID, float]],
    bm25_hits: List[Tuple[UUID, float]],
) -> List[RetrievalResult]:
    """
    Merge dense and BM25 ranked lists using Reciprocal Rank Fusion.

    RRF score = Σ  weight_i / (k + rank_i)

    Returns RetrievalResult objects sorted by descending fused score.
    The full chunk data is fetched from the DB for the merged candidate set.
    """
    rrf_scores: Dict[UUID, float] = {}

    for rank, (chunk_id, _) in enumerate(dense_hits):
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + DENSE_WEIGHT / (RRF_K + rank + 1)

    for rank, (chunk_id, _) in enumerate(bm25_hits):
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + BM25_WEIGHT / (RRF_K + rank + 1)

    if not rrf_scores:
        return []

    sorted_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
    chunk_data = _fetch_chunks_by_ids(sorted_ids)

    results: List[RetrievalResult] = []
    for chunk_id in sorted_ids:
        if chunk_id not in chunk_data:
            continue
        row = chunk_data[chunk_id]
        results.append(
            RetrievalResult(
                chunk_id=chunk_id,
                document_id=row["document_id"],
                content=row["content"],
                score=rrf_scores[chunk_id],
                source_type=row["source_type"] or "",
                source_id=row["source_id"] or "",
                title=row["title"] or "",
                source_url=row["source_url"],
                ticket_type=row["ticket_type"],
                severity=row["severity"],
                component=row["component"],
                team=row["team"],
                service=row["service"],
                heading_context=row["heading_context"],
                metadata=row["metadata"] or {},
            )
        )
    return results


def _fetch_chunks_by_ids(chunk_ids: List[UUID]) -> Dict[UUID, dict]:
    """Batch-fetch chunk rows + parent document metadata."""
    if not chunk_ids:
        return {}

    placeholders = ",".join(["%s"] * len(chunk_ids))
    sql = f"""
        SELECT
            c.id,
            c.document_id,
            c.content,
            c.source_type,
            c.source_id,
            c.ticket_type,
            c.severity,
            c.component,
            c.team,
            c.service,
            c.heading_context,
            c.metadata,
            d.title,
            d.source_url
        FROM rag_chunks c
        JOIN rag_documents d ON d.id = c.document_id
        WHERE c.id IN ({placeholders})
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, chunk_ids)
            rows = cur.fetchall()

    return {
        row[0]: {
            "document_id": row[1],
            "content": row[2],
            "source_type": row[3],
            "source_id": row[4],
            "ticket_type": row[5],
            "severity": row[6],
            "component": row[7],
            "team": row[8],
            "service": row[9],
            "heading_context": row[10],
            "metadata": row[11],
            "title": row[12],
            "source_url": row[13],
        }
        for row in rows
    }


# ── Metadata filter SQL builder ───────────────────────────────────────────────

def _build_where_clause(
    f: Optional[MetadataFilter],
) -> Tuple[str, list]:
    """
    Build a SQL WHERE fragment and parameter list from a MetadataFilter.

    Returns:
        (sql_fragment, params)  — sql_fragment starts with "AND " if non-empty.
    """
    if f is None:
        return "", []

    clauses: List[str] = []
    params: List = []

    if f.source_type:
        clauses.append("c.source_type = %s")
        params.append(f.source_type)
    if f.ticket_type:
        clauses.append("c.ticket_type = %s")
        params.append(f.ticket_type.lower())
    if f.severity:
        clauses.append("c.severity = %s")
        params.append(f.severity.lower())
    if f.component:
        clauses.append("c.component ILIKE %s")
        params.append(f"%{f.component}%")
    if f.team:
        clauses.append("c.team ILIKE %s")
        params.append(f"%{f.team}%")
    if f.service:
        clauses.append("c.service ILIKE %s")
        params.append(f"%{f.service}%")
    if f.labels:
        # Any of the provided labels must appear in the chunk's labels array
        clauses.append("c.labels && %s::text[]")
        params.append(f.labels)

    if not clauses:
        return "", []

    return "AND " + " AND ".join(clauses), params
