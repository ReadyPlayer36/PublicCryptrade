# Stage-2 tests-only commit (review candidate)

This commit is intentionally **not an implementation**. It preserves the Stage-1 frozen specification and approval record, adds a Python 3.12 CI workflow, reads retry/finality/cooldown/storage policy from `matrix.yaml`, and supplies importable `NotImplementedError` production stubs.

## Expected status

- `tests/tools/test_spec_tooling.py` and policy/freeze-integrity tests are intended to pass.
- The behavioral acceptance suite is intentionally red because production behavior has not been implemented. Red tests should fail through explicit `NotImplementedError` stubs or explicit not-yet-implemented security assertions—not because modules cannot be imported.
- The CI workflow always checks collection and the frozen spec tooling. It runs the behavior suite as a non-blocking, explicitly expected-red step for this review commit; this is not a passing acceptance gate.
- Local verification confirmed collection and the focused passing checks, but the complete suite did not finish within the available 200-second execution window. No full-suite pass is claimed; the expected-red run and its runtime should be reviewed before relying on CI behavior.
- No API credentials, private endpoints, orders, or live network requests are included. OBS-01/OBS-02 and finality-lag approval remain prerequisites to any future LIVE acceptance run.

## Review boundaries

Please review this tests-only commit before implementation starts. Do not interpret this scaffold as Milestone 1 approval; Milestone 1 remains BLOCKED.
