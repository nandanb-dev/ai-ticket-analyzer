# Engineering Runbooks

---

## RUNBOOK-001 | Deploying to Production

### Prerequisites
- PR approved by at least 2 engineers
- All CI checks passing (lint, unit, integration, e2e)
- QA sign-off on staging
- Rollback plan documented in the ticket
- Feature flag configured if applicable

### Steps
1. Notify #deployments Slack channel: "Deploying [service] [version] to prod"
2. Verify staging is stable and matches prod config
3. Trigger deploy via CI/CD pipeline (do not deploy manually)
4. Monitor error rate and p99 latency for 10 minutes post-deploy
5. Confirm with on-call that no alerts fired
6. Close the deploy notification in #deployments

### Rollback Procedure
1. Trigger rollback job in CI/CD pipeline
2. Confirm previous version is running (`kubectl get pods -n <namespace>`)
3. Verify error rate returns to baseline
4. Post incident note in #deployments
5. Open a P1/P2 ticket if user impact occurred

### Common Failure Points
- DB migrations not run before service deploy → always run migrations as a pre-step
- Env vars missing in new environment → run config validation script before deploy
- Downstream service not ready → check dependency health endpoints before cutover

---

## RUNBOOK-002 | Database Migration Runbook

### Rules
- Never run destructive migrations (DROP, TRUNCATE) without a backup
- Always use `--dry-run` to preview migrations on staging first
- Migrations must be backward-compatible for at least one release cycle
- Never modify a column type directly — add new column, backfill, then deprecate old

### Steps for Applying Migrations
1. Take a DB snapshot (automated via CI, confirm before proceeding)
2. Run migration on staging: `npm run migrate:staging`
3. Verify row counts and schema with QA
4. Schedule prod migration during low-traffic window (00:00–04:00 IST)
5. Run migration on prod: `npm run migrate:prod`
6. Run smoke tests post-migration
7. Monitor DB query times for 30 minutes

### Rollback
- Reversible migrations: run `npm run migrate:rollback`
- Irreversible (e.g. column drops): restore from snapshot — escalate to P1

---

## RUNBOOK-003 | On-Call Response Runbook

### Severity Definitions
| Level | Response Time | Examples |
|-------|--------------|---------|
| P1    | 15 minutes   | Full outage, data loss, auth down, payment failure |
| P2    | 1 hour       | Partial outage, major feature broken, perf degradation >50% |
| P3    | Next business day | Minor bug, cosmetic issue, non-critical feature broken |

### P1 Response Steps
1. Acknowledge PagerDuty alert within 15 minutes
2. Join #incident-[date] Slack channel (auto-created)
3. Assign Incident Commander (IC) and Comms Lead
4. Post initial update in channel: what is known, what is being investigated
5. Identify blast radius: how many users, which services affected
6. Fix or rollback — do not both simultaneously
7. Post resolution note: what happened, what was fixed, ETA for RCA

### Ticket Requirements Post-Incident
Every P1/P2 must produce:
- A JIRA ticket tagged `incident` with timeline
- An RCA document linked to the ticket
- At least one follow-up ticket per action item from RCA
- Updated runbook if a gap was found

---

## RUNBOOK-004 | Feature Flag Management

### When to Use Feature Flags
- Any user-facing change affecting >10% of users
- A/B tests
- Gradual rollouts for high-risk changes
- Kill switch for experimental features

### Flag Naming Convention
`[team]-[feature]-[variant]`
Example: `payments-new-checkout-v2-enabled`

### Rollout Strategy
1. Start at 1% traffic
2. Monitor error rate and key metrics for 24 hours
3. Ramp to 10%, then 50%, then 100% in 24-hour increments
4. Only ramp if error rate delta < 0.1% vs control

### Ticket Requirements for Feature Flag Work
- AC must specify: flag name, default state, rollout % per phase, kill-switch behavior
- Story must include: "GIVEN flag is disabled WHEN user hits feature THEN fallback behavior X occurs"
- Cleanup ticket must be filed at the time of flag creation (set to resolve within 2 sprints)
