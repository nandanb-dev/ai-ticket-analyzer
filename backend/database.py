"""
database.py
───────────
Central PostgreSQL connection pool and schema management.

Covers:
  - RAG documents / chunks (pgvector)
  - Chat sessions
  - Analysis sessions

The module degrades gracefully when DATABASE_URL is not configured:
  * get_pool() returns None
  * is_db_available() returns False
  * get_connection() raises RuntimeError (callers must handle this)
"""

import logging
from contextlib import contextmanager
from typing import Generator, Optional

import psycopg2
import psycopg2.pool
from psycopg2.extras import register_default_json, register_default_jsonb, register_uuid

from config import DATABASE_URL, EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)

_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


# ── Connection pool ───────────────────────────────────────────────────────────

def get_pool() -> Optional[psycopg2.pool.ThreadedConnectionPool]:
    """Return the shared connection pool, creating it on first call."""
    global _pool
    if _pool is not None:
        return _pool
    if not DATABASE_URL:
        return None
    try:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            dsn=DATABASE_URL,
        )
        register_uuid()
        register_default_json(globally=True)
        register_default_jsonb(globally=True)
        logger.info("PostgreSQL connection pool created.")
    except Exception as exc:
        logger.warning("PostgreSQL unavailable – in-memory fallback active. (%s)", exc)
        _pool = None
    return _pool


def is_db_available() -> bool:
    """Return True if a live PostgreSQL connection can be obtained."""
    pool = get_pool()
    if pool is None:
        return False
    conn = None
    try:
        conn = pool.getconn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        if conn is not None:
            pool.putconn(conn)


@contextmanager
def get_connection() -> Generator:
    """Yield a psycopg2 connection from the pool with pgvector registered.

    Commits on clean exit, rolls back on exception, and always returns
    the connection to the pool.

    Raises:
        RuntimeError: if DATABASE_URL is not set or PostgreSQL is unreachable.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError(
            "DATABASE_URL is not configured or PostgreSQL is unavailable. "
            "Set DATABASE_URL in your .env file."
        )
    conn = pool.getconn()
    try:
        try:
            from pgvector.psycopg2 import register_vector
            register_vector(conn)
        except Exception:
            pass  # pgvector extension may not be installed yet
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
-- pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── RAG: document store ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rag_documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type VARCHAR(50)  NOT NULL,          -- 'jira' | 'confluence' | 'pdf' | 'url'
    source_id   VARCHAR(255) NOT NULL,          -- Jira key / Confluence page ID / filename / URL hash
    source_url  TEXT,
    title       TEXT,
    raw_content TEXT,
    metadata    JSONB        NOT NULL DEFAULT '{{}}',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (source_type, source_id)
);

-- ── RAG: chunk store ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rag_chunks (
    id              UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID    NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    content         TEXT    NOT NULL,
    content_tsv     TSVECTOR,                   -- populated by trigger below
    embedding       VECTOR({dims}),
    -- Filterable metadata
    source_type     VARCHAR(50),
    source_id       VARCHAR(255),
    ticket_type     VARCHAR(50),                -- bug | story | task | epic
    severity        VARCHAR(50),                -- critical | high | medium | low
    component       TEXT,
    team            TEXT,
    service         TEXT,
    labels          TEXT[],
    heading_context TEXT,                       -- nearest heading(s) above this chunk
    metadata        JSONB   NOT NULL DEFAULT '{{}}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- HNSW index for fast approximate nearest-neighbour search
CREATE INDEX IF NOT EXISTS rag_chunks_embedding_hnsw_idx
    ON rag_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Full-text search index for BM25-style keyword retrieval
CREATE INDEX IF NOT EXISTS rag_chunks_fts_idx
    ON rag_chunks USING gin(content_tsv);

-- Metadata indexes for fast filtering
CREATE INDEX IF NOT EXISTS rag_chunks_source_type_idx ON rag_chunks (source_type);
CREATE INDEX IF NOT EXISTS rag_chunks_ticket_type_idx ON rag_chunks (ticket_type);
CREATE INDEX IF NOT EXISTS rag_chunks_severity_idx    ON rag_chunks (severity);
CREATE INDEX IF NOT EXISTS rag_chunks_component_idx   ON rag_chunks (component);
CREATE INDEX IF NOT EXISTS rag_chunks_team_idx        ON rag_chunks (team);
CREATE INDEX IF NOT EXISTS rag_chunks_service_idx     ON rag_chunks (service);
CREATE INDEX IF NOT EXISTS rag_chunks_source_id_idx   ON rag_chunks (source_id);

-- Trigger: keep content_tsv in sync
CREATE OR REPLACE FUNCTION rag_chunks_tsv_update()
RETURNS TRIGGER AS $$
BEGIN
    NEW.content_tsv := to_tsvector('english', COALESCE(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS rag_chunks_tsv_trigger ON rag_chunks;
CREATE TRIGGER rag_chunks_tsv_trigger
    BEFORE INSERT OR UPDATE OF content ON rag_chunks
    FOR EACH ROW EXECUTE FUNCTION rag_chunks_tsv_update();

-- ── Chat sessions ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_key           TEXT        NOT NULL DEFAULT '',
    messages              JSONB       NOT NULL DEFAULT '[]',
    attachments           JSONB       NOT NULL DEFAULT '[]',
    pending_tickets       JSONB,
    awaiting_confirmation BOOLEAN     NOT NULL DEFAULT FALSE,
    last_created          JSONB,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS chat_sessions_updated_idx ON chat_sessions (updated_at DESC);

-- ── Analysis sessions ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analysis_sessions (
    session_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_key      TEXT        NOT NULL DEFAULT '',
    epic_key         TEXT        NOT NULL DEFAULT '',
    ticket_key       TEXT        NOT NULL DEFAULT '',
    user_context     TEXT        NOT NULL DEFAULT '',
    analysis         JSONB       NOT NULL DEFAULT '{{}}',
    revision_history JSONB       NOT NULL DEFAULT '[]',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS analysis_sessions_updated_idx ON analysis_sessions (updated_at DESC);
""".format(dims=EMBEDDING_DIMENSIONS)


def initialize_schema() -> None:
    """Create all tables, indexes, and triggers if they do not already exist."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(_SCHEMA_SQL)
        logger.info("Database schema initialized successfully.")
    except RuntimeError as exc:
        logger.warning("Schema init skipped – %s", exc)
    except Exception as exc:
        logger.error("Schema initialization failed: %s", exc)
