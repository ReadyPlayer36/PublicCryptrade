# Stage-2 acceptance scaffold and observation harness (review candidate)

Branch `impl-obs-harness`, based on commit `b0bc3e36ba2bd72e28eb050424b125c9d3cf2d79`
(tree `99e459664fcfd34a4ce650e5edda98f18b618a4c`). A commit cannot contain its own SHA, so the
SHA of this revision is reported in the submission message, not here. Production code and the
observation harness are actively implemented under `src/trading_app/` and `tools/obs/`; the
Stage-1 frozen specification and its approval record are preserved unchanged.
Milestone 1 remains `BLOCKED`: live acceptance is not authorized, and no API
credentials, private endpoints, orders, or live network requests are included.

## Verified status

Offline verification of this revision — working tree on top of base commit `b0bc3e3`,
Python 3.12.3, in a fresh virtual environment installed from `pyproject.toml`
(`pip install -e ".[dev]"`):

- Full suite: **1239 passed, 0 failed, 0 skipped** in 70.4 s with `filterwarnings = ["error"]`
  (base `b0bc3e3`: 1211 passed; this revision adds 28 tests, all in
  `tests/tools/obs/test_records_snapshot.py`). Results apply to the identified revision and test
  environment; they do not establish live acceptance.
- Gates re-run on this revision: `tools/check_freeze.py` (FREEZE CHECK PASSED),
  `tools/validate_matrix.py` (104 acceptance rows, 58 item bindings, 18 mutation killers) and
  `tools/spec_check.py` (13 passed). Not re-run for this change and therefore not claimed here:
  `tools/red_reason_gate.py`, `tools/concurrency_evidence.py`, `pip-audit`, traceability audit.
- Evidence-bound provenance: `decided_at_ns` and the terminal `timeline_end_ns` are never bare
  scalars. `tools/obs/eventlog.py` is a SHA-256 hash-chained event log bound to a digest of the
  recorded requests. `tools/obs/runstore.py` persists a run (`records.jsonl`, `events.jsonl`,
  `manifest.json`, each written once) and provides the manifest loader: `load_manifest` /
  `load_run` authenticate `manifest.json` against a SHA-256 **pinned out of band**, parse it
  strictly (no duplicate or extra keys, exact types) and verify its self-digest, and every file's
  digest must match the manifest. `audit_pace` no longer has a head-digest parameter: it takes
  an `AuthenticatedManifest`, constructible only by the loader, and `audit_run(run_dir,
  pinned_manifest_sha256=...)` audits a persisted run end to end. A missing, malformed, altered
  or unpinned manifest, or a substituted log or records file, is an audit failure (check a).
  Limit: this is tamper-evident, not tamper-proof; it is exactly as independent as the pinned
  digest, and no key material is used. Fix 7: `AuthenticatedManifest` provenance is by identity
  (`is_loader_issued`, a weak registry filled only by `load_manifest`; the class uses `eq=False`
  so a copy with equal values is not a member), so `dataclasses.replace()`, `object.__new__`,
  `copy`, subclasses and look-alikes are rejected before any attribute is read; persisted records
  and events are validated strictly (`_req_int/_req_range/_req_str/_req_hex64/_req_headers`: no
  coercion, booleans, floats and wrong shapes rejected as `ManifestError`).
  Fix 7b: loader-issued manifests are also sealed off-instance (`_SEALS`, a weak-key dictionary
  holding a SHA-256 over the canonical values of the seven authenticated fields, recorded at
  issue). `manifest_trust_error` rejects in-place mutation or deletion of any of those fields
  (e.g. `object.__setattr__`) before the audit reads the manifest. Residual limit: code that can
  write the module-level registries (`_ISSUED`, `_SEALS`) can still forge trust; this is
  tamper-evidence inside an honest process, not a sandbox.
  Fix 8: no time-of-check/time-of-use gap. `validate_and_snapshot_manifest` reads the seven
  authenticated fields once, recomputes the seal from those very values, and returns an immutable
  `ManifestSnapshot`; `audit_pace` (and `audit_run`) decide only on the snapshot, never on the
  mutable instance, and freeze a list event log into a tuple.
  Fix 9: `audit_pace` freezes its caller-owned inputs once at entry (`records` into a tuple of
  frozen `RequestRecord`s; `skips` and `boundary_skips` into dicts; `expected_boundaries` into a
  tuple), and the digest check, event-log binding, decision matching and every traversal read
  only those frozen copies, so a list mutated during the audit cannot change its outcome. See `docs/obs-harness-map.md`, "Sixth remediation round".
- Source scan (previous revision, not re-run here): `grep -rn "NotImplementedError" src/`
  returned 0 matches; this change touches no file under `src/`.
- Traceability: not re-run for this change. Acceptance remains blocked by absent live/CI
  evidence (OBS-01..03, LIVE-01..05, CI-01, DEP-01/02, INSTALL-01, EVID-01, PY-01), which is an
  evidence gap, not a test failure.

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