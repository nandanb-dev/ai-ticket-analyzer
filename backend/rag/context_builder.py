"""
rag/context_builder.py
──────────────────────
Token-efficient context construction for LLM analysis prompts.

Given a list of RetrievalResult objects, this module:
  1. Deduplicates results by source_id (keeps highest-score chunk per source)
  2. Builds a compact, structured context string within a token budget
  3. Returns both the context string and a list of Citation objects for attribution

Token budget is configurable via CONTEXT_TOKEN_BUDGET (default: 3000 tokens).
Rough token estimate: len(text) / 4  (GPT tokeniser average).
"""

import logging
from typing import List, Tuple

from config import CONTEXT_TOKEN_BUDGET
from rag.models import Citation, RetrievalResult

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 4
_MAX_CHARS = CONTEXT_TOKEN_BUDGET * _CHARS_PER_TOKEN

# Max excerpt length for citations (characters)
_CITATION_EXCERPT_CHARS = 200

# Source-type display labels
_SOURCE_LABELS = {
    "jira": "Jira",
    "confluence": "Confluence",
    "pdf": "Document",
    "url": "Web",
}


def build_context(
    results: List[RetrievalResult],
    token_budget: int = CONTEXT_TOKEN_BUDGET,
) -> Tuple[str, List[Citation]]:
    """
    Build a context string and citation list from retrieval results.

    Args:
        results:      Reranked RetrievalResult list (best-first).
        token_budget: Approximate token budget for the context block.

    Returns:
        (context_text, citations)
          - context_text: Formatted string ready for injection into the LLM prompt.
          - citations:    List of Citation objects for source attribution.
    """
    if not results:
        return "", []

    max_chars = token_budget * _CHARS_PER_TOKEN
    deduplicated = _deduplicate(results)

    context_blocks: List[str] = []
    citations: List[Citation] = []
    chars_used = 0

    for i, result in enumerate(deduplicated, start=1):
        source_label = _SOURCE_LABELS.get(result.source_type, result.source_type.title())
        header = _format_header(i, source_label, result)
        body = result.content.strip()

        # Truncate body if it would exceed the remaining budget
        remaining = max_chars - chars_used - len(header) - 4  # 4 for newlines
        if remaining <= 0:
            break
        if len(body) > remaining:
            body = body[:remaining].rsplit(" ", 1)[0] + " …"

        block = f"{header}\n{body}"
        context_blocks.append(block)
        chars_used += len(block) + 2  # +2 for the blank line separator

        citations.append(
            Citation(
                source_type=result.source_type,
                source_id=result.source_id,
                title=result.title or result.source_id,
                source_url=result.source_url,
                excerpt=result.content[:_CITATION_EXCERPT_CHARS].strip() + (
                    " …" if len(result.content) > _CITATION_EXCERPT_CHARS else ""
                ),
                score=round(result.score, 4),
                doc_type=(result.metadata or {}).get("doc_type"),
                severity_level=(result.metadata or {}).get("severity_level"),
            )
        )

        if chars_used >= max_chars:
            break

    context_text = "\n\n".join(context_blocks)
    return context_text, citations


def _deduplicate(results: List[RetrievalResult]) -> List[RetrievalResult]:
    """
    Keep only the highest-scoring chunk per (source_type, source_id) pair.

    This prevents the context from being dominated by many chunks from a single
    document at the expense of breadth.
    """
    seen: dict = {}
    for result in results:
        key = (result.source_type, result.source_id)
        if key not in seen or result.score > seen[key].score:
            seen[key] = result
    # Re-sort by score after dedup
    return sorted(seen.values(), key=lambda r: r.score, reverse=True)


def _format_header(index: int, source_label: str, result: RetrievalResult) -> str:
    """Format the citation header line for a context block."""
    parts = [f"[{index}] {source_label}: {result.source_id}"]
    if result.title and result.title != result.source_id:
        parts.append(f"— {result.title}")
    extras = []
    if result.ticket_type:
        extras.append(result.ticket_type.title())
    if result.severity:
        extras.append(f"severity:{result.severity}")
    if result.component:
        extras.append(f"component:{result.component}")
    if result.heading_context:
        extras.append(f"§ {result.heading_context}")
    if extras:
        parts.append(f"({', '.join(extras)})")
    if result.source_url:
        parts.append(f"<{result.source_url}>")
    return " ".join(parts)


def format_citations_for_response(citations: List[Citation]) -> List[dict]:
    """Serialise Citation objects to plain dicts for API responses."""
    return [
        {
            "source_type": c.source_type,
            "source_id": c.source_id,
            "title": c.title,
            "source_url": c.source_url,
            "excerpt": c.excerpt,
            "relevance_score": c.score,
            "doc_type": getattr(c, "doc_type", None),
            "severity_level": getattr(c, "severity_level", None),
        }
        for c in citations
    ]
