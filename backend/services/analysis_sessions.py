"""
services/analysis_sessions.py
──────────────────────────────
Analysis session storage with PostgreSQL persistence and in-memory fallback.

When DATABASE_URL is configured and the database is reachable, sessions are
stored in the `analysis_sessions` table.  Otherwise the in-memory dict is
used transparently.
"""

import json
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

_MAX_SESSIONS = 200


@dataclass
class AnalysisSession:
    session_id: str
    project_key: str = ""
    epic_key: str = ""
    ticket_key: str = ""
    user_context: str = ""
    analysis: Dict[str, Any] = field(default_factory=dict)
    revision_history: List[Dict[str, Any]] = field(default_factory=list)


# ── PostgreSQL backend ────────────────────────────────────────────────────────

def _db_available() -> bool:
    try:
        from database import is_db_available
        return is_db_available()
    except Exception:
        return False


def _row_to_session(row) -> AnalysisSession:
    return AnalysisSession(
        session_id=str(row[0]),
        project_key=row[1] or "",
        epic_key=row[2] or "",
        ticket_key=row[3] or "",
        user_context=row[4] or "",
        analysis=row[5] or {},
        revision_history=row[6] or [],
    )


class _PostgresAnalysisStore:
    def create_session(
        self,
        project_key: str = "",
        epic_key: str = "",
        ticket_key: str = "",
        user_context: str = "",
    ) -> AnalysisSession:
        from database import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO analysis_sessions
                        (project_key, epic_key, ticket_key, user_context, analysis, revision_history)
                    VALUES (%s, %s, %s, %s, '{}', '[]')
                    RETURNING id, project_key, epic_key, ticket_key, user_context,
                              analysis, revision_history
                    """,
                    (project_key.strip(), epic_key.strip(), ticket_key.strip(), user_context),
                )
                return _row_to_session(cur.fetchone())

    def get_session(self, session_id: str) -> Optional[AnalysisSession]:
        from database import get_connection
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, project_key, epic_key, ticket_key, user_context,
                               analysis, revision_history
                        FROM analysis_sessions WHERE id = %s
                        """,
                        (session_id,),
                    )
                    row = cur.fetchone()
            return _row_to_session(row) if row else None
        except Exception:
            return None

    def set_analysis(self, session_id: str, analysis: Dict[str, Any]) -> AnalysisSession:
        from database import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Push current analysis into revision_history first
                cur.execute(
                    """
                    UPDATE analysis_sessions
                    SET
                        revision_history = CASE
                            WHEN analysis <> '{}'::jsonb
                            THEN revision_history || jsonb_build_array(analysis)
                            ELSE revision_history
                        END,
                        analysis = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, project_key, epic_key, ticket_key, user_context,
                              analysis, revision_history
                    """,
                    (json.dumps(analysis), session_id),
                )
                row = cur.fetchone()
        if row is None:
            raise KeyError(session_id)
        return _row_to_session(row)

    def delete_session(self, session_id: str) -> None:
        from database import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM analysis_sessions WHERE id = %s", (session_id,))


# ── In-memory backend (original implementation) ───────────────────────────────

class _InMemoryAnalysisStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: Dict[str, AnalysisSession] = {}

    def create_session(
        self,
        project_key: str = "",
        epic_key: str = "",
        ticket_key: str = "",
        user_context: str = "",
    ) -> AnalysisSession:
        session = AnalysisSession(
            session_id=str(uuid4()),
            project_key=project_key.strip(),
            epic_key=epic_key.strip(),
            ticket_key=ticket_key.strip(),
            user_context=user_context,
        )
        with self._lock:
            if len(self._sessions) >= _MAX_SESSIONS:
                oldest_id = next(iter(self._sessions))
                del self._sessions[oldest_id]
            self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[AnalysisSession]:
        with self._lock:
            session = self._sessions.get(session_id)
            return deepcopy(session) if session else None

    def set_analysis(self, session_id: str, analysis: Dict[str, Any]) -> AnalysisSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            if session.analysis:
                session.revision_history.append(deepcopy(session.analysis))
            session.analysis = deepcopy(analysis)
            return deepcopy(session)

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


# ── Adaptive store ────────────────────────────────────────────────────────────

class AnalysisSessionStore:
    """
    Transparent wrapper that uses PostgreSQL when available, in-memory otherwise.
    """

    def __init__(self) -> None:
        self._memory = _InMemoryAnalysisStore()
        self._pg = _PostgresAnalysisStore()

    def _backend(self):
        return self._pg if _db_available() else self._memory

    def create_session(
        self,
        project_key: str = "",
        epic_key: str = "",
        ticket_key: str = "",
        user_context: str = "",
    ) -> AnalysisSession:
        return self._backend().create_session(project_key, epic_key, ticket_key, user_context)

    def get_session(self, session_id: str) -> Optional[AnalysisSession]:
        return self._backend().get_session(session_id)

    def set_analysis(self, session_id: str, analysis: Dict[str, Any]) -> AnalysisSession:
        return self._backend().set_analysis(session_id, analysis)

    def delete_session(self, session_id: str) -> None:
        return self._backend().delete_session(session_id)


analysis_sessions = AnalysisSessionStore()

