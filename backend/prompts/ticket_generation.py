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
  ],
  "bugs": [
    {
      "summary": "[Component] - Brief description of the bug",
      "description": "## Bug Description\\nWhat is happening incorrectly.\\n\\n## Steps to Reproduce\\n1. Step one\\n2. Step two\\n\\n## Expected Behavior\\nWhat should happen.\\n\\n## Actual Behavior\\nWhat is happening instead.",
      "priority": "High",
      "story_points": 3,
      "labels": ["bug"],
      "acceptance_criteria": [
        {"given": "the bug scenario", "when": "user performs the action", "then": "the expected behavior occurs without error"}
      ],
      "environment": "Production/Staging/Development"
    }
  ]
}

Rules:
- If user specifies constraints (e.g., "one story"), follow those exactly - do not add extra tickets
- If no constraints AND it's a feature request, cover EVERY feature mentioned — do not skip anything
- Each story must have ≥3 acceptance criteria (Given/When/Then) and ≥3 test cases (mix of positive, negative, edge)
- Each task must have ≥2 acceptance criteria
- Each bug must have ≥1 acceptance criteria describing the fix verification
- Edge cases must be feature-specific — no generic placeholders
- story_points must be Fibonacci: 1, 2, 3, 5, 8, 13, or 21
- epic_index = 0-based index of the parent epic in the "epics" array (use -1 or omit if no epics)
- story_index = 0-based index of the parent story in the "stories" array (use -1 or omit if no stories)
- Return empty arrays [] for ticket types user didn't request

ISSUE TYPE DETECTION:
- **Bug**: User reports something broken, error, crash, issue, not working, fix needed, regression
- **Story**: User-facing feature request (As a user, I want...)
- **Task**: Technical/implementation work, internal changes, refactoring
- **Epic**: Large initiative grouping multiple stories
"""

TICKET_GENERATION_PROMPT = ChatPromptTemplate.from_messages([
    SystemMessage(content=SYSTEM_PROMPT + "\n" + _SCHEMA),
    HumanMessagePromptTemplate.from_template(
        """Analyze the following PRD/context and generate JIRA tickets.

IMPORTANT - Parse user constraints carefully:

QUANTITY RULES (extract numbers from user request):
- "a ticket" / "one ticket" / "1 ticket" → exactly 1 ticket (detect type from context)
- "two stories" / "2 stories" → exactly 2 stories only
- "three tasks" / "3 tasks" → exactly 3 tasks only
- "a bug" / "bug ticket" / "one bug" → exactly 1 bug
- Number words: one=1, two=2, three=3, four=4, five=5, six=6, seven=7, eight=8, nine=9, ten=10

TYPE RULES:
- "story/stories" → generate only stories (no epics, no tasks, no bugs)
- "task/tasks" → generate only tasks
- "bug/bugs" → generate only bugs
- "epic/epics" → generate only epics
- "epic and stories" → generate epic + stories (no tasks)
- "create tickets" / "generate tickets" (plural, no specific type) → generate full hierarchy (epics, stories, tasks)

AUTO-DETECT ISSUE TYPE (when user says "create a ticket" without specifying type):
- If context describes something BROKEN/ERROR/CRASH/NOT WORKING → create a Bug
- If context describes a NEW FEATURE for users → create a Story  
- If context describes TECHNICAL/INTERNAL work → create a Task
- If context describes a LARGE INITIATIVE with multiple features → create an Epic

EXAMPLES:
- "create a ticket for login bug" → 1 bug
- "create two stories for user authentication" → 2 stories
- "create a bug ticket for the password modal error" → 1 bug
- "generate 3 tasks for the API refactor" → 3 tasks
- "create tickets for the new dashboard feature" → full hierarchy (epic + stories + tasks)

Parse the "Latest instruction" below for quantity and type constraints.

{prd_content}"""
    ),
])
