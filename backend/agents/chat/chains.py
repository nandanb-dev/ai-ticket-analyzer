from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from config import (
    CHAT_MODEL,
    OPENAI_API_KEY,
    GOOGLE_API_KEY,
    GROQ_API_KEY,
    OPENAI_CHAT_MODEL,
    GOOGLE_CHAT_MODEL,
    GROQ_CHAT_MODEL,
)
from prompts.system import SYSTEM_PROMPT
from prompts.ticket_generation import TICKET_GENERATION_PROMPT
from prompts.clarification import CLARIFICATION_SYSTEM_PROMPT, DECISION_SYSTEM_PROMPT

from agents.chat.models import IntentDecision, ClarificationAnalysis, EditDraftRequest


_base_llm = None
_decision_chain = None
_response_chain = None
_ticket_chain = None
_clarification_chain = None
_edit_draft_chain = None


def get_llm():
    global _base_llm
    if _base_llm is not None:
        return _base_llm

    if OPENAI_API_KEY:
        model = CHAT_MODEL if CHAT_MODEL.startswith(("gpt", "o1", "o3", "o4")) else OPENAI_CHAT_MODEL
        _base_llm = ChatOpenAI(model=model, temperature=0.2, api_key=OPENAI_API_KEY)
        return _base_llm

    if GOOGLE_API_KEY:
        model = CHAT_MODEL if "gemini" in CHAT_MODEL.lower() else GOOGLE_CHAT_MODEL
        _base_llm = ChatGoogleGenerativeAI(model=model, temperature=0.2, api_key=GOOGLE_API_KEY)
        return _base_llm

    if GROQ_API_KEY:
        model = CHAT_MODEL if "llama" in CHAT_MODEL.lower() or "mixtral" in CHAT_MODEL.lower() else GROQ_CHAT_MODEL
        _base_llm = ChatGroq(model=model, temperature=0.2, api_key=GROQ_API_KEY)
        return _base_llm

    raise RuntimeError("No LLM API key configured. Set OPENAI_API_KEY (preferred) in backend/.env")

    return _base_llm


def get_decision_chain():
    global _decision_chain
    if _decision_chain is not None:
        return _decision_chain

    prompt = ChatPromptTemplate.from_messages([
        ("system", DECISION_SYSTEM_PROMPT),
        (
            "human",
            "Forced action: {forced_action}\n"
            "Awaiting confirmation: {awaiting_confirmation}\n"
            "Has pending tickets: {has_pending_tickets}\n"
            "Project key: {project_key}\n"
            "Conversation:\n{history_text}\n\n"
            "Known documents:\n{attachment_text}\n\n"
            "Additional context in this turn:\n{context_text}\n\n"
            "Latest user message:\n{latest_user_message}"
        ),
    ])
    _decision_chain = prompt | get_llm().with_structured_output(IntentDecision)
    return _decision_chain


def get_response_chain():
    global _response_chain
    if _response_chain is not None:
        return _response_chain

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            SYSTEM_PROMPT + "\n"
            "You are now in a live chat with a user. Be concise, grounded in the provided context, and helpful. "
            "If the user is discussing requirements, keep the answer context-aware and mention missing details only when truly needed. "
            "Do not invent facts not present in the conversation, uploaded material, or retrieved knowledge-base context. "
            "When retrieved context is relevant, use it to answer directly and accurately."
        ),
        (
            "human",
            "Conversation so far:\n{history_text}\n\n"
            "Known documents:\n{attachment_text}\n\n"
            "Knowledge Base Context (RAG):\n{rag_context}\n\n"
            "Additional context in this turn:\n{context_text}\n\n"
            "User message:\n{latest_user_message}"
        ),
    ])
    _response_chain = prompt | get_llm()
    return _response_chain


def get_ticket_chain():
    global _ticket_chain
    if _ticket_chain is not None:
        return _ticket_chain
    _ticket_chain = TICKET_GENERATION_PROMPT | get_llm() | JsonOutputParser()
    return _ticket_chain


def get_clarification_chain():
    """Chain for analyzing requirements and generating clarification questions"""
    global _clarification_chain
    if _clarification_chain is not None:
        return _clarification_chain

    prompt = ChatPromptTemplate.from_messages([
        ("system", CLARIFICATION_SYSTEM_PROMPT),
        (
            "human",
            "Analyze this for development readiness:\n\n"
            "## Conversation Context\n{history_text}\n\n"
            "## Uploaded Documents\n{attachment_text}\n\n"
            "## Knowledge Base Context (RAG)\n{rag_context}\n\n"
            "## Additional Context\n{context_text}\n\n"
            "## Latest Input\n{latest_user_message}\n\n"
            "Identify gaps and generate clarifying questions. "
            "Use the knowledge base context to inform your suggestions and identify patterns from similar past requirements. "
            "Focus on what's truly blocking development vs nice-to-have details."
        ),
    ])
    _clarification_chain = prompt | get_llm().with_structured_output(ClarificationAnalysis)
    return _clarification_chain


def get_edit_draft_chain():
    """Chain for parsing user's edit request for draft tickets"""
    global _edit_draft_chain
    if _edit_draft_chain is not None:
        return _edit_draft_chain

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You parse user requests to edit draft tickets.

The user has pending draft tickets and wants to modify one of them.
Extract the following from their request:
- ticket_type: "epic", "story", or "task"
- ticket_index: 0-based index (first=0, second=1, etc.)
- field: "summary", "description", "priority", "story_points", "labels", or "acceptance_criteria"
- action: "set" (replace value), "append" (add to existing), or "remove" (delete/clear)
- value: the new content to apply
- explanation: brief description of the change

Examples:
- "change priority of the first story to High" → story, 0, priority, set, "High"
- "add OAuth with Google to ticket 1's description" → story, 0, description, append, "OAuth with Google"
- "update acceptance criteria for story 2: user can login" → story, 1, acceptance_criteria, set, "user can login"
- "remove the second task" → task, 1, summary, remove, ""

If user says "ticket 1" or "first ticket", assume it's a story (most common).
If user says "the story" or "the task", use index 0 (first one)."""
        ),
        (
            "human",
            "Current pending tickets:\n{pending_tickets_summary}\n\n"
            "User request:\n{latest_user_message}\n\n"
            "Parse this edit request."
        ),
    ])
    _edit_draft_chain = prompt | get_llm().with_structured_output(EditDraftRequest)
    return _edit_draft_chain