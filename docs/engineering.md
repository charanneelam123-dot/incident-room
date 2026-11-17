# Engineering notes

## Why this is more than a chat window

The model's output is only one part of the run. Python owns tool permissions,
numeric telemetry queries, the evidence registry, final-report checks, resource
limits, and action decisions. Those boundaries remain in place if a model asks
for an unsupported tool or invents a source ID.

The dashboard reads intermediate run snapshots while the background worker adds
events. It never receives provider credentials. The SQLite document is a convenient
small-project event snapshot, not an append-only compliance ledger. Run data is
not tenant-isolated because this is a local single-operator application.

## What an approval means here

Approval changes a durable decision record from absent to a unique version-1
outcome. The result says `external_system_changed: false`. There is no production
executor hiding behind the button. A real integration would need a separate
executor with scoped credentials and a recovery check, plus authenticated operator
identities and stronger auditing.

The scenario allowlist encodes a permitted target. It prevents arbitrary writes
but also leaks the intended remediation boundary through tool feedback. Evaluate
investigation quality separately from whether the proposal passes this policy.

## Model evaluation still needed

The current cases are synthetic and there are only three. A replay already knows
the expected diagnosis. The live evaluator checks substrings and action names;
it can miss a fluent but incorrect explanation, and reject a correct paraphrase.
Before making accuracy claims, add domain-reviewed variants, held-out incidents,
missing-data cases, ambiguous evidence, and adversarial runbook text. Have a human
grade whether each finding actually follows from its cited observation.

Quote membership is an attribution check, not an entailment check. Confidence is
the model's label, not a calibrated probability. The alternative explanation is
required text and a second service inspection is enforced; those checks do not
guarantee that the alternative was considered well.

## Resource boundaries

The turn and tool limits are hard application bounds. Token usage is observed
after each response, so one response can cross the threshold. The wall-clock
deadline is checked between operations; a provider request can occupy its full
30-second timeout. Interrupted jobs are preserved but not resumed. A deployed
backend would need a worker queue with durable job status rather than two threads.

## Data handling

All bundled logs and credentials are fictional identifiers. There are no secret
values in the sample data. If real logs are introduced, redact them before both
storage and model calls; this version does not claim to detect arbitrary PII.
Reports and the SQLite database should be treated as containing their input data.

The Sites deployment is a static replay. Model calls and approval persistence run
only in the locally started Python server. This keeps the public source useful
without placing an unprotected API-key-backed service on the internet.
