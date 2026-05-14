"""
services/chat_sessions.py
─────────────────────────
Chat session storage with PostgreSQL persistence and in-memory fallback.

When DATABASE_URL is configured and the database is reachable, sessions
are stored in the `chat_sessions` table (persists across server restarts).
Otherwise the original in-memory dict is used transparently.
"""

import json
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

_MAX_SESSIONS = 500
_MAX_MESSAGES_PER_SESSION = 200
_MAX_ATTACHMENTS_PER_SESSION = 20
_MAX_ATTACHMENT_CHARS = 100_000


@dataclass
class ChatSession:
    session_id: str
    project_key: str = ""
    messages: List[Dict[str, str]] = field(default_factory=list)
    attachments: List[Dict[str, str]] = field(default_factory=list)
    pending_tickets: Optional[Dict[str, Any]] = None
    awaiting_confirmation: bool = False
    last_created: Optional[Dict[str, Any]] = None


# ── PostgreSQL backend ────────────────────────────────────────────────────────

def _db_available() -> bool:
    try:
        from database import is_db_available
        return is_db_available()
    except Exception:
        return False


def _as_json(value, default):
    if value is None:
        return default
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return json.loads(value)
        except Exception:
            return default
    return value


def _row_to_session(row) -> ChatSession:
    return ChatSession(
        session_id=str(row[0]),
        project_key=row[1] or "",
        messages=_as_json(row[2], []),
        attachments=_as_json(row[3], []),
        pending_tickets=_as_json(row[4], None),
        awaiting_confirmation=bool(row[5]),
        last_created=_as_json(row[6], None),
    )


