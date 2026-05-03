from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4

_MAX_SESSIONS = 200


@dataclass
class AnalysisSession:
    session_id: str
    project_key: str = ""
    epic_key: str = ""
    ticket_key: str = ""
    user_context: str = ""
    analysis: Dict[str, Any] = field(default_factory=dict)
    # Tracks all revisions so the user can always reference the latest
    revision_history: List[Dict[str, Any]] = field(default_factory=list)


class AnalysisSessionStore:
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
            # Push previous analysis into history before overwriting
            if session.analysis:
                session.revision_history.append(deepcopy(session.analysis))
            session.analysis = deepcopy(analysis)
            return deepcopy(session)

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


analysis_sessions = AnalysisSessionStore()
