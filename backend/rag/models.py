"""
rag/models.py
─────────────
Shared data-transfer objects for the RAG pipeline.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID


@dataclass
class DocumentRecord:
    """A source document to be ingested into the knowledge base."""
    source_type: str           # 'jira' | 'confluence' | 'pdf' | 'url'
    source_id: str             # Jira key, Confluence page ID, filename, URL hash
    title: str
    raw_content: str
    source_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: Optional[UUID] = None


@dataclass
class ChunkRecord:
    """A single chunk derived from a DocumentRecord."""
    document_id: UUID
    chunk_index: int
    content: str
    embedding: Optional[List[float]] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    ticket_type: Optional[str] = None   # bug | story | task | epic
    severity: Optional[str] = None      # critical | high | medium | low
    component: Optional[str] = None
    team: Optional[str] = None
    service: Optional[str] = None
    labels: Optional[List[str]] = None
    heading_context: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: Optional[UUID] = None


@dataclass
class MetadataFilter:
    """Filters applied during semantic retrieval."""
    ticket_type: Optional[str] = None
    severity: Optional[str] = None
    component: Optional[str] = None
    team: Optional[str] = None
    service: Optional[str] = None
    source_type: Optional[str] = None
    labels: Optional[List[str]] = None


@dataclass
class RetrievalResult:
    """A single ranked retrieval hit."""
    chunk_id: UUID
    document_id: UUID
    content: str
    score: float                        # fused RRF score (higher = more relevant)
    source_type: str
    source_id: str
    title: str
    source_url: Optional[str]
    ticket_type: Optional[str]
    severity: Optional[str]
    component: Optional[str]
    team: Optional[str]
    service: Optional[str]
    heading_context: Optional[str]
    metadata: Dict[str, Any]


@dataclass
class Citation:
    """Source attribution returned alongside analysis results."""
    source_type: str
    source_id: str
    title: str
    source_url: Optional[str]
    excerpt: str                        # first ~200 chars of the chunk
    score: float
