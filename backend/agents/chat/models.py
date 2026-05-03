from typing import Any, Dict, List, Literal, Optional, TypedDict

from pydantic import BaseModel, Field


class IntentDecision(BaseModel):
    action: Literal["respond", "generate_tickets", "confirm_tickets", "ask_for_more_context"] = Field(
        description="Best next action for this user turn."
    )
    reason: str = Field(description="Short explanation for the selected action.")
    missing_information: List[str] = Field(default_factory=list)


class ChatState(TypedDict):
    session_id: str
    latest_user_message: str
    context_text: str
    project_key: str
    pending_tickets: Optional[Dict[str, Any]]
    awaiting_confirmation: bool
    conversation_history: List[Dict[str, str]]
    attachments: List[Dict[str, str]]
    forced_action: Optional[str]
    decision: Optional[Dict[str, Any]]
    reply: Optional[str]
    generated_tickets: Optional[Dict[str, Any]]
    created: Optional[Dict[str, Any]]
    error: Optional[str]