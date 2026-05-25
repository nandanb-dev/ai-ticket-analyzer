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
- If user specifies constraints (e.g., "one story"), follow those exactly - do not add extra tickets
- If no constraints, cover EVERY feature mentioned in the PRD — do not skip anything
- Keep summaries and descriptions concise and implementation-ready; avoid verbose or generic filler text
- Each story must have ≥3 acceptance criteria (Given/When/Then) and ≥3 test cases (mix of positive, negative, edge)
- Each task must have ≥2 acceptance criteria
- Edge cases must be feature-specific — no generic placeholders
- story_points must be Fibonacci: 1, 2, 3, 5, 8, 13, or 21
- epic_index = 0-based index of the parent epic in the "epics" array (use -1 or omit if no epics)
- story_index = 0-based index of the parent story in the "stories" array (use -1 or omit if no stories)
- Return empty arrays [] for ticket types user didn't request
"""

TICKET_GENERATION_PROMPT = ChatPromptTemplate.from_messages([
    SystemMessage(content=SYSTEM_PROMPT + "\n" + _SCHEMA),
    HumanMessagePromptTemplate.from_template(
        """Analyze the following PRD/context and generate JIRA tickets.

IMPORTANT - Respect user constraints:
- If user asks for "one story" or "1 story" → generate exactly 1 story (no epics, no tasks)
- If user asks for "only stories" → generate only stories (no epics, no tasks)
- If user asks for "2 tasks" → generate exactly 2 tasks
- If user asks for "epic and stories" → generate epic + stories (no tasks)
- If user asks for "create tickets" or "generate tickets" (no quantity) → generate all (epics, stories, tasks)
- Default when no constraint specified: generate appropriate epics, stories, AND tasks

Parse the "Latest instruction" below for any quantity or type constraints.

Quality bar for Jira-ready output:
- Summary style:
  • Story: single sentence in "As a [role], I want [action] so that [benefit]" format
  • Task: imperative technical action (for example "Implement OAuth callback validation")
- Description style:
  • Maximum 5-8 concise bullet points across sections
  • Include scope boundaries, key technical notes, and non-goals
  • No repeated context paragraphs
- Acceptance criteria style:
  • Testable, objective, and measurable
  • Avoid vague terms like "properly", "quickly", "user-friendly" without measurable definition
- Test cases style:
  • Realistic and brief, with concrete expected outcomes
  • At least one negative and one edge case per story
- Keep labels minimal and useful (3-5 max per ticket)

{prd_content}"""
    ),
])
