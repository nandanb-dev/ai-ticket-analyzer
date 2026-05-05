from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from uuid import uuid4

from config import MONGODB_URI
from database import get_database

_MAX_SESSIONS = 200

ANALYSIS_SESSIONS_COLLECTION = "analysis_sessions"


@dataclass
class AnalysisSession:
    session_id: str
    project_key: str = ""
    epic_key: str = ""
    ticket_key: str = ""
    user_context: str = ""
    analysis: Dict[str, Any] = field(default_factory=dict)
    revision_history: List[Dict[str, Any]] = field(default_factory=list)


@runtime_checkable        # In future, we can use isinstance() and issubclass() checks on a Protocol
class AnalysisSessionStoreProtocol(Protocol):
    async def create_session(
        self,
        project_key: str = "",
        epic_key: str = "",
        ticket_key: str = "",
        user_context: str = "",
    ) -> AnalysisSession: ...
    async def get_session(self, session_id: str) -> Optional[AnalysisSession]: ...
    async def set_analysis(self, session_id: str, analysis: Dict[str, Any]) -> AnalysisSession: ...
    async def delete_session(self, session_id: str) -> None: ...


class InMemoryAnalysisSessionStore(AnalysisSessionStoreProtocol):
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._sessions: Dict[str, AnalysisSession] = {}

    async def create_session(
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
        async with self._lock:
            if len(self._sessions) >= _MAX_SESSIONS:
                oldest_id = next(iter(self._sessions))
                del self._sessions[oldest_id]
            self._sessions[session.session_id] = session
        return session

    async def get_session(self, session_id: str) -> Optional[AnalysisSession]:
        async with self._lock:
            session = self._sessions.get(session_id)
            return deepcopy(session) if session else None

    async def set_analysis(self, session_id: str, analysis: Dict[str, Any]) -> AnalysisSession:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            if session.analysis:
                session.revision_history.append(deepcopy(session.analysis))
            session.analysis = deepcopy(analysis)
            return deepcopy(session)

    async def delete_session(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)


def _doc_to_analysis_session(doc: Dict[str, Any]) -> AnalysisSession:
    return AnalysisSession(
        session_id=doc["session_id"],
        project_key=doc.get("project_key", ""),
        epic_key=doc.get("epic_key", ""),
        ticket_key=doc.get("ticket_key", ""),
        user_context=doc.get("user_context", ""),
        analysis=deepcopy(doc.get("analysis", {})),
        revision_history=deepcopy(doc.get("revision_history", [])),
    )


def _analysis_session_to_doc(session: AnalysisSession) -> Dict[str, Any]:
    return {
        "_id": session.session_id,
        "session_id": session.session_id,
        "project_key": session.project_key,
        "epic_key": session.epic_key,
        "ticket_key": session.ticket_key,
        "user_context": session.user_context,
        "analysis": deepcopy(session.analysis),
        "revision_history": deepcopy(session.revision_history),
    }


class MongoAnalysisSessionStore(AnalysisSessionStoreProtocol):
    def _coll(self):
        return get_database()[ANALYSIS_SESSIONS_COLLECTION]

    async def create_session(
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
        await self._coll().insert_one(_analysis_session_to_doc(session))
        return session

    async def get_session(self, session_id: str) -> Optional[AnalysisSession]:
        doc = await self._coll().find_one({"_id": session_id})
        return _doc_to_analysis_session(doc) if doc else None

    async def set_analysis(self, session_id: str, analysis: Dict[str, Any]) -> AnalysisSession:
        doc = await self._coll().find_one({"_id": session_id})
        if doc is None:
            raise KeyError(session_id)
        prev = doc.get("analysis") or {}
        new_analysis = deepcopy(analysis)
        if prev:
            await self._coll().update_one(
                {"_id": session_id},
                {
                    "$push": {"revision_history": deepcopy(prev)},
                    "$set": {"analysis": new_analysis},
                },
            )
        else:
            await self._coll().update_one({"_id": session_id}, {"$set": {"analysis": new_analysis}})
        out = await self.get_session(session_id)
        assert out is not None
        return out

    async def delete_session(self, session_id: str) -> None:
        await self._coll().delete_one({"_id": session_id})


def _make_analysis_session_store() -> AnalysisSessionStoreProtocol:
    if MONGODB_URI.strip():
        return MongoAnalysisSessionStore()
    return InMemoryAnalysisSessionStore()


analysis_sessions: AnalysisSessionStoreProtocol = _make_analysis_session_store()
