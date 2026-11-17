# Project introduction

I built Incident Room, a small incident investigation sandbox for a fictional
online store.

An alert starts the investigation. The agent can query metrics, read logs, check
releases, and search runbooks. Its report has to cite observations that actually
came back from those tools. If a reference or quote fails validation, the model
can correct the report within its remaining budget.

Fixes take a different path. The agent proposes an allowed sandbox action, and
an operator reviews it. Concurrent approvals cannot apply the same decision twice.

One example has low HTTP error rates but stale inventory. Another has noisy payment
logs even though checkout is the source of the problem. These examples made the
evidence trail more useful than a confident paragraph alone.

The repository includes a local dashboard, SQLite run history, tests, and a hosted
replay demo. Replay results are labeled; live model quality still needs evaluation.

Code: https://github.com/charanneelam123-dot/incident-room
