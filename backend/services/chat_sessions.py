from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock
from typing import Any
from uuid import uuid4


@dataclass
class ChatSession:
    session_id: str
    project_key: str = ""
    messages: list[dict[str, str]] = field(default_factory=list)
    attachments: list[dict[str, str]] = field(default_factory=list)
    pending_tickets: dict[str, Any] | None = None
    awaiting_confirmation: bool = False
    last_created: dict[str, Any] | None = None


class ChatSessionStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: dict[str, ChatSession] = {}

    def create_session(self, project_key: str = "") -> ChatSession:
        session = ChatSession(session_id=str(uuid4()), project_key=project_key.strip())
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> ChatSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
            return deepcopy(session) if session else None

    def append_message(self, session_id: str, role: str, content: str) -> ChatSession:
        with self._lock:
            session = self._sessions[session_id]
            session.messages.append({"role": role, "content": content})
            return deepcopy(session)

    def add_attachment(self, session_id: str, name: str, content: str) -> ChatSession:
        with self._lock:
            session = self._sessions[session_id]
            session.attachments.append({"name": name, "content": content})
            return deepcopy(session)

    def update_project_key(self, session_id: str, project_key: str) -> ChatSession:
        with self._lock:
            session = self._sessions[session_id]
            session.project_key = project_key.strip()
            return deepcopy(session)

    def set_pending_tickets(self, session_id: str, tickets: dict[str, Any] | None, awaiting_confirmation: bool) -> ChatSession:
        with self._lock:
            session = self._sessions[session_id]
            session.pending_tickets = deepcopy(tickets)
            session.awaiting_confirmation = awaiting_confirmation
            return deepcopy(session)

    def set_last_created(self, session_id: str, created: dict[str, Any] | None) -> ChatSession:
        with self._lock:
            session = self._sessions[session_id]
            session.last_created = deepcopy(created)
            return deepcopy(session)


chat_sessions = ChatSessionStore()