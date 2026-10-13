# Stage-2 tests-only acceptance scaffold (review candidate)

This commit is **not an implementation** and does not authorize production implementation. It preserves the Stage-1 frozen specification, keeps Milestone 1 `BLOCKED`, and adds acceptance tests plus test-gate tooling around explicit `NotImplementedError` production stubs.

## Test design

- Independent finality, retry/cooldown, and golden-hash vectors live in `tests/fixtures/vectors/`.
- `tests/fixtures/policy.py` is the only test-side reader of `matrix.yaml`. Production modules must not import the acceptance matrix; `src/trading_app/policy.py` has been removed.
- `src/trading_app/data/finality.py` defines the pure `is_final` and `effective_end_ms` contract stubs. Client-level tests check end-time clamping and aborting when upstream returns `close_time_ms >= B`.
- Deterministic dependencies (`sleep`, `jitter`, `now_ms`, and `http_client`) are injected through constructors in behavioral tests; tests do not monkeypatch global clocks or sleep functions.
- `tests/tools/test_degenerate_double.py` runs client and validator tests against degenerate doubles and fails if any of those tests pass.
- `tools/red_reason_gate.py` accepts a red test only when the traceback contains a `NotImplementedError` from `src/trading_app/`. Test-body placeholders, other failures, skips, collection errors, and unexpected passes are rejected. The passing tooling/hygiene allowlist is documented in the gate and `docs/stage2-test-decisions.md`.

## CI and evidence

- Python 3.12 and pytest 9.1.1 are the required CI baseline.
- Freeze, matrix validation, and specification/source checks are blocking.
- The expected-red suite exports JUnit and must pass the red-reason gate; JUnit is uploaded as a CI artifact. `pip-audit` remains nonblocking until the final gate.
- Offline tests never call Binance. No credentials, private endpoints, orders, or live requests are included. OBS-01/OBS-02, finality-lag approval, and actual live/CI evidence remain outstanding.

## Provenance and review boundary

The public baseline commit is `a88a843f7c79354b193234fc3cdbfad9b661d098`, with tree `408a6a4263528d846a5277fab9f75f0ff036dd74`. The local source bundle's original commit identity was `de1bd38e73d7b6cdd0ab2d2bc0c42d105ae470a2`; its tree matches the public baseline, but that original history is not present in the public repository. The revised commit message records this provenance gap. Pushing original bundle history, if desired, is a separate operation on a separate branch.

The tests-only candidate is not approved until reviewed. Milestone 1 remains **BLOCKED**, and production implementation remains unauthorized.
