from typing import TypedDict, Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from config import OPENAI_API_KEY
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

    llm = ChatOpenAI(model="gpt-4o", temperature=0.2, api_key=OPENAI_API_KEY)
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