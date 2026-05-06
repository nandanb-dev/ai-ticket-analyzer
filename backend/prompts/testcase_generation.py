from langchain_core.prompts import ChatPromptTemplate

TESTCASE_PROMPT = ChatPromptTemplate.from_template("""
You are a QA engineer.

Generate test cases.

Rules:
- Include positive, negative, edge cases
- Return ONLY JSON
- Each test case:
  scenario, steps, expected_result

---

Story:
{story}

Acceptance Criteria:
{acceptance_criteria}

---

Return:
[
  {{
    "scenario": "...",
    "steps": ["..."],
    "expected_result": "..."
  }}
]
""")