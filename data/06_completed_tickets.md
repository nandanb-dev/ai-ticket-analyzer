# Completed Jira Tickets — Historical Archive

---

## PROJ-101 | Story | Add Connection Pool Health Check to Payment Service
**Priority:** High | **Points:** 3 | **Team:** Payments | **Component:** payment-service
**Status:** Done | **Sprint:** Sprint 14

### Description
Following INC-001, all DB-connected services must expose a connection pool health metric and alert when utilization crosses 80%.

### Acceptance Criteria
- GIVEN the payment service is running WHEN the /health endpoint is called THEN it returns current pool utilization as a percentage
- GIVEN pool utilization exceeds 80% WHEN the metric is evaluated THEN a CloudWatch alarm fires and pages on-call
- GIVEN pool utilization is at 100% WHEN a new request arrives THEN it returns 503 with "service temporarily unavailable" within 2 seconds
- GIVEN an async DB handler completes WHEN the transaction is done THEN the connection is released back to the pool immediately

### Implementation Notes
Used PgBouncer metrics endpoint. ESLint rule `no-floating-promises` added to catch missing awaits.

---

## PROJ-118 | Story | Implement JWT Config Validation at Service Startup
**Priority:** Critical | **Points:** 2 | **Team:** Platform | **Component:** auth-service
**Status:** Done | **Sprint:** Sprint 15

### Description
Auth service must validate all critical JWT configuration values at startup and fail fast with a descriptive error if any are missing or invalid. Stemming from INC-002 / RCA-002.

### Acceptance Criteria
- GIVEN JWT_EXPIRY_SECONDS is not set WHEN auth-service starts THEN process exits with code 1 and logs "FATAL: JWT_EXPIRY_SECONDS is required"
- GIVEN JWT_EXPIRY_SECONDS is set to 0 WHEN auth-service starts THEN process exits with code 1 and logs "FATAL: JWT_EXPIRY_SECONDS must be > 0"
- GIVEN all config is valid WHEN auth-service starts THEN it starts normally within 5 seconds
- GIVEN secrets are rotated WHEN auth-service is restarted THEN it picks up new values without code changes

### Implementation Notes
Added `validateConfig()` function called at top of `main()`. Throws on any invalid value. Integration test added that mocks missing env vars.

---

## PROJ-134 | Story | Add DLQ to All Notification Service Queues
**Priority:** High | **Points:** 5 | **Team:** Growth | **Component:** notification-service
**Status:** Done | **Sprint:** Sprint 16

### Description
Following INC-003, all SQS queues in notification-service must have a configured DLQ with max receive count of 3 and a queue depth alarm.

### Acceptance Criteria
- GIVEN a notification message fails processing WHEN it has been attempted 3 times THEN it is routed to the DLQ
- GIVEN a message lands in the DLQ WHEN the alarm evaluates THEN on-call is paged within 5 minutes
- GIVEN queue depth exceeds 1000 messages WHEN alarm fires THEN #on-call Slack channel receives an alert
- GIVEN a new notification type is added WHEN its queue is provisioned THEN the Terraform module enforces DLQ creation automatically

### Implementation Notes
Terraform SQS module updated with `dlq_enabled = true` as non-optional param. Runbook updated.

---

## PROJ-145 | Story | Zero-Downtime Elasticsearch Reindex via Alias Swap
**Priority:** High | **Points:** 8 | **Team:** Discovery | **Component:** search-service
**Status:** Done | **Sprint:** Sprint 17

### Description
Following INC-004, all Elasticsearch reindex operations must use index aliasing strategy. Direct writes to live indices are prohibited.

### Acceptance Criteria
- GIVEN a reindex is triggered WHEN it completes THEN the alias is swapped atomically with no dropped search queries
- GIVEN the reindex is in progress WHEN a live search query is made THEN it returns results from the current active index without errors
- GIVEN the new index fails validation WHEN the reindex pipeline runs THEN the alias swap does not occur and an alert fires
- GIVEN the alias swap completes WHEN the old index is verified as stable THEN the old index is deleted after 24 hours

---

## PROJ-201 | Epic | Multi-Tenant Support for AI Ticket Analyzer
**Priority:** High | **Points:** 34 | **Team:** Platform | **Component:** ticket-analyzer
**Status:** In Progress | **Sprint:** Sprint 22

### Description
Implement org_id + project_key scoping across all data stores, APIs, and RAG pipeline to support multiple organizations using the AI Ticket Analyzer without data leakage.

### Child Stories
- PROJ-202: Add org_id + project_key to all DB schemas
- PROJ-203: Scope RAG vector store by org_id + project_key
- PROJ-204: JIRA credential isolation per org/project in secrets manager
- PROJ-205: MCP server wrapper for core APIs
- PROJ-206: Cross-tenant isolation integration tests

### Top-Level Acceptance Criteria
- GIVEN org A's tickets WHEN org B queries the analyzer THEN org B receives zero results from org A
- GIVEN JIRA credentials for project KAN in org A WHEN org B attempts to use them THEN access is denied
- GIVEN a new org onboards WHEN they configure their project key THEN their data is fully isolated from day one

---

## PROJ-089 | Bug | Fix Async Handler Missing Await in Payment Confirmation
**Priority:** Critical | **Points:** 1 | **Team:** Payments | **Component:** payment-service
**Status:** Done | **Sprint:** Sprint 13

### Description
Hotfix for INC-001. Missing `await` in `confirmPayment()` DB call causing connection pool exhaustion under load.

### Acceptance Criteria
- GIVEN a payment confirmation is processed WHEN the DB call completes THEN the connection is released immediately
- GIVEN 100 concurrent payment confirmations WHEN all complete THEN pool utilization returns below 20% within 10 seconds
- GIVEN the fix is deployed WHEN load test runs at 200 RPS THEN error rate is < 0.1%

### Root Cause
`const result = db.query(...)` → should be `const result = await db.query(...)`
