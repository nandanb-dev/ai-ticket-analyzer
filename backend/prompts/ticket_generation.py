from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate

from prompts.system import SYSTEM_PROMPT

_SCHEMA = """
Return a single JSON object — no markdown fences, no extra text — matching this structure exactly:

{
  "epics": [
    {
      "summary": "Epic title (feature area)",
      "description": "## Overview\\nWhat this epic covers and why.\\n\\n## Requirements\\n- requirement 1\\n- requirement 2",
      "priority": "High",
      "story_points": 21,
      "labels": ["epic"]
    }
  ],
  "stories": [
    {
      "summary": "As a [role], I want [action] so that [benefit]",
      "epic_index": 0,
      "description": "## Overview\\nUser-facing description of the feature.",
      "priority": "High",
      "story_points": 5,
      "labels": ["story"],
      "acceptance_criteria": [
        {"given": "the user is on the login page", "when": "they submit valid credentials", "then": "they are redirected to the dashboard"}
      ],
      "test_cases": [
        {"type": "positive", "title": "Successful login", "steps": ["Navigate to login", "Enter valid credentials", "Click submit"], "expected": "User is redirected to dashboard"},
        {"type": "negative", "title": "Invalid password", "steps": ["Navigate to login", "Enter wrong password", "Click submit"], "expected": "Error message is shown"},
        {"type": "edge",     "title": "Login with expired session token", "steps": ["Use an expired token"], "expected": "User is redirected to login with session-expired message"}
      ],
      "edge_cases": [
        "What happens when the user submits the form with JavaScript disabled?",
        "What happens when the API is down during credential validation?"
      ]
    }
  ],
  "tasks": [
    {
      "summary": "Implement [specific technical component]",
      "story_index": 0,
      "description": "Technical implementation details, affected files, and approach.",
      "priority": "Medium",
      "story_points": 3,
      "labels": ["task"],
      "acceptance_criteria": [
        {"given": "the endpoint receives a valid request", "when": "the handler executes", "then": "it returns a 200 response with the expected payload"},
        {"given": "the endpoint receives an invalid request", "when": "validation fails", "then": "it returns a 422 with a descriptive error message"}
      ]
    }
  ]
}

Rules:
- Cover EVERY feature mentioned in the PRD — do not skip anything
- Each story must have ≥3 acceptance criteria (Given/When/Then) and ≥3 test cases (mix of positive, negative, edge)
- Each task must have ≥2 acceptance criteria
- Edge cases must be feature-specific — no generic placeholders
- story_points must be Fibonacci: 1, 2, 3, 5, 8, 13, or 21
- epic_index = 0-based index of the parent epic in the "epics" array
- story_index = 0-based index of the parent story in the "stories" array
"""

TICKET_GENERATION_PROMPT = ChatPromptTemplate.from_messages([
    SystemMessage(content=SYSTEM_PROMPT + "\n" + _SCHEMA),
    HumanMessagePromptTemplate.from_template(
        "Analyze the following PRD and generate all JIRA tickets:\n\n{prd_content}"
    ),
])
