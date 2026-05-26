# P1/P2 Incident Tickets — Historical Archive

---

## INC-001 | P1 | Payment Service Outage
**Date:** 2024-01-15
**Component:** payment-service
**Team:** Payments
**Severity:** P1
**Duration:** 47 minutes
**Service:** checkout, billing

### Summary
Payment processing API became unresponsive due to a connection pool exhaustion in the PostgreSQL adapter. All checkout flows were blocked. Approximately 3,200 transactions failed during the window.

### Root Cause
A recent deploy introduced a missing `await` in an async DB call inside the payment confirmation handler. This caused connections to never be released back to the pool. Under sustained load, the pool hit its 100-connection ceiling within 8 minutes of deployment.

### Fix Applied
Rolled back the offending commit. Added connection pool monitoring with auto-alert at 80% utilization. Patched the async handler in the hotfix branch.

### Acceptance Criteria Gaps Identified
- No load testing AC was present in the original story
- No connection pool limits were specified in the implementation ticket
- Story lacked a rollback plan section

### Tags: payment, postgres, connection-pool, async, p1, outage

---

## INC-002 | P1 | Auth Token Expiry Loop
**Date:** 2024-02-03
**Component:** auth-service
**Team:** Platform
**Severity:** P1
**Duration:** 2 hours 14 minutes
**Service:** all authenticated routes

### Summary
A misconfigured JWT expiry value (set to `0` instead of `86400`) caused all tokens to expire immediately on issue. All users were logged out and could not re-authenticate. Affected 100% of active sessions.

### Root Cause
Environment variable `JWT_EXPIRY_SECONDS` was not set in the production `.env` file after a secrets rotation. The application defaulted to `0`. No validation existed for this config value at startup.

### Fix Applied
Set correct value in secrets manager. Added startup config validation that throws a fatal error if `JWT_EXPIRY_SECONDS` is zero or missing.

### Acceptance Criteria Gaps Identified
- No AC around config validation on service startup
- No mention of fallback/default values for critical env vars
- Missing negative test case: "GIVEN token expiry is misconfigured WHEN service starts THEN startup should fail with a clear error"

### Tags: auth, jwt, config, env-vars, p1, session

---

## INC-003 | P2 | Notification Service Delay
**Date:** 2024-03-10
**Component:** notification-service
**Team:** Growth
**Severity:** P2
**Duration:** 6 hours
**Service:** email, push notifications

### Summary
Email and push notifications were delayed by 4–6 hours due to a queue backlog caused by a missing dead-letter queue configuration. Retries on failed messages were blocking the main queue.

### Root Cause
A new notification type was added without configuring a DLQ for its SQS queue. Failed messages retried indefinitely, starving valid messages of processing capacity.

### Fix Applied
Added DLQ to all notification queues. Implemented max retry count of 3 before routing to DLQ. Added queue depth alarm at 1000 messages.

### Acceptance Criteria Gaps Identified
- Story had no AC for failure/retry behavior
- No mention of DLQ requirements in the ticket
- Missing edge case: "GIVEN a notification fails to send WHEN retried 3 times THEN message should be routed to DLQ and alert triggered"

### Tags: notifications, sqs, dlq, queue, retry, p2

---

## INC-004 | P2 | Search Index Corruption
**Date:** 2024-04-22
**Component:** search-service
**Team:** Discovery
**Severity:** P2
**Duration:** 3 hours
**Service:** product search, filters

### Summary
Elasticsearch index became partially corrupted after a bulk reindex operation ran concurrently with live writes. Search results were returning stale or missing records.

### Root Cause
The reindex script did not implement index aliasing. It wrote directly to the live index, causing partial overlap with real-time write operations.

### Fix Applied
Rewrote reindex pipeline to use index aliasing (write to new index, swap alias atomically). Added a read-only lock during alias swap.

### Acceptance Criteria Gaps Identified
- Reindex story had no AC for zero-downtime requirement
- No mention of alias strategy
- Missing: "GIVEN a reindex is triggered WHEN it completes THEN alias should be swapped atomically with no dropped queries"

### Tags: elasticsearch, search, reindex, aliasing, p2, corruption
