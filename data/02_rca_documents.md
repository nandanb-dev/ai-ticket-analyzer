# Root Cause Analysis Documents

---

## RCA-001 | Payment Service Outage — 2024-01-15

### Incident Summary
Production payment API returned 503 for 47 minutes. ~3,200 transactions failed.

### Timeline
- 14:02 — Deploy of `feat/payment-confirmation-v2` to production
- 14:10 — First alerts: DB connection errors in payment-service logs
- 14:14 — On-call engineer paged
- 14:22 — Root cause identified (connection pool exhaustion)
- 14:34 — Rollback initiated
- 14:49 — Service fully restored

### Five Whys
1. Why did the service go down? → DB connection pool was exhausted
2. Why was the pool exhausted? → Connections were never released
3. Why were connections never released? → `await` was missing in async DB handler
4. Why was this not caught? → No async-specific linting rule; no load test in CI
5. Why was there no load test? → Story had no AC requiring performance validation

### Contributing Factors
- No connection pool utilization alert existed pre-incident
- PR reviewer did not flag missing `await` (async code review gap)
- Staging environment pool limit was set to 500 (much higher than prod's 100), masking the issue

### Action Items
| # | Action | Owner | Status |
|---|--------|-------|--------|
| 1 | Add ESLint rule for unhandled async DB calls | Platform | Done |
| 2 | Align staging/prod pool limits | DevOps | Done |
| 3 | Add pool utilization alert at 80% | DevOps | Done |
| 4 | Require load test AC for all payment-related stories | PM | In Progress |

### Lessons for Ticket Writing
- Payment stories must include: load expectations, connection/resource limits, rollback steps
- AC must cover failure paths, not just happy path
- Staging config parity with prod must be verified in DevOps checklist

---

## RCA-002 | Auth Token Loop — 2024-02-03

### Incident Summary
All users logged out, unable to re-authenticate for 2h 14m due to JWT expiry misconfiguration.

### Timeline
- 09:15 — Secrets rotation completed by security team
- 09:18 — Auth service restarted to pick up new secrets
- 09:20 — First reports of users being logged out
- 09:35 — On-call identified JWT_EXPIRY_SECONDS = 0 in prod
- 10:12 — Correct value set; auth service restarted
- 11:29 — All sessions restored

### Five Whys
1. Why were users logged out? → Tokens expired immediately on issue
2. Why were tokens expiring immediately? → JWT_EXPIRY_SECONDS was 0
3. Why was it 0? → Not set in prod after secrets rotation
4. Why was it not set? → No post-rotation checklist included this var
5. Why no checklist item? → Var was added recently without updating runbook

### Action Items
| # | Action | Owner | Status |
|---|--------|-------|--------|
| 1 | Add startup validation for all critical env vars | Platform | Done |
| 2 | Update secrets rotation runbook | Security | Done |
| 3 | Add integration test: service fails to start with invalid JWT config | QA | Done |
| 4 | Scan all services for unvalidated critical env vars | Platform | In Progress |

### Lessons for Ticket Writing
- Auth-related tickets must include AC for config validation at startup
- Any ticket involving env vars must specify valid ranges/defaults
- Negative test cases are mandatory for auth, payments, and config-change tickets

---

## RCA-003 | Notification Queue Backlog — 2024-03-10

### Incident Summary
Notification delays of 4–6 hours affecting all users for 6 hours.

### Five Whys
1. Why were notifications delayed? → Queue backlog of ~48,000 messages
2. Why was there a backlog? → Retries on failed messages blocked the queue
3. Why did retries block the queue? → No DLQ configured; messages retried indefinitely
4. Why no DLQ? → New notification type added without standard queue setup
5. Why no standard setup? → No checklist enforced for new queue provisioning

### Action Items
| # | Action | Owner | Status |
|---|--------|-------|--------|
| 1 | DLQ mandatory for all new SQS queues (infra policy) | DevOps | Done |
| 2 | Max retry = 3 enforced via Terraform module | DevOps | Done |
| 3 | Queue depth alarm at 1000 messages | DevOps | Done |
| 4 | Update story template to include queue/retry requirements | PM | Done |

### Lessons for Ticket Writing
- Any story involving async messaging must specify: retry policy, DLQ behavior, alarm thresholds
- AC must include failure path: "GIVEN message fails WHEN retried N times THEN route to DLQ"
