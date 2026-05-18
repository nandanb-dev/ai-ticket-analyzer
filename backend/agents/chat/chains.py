from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from config import CHAT_MODEL, OPENAI_API_KEY, GOOGLE_API_KEY, GROQ_API_KEY
from prompts.system import SYSTEM_PROMPT
from prompts.ticket_generation import TICKET_GENERATION_PROMPT

from agents.chat.models import IntentDecision, ClarificationAnalysis


_base_llm = None
_decision_chain = None
_response_chain = None
_ticket_chain = None
_clarification_chain = None


# ── Clarification Analysis Prompt ────────────────────────────────────────────

CLARIFICATION_SYSTEM_PROMPT = """You are a senior technical product analyst who identifies gaps in requirements BEFORE development starts.

Analyze the provided requirements/context and identify what's missing or ambiguous in these areas:

1. **REQUIREMENTS** - Are the functional requirements clear and complete?
   - User stories properly defined (As a... I want... So that...)?
   - Business goals and success metrics specified?
   - Scope boundaries clear (what's in/out)?

2. **ACCEPTANCE CRITERIA** - Can QA write tests from this?
   - Given/When/Then format used?
   - Happy path, error cases, and edge cases covered?
   - Measurable and specific (not vague)?

3. **DEPENDENCIES** - Are blockers and integrations identified?
   - External APIs or services needed?
   - Database changes or migrations?
   - Other teams or tickets this depends on?
   - Feature flags or rollout strategy?

4. **IMPLEMENTATION DETAILS** - Can a developer start coding?
   - Technical approach outlined?
   - UI/UX mockups or flow descriptions?
   - Data models and API contracts?
   - Error handling strategy?

5. **SECURITY** - Are security requirements addressed?
   - Authentication/authorization needs?
   - Data validation and sanitization?
   - Sensitive data handling?

6. **PERFORMANCE** - Are performance expectations clear?
   - Response time requirements?
   - Load/scale expectations?
   - Caching strategy?

For each gap found:
- Classify its severity (blocking/important/nice_to_have)
- Generate a targeted clarifying question
- Provide 2-4 intelligent suggestions the user can choose from
- Hint at logical follow-up questions

Be conversational but efficient. Prioritize blocking issues first."""


def get_llm() -> ChatGroq: #ChatGoogleGenerativeAI, ChatOpenAI, ChatGroq
    global _base_llm
    if _base_llm is not None:
        return _base_llm
    # if not OPENAI_API_KEY:
    #     raise RuntimeError("OPENAI_API_KEY is not configured in .env")
    # _base_llm = ChatOpenAI(model=CHAT_MODEL, temperature=0.2, api_key=OPENAI_API_KEY)
    # if not GOOGLE_API_KEY:
    #     raise RuntimeError("GOOGLE_API_KEY is not configured in .env")
    # _base_llm = ChatGoogleGenerativeAI(model=CHAT_MODEL, temperature=0.2, api_key=GOOGLE_API_KEY)
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured in .env")
    _base_llm = ChatGroq(model=CHAT_MODEL, temperature=0.2, api_key=GROQ_API_KEY)
    return _base_llm


def get_decision_chain():
    global _decision_chain
    if _decision_chain is not None:
        return _decision_chain

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are routing a product-ops chat assistant.
Pick exactly one action: respond, generate_tickets, confirm_tickets, ask_for_more_context, clarify_requirements.

DECISION RULES:
- **clarify_requirements**: When user wants to create tickets but:
  • Requirements are ambiguous or incomplete
  • Acceptance criteria are missing or vague
  • Dependencies are not identified
  • Implementation details are insufficient for a developer to start
  • This is the FIRST time user is asking for tickets from new requirements

- **generate_tickets**: When requirements are clear AND complete enough to create actionable tickets,
  OR when user explicitly says to proceed despite incomplete info

- **confirm_tickets**: Only when user explicitly approves ticket creation or forced_action says so

- **ask_for_more_context**: When you need basic context (project info, general topic) - NOT for detailed requirements

- **respond**: For general questions, discussions, or non-ticket conversations

Prefer clarify_requirements over generate_tickets when requirements quality is uncertain."""
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
            "## Additional Context\n{context_text}\n\n"
            "## Latest Input\n{latest_user_message}\n\n"
            "Identify gaps and generate clarifying questions. "
            "Focus on what's truly blocking development vs nice-to-have details."
        ),
    ])
    _clarification_chain = prompt | get_llm().with_structured_output(ClarificationAnalysis)
    return _clarification_chain