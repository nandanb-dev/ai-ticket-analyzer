# Architecture Decision Records (ADRs)

---

## ADR-001 | Use PostgreSQL as Primary Datastore

**Date:** 2023-06-10
**Status:** Accepted
**Team:** Platform
**Deciders:** Nandan, Srinidhi, Lead Architect

### Context
We needed a primary relational datastore for transactional data (orders, users, payments). Evaluated PostgreSQL, MySQL, and CockroachDB.

### Decision
PostgreSQL chosen for its ACID guarantees, JSON support, mature ecosystem, and team familiarity.

### Consequences
- Connection pool management is critical — use PgBouncer in transaction mode for high-concurrency services
- Max pool size per service instance: 20 connections (prod), 10 (staging)
- All services must implement connection pool health checks
- Async services must explicitly release connections — missing `await` on DB calls is a known failure mode (see INC-001)

### Ticket Implications
Any ticket touching DB layer must include:
- Expected query volume / connection count
- Index strategy for new queries (EXPLAIN ANALYZE required for queries on tables >100k rows)
- Migration strategy and rollback plan

---

## ADR-002 | Event-Driven Architecture via SQS for Async Workloads

**Date:** 2023-08-15
**Status:** Accepted
**Team:** Platform
**Deciders:** Nandan, DevOps Lead

### Context
Notification, email, and background processing workloads needed decoupling from synchronous API paths.

### Decision
AWS SQS with Lambda consumers for all async workloads. SNS fan-out for multi-consumer events.

### Consequences
- Every SQS queue must have a paired Dead Letter Queue (DLQ) — no exceptions (see INC-003)
- Max receive count before DLQ routing: 3
- Queue depth alarms mandatory at 1000 messages
- Visibility timeout must be >= 6x Lambda function timeout

### Ticket Implications
Any ticket introducing a new queue must specify:
- Queue name and type (standard vs FIFO)
- DLQ configuration
- Retry policy and max attempts
- Consumer throughput expectations
- Alarm thresholds

---

## ADR-003 | JWT-Based Auth with Short-Lived Tokens

**Date:** 2023-07-01
**Status:** Accepted
**Team:** Platform / Security

### Decision
JWTs for stateless auth. Access token TTL: 15 minutes. Refresh token TTL: 7 days. Stored in httpOnly cookies only (never localStorage).

### Consequences
- JWT_EXPIRY_SECONDS must be validated at service startup — zero or missing value is a fatal config error (see INC-002, RCA-002)
- Refresh token rotation on every use (sliding window)
- All auth-related config must be in secrets manager, not .env files checked into git

### Ticket Implications
Auth tickets must include:
- Token TTL requirements
- Cookie security flags (httpOnly, Secure, SameSite)
- AC for startup config validation
- Negative AC: expired token, invalid token, missing token scenarios

---

## ADR-004 | Elasticsearch for Search and Discovery

**Date:** 2023-09-20
**Status:** Accepted
**Team:** Discovery

### Decision
Elasticsearch 8.x for all product search, filtering, and faceting. Index aliasing is mandatory for all indices to support zero-downtime reindexing.

### Consequences
- Direct writes to live index are prohibited — always write to versioned index, swap alias atomically (see INC-004)
- Reindex pipelines must use blue/green index strategy
- All indices must have explicit mapping — dynamic mapping disabled in prod
- Shard count must be determined at index creation (cannot be changed later)

### Ticket Implications
Search tickets must include:
- Index alias strategy
- Zero-downtime reindex plan if schema changes are involved
- Mapping changes must be backward-compatible or require a full reindex with alias swap

---

## ADR-005 | Multi-Tenancy via project_key + org_id Scoping

**Date:** 2024-05-01
**Status:** Accepted
**Team:** Platform
**Deciders:** Nandan, Srinidhi

### Context
AI Ticket Analyzer needs to support multiple organizations and projects without data leakage between tenants.

### Decision
All data (RAG vectors, chat sessions, analysis results, JIRA credentials) scoped by composite key: `org_id + project_key`. No global queries allowed in multi-tenant contexts.

### Consequences
- Every DB table and vector store collection must have `org_id` and `project_key` columns/metadata fields
- All API endpoints must resolve `org_id` from the authenticated MCP context — never trust client-supplied `org_id`
- JIRA credentials stored in secrets manager keyed as `{org_id}/{project_key}/jira_token`
- RAG retrieval must always include metadata filter: `{ org_id: X, project_key: Y }`

### Ticket Implications
Any ticket in the AI Ticket Analyzer project must:
- Specify which data is org-scoped vs global
- Include AC for cross-tenant isolation: "GIVEN org A's data WHEN org B queries THEN org B receives no results"
- Never hardcode org_id or project_key in test fixtures — use parameterized test data
