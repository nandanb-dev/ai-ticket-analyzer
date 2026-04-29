from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


class IntentDecision(BaseModel):
    action: Literal["respond", "generate_tickets", "confirm_tickets", "ask_for_more_context"] = Field(
        description="Best next action for this user turn."
    )
    reason: str = Field(description="Short explanation for the selected action.")
    missing_information: list[str] = Field(default_factory=list)


class ChatState(TypedDict):
    session_id: str
    latest_user_message: str
    context_text: str
    project_key: str
    pending_tickets: dict[str, Any] | None
    awaiting_confirmation: bool
    conversation_history: list[dict[str, str]]
    attachments: list[dict[str, str]]
    forced_action: str | None
    decision: dict[str, Any] | None
    reply: str | None
    generated_tickets: dict[str, Any] | None
    created: dict[str, Any] | None
    error: str | None