from typing import Any, Dict, List, Literal, Optional, TypedDict

from pydantic import BaseModel, Field


# ── Clarification Models ─────────────────────────────────────────────────────


class ClarificationCategory(BaseModel):
    """Identifies what type of information is missing"""
    category: Literal[
        "requirements",
        "acceptance_criteria",
        "dependencies",
        "implementation_details",
        "security",
        "performance",
        "ux_flow"
    ] = Field(description="Category of missing information")
    severity: Literal["blocking", "important", "nice_to_have"] = Field(
        description="How critical this clarification is before proceeding"
    )
    description: str = Field(description="What specifically is unclear or missing")


class ClarificationQuestion(BaseModel):
    """A targeted question to ask the user"""
    question: str = Field(description="The clarifying question to ask")
    category: str = Field(description="Which category this addresses")
    suggestions: List[str] = Field(
        default_factory=list,
        description="2-4 intelligent suggestions/options the user can choose from"
    )
    follow_up_hint: str = Field(
        default="",
        description="What follow-up question might come next based on the answer"
    )


class ClarificationAnalysis(BaseModel):
    """Full analysis of what clarifications are needed"""
    needs_clarification: bool = Field(
        description="Whether clarification is required before proceeding"
    )
    readiness_score: int = Field(
        description="1-10 score of how ready this is for development (10=ready)"
    )
    summary: str = Field(description="Brief summary of the clarification needs")
    gaps: List[ClarificationCategory] = Field(default_factory=list)
    questions: List[ClarificationQuestion] = Field(default_factory=list)
    can_proceed_with_assumptions: bool = Field(
        default=False,
        description="Whether we can proceed by making reasonable assumptions"
    )
    assumptions_if_proceed: List[str] = Field(
        default_factory=list,
        description="Assumptions we would make if proceeding without full clarification"
    )


# ── Intent Decision Model ────────────────────────────────────────────────────


class IntentDecision(BaseModel):
    action: Literal[
        "respond",
        "generate_tickets",
        "confirm_tickets",
        "ask_for_more_context",
        "clarify_requirements",
        "edit_draft"
    ] = Field(description="Best next action for this user turn.")
    reason: str = Field(description="Short explanation for the selected action.")
    missing_information: List[str] = Field(default_factory=list)
    clarification_priority: Literal["blocking", "important", "optional"] = Field(
        default="optional",
        description="How urgent the clarification is"
    )


# ── Edit Draft Model ─────────────────────────────────────────────────────────


class EditDraftRequest(BaseModel):
    """Parsed user request to edit a draft ticket"""
    ticket_type: Literal["epic", "story", "task"] = Field(
        description="Type of ticket to edit"
    )
    ticket_index: int = Field(
        description="0-based index of the ticket within its type (0 = first, 1 = second, etc.)"
    )
    field: Literal["summary", "description", "priority", "story_points", "labels", "acceptance_criteria"] = Field(
        description="Which field to update"
    )
    action: Literal["set", "append", "remove"] = Field(
        default="set",
        description="What to do: set (replace), append (add to), or remove"
    )
    value: str = Field(
        description="The new value or content to apply"
    )
    explanation: str = Field(
        default="",
        description="Brief explanation of the change"
    )


# ── Chat State ───────────────────────────────────────────────────────────────


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
    clarification_analysis: Optional[Dict[str, Any]]
    clarification_round: int