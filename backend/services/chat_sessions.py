from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from uuid import uuid4

from config import MONGODB_URI
from database import get_database

_MAX_SESSIONS = 500
_MAX_MESSAGES_PER_SESSION = 200
_MAX_ATTACHMENTS_PER_SESSION = 20
_MAX_ATTACHMENT_CHARS = 100_000

CHAT_SESSIONS_COLLECTION = "chat_sessions"


@dataclass
class ChatSession:
    session_id: str
    project_key: str = ""
    messages: List[Dict[str, str]] = field(default_factory=list)
    attachments: List[Dict[str, str]] = field(default_factory=list)
    pending_tickets: Optional[Dict[str, Any]] = None
    awaiting_confirmation: bool = False
    last_created: Optional[Dict[str, Any]] = None


@runtime_checkable        # In future, we can use isinstance() and issubclass() checks on a Protocol
class ChatSessionStoreProtocol(Protocol):
    async def create_session(self, project_key: str = "") -> ChatSession: ...
    async def get_session(self, session_id: str) -> Optional[ChatSession]: ...
    async def append_message(self, session_id: str, role: str, content: str) -> ChatSession: ...
    async def add_attachment(self, session_id: str, name: str, content: str) -> ChatSession: ...
    async def update_project_key(self, session_id: str, project_key: str) -> ChatSession: ...
    async def set_pending_tickets(
        self, session_id: str, tickets: Optional[Dict[str, Any]], awaiting_confirmation: bool
    ) -> ChatSession: ...
    async def set_last_created(self, session_id: str, created: Optional[Dict[str, Any]]) -> ChatSession: ...


class InMemoryChatSessionStore(ChatSessionStoreProtocol):
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._sessions: Dict[str, ChatSession] = {}

    async def create_session(self, project_key: str = "") -> ChatSession:
        session = ChatSession(session_id=str(uuid4()), project_key=project_key.strip())
        async with self._lock:
            if len(self._sessions) >= _MAX_SESSIONS:
                oldest_id = next(iter(self._sessions))
                del self._sessions[oldest_id]
            self._sessions[session.session_id] = session
        return session

    async def get_session(self, session_id: str) -> Optional[ChatSession]:
        async with self._lock:
            session = self._sessions.get(session_id)
            return deepcopy(session) if session else None

    async def append_message(self, session_id: str, role: str, content: str) -> ChatSession:
        async with self._lock:
            session = self._sessions[session_id]
            session.messages.append({"role": role, "content": content})
            if len(session.messages) > _MAX_MESSAGES_PER_SESSION:
                session.messages = session.messages[-_MAX_MESSAGES_PER_SESSION:]
            return deepcopy(session)

    async def add_attachment(self, session_id: str, name: str, content: str) -> ChatSession:
        async with self._lock:
            session = self._sessions[session_id]
            if len(session.attachments) >= _MAX_ATTACHMENTS_PER_SESSION:
                session.attachments.pop(0)
            session.attachments.append({"name": name, "content": content[:_MAX_ATTACHMENT_CHARS]})
            return deepcopy(session)

    async def update_project_key(self, session_id: str, project_key: str) -> ChatSession:
        async with self._lock:
            session = self._sessions[session_id]
            session.project_key = project_key.strip()
            return deepcopy(session)

    async def set_pending_tickets(
        self, session_id: str, tickets: Optional[Dict[str, Any]], awaiting_confirmation: bool
    ) -> ChatSession:
        async with self._lock:
            session = self._sessions[session_id]
            session.pending_tickets = deepcopy(tickets)
            session.awaiting_confirmation = awaiting_confirmation
            return deepcopy(session)

    async def set_last_created(self, session_id: str, created: Optional[Dict[str, Any]]) -> ChatSession:
        async with self._lock:
            session = self._sessions[session_id]
            session.last_created = deepcopy(created)
            return deepcopy(session)


