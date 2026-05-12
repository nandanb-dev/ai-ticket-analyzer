from typing import TypedDict, Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END

from config import OPENAI_API_KEY, GOOGLE_API_KEY, GROQ_API_KEY
from prompts.testcase_generation import TESTCASE_PROMPT


class TestCaseState(TypedDict):
    story: str
    acceptance_criteria: list
    result: Optional[list]
    error: Optional[str]


_chain = None


def _get_chain():
    global _chain
    if _chain:
        return _chain

    # if not OPENAI_API_KEY:
    #     raise RuntimeError("OPENAI_API_KEY is not configured in .env")
    # llm = ChatOpenAI(model="gpt-4o", temperature=0.2, api_key=OPENAI_API_KEY)

    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not configured in .env")
    llm = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0.2)

    # if not GROQ_API_KEY:
    #     raise RuntimeError("GROQ_API_KEY is not configured in .env")
    # llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2, api_key=GROQ_API_KEY)

    _chain = TESTCASE_PROMPT | llm | JsonOutputParser()
    return _chain


def _generate_node(state: TestCaseState):
    try:
        result = _get_chain().invoke({
            "story": state["story"],
            "acceptance_criteria": "\n".join(state["acceptance_criteria"])
        })
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}


_graph = StateGraph(TestCaseState)

_graph.add_node("generate", _generate_node)
_graph.set_entry_point("generate")
_graph.add_edge("generate", END)

_agent = _graph.compile()


def run_testcase_agent(story: str, acceptance_criteria: list):
    final = _agent.invoke({
        "story": story,
        "acceptance_criteria": acceptance_criteria,
        "result": None,
        "error": None
    })

    if final.get("error"):
        raise RuntimeError(final["error"])

    return final["result"]