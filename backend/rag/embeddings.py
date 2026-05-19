"""
rag/embeddings.py
─────────────────
Embedding pipeline using provider-key based text embedding APIs.

Features:
  - Batched embedding generation (up to 2048 texts per API call)
  - Single-text convenience wrapper
  - Stores / updates embeddings in rag_chunks via the central DB connection
  - Graceful error handling: returns zero-vectors on failure rather than
    crashing the ingestion pipeline

Uses GROQ_API_KEY by default (OpenAI-compatible endpoint).
"""

import logging
from typing import List, Optional
from uuid import UUID

from config import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, GROQ_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY
from database import get_connection

logger = logging.getLogger(__name__)

# OpenAI allows up to 2048 inputs per embeddings request
_BATCH_SIZE = 512


# ── Lazy client ───────────────────────────────────────────────────────────────

_client = None


def _get_client():
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is not configured. "
                "Embeddings are configured to use Groq in this project. "
                "Set GROQ_API_KEY in your .env file."
            )
        from openai import OpenAI

        # Default provider: Groq (OpenAI-compatible API surface)
        _client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

        # Alternative provider: OpenAI (uncomment to use)
        # if not OPENAI_API_KEY:
        #     raise RuntimeError(
        #         "OPENAI_API_KEY is not configured. "
        #         "Set OPENAI_API_KEY in your .env file."
        #     )
        # _client = OpenAI(api_key=OPENAI_API_KEY)

        # Alternative provider: Gemini (uncomment to use)
        # NOTE: Gemini uses a different client and response shape than OpenAI-compatible APIs.
        # if not GOOGLE_API_KEY:
        #     raise RuntimeError(
        #         "GOOGLE_API_KEY is not configured. "
        #         "Set GOOGLE_API_KEY in your .env file."
        #     )
        # from google import genai
        # _client = genai.Client(api_key=GOOGLE_API_KEY)
    return _client


# ── Public API ────────────────────────────────────────────────────────────────

def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of texts.

    Args:
        texts: List of strings to embed.

    Returns:
        List of embedding vectors (same order as input).
        Returns zero-vectors for any failed batches.
    """
    if not texts:
        return []

    client = _get_client()
    all_embeddings: List[List[float]] = []

    for batch_start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[batch_start : batch_start + _BATCH_SIZE]
        try:
            # Default (Groq / OpenAI-compatible)
            response = client.embeddings.create(input=batch, model=EMBEDDING_MODEL)

            # Sort by index to preserve order for OpenAI-compatible providers (Groq/OpenAI)
            sorted_data = sorted(response.data, key=lambda d: d.index)
            all_embeddings.extend([item.embedding for item in sorted_data])

            # Alternative OpenAI usage (same shape as above)
            # response = client.embeddings.create(
            #     input=batch,
            #     model=EMBEDDING_MODEL,
            #     dimensions=EMBEDDING_DIMENSIONS if "text-embedding-3" in EMBEDDING_MODEL else None,
            # )
            # sorted_data = sorted(response.data, key=lambda d: d.index)
            # all_embeddings.extend([item.embedding for item in sorted_data])

            # Alternative Gemini usage (different API/response shape)
            # from google import genai
            # gemini_client = genai.Client(api_key=GOOGLE_API_KEY)
            # for text in batch:
            #     gemini_resp = gemini_client.models.embed_content(
            #         model=EMBEDDING_MODEL,
            #         contents=text,
            #     )
            #     all_embeddings.append(gemini_resp.embeddings[0].values)
        except Exception as exc:
            logger.error("Embedding batch %d failed: %s", batch_start // _BATCH_SIZE, exc)
            # Fill with zero-vectors so the rest of the pipeline continues
            all_embeddings.extend([[0.0] * EMBEDDING_DIMENSIONS] * len(batch))

    return all_embeddings


def embed_query(text: str) -> List[float]:
    """
    Generate a single embedding for a query string.

    Args:
        text: The query text.

    Returns:
        Embedding vector as a list of floats.
    """
    results = embed_texts([text])
    return results[0] if results else [0.0] * EMBEDDING_DIMENSIONS


def embed_and_store_chunks(chunk_ids: List[UUID], texts: List[str]) -> int:
    """
    Generate embeddings for the given texts and persist them to rag_chunks.

    Args:
        chunk_ids: List of chunk UUIDs (must match texts by position).
        texts: List of chunk text content.

    Returns:
        Number of chunks successfully updated.
    """
    if not chunk_ids or not texts:
        return 0

    embeddings = embed_texts(texts)
    updated = 0

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                for chunk_id, embedding in zip(chunk_ids, embeddings):
                    if all(v == 0.0 for v in embedding):
                        continue  # Skip zero-vectors (failed embedding)
                    cur.execute(
                        "UPDATE rag_chunks SET embedding = %s WHERE id = %s",
                        (embedding, chunk_id),
                    )
                    updated += 1
    except Exception as exc:
        logger.error("Failed to persist embeddings to DB: %s", exc)

    return updated
