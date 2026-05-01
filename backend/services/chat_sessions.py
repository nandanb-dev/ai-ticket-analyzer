from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4

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


class ChatSessionStore:
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

    def set_pending_tickets(self, session_id: str, tickets: Optional[Dict[str, Any]], awaiting_confirmation: bool) -> ChatSession:
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


chat_sessions = ChatSessionStore()