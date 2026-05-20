# RAG Test Data — Jira Ticket Analyzer

This file contains test tickets designed to validate that the RAG pipeline correctly
retrieves relevant historical context and improves analysis quality.

Each test case includes:
- The input ticket
- Expected RAG documents that should be retrieved
- Expected issues the analyzer should flag
- Expected suggestions grounded in historical context

---

## TEST-001 | Should trigger INC-001 + ADR-001 + PROJ-101 context

### Input Ticket
```json
{
  "key": "TODO-001",
  "issue_type": "Story",
  "summary": "Refactor payment confirmation to use async DB calls",
  "description": "We need to update the payment confirmation handler to use the new async database adapter introduced in v3.2. This will improve performance.",
  "priority": "High",
  "story_points": 3,
  "labels": ["payment-service"],
  "acceptance_criteria": [
    {
      "given": "A valid payment request",
      "when": "Confirmation is triggered",
      "then": "Payment is confirmed successfully"
    }
  ]
}
```

### Expected RAG Retrieval
- INC-001 (payment service outage caused by missing await on async DB call)
- ADR-001 (PostgreSQL connection pool limits, async handler warning)
- PROJ-101 (health check story post-INC-001)
- PROJ-089 (hotfix for exact same pattern)

### Expected Analyzer Output
**Issues:**
- CRITICAL: Missing await in async DB calls is a known P1 failure mode for this service (INC-001, PROJ-089)
- MAJOR: No AC for connection pool behavior under load
- MAJOR: No negative AC (what happens if DB is unavailable?)
- MINOR: No rollback plan mentioned

**Suggested AC additions (grounded in history):**
- GIVEN 100 concurrent payment confirmations WHEN all complete THEN pool utilization returns to baseline
- GIVEN DB is unavailable WHEN confirmation is triggered THEN 503 is returned within 2 seconds
- GIVEN the async handler completes WHEN the transaction ends THEN connection is released immediately

**Suggested labels:** `needs-load-test`, `payment-service`

---

## TEST-002 | Should trigger INC-003 + ADR-002 + PROJ-134 context

### Input Ticket
```json
{
  "key": "TODO-002",
  "issue_type": "Story",
  "summary": "Add email notification for new user signup",
  "description": "Send a welcome email when a new user completes registration. Use the existing notification service.",
  "priority": "Medium",
  "story_points": 2,
  "labels": ["notification-service"],
  "acceptance_criteria": [
    {
      "given": "A user completes signup",
      "when": "Registration is confirmed",
      "then": "A welcome email is sent"
    }
  ]
}
```

### Expected RAG Retrieval
- INC-003 (notification queue backlog from missing DLQ)
- ADR-002 (SQS DLQ mandatory, retry policy, queue depth alarms)
- PROJ-134 (DLQ implementation story)

### Expected Analyzer Output
**Issues:**
- CRITICAL: No DLQ or retry policy specified — this exact omission caused a 6-hour P2 incident (INC-003)
- MAJOR: No AC for failure path (what happens if email fails to send?)
- MAJOR: No queue depth / alarm threshold mentioned
- MINOR: Story points may be underestimated — queue setup adds complexity

**Suggested AC additions:**
- GIVEN the welcome email fails to send WHEN retried 3 times THEN message is routed to DLQ and alert fires
- GIVEN queue depth exceeds 1000 WHEN alarm evaluates THEN on-call is paged
- GIVEN the notification service is down WHEN signup occurs THEN signup still succeeds and email is queued for retry

---

## TEST-003 | Should trigger INC-002 + ADR-003 + PROJ-118 context

### Input Ticket
```json
{
  "key": "TODO-003",
  "issue_type": "Task",
  "summary": "Update JWT token expiry to 30 minutes",
  "description": "Change the JWT access token TTL from 15 minutes to 30 minutes based on UX feedback that users are getting logged out too often.",
  "priority": "Low",
  "labels": ["auth-service"],
  "acceptance_criteria": [
    {
      "given": "A user logs in",
      "when": "A token is issued",
      "then": "Token is valid for 30 minutes"
    }
  ]
}
```

### Expected RAG Retrieval
- INC-002 (JWT expiry misconfiguration caused full auth outage)
- ADR-003 (JWT TTL rules, startup validation requirement)
- PROJ-118 (startup config validation implementation)
- RCA-002 (five whys on JWT expiry incident)

### Expected Analyzer Output
**Issues:**
- CRITICAL: JWT config changes have caused a P1 outage before (INC-002) — startup validation AC is mandatory
- MAJOR: No AC for invalid/zero/missing JWT_EXPIRY_SECONDS at startup
- MAJOR: No AC for expired token behavior
- MAJOR: Priority should be Medium or High given auth outage history — Low is misleading
- MINOR: Missing story points

**Suggested AC additions:**
- GIVEN JWT_EXPIRY_SECONDS is 0 or missing WHEN auth-service starts THEN startup fails with fatal error
- GIVEN a token has expired WHEN a request is made THEN 401 is returned with re-auth prompt
- GIVEN the value is updated in secrets manager WHEN service restarts THEN new TTL is applied without code changes

---

## TEST-004 | Should trigger ADR-004 + INC-004 context

### Input Ticket
```json
{
  "key": "TODO-004",
  "issue_type": "Story",
  "summary": "Add new 'brand' field to product search index",
  "description": "Product search needs to support filtering by brand. Add brand as a filterable field to the Elasticsearch index.",
  "priority": "Medium",
  "story_points": 5,
  "labels": ["search-service"],
  "acceptance_criteria": [
    {
      "given": "A user searches with a brand filter",
      "when": "Search API is called",
      "then": "Results are filtered by brand correctly"
    }
  ]
}
```

