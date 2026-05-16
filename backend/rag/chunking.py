"""
rag/chunking.py
───────────────
Recursive Semantic Chunking with overlap and metadata enrichment.

Strategy (in priority order):
  1. Split at Markdown / Confluence headings (## …)
  2. If a section is still too large, split at double-newline (paragraphs)
  3. If a paragraph is still too large, split at sentence boundaries (. ! ?)
  4. Final safety: hard-split at character limit

Overlap: the last CHUNK_OVERLAP_TOKENS tokens of each chunk are prepended
to the next chunk so context isn't lost across boundaries.

Each chunk is enriched with:
  - heading_context: the nearest heading(s) above it (breadcrumb)
  - chunk_index: position within the document
"""

import re
from typing import List, Optional, Tuple

from config import CHUNK_MAX_TOKENS, CHUNK_MIN_TOKENS, CHUNK_OVERLAP_TOKENS
from rag.models import ChunkRecord, DocumentRecord

# Approximate tokens from characters (GPT tokeniser average)
_CHARS_PER_TOKEN = 4

_MAX_CHARS = CHUNK_MAX_TOKENS * _CHARS_PER_TOKEN
_MIN_CHARS = CHUNK_MIN_TOKENS * _CHARS_PER_TOKEN
_OVERLAP_CHARS = CHUNK_OVERLAP_TOKENS * _CHARS_PER_TOKEN

# Heading pattern: markdown (#) or Confluence-style ===
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Sentence boundary (greedy split at . ! ? followed by space/newline)
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


# ── Public API ────────────────────────────────────────────────────────────────

def chunk_document(doc: DocumentRecord) -> List[ChunkRecord]:
    """
    Chunk a DocumentRecord into a list of ChunkRecords.

    Args:
        doc: The source document (must have raw_content populated).

    Returns:
        List of ChunkRecord objects ready for embedding and storage.
    """
    text = doc.raw_content or ""
    if not text.strip():
        return []

    raw_chunks = _recursive_split(text)

    chunks: List[ChunkRecord] = []
    prev_tail = ""

    for idx, (chunk_text, heading_ctx) in enumerate(raw_chunks):
        # Prepend overlap from previous chunk
        if prev_tail:
            chunk_text = prev_tail + "\n" + chunk_text

        chunk_text = chunk_text.strip()
        if len(chunk_text) < _MIN_CHARS // 2:
            # Too small even with overlap — merge into previous if possible
            if chunks:
                prev = chunks[-1]
                merged = prev.content + "\n" + chunk_text
                prev.content = merged.strip()
            continue

        # Capture tail for next chunk's overlap
        prev_tail = _tail_overlap(chunk_text)

        # Inherit metadata from the document
        chunk = ChunkRecord(
            document_id=doc.id,
            chunk_index=idx,
            content=chunk_text,
            source_type=doc.source_type,
            source_id=doc.source_id,
            heading_context=heading_ctx or None,
            # Structured metadata propagated from the document's metadata dict
            ticket_type=doc.metadata.get("ticket_type"),
            severity=doc.metadata.get("severity"),
            component=doc.metadata.get("component"),
            team=doc.metadata.get("team"),
            service=doc.metadata.get("service"),
            labels=doc.metadata.get("labels"),
            metadata=doc.metadata,
        )
        chunks.append(chunk)

    # Re-index after any merges
    for i, chunk in enumerate(chunks):
        chunk.chunk_index = i

    return chunks


# ── Splitting helpers ─────────────────────────────────────────────────────────

def _recursive_split(text: str) -> List[Tuple[str, str]]:
    """
    Split text recursively, returning (chunk_text, heading_breadcrumb) pairs.
    """
    results: List[Tuple[str, str]] = []
    _split_section(text, heading_ctx="", results=results)
    return results


