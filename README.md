# Stage-2 acceptance scaffold and observation harness (review candidate)

Branch `impl-obs-harness` (tip `b303ce6`). Production code and the observation
harness are actively implemented under `src/trading_app/` and `tools/obs/`; the
Stage-1 frozen specification and its approval record are preserved unchanged.
Milestone 1 remains `BLOCKED`: live acceptance is not authorized, and no API
credentials, private endpoints, orders, or live network requests are included.

## Verified status

Offline verification of this revision — commit `b303ce60be884108655b5d7dcc58db71ac4fac45`,
tree `e556935dd3f917ff871291fdfda7d75279ecee56`, Python 3.12.3, pytest 9.1.1,
in a fresh environment installed from `pyproject.toml`:

- Full suite: **1012 passed, 0 failed, 0 skipped** in 72.7 s with
  `filterwarnings = ["error"]`. Results apply to the identified revision and
  test environment; they do not establish live acceptance.
- Source scan: `grep -rn "NotImplementedError" src/` returns **0 matches** across
  15 files / 1988 lines. The absence of stubs is established by that scan, not
  inferred from the green suite.
- Blocking gates pass at this revision: collection, `tools/check_freeze.py`,
  `tools/validate_matrix.py` (104 acceptance rows, 58 item bindings,
  18 mutation killers), `tools/spec_check.py`, `tools/red_reason_gate.py`, and
  `tools/concurrency_evidence.py` (3 runs plus verification).
- `pip-audit` on that dependency set (2026-10-28 UTC): no known vulnerabilities.
- Traceability audit: `structural=0` defects; **14 unique acceptance rows** lack
  evidence (**15 findings** — `INSTALL-01` is reported twice): `OBS-01..03`,
  `LIVE-01..05`, `CI-01`, `DEP-01/02`, `INSTALL-01`, `EVID-01`, `PY-01`.
  Missing evidence is an evidence gap, not 15 software defects; acceptance stays
  blocked by absent live/CI evidence, not by a test failure.

## Test design

- Independent finality, retry/cooldown, and golden-hash vectors live in
  `tests/fixtures/vectors/`.
- `tests/fixtures/policy.py` is the only test-side reader of `matrix.yaml`;
  production modules must not import the acceptance matrix, and
  `src/trading_app/policy.py` has been removed.
- `src/trading_app/data/finality.py` implements the pure `is_final` and
  `effective_end_ms` contract, including validation errors. Client-level tests
  check end-time clamping and aborting when upstream returns
  `close_time_ms >= B`.
- Deterministic dependencies (`sleep`, `jitter`, `now_ms`, `http_client`) are
  injected through constructors in behavioral tests; tests do not monkeypatch
  global clocks or sleep functions.
- `tests/tools/test_degenerate_double.py` runs client and validator tests
  against degenerate doubles and fails if any of those tests pass.
- `tools/red_reason_gate.py` accepts a red test only when the traceback contains
  a `NotImplementedError` from `src/trading_app/`. In both expected-red modes it
  rejects test-body placeholders, other failures, skips, suite-level
  (collection) errors, and testcase-level setup/teardown errors. CI runs it with
  `--implementation-stage`, which additionally permits passing behavioral tests
  while implementation is active: a property of this stage, not an acceptance
  signal. The default mode requires every pass to be allowlisted; the separate
  `--final-gate` mode requires pytest exit 0, zero failures/skips/errors, no hollow
  tests, and an empty hollow allowlist, and cannot be combined with
  `--implementation-stage`. The behaviour is exercised by
  `tests/tools/test_red_reason_gate.py`,
  `tests/tools/test_red_reason_gate_implementation_stage.py` and
  `tests/tools/test_no_hollow_tests.py` (23 tests) and documented in
  `docs/stage2-test-decisions.md`.

## Observation harness

- `tools/obs/` implements the harness: request pacing, absolute-monotonic
  watchdog deadline, cancellation-safe transport, drift estimator, admission and
  audit, per protocol v0.5 (`docs/obs-protocol.md`, `docs/obs-harness-map.md`).
- `tests/tools/obs/` (7 files) covers pacer, watchdog/transport, estimator,
  harness safety and audit; `tests/observations/` covers the OBS-01/OBS-02/OBS-03
  gates.

## CI and evidence

- Baseline is Python 3.12 with pytest pinned exactly (`pytest==9.1.1`), matching
  CI's version assertion; the pin applies to the `dev` extra only, so downstream
  runtime installs are unaffected. No lockfile exists yet, so other dependencies
  remain range-resolved — full environment reproducibility still requires the
  outstanding `requirements-hashed.txt`.
- Blocking steps: collection, freeze hashes, matrix validation, spec/source
  comparison, red-reason gate, concurrency evidence. `pip-audit` remains
  nonblocking until the final gate.
- CI produces JUnit and traceability artifacts. Required CI/live acceptance
  evidence remains outstanding until that evidence is collected, verified, and
  accepted by the gates — artifact availability is not a satisfied evidence gate.
- Offline tests never call Binance; "live" scenarios are represented
  deterministically with fake public responses.
- Outstanding before acceptance: live/CI JUnit evidence, `requirements-hashed.txt`
  constraints evidence, and finality-lag approval.

## Leftover review scaffolding

`reports/`, `commit-object.txt` and `stage2_tests_only_revision.patch` are
historical evidence of earlier review rounds. They are not inputs to any test or
gate and may be removed in a later cleanup.

## Provenance and review boundary

The public baseline commit is `a88a843f7c79354b193234fc3cdbfad9b661d098`, with
tree `408a6a4263528d846a5277fab9f75f0ff036dd74`. The local source bundle's
original commit identity was `de1bd38e73d7b6cdd0ab2d2bc0c42d105ae470a2`; its
tree matches the public baseline, but that original history is not present in
the public repository. The revised commit message records this provenance gap.
Pushing original bundle history, if desired, is a separate operation on a
separate branch.

Implementation is active on this branch but is not accepted: Milestone 1 remains
**BLOCKED** until the outstanding evidence and approvals above are cleared.