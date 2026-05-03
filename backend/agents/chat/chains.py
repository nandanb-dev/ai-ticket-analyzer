from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from config import CHAT_MODEL, GOOGLE_API_KEY
from prompts.system import SYSTEM_PROMPT
from prompts.ticket_generation import TICKET_GENERATION_PROMPT

from agents.chat.models import IntentDecision


_base_llm = None
_decision_chain = None
_response_chain = None
_ticket_chain = None


def get_llm() -> ChatGoogleGenerativeAI:
    global _base_llm
    if _base_llm is not None:
        return _base_llm
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not configured in .env")
    _base_llm = ChatGoogleGenerativeAI(model=CHAT_MODEL, temperature=0.2, api_key=GOOGLE_API_KEY)
    return _base_llm


def get_decision_chain():
    global _decision_chain
    if _decision_chain is not None:
        return _decision_chain

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are routing a product-ops chat assistant. "
            "Pick exactly one action: respond, generate_tickets, confirm_tickets, ask_for_more_context. "
            "Choose confirm_tickets only when the user is explicitly approving ticket creation or forced_action says so. "
            "Choose generate_tickets only when the user wants ticket decomposition or Jira-ready tickets. "
            "Choose ask_for_more_context when ticket generation is requested but the available information is too thin. "
            "Otherwise choose respond."
        ),
        (
            "human",
            "Forced action: {forced_action}\n"
            "Awaiting confirmation: {awaiting_confirmation}\n"
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
            "Do not invent facts not present in the conversation or uploaded material."
        ),
        (
            "human",
            "Conversation so far:\n{history_text}\n\n"
            "Known documents:\n{attachment_text}\n\n"
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