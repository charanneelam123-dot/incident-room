# Database connection pool exhaustion
If timeouts follow a release, compare before/after database connections and inspect the release configuration. Each replica owns its own connection pool. A per-replica pool increase can exceed the database's shared limit. Consider rolling back the implicated release after human review. Error rates alone do not identify the cause.

# Expired payment credentials
A provider 401 with an explicit credential expiry is evidence of an expired credential. Check the timestamp and deployment history. Rotate the test credential in the sandbox after approval. A release rollback does not renew an expired credential. Never include secret values in a report.

# Stale inventory cache
Compare cached quantity with the authoritative inventory observation. Low HTTP error rates do not prove data freshness. If the inventory-cache-v2 flag disabled refresh, consider turning the flag off in the sandbox after human review. Confirm both the timestamp and source quantity before proposing a change.

# Incident evidence discipline
Record observations before proposing a cause. A deployment near an incident is correlation, not proof. Examine an alternative service when the alert names several. Any executable action is a proposal until an operator approves it. Never run shell commands or change a production service.