class _PostgresChatStore:
    """PostgreSQL-backed chat session store."""

    def create_session(self, project_key: str = "") -> ChatSession:
        from database import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_sessions (project_key, messages, attachments)
                    VALUES (%s, '[]', '[]')
                    RETURNING session_id, project_key, messages, attachments,
                              pending_tickets, awaiting_confirmation, last_created
                    """,
                    (project_key.strip(),),
                )
                return _row_to_session(cur.fetchone())

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        from database import get_connection
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT session_id, project_key, messages, attachments,
                               pending_tickets, awaiting_confirmation, last_created
                        FROM chat_sessions WHERE session_id = %s
                        """,
                        (session_id,),
                    )
                    row = cur.fetchone()
            return _row_to_session(row) if row else None
        except Exception:
            return None

    def append_message(self, session_id: str, role: str, content: str) -> ChatSession:
        from database import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_sessions
                    SET messages = (
                        CASE
                          WHEN jsonb_array_length(messages) >= %s
                          THEN (messages - 0)
                          ELSE messages
                        END
                        || %s::jsonb
                    ),
                    updated_at = NOW()
                    WHERE session_id = %s
                    RETURNING session_id, project_key, messages, attachments,
                              pending_tickets, awaiting_confirmation, last_created
                    """,
                    (
                        _MAX_MESSAGES_PER_SESSION,
                        json.dumps([{"role": role, "content": content}]),
                        session_id,
                    ),
                )
                row = cur.fetchone()
        if row is None:
            raise KeyError(session_id)
        return _row_to_session(row)

    def add_attachment(self, session_id: str, name: str, content: str) -> ChatSession:
        from database import get_connection
        truncated = content[:_MAX_ATTACHMENT_CHARS]
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_sessions
                    SET attachments = (
                        CASE
                          WHEN jsonb_array_length(attachments) >= %s
                                                    THEN (attachments - 0)
                          ELSE attachments
                        END
                        || %s::jsonb
                    ),
                    updated_at = NOW()
                                        WHERE session_id = %s
                                        RETURNING session_id, project_key, messages, attachments,
                              pending_tickets, awaiting_confirmation, last_created
                    """,
                    (
                        _MAX_ATTACHMENTS_PER_SESSION,
                        json.dumps([{"name": name, "content": truncated}]),
                        session_id,
                    ),
                )
                row = cur.fetchone()
        if row is None:
            raise KeyError(session_id)
        return _row_to_session(row)

    def update_project_key(self, session_id: str, project_key: str) -> ChatSession:
        from database import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_sessions SET project_key = %s, updated_at = NOW()
                    WHERE session_id = %s
                    RETURNING session_id, project_key, messages, attachments,
                              pending_tickets, awaiting_confirmation, last_created
                    """,
                    (project_key.strip(), session_id),
                )
                row = cur.fetchone()
        if row is None:
            raise KeyError(session_id)
        return _row_to_session(row)

    def set_pending_tickets(
        self, session_id: str, tickets: Optional[Dict[str, Any]], awaiting_confirmation: bool
    ) -> ChatSession:
        from database import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_sessions
                    SET pending_tickets = %s, awaiting_confirmation = %s, updated_at = NOW()
                    WHERE session_id = %s
                    RETURNING session_id, project_key, messages, attachments,
                              pending_tickets, awaiting_confirmation, last_created
                    """,
                    (
                        json.dumps(tickets) if tickets is not None else None,
                        awaiting_confirmation,
                        session_id,
                    ),
                )
                row = cur.fetchone()
        if row is None:
            raise KeyError(session_id)
        return _row_to_session(row)

    def set_last_created(self, session_id: str, created: Optional[Dict[str, Any]]) -> ChatSession:
        from database import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_sessions SET last_created = %s, updated_at = NOW()
                    WHERE session_id = %s
                    RETURNING session_id, project_key, messages, attachments,
                              pending_tickets, awaiting_confirmation, last_created
                    """,
                    (json.dumps(created) if created is not None else None, session_id),
                )
                row = cur.fetchone()
        if row is None:
            raise KeyError(session_id)
        return _row_to_session(row)


# ── In-memory backend (original implementation) ───────────────────────────────

class _InMemoryChatStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: Dict[str, ChatSession] = {}

    def create_session(self, project_key: str = "") -> ChatSession:
        session = ChatSession(session_id=str(uuid4()), project_key=project_key.strip())
        with self._lock:
            if len(self._sessions) >= _MAX_SESSIONS:
                oldest_id = next(iter(self._sessions))
                del self._sessions[oldest_id]
            self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        with self._lock:
            session = self._sessions.get(session_id)
            return deepcopy(session) if session else None

    def append_message(self, session_id: str, role: str, content: str) -> ChatSession:
        with self._lock:
            session = self._sessions[session_id]
            session.messages.append({"role": role, "content": content})
            if len(session.messages) > _MAX_MESSAGES_PER_SESSION:
                session.messages = session.messages[-_MAX_MESSAGES_PER_SESSION:]
            return deepcopy(session)

    def add_attachment(self, session_id: str, name: str, content: str) -> ChatSession:
        with self._lock:
            session = self._sessions[session_id]
            if len(session.attachments) >= _MAX_ATTACHMENTS_PER_SESSION:
                session.attachments.pop(0)
            session.attachments.append({"name": name, "content": content[:_MAX_ATTACHMENT_CHARS]})
            return deepcopy(session)

    def update_project_key(self, session_id: str, project_key: str) -> ChatSession:
        with self._lock:
            session = self._sessions[session_id]
            session.project_key = project_key.strip()
            return deepcopy(session)

    def set_pending_tickets(
        self, session_id: str, tickets: Optional[Dict[str, Any]], awaiting_confirmation: bool
    ) -> ChatSession:
        with self._lock:
            session = self._sessions[session_id]
            session.pending_tickets = deepcopy(tickets)
            session.awaiting_confirmation = awaiting_confirmation
            return deepcopy(session)

    def set_last_created(self, session_id: str, created: Optional[Dict[str, Any]]) -> ChatSession:
        with self._lock:
            session = self._sessions[session_id]
            session.last_created = deepcopy(created)
            return deepcopy(session)


# ── Adaptive store: PostgreSQL when available, else in-memory ─────────────────

class ChatSessionStore:
    """
    Transparent wrapper that delegates to the PostgreSQL backend when the
    database is available, or falls back to the in-memory backend otherwise.
    """

    def __init__(self) -> None:
        self._memory = _InMemoryChatStore()
        self._pg = _PostgresChatStore()

    def _backend(self):
        return self._pg if _db_available() else self._memory

    def create_session(self, project_key: str = "") -> ChatSession:
        return self._backend().create_session(project_key)

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        return self._backend().get_session(session_id)

    def append_message(self, session_id: str, role: str, content: str) -> ChatSession:
        return self._backend().append_message(session_id, role, content)

    def add_attachment(self, session_id: str, name: str, content: str) -> ChatSession:
        return self._backend().add_attachment(session_id, name, content)

    def update_project_key(self, session_id: str, project_key: str) -> ChatSession:
        return self._backend().update_project_key(session_id, project_key)

    def set_pending_tickets(
        self,
        session_id: str,
        tickets: Optional[Dict[str, Any]],
        awaiting_confirmation: bool,
    ) -> ChatSession:
        return self._backend().set_pending_tickets(session_id, tickets, awaiting_confirmation)

    def set_last_created(self, session_id: str, created: Optional[Dict[str, Any]]) -> ChatSession:
        return self._backend().set_last_created(session_id, created)


chat_sessions = ChatSessionStore()