def _doc_to_chat_session(doc: Dict[str, Any]) -> ChatSession:
    return ChatSession(
        session_id=doc["session_id"],
        project_key=doc.get("project_key", ""),
        messages=deepcopy(doc.get("messages", [])),
        attachments=deepcopy(doc.get("attachments", [])),
        pending_tickets=deepcopy(doc["pending_tickets"]) if doc.get("pending_tickets") is not None else None,
        awaiting_confirmation=bool(doc.get("awaiting_confirmation", False)),
        last_created=deepcopy(doc["last_created"]) if doc.get("last_created") is not None else None,
    )


def _chat_session_to_doc(session: ChatSession) -> Dict[str, Any]:
    return {
        "_id": session.session_id,
        "session_id": session.session_id,
        "project_key": session.project_key,
        "messages": deepcopy(session.messages),
        "attachments": deepcopy(session.attachments),
        "pending_tickets": deepcopy(session.pending_tickets) if session.pending_tickets is not None else None,
        "awaiting_confirmation": session.awaiting_confirmation,
        "last_created": deepcopy(session.last_created) if session.last_created is not None else None,
    }


class MongoChatSessionStore(ChatSessionStoreProtocol):
    def _coll(self):
        return get_database()[CHAT_SESSIONS_COLLECTION]

    async def create_session(self, project_key: str = "") -> ChatSession:
        session = ChatSession(session_id=str(uuid4()), project_key=project_key.strip())
        await self._coll().insert_one(_chat_session_to_doc(session))
        return session

    async def get_session(self, session_id: str) -> Optional[ChatSession]:
        doc = await self._coll().find_one({"_id": session_id})
        return _doc_to_chat_session(doc) if doc else None

    async def append_message(self, session_id: str, role: str, content: str) -> ChatSession:
        msg = {"role": role, "content": content}
        result = await self._coll().update_one(
            {"_id": session_id},
            {"$push": {"messages": {"$each": [msg], "$slice": -_MAX_MESSAGES_PER_SESSION}}},
        )
        if result.matched_count == 0:
            raise KeyError(session_id)
        out = await self.get_session(session_id)
        assert out is not None
        return out

    async def add_attachment(self, session_id: str, name: str, content: str) -> ChatSession:
        doc = await self._coll().find_one({"_id": session_id})
        if doc is None:
            raise KeyError(session_id)
        attachments = deepcopy(doc.get("attachments", []))
        if len(attachments) >= _MAX_ATTACHMENTS_PER_SESSION:
            attachments.pop(0)
        attachments.append({"name": name, "content": content[:_MAX_ATTACHMENT_CHARS]})
        await self._coll().update_one({"_id": session_id}, {"$set": {"attachments": attachments}})
        out = await self.get_session(session_id)
        assert out is not None
        return out

    async def update_project_key(self, session_id: str, project_key: str) -> ChatSession:
        result = await self._coll().update_one(
            {"_id": session_id},
            {"$set": {"project_key": project_key.strip()}},
        )
        if result.matched_count == 0:
            raise KeyError(session_id)
        out = await self.get_session(session_id)
        assert out is not None
        return out

    async def set_pending_tickets(
        self, session_id: str, tickets: Optional[Dict[str, Any]], awaiting_confirmation: bool
    ) -> ChatSession:
        result = await self._coll().update_one(
            {"_id": session_id},
            {
                "$set": {
                    "pending_tickets": deepcopy(tickets) if tickets is not None else None,
                    "awaiting_confirmation": awaiting_confirmation,
                }
            },
        )
        if result.matched_count == 0:
            raise KeyError(session_id)
        out = await self.get_session(session_id)
        assert out is not None
        return out

    async def set_last_created(self, session_id: str, created: Optional[Dict[str, Any]]) -> ChatSession:
        result = await self._coll().update_one(
            {"_id": session_id},
            {"$set": {"last_created": deepcopy(created) if created is not None else None}},
        )
        if result.matched_count == 0:
            raise KeyError(session_id)
        out = await self.get_session(session_id)
        assert out is not None
        return out


def _make_chat_session_store() -> ChatSessionStoreProtocol:
    if MONGODB_URI.strip():
        return MongoChatSessionStore()
    return InMemoryChatSessionStore()


chat_sessions: ChatSessionStoreProtocol = _make_chat_session_store()
