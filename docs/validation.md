# Validation record

2026-11-17, Python 3.14.5 on Windows.

- 29 unit and HTTP integration tests passed.
- Three scripted incident regressions completed with pending proposals and no execution.
- Built the Python wheel. GitHub CI also installs the package and runs its CLI.
- Chrome checked the local API dashboard end to end: start investigation, inspect
  a citation, enter an approval reason, and observe the persisted sandbox outcome.
- The 390px viewport had no horizontal overflow and no browser script errors.
- The static replay is generated from the actual Python workflow, with an explicit
  no-model-calls label. It does not substitute for a live-model evaluation.

Live tool selection and report correction have mocked-provider tests. No paid
model calls or live-model quality evaluation have been run. The token and latency
figures in replay mode must not be presented as model performance measurements.
