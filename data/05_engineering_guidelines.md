# Engineering Guidelines & Ticket Writing Standards

---

## GUIDE-001 | Jira Ticket Quality Standards

### Mandatory Fields for All Tickets
- **Summary:** Concise, action-oriented. Format: `[Verb] [Object] [Context]`
  - Good: "Add DLQ configuration to notification-service SQS queues"
  - Bad: "Fix notification stuff"
- **Description:** Must include background, problem statement, and proposed approach
- **Acceptance Criteria:** Minimum 3 AC in GIVEN/WHEN/THEN format
- **Story Points:** Required for all Stories and Tasks. Use Fibonacci: 1, 2, 3, 5, 8, 13
- **Priority:** Must be set — never leave as default
- **Labels:** At minimum: service name, team name
- **Component:** Must map to a known system component

### Story Point Guidelines
| Points | Scope |
|--------|-------|
| 1      | Trivial config change, single-line fix |
| 2      | Small, well-understood change, 1–2 files |
| 3      | Medium task, some design decisions needed |
| 5      | Larger task, multiple components, some unknowns |
| 8      | Complex, spans services or requires spikes |
| 13     | Too large — must be broken down |

### Acceptance Criteria Rules
1. Every AC must follow GIVEN/WHEN/THEN format
2. Every ticket must have at least one negative/failure AC
3. Security-sensitive tickets must include an AC for unauthorized access scenarios
4. Performance-sensitive tickets must include an AC with specific latency/throughput targets
5. Config-change tickets must include an AC validating startup behavior with invalid/missing config

### Red Flags in Tickets (auto-flagged by analyzer)
- No acceptance criteria
- AC without GIVEN/WHEN/THEN
- Story points missing or > 8 (without spike justification)
- No rollback plan for infra/DB tickets
- Missing priority
- Vague summary (contains words like "fix", "update", "improve" without specifics)
- No labels or component
- Description under 50 words

---

## GUIDE-002 | Acceptance Criteria Templates by Ticket Type

### API Endpoint Story
```
GIVEN a valid authenticated request with [params]
WHEN the [endpoint] is called
THEN it returns [expected response] with status [code]

GIVEN an unauthenticated request
WHEN the [endpoint] is called
THEN it returns 401 Unauthorized

GIVEN invalid/malformed input [specify]
WHEN the [endpoint] is called
THEN it returns 400 Bad Request with a descriptive error message

GIVEN the downstream service is unavailable
WHEN the [endpoint] is called
THEN it returns 503 with a graceful error and does not expose internal details
```

### Database Migration Story
```
GIVEN the migration has not been run
WHEN it is applied in staging
THEN all existing data is preserved and schema matches expected state

GIVEN the migration is applied
WHEN it is rolled back
THEN the schema reverts to the previous state without data loss

GIVEN the service runs after migration
WHEN it processes a record in the new schema
THEN it behaves identically to pre-migration behavior
```

### Auth / Security Story
```
GIVEN a valid token within TTL
WHEN a request is made to a protected route
THEN the request is processed successfully

GIVEN an expired token
WHEN a request is made to a protected route
THEN 401 is returned and the user is prompted to re-authenticate

GIVEN a token from org A
WHEN a request is made to access org B's data
THEN 403 is returned and no org B data is exposed

GIVEN JWT_EXPIRY_SECONDS is missing or zero
WHEN the auth service starts
THEN startup fails with a clear fatal error message
```

### Async / Queue Story
```
GIVEN a valid message is published to the queue
WHEN the consumer processes it
THEN the expected side effect occurs and message is acknowledged

GIVEN a message fails processing
WHEN it has been retried [N] times
THEN it is routed to the DLQ and an alert is triggered

GIVEN queue depth exceeds [threshold]
WHEN the alarm fires
THEN on-call is paged within 5 minutes
```

### Feature Flag Story
```
GIVEN the feature flag is enabled
WHEN a user accesses the feature
THEN the new behavior is presented

GIVEN the feature flag is disabled
WHEN a user accesses the feature
THEN the existing/fallback behavior is presented and no errors occur

GIVEN the flag is toggled off mid-session
WHEN the user's next request is processed
THEN the fallback is applied gracefully without a crash or data corruption
```

---

## GUIDE-003 | Labels and Component Taxonomy

### Service Labels
`payment-service` | `auth-service` | `notification-service` | `search-service` | `api-gateway` | `ticket-analyzer`

### Type Labels
`feature` | `bug` | `tech-debt` | `security` | `performance` | `infra` | `migration` | `incident` | `spike`

### Cross-Cutting Labels
`needs-load-test` | `needs-migration` | `needs-feature-flag` | `breaking-change` | `multi-tenant` | `rag` | `mcp-integration`

---

## GUIDE-004 | Definition of Done

A ticket is only Done when:
- [ ] Code reviewed by ≥ 2 engineers
- [ ] All AC verified by QA or developer with evidence (test output / screenshots)
- [ ] Unit tests written for new logic (coverage delta > 0)
- [ ] Integration test added for new endpoints
- [ ] No new lint warnings introduced
- [ ] Documentation updated if public API changed
- [ ] Feature flag configured if change affects >10% of users
- [ ] Rollback plan executed successfully (for infra/DB tickets)
- [ ] Ticket updated with "Done" status and test evidence linked
