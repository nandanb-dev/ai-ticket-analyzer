# Prompt Engineering Reference

This document details every prompt used by the AI Ticket Analyzer and explains
the design decisions behind them.

---

## 1. System Prompt

**Purpose:** Sets the AI's persona, expertise, and quality standards for the
entire conversation.

**Key design decisions:**
- Establishes 10+ years of cross-functional experience to get senior-level output
- Explicitly lists the four audiences (Developer, QA, PM, Product) so the AI
  generates content suitable for each
- Defines ticket hierarchy (Epic → Story → Task → Bug) with exact naming conventions
- Provides a Fibonacci reference table so estimates are calibrated
- Includes a full Description Template the AI must follow in every ticket
- Sets minimum AC counts per ticket type (≥5 for Epic, ≥3 for Story)

---

## 2. Ticket Generation User Prompt

**Purpose:** Instructs the AI on the document, configuration, and exact JSON
output schema.

### Prompt Template Variables

| Variable | Description | Example |
|---|---|---|
| `{document_content}` | Combined text of all parsed documents | Full PRD text |
| `{project_key}` | JIRA project key | `PROJ` |
| `{team_name}` | Team name for context | `Platform Engineering` |
| `{sprint_length}` | Sprint duration in weeks (calibrates estimates) | `2` |
| `{tech_stack}` | Technologies used (affects technical notes) | `Python, React, PostgreSQL` |
| `{team_velocity}` | Story points per sprint (normalises estimates) | `40` |

### Output Schema Design

The prompt enforces a strict JSON schema with these ticket types:

#### Epic
```json
{
  "summary": "Feature Area: High-level goal",
  "epic_name": "Short name (roadmap label)",
  "description": "Markdown using Description Template",
  "priority": "High",
  "story_points": 21,
  "labels": ["epic", "auth"],
  "components": ["Backend", "API"],
  "acceptance_criteria": [
    { "given": "...", "when": "...", "then": "..." }
  ],
  "test_cases": [
    {
      "id": "TC-EP001-01",
      "title": "...",
      "type": "positive | negative | edge | performance | security | integration",
      "preconditions": ["..."],
      "steps": ["Step 1: ...", "Step 2: ..."],
      "expected_result": "...",
      "test_data": "... or null",
      "severity": "Critical | High | Medium | Low"
    }
  ],
  "edge_cases": ["Specific scenario: what happens when X?"],
  "definition_of_done": ["..."],
  "dependencies": ["..."],
  "assignee_role": "Tech Lead",
  "security_considerations": "OWASP reference",
  "performance_requirements": "P95 < 200ms",
  "api_contracts": "POST /api/v1/auth/login → 200 {token}"
}
```

#### Story
Same as Epic plus:
- `epic_link` — parent epic summary
- `ui_ux_notes` — accessibility, wireframe references
- `api_endpoints` — specific endpoints this story implements
- `database_changes` — schema migrations required

#### Task
Same as Story plus:
- `story_link` — parent story summary
- `technical_approach` — recommended implementation strategy
- `estimated_hours` — effort in hours

#### Bug
- `steps_to_reproduce` — ordered reproduction steps
- `actual_behavior` — current incorrect state
- `expected_behavior` — correct state after fix

---

## 3. Acceptance Criteria Rules

Every AC follows **Gherkin BDD** format:

```
GIVEN [initial context]
WHEN  [action or event]
THEN  [expected observable outcome]
```

**Quality checklist applied in the prompt:**
- ✅ Testable — a QA engineer can automate it directly
- ✅ Unambiguous — no vague terms ("should work", "looks good")
- ✅ Complete — covers success, failure, and boundary conditions
- ✅ Singular — one observable outcome per criterion

**Examples of good vs. bad AC:**

| ❌ Bad | ✅ Good |
|---|---|
| "Login should work" | `GIVEN a registered user, WHEN they submit valid email+password, THEN a JWT access token (15-min TTL) is returned with status 200` |
| "Handle errors" | `GIVEN a user enters a wrong password 5 times, WHEN they attempt login again, THEN the account is locked for 30 minutes and a 423 status is returned` |

---

## 4. Test Case Design

The prompt mandates **minimum 3 test cases per Story**:

| # | Type | Purpose |
|---|---|---|
| 1 | `positive` | Happy path — valid input, expected success outcome |
| 2 | `negative` | Invalid input — error handling, rejection, validation |
| 3 | `edge` | Boundary values — empty, null, max-length, special chars |

Additional types generated when relevant:
- `security` — auth bypass, injection, IDOR, rate limit
- `performance` — for latency/throughput requirements
- `integration` — for cross-service flows

---

## 5. Edge Case Categories

The prompt instructs the AI to generate edge cases in these categories:

1. **Input boundaries** — empty string, null, max-length, negative numbers, zero
2. **Concurrency** — simultaneous requests, race conditions, double-submit
3. **Network failures** — timeout, connection reset, partial response
4. **Data integrity** — partial writes, rollback on failure, orphaned records
5. **Authentication/Authorization** — expired token, revoked session, role escalation
6. **External dependencies** — third-party API down, rate limited, returns unexpected data
7. **Character encoding** — unicode, emoji, SQL injection patterns, XSS payloads
8. **State transitions** — invalid state machine transitions, replay attacks

---

## 6. Definition of Done Template

Every ticket includes this standardised DoD:

```
□ Code implemented, linted, and passing all static analysis
□ Unit tests written with ≥80% branch coverage
□ Integration tests passing in CI/CD pipeline
□ Peer code review by ≥2 developers
□ QA tested all acceptance criteria — test evidence attached
□ API documentation updated in Swagger
□ Performance benchmark verified
□ Security checklist completed (OWASP)
□ Product Owner acceptance confirmed
□ Release notes / changelog updated
```

---

## 7. Chunking Strategy for Large Documents

For documents exceeding **60,000 characters** (~10,000 words):

1. Split into chunks of ~20,000 characters
2. Summarize each chunk using `DOCUMENT_CHUNK_SUMMARY_PROMPT`
3. Concatenate summaries and use as input to the main ticket generation
4. All requirements, numbers, and technical constraints are preserved in summaries

---

## 8. Prompt Tuning Tips

| Goal | Adjustment |
|---|---|
| More granular tasks | Decrease `team_velocity` or `sprint_length` |
| Fewer tickets | Increase `story_points` default in prompt |
| More security focus | Add "Security team" to team context |
| Frontend-heavy output | Add "React, TypeScript, CSS" to tech stack |
| API-first output | Add "API-first, OpenAPI, REST" to tech stack |
| Better estimates | Provide historical sprint data in `team_name` context |

---

## 9. MCP Atlassian Integration

The application backend integrates with Jira via direct REST API calls in
`backend/services/jira.py`. It does **not** use an internal `JiraClient` backed
by `mcp-atlassian`.

[mcp-atlassian](https://github.com/sooperset/mcp-atlassian) is useful as an
**optional external MCP/IDE integration** you can configure for tools such as
Claude Desktop, Cursor, or VS Code Copilot to let your AI assistant manage
Jira directly outside the app runtime.

### Optional MCP Server Config (Claude Desktop / Cursor)

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "JIRA_URL": "https://your-company.atlassian.net",
        "JIRA_USERNAME": "your.email@company.com",
        "JIRA_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

Once configured, you can ask your AI assistant:
- *"Create the tickets from this analysis in project PROJ"*
- *"Find all open stories in the AUTH epic"*
- *"Update the priority of PROJ-42 to Highest"*
