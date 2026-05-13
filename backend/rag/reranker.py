"""
rag/reranker.py
───────────────
Cross-encoder reranking using flashrank (ONNX-based, no PyTorch required).

Pipeline:
  Retrieve top-50 candidates (dense + BM25 fused)
          ↓
  Cross-encoder reranker (ms-marco-MiniLM-L-12-v2)
          ↓
  Return best 5–10 chunks

flashrank: https://github.com/PrithivirajDamodaran/FlashRank
"""

import logging
from typing import List, Optional

from config import CROSS_ENCODER_MODEL, RERANK_TOP_N
from rag.models import RetrievalResult

logger = logging.getLogger(__name__)

_ranker = None


def _get_ranker():
    """Lazy-load the flashrank cross-encoder (downloads model on first use)."""
    global _ranker
    if _ranker is None:
        try:
            from flashrank import Ranker
            _ranker = Ranker(model_name=CROSS_ENCODER_MODEL, cache_dir="/tmp/flashrank_cache")
            logger.info("Cross-encoder reranker loaded: %s", CROSS_ENCODER_MODEL)
        except ImportError:
            logger.warning(
                "flashrank not installed. Reranking disabled. "
                "Install it with: pip install flashrank"
            )
            _ranker = False  # sentinel: tried but unavailable
        except Exception as exc:
            logger.warning("Failed to load cross-encoder reranker: %s. Skipping reranking.", exc)
            _ranker = False
    return _ranker if _ranker is not False else None


def rerank(
    query: str,
    candidates: List[RetrievalResult],
    top_n: int = RERANK_TOP_N,
) -> List[RetrievalResult]:
    """
    Rerank retrieval candidates using a cross-encoder model.

    Args:
        query:      The original query / ticket text used for retrieval.
        candidates: List of RetrievalResult objects (pre-fused by RRF).
        top_n:      Maximum number of results to return after reranking.

    Returns:
        Top-N RetrievalResult objects sorted by cross-encoder score (best first).
        Falls back to RRF-sorted order if the reranker is unavailable.
    """
    if not candidates:
        return []

    ranker = _get_ranker()
    if ranker is None:
        # Fallback: return top-N by RRF score
        return candidates[:top_n]

    try:
        from flashrank import RerankRequest

        passages = [
            {"id": i, "text": result.content}
            for i, result in enumerate(candidates)
        ]
        request = RerankRequest(query=query, passages=passages)
        reranked_passages = ranker.rerank(request)

        # Map reranked passages back to RetrievalResult objects
        index_to_result = {i: result for i, result in enumerate(candidates)}
        reranked_results: List[RetrievalResult] = []

        for passage in reranked_passages[:top_n]:
            idx = passage.get("id")
            score = passage.get("score", 0.0)
            if idx is not None and idx in index_to_result:
                result = index_to_result[idx]
                # Update score with cross-encoder score
                result.score = float(score)
                reranked_results.append(result)

        return reranked_results

    except Exception as exc:
        logger.warning("Reranking failed (%s), falling back to RRF order.", exc)
        return candidates[:top_n]