### Expected RAG Retrieval
- INC-004 (search index corruption from direct writes during reindex)
- ADR-004 (alias strategy mandatory, dynamic mapping disabled)
- PROJ-145 (zero-downtime reindex implementation)

### Expected Analyzer Output
**Issues:**
- CRITICAL: Schema changes to Elasticsearch require alias-based reindex — direct writes to live index caused P2 corruption (INC-004)
- MAJOR: No mention of reindex strategy or alias swap
- MAJOR: No AC for zero-downtime requirement
- MINOR: No mention of mapping type for 'brand' field (keyword vs text)

**Suggested AC additions:**
- GIVEN the brand field is added WHEN the mapping is applied THEN it is done via alias swap with no dropped queries
- GIVEN a reindex is in progress WHEN a live search query is made THEN existing results are returned without errors
- GIVEN brand filter is applied WHEN the field has a null value THEN results exclude null-brand products gracefully

---

## TEST-005 | Multi-Tenant / RAG scoping test — Should trigger ADR-005

### Input Ticket
```json
{
  "key": "TODO-005",
  "issue_type": "Story",
  "summary": "Store analysis results in database",
  "description": "Persist ticket analysis results so users can review past analyses. Store in the analysis_results table.",
  "priority": "Medium",
  "story_points": 3,
  "labels": ["ticket-analyzer"],
  "acceptance_criteria": [
    {
      "given": "An analysis completes",
      "when": "Results are saved",
      "then": "User can retrieve past analysis results"
    }
  ]
}
```

### Expected RAG Retrieval
- ADR-005 (multi-tenant scoping via org_id + project_key)
- PROJ-201 (multi-tenant epic)

### Expected Analyzer Output
**Issues:**
- CRITICAL: No org_id or project_key scoping — storing results without tenant isolation violates ADR-005 and will cause cross-org data leakage
- CRITICAL: No AC for cross-tenant isolation
- MAJOR: No mention of data retention policy
- MINOR: "User" is ambiguous — specify org context

**Suggested AC additions:**
- GIVEN org A's analysis results WHEN org B queries the same endpoint THEN org B receives no results from org A
- GIVEN results are stored WHEN queried THEN they are always filtered by org_id + project_key
- GIVEN a user from org A WHEN they view past analyses THEN only their org's results are returned

---

## TEST-006 | Well-written ticket — should score high (8+/10)

### Input Ticket
```json
{
  "key": "TODO-006",
  "issue_type": "Story",
  "summary": "Add DLQ and retry policy to order-confirmation SQS queue",
  "description": "The order-confirmation queue currently has no DLQ configured. Following the ADR-002 mandate and learnings from INC-003, we need to add a DLQ with max receive count of 3 and a CloudWatch alarm at 1000 messages depth. Terraform module should enforce this going forward.",
  "priority": "High",
  "story_points": 3,
  "labels": ["notification-service", "infra"],
  "acceptance_criteria": [
    {
      "given": "An order confirmation message fails processing",
      "when": "It has been attempted 3 times",
      "then": "Message is routed to the DLQ and an alert fires within 5 minutes"
    },
    {
      "given": "Queue depth exceeds 1000 messages",
      "when": "CloudWatch alarm evaluates",
      "then": "On-call is paged via PagerDuty"
    },
    {
      "given": "A new queue is provisioned via Terraform",
      "when": "The module is applied",
      "then": "DLQ is created automatically without additional configuration"
    },
    {
      "given": "A valid order message is published",
      "when": "Consumer processes it",
      "then": "Order confirmation side effect occurs and message is acknowledged"
    }
  ]
}
```

### Expected Analyzer Output
**Expected score:** 8–9/10
**Issues:** Minor only
- MINOR: No explicit mention of visibility timeout alignment with Lambda timeout
- MINOR: Could add AC for DLQ monitoring / reprocessing workflow

---

## TEST-007 | Vague ticket — should score low (2–3/10)

### Input Ticket
```json
{
  "key": "TODO-007",
  "issue_type": "Story",
  "summary": "Fix the auth thing",
  "description": "Auth is broken sometimes. Need to fix it.",
  "priority": "Medium",
  "labels": [],
  "acceptance_criteria": []
}
```

### Expected Analyzer Output
**Expected score:** 1–2/10
**Issues:**
- CRITICAL: No acceptance criteria whatsoever
- CRITICAL: Summary is vague — "fix the auth thing" provides no actionable scope
- CRITICAL: Description is insufficient — no reproduction steps, no affected component
- MAJOR: No labels or component
- MAJOR: No story points
- MAJOR: "Sometimes" is not a testable condition — requires specificity

---

## Chunking Recommendations for RAG Ingestion

| Document Type | Chunk Strategy | Chunk Size |
|--------------|---------------|-----------|
| Incident tickets | One chunk per incident | ~500 tokens |
| RCA documents | Split by section (timeline, five whys, action items) | ~300 tokens |
| Runbooks | Split by step group | ~400 tokens |
| ADRs | One chunk per ADR | ~400 tokens |
| Engineering guidelines | Split by rule category | ~300 tokens |
| Completed tickets | One chunk per ticket | ~400 tokens |

## Metadata Schema for Vector Store

```json
{
  "doc_type": "incident | rca | runbook | adr | guideline | ticket",
  "severity": "p1 | p2 | p3 | null",
  "component": "payment-service | auth-service | ...",
  "team": "platform | payments | growth | discovery",
  "tags": ["async", "jwt", "queue", ...],
  "org_id": "string",
  "project_key": "string",
  "date": "YYYY-MM-DD"
}
```