def _split_section(
    text: str,
    heading_ctx: str,
    results: List[Tuple[str, str]],
) -> None:
    """Recursively split a section of text."""
    text = text.strip()
    if not text:
        return

    # If small enough, emit as-is
    if len(text) <= _MAX_CHARS:
        results.append((text, heading_ctx))
        return

    # Try splitting at headings first
    sections = _split_at_headings(text)
    if len(sections) > 1:
        for section_text, section_heading in sections:
            new_ctx = _combine_headings(heading_ctx, section_heading)
            _split_section(section_text, new_ctx, results)
        return

    # Try paragraph splits
    paragraphs = re.split(r"\n{2,}", text)
    if len(paragraphs) > 1:
        _emit_paragraph_groups(paragraphs, heading_ctx, results)
        return

    # Try sentence splits
    sentences = _SENTENCE_END_RE.split(text)
    if len(sentences) > 1:
        _emit_sentence_groups(sentences, heading_ctx, results)
        return

    # Hard split at character limit
    for i in range(0, len(text), _MAX_CHARS):
        chunk = text[i : i + _MAX_CHARS]
        results.append((chunk, heading_ctx))


def _split_at_headings(text: str) -> List[Tuple[str, str]]:
    """
    Split text at Markdown heading boundaries.

    Returns list of (section_text, heading_text) tuples.
    """
    parts = _HEADING_RE.split(text)
    # parts pattern: [pre_text, hashes, title, body, hashes, title, body, ...]
    sections: List[Tuple[str, str]] = []

    pre_text = parts[0].strip()
    if pre_text:
        sections.append((pre_text, ""))

    i = 1
    while i < len(parts) - 2:
        hashes = parts[i]
        title = parts[i + 1].strip()
        body = parts[i + 2].strip() if (i + 2) < len(parts) else ""
        heading_line = "#" * len(hashes) + " " + title
        section_body = heading_line + ("\n" + body if body else "")
        sections.append((section_body, title))
        i += 3

    return sections if len(sections) > 1 else []


def _emit_paragraph_groups(
    paragraphs: List[str],
    heading_ctx: str,
    results: List[Tuple[str, str]],
) -> None:
    """Greedily group paragraphs into chunks ≤ _MAX_CHARS."""
    current_parts: List[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current_len + para_len + 2 > _MAX_CHARS and current_parts:
            results.append(("\n\n".join(current_parts), heading_ctx))
            current_parts = []
            current_len = 0
        if para_len > _MAX_CHARS:
            # Paragraph itself is too large — recurse
            if current_parts:
                results.append(("\n\n".join(current_parts), heading_ctx))
                current_parts = []
                current_len = 0
            _split_section(para, heading_ctx, results)
        else:
            current_parts.append(para)
            current_len += para_len + 2

    if current_parts:
        results.append(("\n\n".join(current_parts), heading_ctx))


def _emit_sentence_groups(
    sentences: List[str],
    heading_ctx: str,
    results: List[Tuple[str, str]],
) -> None:
    """Greedily group sentences into chunks ≤ _MAX_CHARS."""
    current_parts: List[str] = []
    current_len = 0

    for sent in sentences:
        sent_len = len(sent)
        if current_len + sent_len + 1 > _MAX_CHARS and current_parts:
            results.append((" ".join(current_parts), heading_ctx))
            current_parts = []
            current_len = 0
        current_parts.append(sent)
        current_len += sent_len + 1

    if current_parts:
        results.append((" ".join(current_parts), heading_ctx))


def _tail_overlap(text: str) -> str:
    """Return the last _OVERLAP_CHARS characters of text for overlap prepending."""
    if len(text) <= _OVERLAP_CHARS:
        return text
    # Try to break at a sentence boundary
    tail = text[-_OVERLAP_CHARS:]
    # Find first sentence start within the tail
    match = _SENTENCE_END_RE.search(tail)
    if match:
        return tail[match.end():]
    return tail


def _combine_headings(parent: str, child: str) -> str:
    if parent and child:
        return f"{parent} > {child}"
    return child or parent
