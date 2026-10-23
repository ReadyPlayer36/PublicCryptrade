# Stage D3 requirement map (CLI, strict-end, stored-data verification)

Implementer-produced evidence; the independent reviewer is asked to confirm each row. Public data only; no credentials, orders or private endpoints.

| ID | Frozen requirement | Bound test(s) | What it proves |
|---|---|---|---|
| CLI-01 | Thin script succeeds end to end against the mocked public client. | `tests/integration/test_cli.py::test_download_script_with_mocked_public_client`, `::test_script_wrapper_is_thin_and_runnable` (HYGIENE-01) | 12 candles stored, exact two-line output, only `/api/v3/time` then `/api/v3/klines` on the primary host, rerun inserts 0. |
| CLI-02 | Documented exit codes, clean errors, no tracebacks, `--strict-end`. | `test_cli_exit_codes_and_clean_expected_errors`, `test_strict_end_fails_without_storing_and_default_clamps`, `test_verify_mode_exit_codes_and_read_only`, `test_invalid_iso_datetime_is_a_clean_usage_error`, `test_service_rejects_non_boolean_strict_end` | Exit 0 ok / 1 operational / 2 usage-config / 3 verify found problems / 4 strict-end / 70 internal. Every failure is ONE fixed-vocabulary line (built by `safe_error_text`, never from exception text): an input value, a response body and an internal exception message are proven not to leak. Default clamps and records requested vs effective end; `--strict-end` fails with exit 4, stores nothing and writes a failure audit row. |
| VERIFY-01/02 | Decimal/string-safe comparisons; never CAST AS REAL. | `tests/unit/test_verification_sql.py::test_decimal_string_safe_comparisons`, `::test_no_cast_as_real` | No verification SQL contains CAST / REAL / FLOAT, no `float()` in the module, decimal columns never appear in WHERE/HAVING/ON; a 1e-20 difference that float cannot see is caught. |
| VERIFY-03 / M1-15 | Count, continuity, OHLC validity, invalid volume, no silent repair. | `tests/integration/test_sqlite_verification.py` (8 tests) | Per-series counts; SERIES_GAP / MISALIGNED_OPEN / DUPLICATE_CANDLE; INVALID_OHLC, NONPOSITIVE_PRICE, NEGATIVE_VOLUME, BAD_DECIMAL_TEXT (NaN/Infinity/garbage); series never mixed; read-only (`query_only` ON before the first SELECT, OFF afterwards, no write statements); file bytes unchanged. |

## Decisions
- `--verify` is a mode of the same CLI (no download options allowed with it); verification lives in `trading_app/data/verification.py`.
- `--strict-end` is checked after the fetch and BEFORE any write; the default is unchanged (clamp).
- Exit 70 is for unexpected bugs only; it still prints no traceback and no message text.

## Honest notes
- Duplicates cannot occur in a healthy database (unique constraint); they are tested on a deliberately damaged table without the constraint.
- A first connection switches the file to WAL mode (journal header change, not a data write); the byte-identity test accounts for this.
- Not covered here: live evidence (LIVE-04 future-end run), OBS-01/OBS-02, lag approval. Milestone 1 remains BLOCKED on those and on the final gate.

## Status of the mutation evidence (reviewer condition)
- The 13-mutation run recorded for Stage D3 (`mutation-log.txt`, produced on commit `ef9fe11`) is **supplementary code-level validation only**. It was produced by an ad-hoc script that mutates the new D3 code (`cli.py`, `service.py` strict-end, `verification.py`) and checks that the D3 test files fail.
- It is **not** the frozen mutation gate. The frozen 16-required-mutant matrix run (`tools/run_mutations.py`, each mutant with its bound killer test) is **reserved for the final release gate** and is not claimed, replaced or satisfied by this run.
- Nothing in Stage D3 changes the Milestone 1 status: Milestone 1 remains BLOCKED.
