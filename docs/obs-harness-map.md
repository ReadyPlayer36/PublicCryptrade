OBS harness building blocks: requirement map (protocol v0.5)
Scope of this commit (as authorized after the v0.5 sign-off): the offline-testable pieces of the OBS-01/OBS-02 harness. NOT included, and not runnable: a session runner, the OBS-01 probe runner, the pre-registration step, the evidence writer, the analysis function (stable-time and lag formula) or any --live entry point. No live request was made. Milestone 1 remains BLOCKED.
New code lives in tools/obs/ (outside src/trading_app/, not imported by production code, standard library only). Tests: tests/tools/obs/, doubles tests/fixtures/obs_fakes.py, golden vectors tests/fixtures/vectors/obs_estimator_vectors.json with the independent generator generate_obs_vectors.py (it imports nothing from the harness; a test regenerates the vectors and compares).
Protocol item
Module
Tests
PACE-1, 2, 3, 4, 6 completion-aware single pacer, rolling caps, no early start, no catch-up, abort after 3 no-response requests
pacer.py (Pacer, release_ns, window_count)
test_pacer.py
PACE-5 audit (a)-(g), OBS-01 profile, open-left/closed-right windows
audit.py
test_audit.py (GV-8)
PACE-7 admission (strict inequality, only theta_lo decides)
admission.py
test_admission.py (GV-5)
PACE-8 strict 17 s deadline anchored at the pacer's start_ns, socket-shutdown watchdog, shared cancellation state; 18 s audit backstop
watchdog.py, transport.py, pacer.py, audit.py check (e)
test_watchdog_transport.py (GV-9, DNS-stall, loopback), test_pacer.py
5.2 estimator, v0.5 interval [s-b-delta(t-a), s+1ms-a+delta(t-a)], deadline D(X)=X-theta_lo, fixed point
estimator.py
test_estimator.py (GV-1 to GV-7, containment, 123.4 ms edge)
5.3 SYNC adequacy (w <= W_max, empty intersection, 60 s fallback window)
estimator.py
test_estimator.py (GV-4, fallback)
Allow-list safety (host, two paths, exact klines parameters, GET only, no redirects, no proxies, no credentials)
specs.py, transport.py
test_pacer.py, test_watchdog_transport.py, test_harness_safety.py
Remediation of the six re-audit findings (this revision)
#
Finding
Change
Regression tests
1
Pacer serialization
Pacer.execute takes a non-blocking single-flight lock; a call made while another is in flight (other thread, or re-entrant from inside the transport) raises ConcurrentExecution and changes nothing
test_a_concurrent_execute_is_rejected_and_changes_nothing, test_a_reentrant_execute_from_inside_the_transport_is_rejected, test_many_threads_never_overlap_inside_the_transport
2
Non-200 abort
Any status other than 200 appends the record, aborts the pacer (HTTP-<status>), disables the transport and raises NonOkResponse; the transport also disables itself on any non-200, so bypassing the pacer is refused (TransportDisabled)
test_every_non_200_response_aborts_the_pacer_and_disables_the_transport (11 statuses), test_any_non_200_response_permanently_disables_the_transport, test_a_real_non_200_over_a_socket_stops_all_egress
3
DNS-safe cancellation
CancellationState (atomic begin_send/cancel) is checked after connection creation, after connection setup and immediately before the request is written; the watchdog marks it cancelled at the deadline; a worker that wakes later can never connect or send; a cancellation that does not complete disables the transport permanently (CANCEL_FAILED) and the pacer records it, aborts and raises CancellationFailed
test_stalled_dns_never_sends_after_the_cancellation_and_disables_the_transport, test_dns_that_returns_inside_the_allowance_is_a_clean_cancellation_without_a_send, test_a_worker_released_after_cancellation_never_connects_or_sends, test_begin_send_and_cancel_are_atomic_under_races, test_a_stalled_connect_inside_the_pacer_is_recorded_as_a_failed_cancellation_and_ends_the_run
4
Start-anchored deadline
The pacer passes deadline_at_ns = start_ns + 17 s (absolute monotonic); the transport computes the remaining time from the same clock, so time spent before the transport is reached counts, and an already-passed deadline sends nothing
test_the_deadline_passed_to_the_transport_is_start_ns_plus_17_seconds, test_the_deadline_is_anchored_at_the_recorded_start_even_after_a_late_wake, test_time_spent_before_the_transport_is_reached_counts_against_the_deadline, test_a_deadline_that_has_already_passed_sends_nothing
5
Hardened audit
(a) the records themselves must end at the first non-200, third consecutive failure or failed cancellation, and the recorded abort position must match; (f) unknown group names, roles and kinds, role/path mismatches, inconsistent metadata, missing resync, and every skipped group must be VERIFIED (a consistent MISSED-WINDOW AdmissionDecision with no later group sent, a failed last request, or an abort at the end; expected_boundaries/boundary_skips verify whole boundaries); (g) jsonl_count, wrapper_count and manifest_count are all required and must be integers equal to the record count
test_audit.py (50 tests)
6
Regression tests
listed above; 557 tests in tests/tools/obs

Third remediation round (non-blocking cancellation, absolute watchdog, evidence-tied decisions)
#
Finding
Change
Regression tests
1
cancel() must never be starved by an active write
The cancellation lock is gone. CancellationState.cancel() is lock-free (flag first), then the transport shuts the socket down: a blocked read or write wakes at once, and a write attempted afterwards fails in the kernel, so nothing is transmitted after cancel() returns. Ordering relied on: cancel sets the flag then reads the socket; the worker obtains its socket then reads the flag; auto_open = 0 and the conn.sock is None check prevent any reconnect.
test_cancel_is_never_blocked_by_a_write_in_progress, test_a_blocked_write_is_interrupted_at_the_deadline_by_a_socket_shutdown, test_cancel_proceeds_while_the_worker_is_inside_the_pre_write_check_and_nothing_is_transmitted (the previous lock design would deadlock there)
2
Watchdog against the absolute deadline
run_with_deadline(fn, cancel, deadline_at_ns=..., clock=...) re-reads the monotonic clock on every wait (join(remaining) recomputed each loop), so thread start-up latency and spurious early wake-ups cannot stretch or shorten the deadline; the cancellation allowance is measured from the moment the cancel was issued
test_thread_start_up_latency_is_inside_the_absolute_deadline_not_added_to_it, test_the_watchdog_fires_at_the_absolute_deadline_and_not_before (0.1/0.2/0.3 s, fires within 50 ms), test_spurious_early_join_returns_never_fire_the_cancel_early, test_each_wait_is_recomputed_from_the_clock_so_timeouts_shrink_as_time_passes, test_the_cancellation_allowance_is_measured_from_the_moment_the_cancel_was_issued
3
Evidence-tied skip validation
validate_decision_evidence rebuilds the estimator input from the RECORDS (every /api/v3/time request with HTTP 200 that completed at or before m_e_ns, serverTime parsed from its recorded body; unusable body = failure), runs the approved OffsetEstimator (exact rationals, drift widening from the request start, 600 s retention by completion time, 60 s fallback) and requires theta_lo and theta_hi to EQUAL the decision's claims; it also brackets m_e_ns between the earliest start the pacer rules allow after the preceding request (completion, spacing, rolling caps recomputed from the records) and the start of the next recorded request. Behavior change: ONE verified MISSED-WINDOW decision for the first skipped group now covers the rest of that boundary (the harness evaluates admission once and then sends nothing more); later groups need no evidence of their own.
test_a_self_consistent_decision_with_fabricated_theta_is_rejected, test_each_theta_bound_is_checked_separately, test_a_decision_computed_from_a_subset_of_the_recorded_samples_is_rejected, test_a_decision_that_uses_a_sample_which_was_never_recorded_is_rejected, test_altered_recorded_responses_no_longer_support_the_decision, test_a_time_response_without_a_usable_server_time_fails_closed (9 bodies), test_the_retention_rule_is_applied_by_the_audit_not_taken_from_the_decision, test_the_fallback_window_rule_of_the_estimator_is_reproduced_by_the_audit, test_samples_after_m_e_do_not_influence_the_audit, bracket tests, and the honest-decision tests for all five groups
Note on independence: the audit uses the same OffsetEstimator implementation as the harness (one source of truth for the approved rules); its inputs, however, come only from the records, never from the decision, and the golden vectors GV-1 to GV-7 pin the estimator itself.
Fourth remediation round (send-boundary race proof, bounded terminal skips)
#
Finding
Change
Regression tests
1
Deterministic proof that nothing is transmitted after a cancellation that lands between the final checks and conn.request()
Tests pause the worker after every transport check has passed and before anything is written (at the statement right before conn.request(), and at the entry of conn.request()), let the watchdog cancel while it is paused, and release the worker only after cancel() has COMPLETED (events decide the order, never sleeps). A loopback byte sink records what reaches the server. The cancellation's two mechanisms are disabled one at a time to separate EXECUTION PREVENTION from CLEANUP: production (both) transmits 0 bytes and request() is refused by the closed connection (NotConnected, no reconnect); socket shutdown alone (cleanup ignored) lets the write be attempted and the kernel refuses it (sendall error, 0 bytes); connection close alone refuses it before any send; with BOTH disabled the sink receives the request (control: the detector sees transmissions). A kernel-level test shows shutdown() alone prevents any send.
test_cancellation_between_the_final_checks_and_conn_request_transmits_not_one_byte (2 pause points), test_the_socket_shutdown_alone_prevents_the_write_when_the_cleanup_is_disabled (2), test_closing_the_connection_alone_prevents_the_write_when_the_shutdown_is_disabled, test_control_with_both_mechanisms_disabled_the_request_is_transmitted (2), test_control_without_any_cancellation_the_pause_alone_changes_nothing, test_shutdown_alone_prevents_any_send_at_the_kernel_level, test_fake_transport_level_ordering_of_the_race_is_deterministic
2
Upper bound on m_e_ns for terminal skips
AdmissionDecision now records decided_at_ns (the clock read of the decision; required, a decision without it is refused). The audit binds the decision time between the completion of the preceding request and an audited upper bound: the start of the next recorded request, or, for a terminal skip, the new timeline_end_ns argument (audited run end, must be an integer not before the last record); a terminal skip without that bound is rejected as unbounded. m_e_ns must equal max(decided_at_ns, earliest pacer start recomputed from the records) exactly, so an inflated or deflated m_e_ns cannot pass.
test_a_terminal_skip_without_an_audited_timeline_bound_is_rejected, test_the_decision_timestamp_must_not_exceed_the_audited_timeline_end, test_an_inflated_decision_time_cannot_hide_behind_a_consistent_theta, test_m_e_is_tied_exactly_to_the_decision_time_and_the_pacer_rules, test_a_non_terminal_skip_is_bounded_by_the_next_recorded_request_not_by_the_timeline, test_the_recorded_decision_timestamp_must_be_a_valid_integer_not_after_m_e, test_a_decision_without_a_recorded_timestamp_cannot_be_used_as_skip_evidence, admission tests
Runner requirement: when a group is skipped the runner must call decide_admission(..., decided_at_ns=<clock read>) and store the run's final monotonic instant as timeline_end_ns in the manifest.
Mutation check of the first revision: 61 mutants on tools/obs (own script, NOT the frozen 16-mutant matrix run), all killed; three survivors in the first pass were closed by tightening tests.
Second remediation round (three targeted findings)
#
Finding
Change
Regression tests
1
Atomic cancellation and send guard
CancellationState.guarded_send(allowed, send) runs the cancellation check, the absolute-deadline check and the request write (conn.request) inside ONE critical section shared with cancel(); cancel() therefore waits for an in-progress write (bounded by SEND_TIMEOUT_S = 0.25 s) and can never fall between the check and the write. conn.auto_open = 0 is set right after connect() so http.client can never silently reconnect a closed connection, and the worker reads conn.sock once and refuses to write if it is gone
test_the_write_is_inside_the_critical_section_so_cancel_cannot_interleave, test_guarded_send_and_cancel_are_atomic_under_races, test_a_cancellation_during_the_write_waits_for_the_write_and_never_reconnects, test_a_connection_closed_between_setup_and_the_write_is_never_written_or_reopened, test_real_http_client_never_reconnects_after_a_cancellation_close, test_a_normal_request_disables_implicit_reconnection_and_uses_short_write_timeout
2
Absolute deadline inside the worker
the worker re-reads the monotonic clock against the absolute deadline (start_ns + 17 s) at three points: on entry (thread start-up latency), before connection setup, and inside the critical section immediately before the write (>= the deadline means no send); any of them cancels the state for good
test_worker_started_after_the_absolute_deadline_does_nothing, test_deadline_passing_before_connection_setup_creates_but_never_connects, test_deadline_passing_during_setup_is_caught_inside_the_critical_section_before_the_write, test_the_deadline_boundary_is_inclusive_for_cancellation, test_pacer_passes_the_start_anchored_deadline_down_to_the_worker_checks
3
Rigorous skipped-group admission validation
validate_missed_window_decision recomputes everything it can from the audit's own inputs: exact class and exact types; lower_server_ns == m_e_ns + theta_lo and upper_server_ns == m_e_ns + theta_hi exactly; theta_lo <= theta_hi; limit_ns == (T + o + tol) x 1e6 from the boundary and the group's own window (GROUP_WINDOWS_MS); the strict inequality lower_server_ns > limit_ns (equality is not a skip); m_e_ns a non-negative integer not earlier than the completion of the preceding request of that boundary; skip evidence for unknown boundaries or groups is refused
test_audit.py: test_the_strict_skip_inequality_equality_is_not_a_skip, test_derived_server_bounds_must_equal_m_e_plus_theta_exactly, test_limit_must_be_recomputed_from_the_boundary_and_the_group_window, test_non_exact_or_mistyped_numbers_are_rejected, test_m_e_must_not_precede_the_completion_of_the_preceding_request, test_audit_rejects_every_malformed_decision_and_accepts_the_consistent_one, test_a_decision_produced_by_the_real_admission_function_passes_the_audit and others
Residual, for the runner stage: the audit now recomputes theta from the recorded /time bodies (third round, below); the runner must therefore store each /time response body in its request record (the pacer already does) and pass skips as {(boundary_ms, first_skipped_group): decision}.
Decisions and findings for the reviewer
PACE-8 mechanism (finding). An experiment (loopback only) showed that calling httpx.Client.close() from another thread does NOT interrupt a blocked read, whereas socket.shutdown(SHUT_RDWR) does. The transport is therefore built on http.client and the watchdog shuts the socket down and then closes the connection. The protocol sentence "closes its connection" is satisfied; the mechanism is the shutdown. The pacer takes end_ns after the cancellation has finished.
Cancellation limits. The connect phase has its own 5 s socket timeout (TLS handshake included). DNS resolution cannot be interrupted, so it is made harmless instead: nothing is ever sent after a cancellation (shared state, section above), and a cancellation that does not finish within the 1 s allowance disables the transport and ends the run (INCIDENT-CANCEL). Reviewer: accept?
Outcome codes without an HTTP response: DEADLINE (watchdog), TIMEOUT (socket timeout), CONNECT_ERROR (anything else), CANCEL_FAILED (a cancellation that did not complete; always the last record, 17 s to 19 s). Check (e) requires a DEADLINE record to last between 17 s and 18 s.
Group audit (f) harness decisions (the protocol did not spell these out): a group whose last request failed (no 200) may be a PREFIX of the defined role order; a resync group has 3 to 7 /time calls (3 plus up to 4 extra), or fewer only when its last call failed; skipped groups inside a boundary are allowed (MISSED-WINDOW), but order must never go backwards.
Arithmetic. Decisions use exact rational arithmetic (fractions.Fraction); exported intervals are rounded outward to whole nanoseconds; deadlines are rounded up. The estimator retains samples with b_j >= t - 600 s evaluated at the decision time, and the deadline wake loop re-evaluates the retained set at each wake.
The pacer starts at max(earliest, target) and never reorders; a wake that is late is recorded as late and judged only by V1 (not part of this commit).
The default HttpTransport accepts only https://data-api.binance.vision; a loopback http base URL exists solely for offline tests.
Evidence summary (this commit, Python 3.12.3)
See the evidence files delivered with this commit: full-suite JUnit and console output, coverage of tools/obs, the mutation log (29 mutants on the new code, own script, NOT the frozen 16-mutant matrix run), and the repository gate outputs.

Fifth remediation round (evidence-bound admission provenance)
#
Finding
Change
Regression tests
1
decided_at_ns and the terminal timeline_end_ns were bare scalars; a fabricated pair that was arithmetically consistent would pass
New tools/obs/eventlog.py: an append-only log (EventLogWriter) of DECISION and TIMELINE_END events. Each entry carries records_before and records_digest (SHA-256 of exactly those request records, bodies hashed) and prev_hash / entry_hash (SHA-256 of canonical JSON), so editing, dropping, inserting or reordering an event breaks the chain, and a log from another run fails the record binding. verify_event_log(events, manifest_head_digest, records) rebuilds the chain, matches the manifest head, and returns a VerifiedEventLog that cannot be constructed elsewhere. audit_pace(event_log=, event_log_head=) replaces the timeline_end_ns scalar (passing it is now a TypeError); validate_decision_evidence requires the verified log and the (boundary, group): decided_at_ns and m_e_ns must equal the ONE recorded DECISION event, logged right after the preceding request (records_before == previous seq), and the terminal bound is the log's TIMELINE_END event (which must cover every record). A missing log, event, terminal event, or any mismatch fails closed (check a or f).
tests/tools/obs/test_provenance.py: test_audit_pace_has_no_bare_timeline_end_parameter, test_a_consistent_decision_without_any_log_is_rejected, test_a_consistent_decision_absent_from_a_valid_log_is_rejected, test_a_fabricated_but_arithmetically_consistent_decision_time_is_rejected, test_a_fabricated_timeline_end_is_rejected_even_when_consistent_with_the_decision, test_a_tampered_field_is_rejected, test_a_tampered_entry_rehashed_by_the_forger_breaks_the_chain_and_the_manifest_digest, test_dropping_inserting_or_reordering_events_is_rejected, test_a_truncated_log_that_loses_its_terminal_event_is_rejected, test_a_terminal_skip_without_a_timeline_end_event_is_unbounded_and_rejected, test_a_decision_event_with_a_different_m_e_or_decision_time_is_rejected, test_a_decision_event_logged_for_another_group_or_boundary_does_not_bind_this_decision, test_a_log_from_a_different_run_is_rejected_by_the_record_binding, test_the_chain_hash_is_the_documented_sha256_of_canonical_json, and others
Supersedes item 2 of the fourth round: the "new timeline_end_ns argument" no longer exists; the bound comes from the verified TIMELINE_END event. Tests that exercised the scalar (test_audit.py) now go through an honest recorder in tests/fixtures/obs_fakes.py (recorded_events / verified_log_for); audit_all(timeline_end_ns=...) is a test convenience that logs the value, never a scalar passed to the audit.
Runner requirement (replaces the fourth-round note): when a group is skipped the runner calls decide_admission(..., decided_at_ns=<clock read>) and immediately EventLogWriter.append_decision(...) with the records completed so far; at the end of the run it appends TIMELINE_END, and stores writer.events and writer.head_digest in the manifest. The head digest must be recorded where the operator cannot rewrite it afterwards (limit: whoever controls records, log and head together can forge a consistent triple).
Mutation check (own spot check, not the frozen 16-mutant matrix): disabling the decided_at_ns equality check, the missing-event check, or the head-digest comparison makes 4 tests fail each; all were restored.

Sixth remediation round (persisted run manifest and independent authentication)
#
Finding
Change
Regression tests
1
event_log_head reached audit_pace as an unverified scalar, so a forger who rewrote the log could supply a matching head
New tools/obs/runstore.py. write_run persists records.jsonl, events.jsonl and manifest.json once (exclusive create; an inconsistent log is refused) and returns the SHA-256 of manifest.json, to be PINNED out of band. load_manifest(path, pinned_sha256=) requires a well-formed pin, matches the file bytes to it, parses strictly (no duplicate keys, exact key set and types, format obs-run-manifest/1) and verifies the manifest self-digest; it returns an AuthenticatedManifest (record and event counts, file digests, records digest, event_log_head), constructible only by the loader. load_run also matches both jsonl files to the manifest digests and the counts. audit_pace(event_log=, manifest=) replaces event_log_head: a missing or non-authenticated manifest, a record count or digest that differs from the audited records, or an event count that differs all fail check (a); the chain head is taken from the manifest only. audit_run(run_dir, pinned_manifest_sha256=, wrapper_count=) loads and audits a persisted run; load failures become check (a) failures, not exceptions. The jsonl and manifest counts come from the persisted files; the wrapper count is supplied by the caller.
tests/tools/obs/test_run_manifest_e2e.py (31 tests): test_a_complete_run_round_trips_through_disk_and_passes_the_audit, test_the_head_digest_comes_only_from_the_authenticated_manifest, test_a_missing_manifest_or_artifact_fails_closed, test_a_missing_or_malformed_pinned_digest_fails_closed, test_a_wrong_pin_fails_closed, test_a_malformed_manifest_is_rejected_even_with_a_matching_pin (7 shapes), test_editing_the_manifest_without_the_pin_is_detected, test_editing_a_manifest_field_breaks_the_self_digest_even_if_the_forger_re_pins, test_a_fully_re_digested_forged_manifest_is_rejected_by_the_original_pin, test_altering_the_head_digest_to_fit_a_substituted_log_is_rejected, test_any_byte_change_in_a_persisted_file_is_detected (2 files), test_a_records_file_from_another_run_is_rejected, test_a_truncated_jsonl_file_is_rejected_even_when_re_pinned, test_dropping_the_terminal_event_from_a_persisted_run_is_rejected, test_a_persisted_run_without_a_recorded_decision_cannot_justify_a_skip, test_a_persisted_run_without_a_timeline_end_cannot_bound_a_terminal_skip
Test convenience: tests/fixtures/obs_fakes.py audit_all(event_log_head=...) persists that head as a manifest and loads it through the real loader; it never reaches the audit as a scalar.
Not covered (stated): AdmissionDecision objects (skips) are still passed by the caller and are checked against the logged DECISION events, not persisted; the pin's own storage (where it is recorded and who can rewrite it) is an operational control outside this code. Mutation spot check (own, not the frozen 16-mutant run): disabling the pin match, the records-file digest, the events-file digest, the manifest self-digest or the isinstance check on the manifest makes 1 to 7 tests fail each; all were restored.

Seventh remediation round (manifest trust boundary and strict persisted types)
#
Finding
Change
Regression tests
1
isinstance() and the private token on AuthenticatedManifest could be bypassed: dataclasses.replace() re-passes every init field, and object.__new__ skips __init__
tools/obs/runstore.py: a process-level weak registry _ISSUED (weakref.WeakSet) that load_manifest alone fills, and is_loader_issued(candidate), true only for the exact instances minted by the loader (type must be exactly AuthenticatedManifest; non-weakref-able candidates are False; no attribute is read). The dataclass is now frozen with eq=False so instances hash and compare by identity: with value equality a replace() copy would hash and compare equal to the genuine instance and the WeakSet lookup would accept it. tools/obs/audit.py uses is_loader_issued(manifest) before touching the manifest. Note: the registry lives in runstore.py (there is no tools/obs/manifest.py in the repository).
tests/tools/obs/test_manifest_trust_and_types.py: test_forged_or_copied_manifests_are_not_loader_issued_and_the_audit_rejects_them (replace, replace with change, object.__new__, subclass, copy.copy, copy.deepcopy, look-alike namespace, dict, None, int), test_a_forged_manifest_carrying_a_matching_head_is_rejected_even_though_every_field_is_equal, test_the_check_happens_before_any_attribute_access
2
load_run coerced raw JSON (str() on headers and fields) and passed unvalidated numbers, so booleans and floats could enter RequestRecord and LogEvent
tools/obs/runstore.py: _req_int (rejects bool and non-int), _req_range, _req_str, _req_hex64, _req_headers and _req_fields (exact two-element list shapes, string names and values, int or string field values), with per-field ranges (seq, timestamps, boundary and counts in 0..2^63-1, status 100..599). load_run builds every record and event through them; any unforeseen ValueError, TypeError, KeyError, AttributeError or OverflowError is normalised to ManifestError, which audit_run reports as a check (a) failure.
tests/tools/obs/test_manifest_trust_and_types.py: 35 wrong-type or out-of-range record cases and 23 event cases (each re-pinned so only the validators can object), test_valid_artifacts_load_with_exact_types_and_no_coercion, test_headers_with_content_survive_a_round_trip_exactly
Mutation spot check (own, not the frozen 16-mutant run): reverting the audit to isinstance, switching the dataclass back to value equality, removing the registry add, dropping the bool rejection, or coercing headers with str() makes 7, 5, 81, 6 and 3 tests fail respectively; all restored.

Seventh-b remediation round (off-instance seal against in-place mutation)
#
Finding
Change
Regression tests
1
A genuine, loader-issued AuthenticatedManifest could be mutated in place with object.__setattr__, keeping its registry identity while changing event_log_head and the counts
tools/obs/runstore.py: _TRUSTED_FIELDS (record_count, records_file_sha256, records_digest, event_count, events_file_sha256, event_log_head, manifest_sha256) and _SEALS, a weak-key dictionary OUTSIDE the instance holding SHA-256 over the canonical current values of those fields, written by _register() at issue (load_manifest). manifest_trust_error(candidate) returns the not-supplied message for a wrong type or a non-issued instance (no attribute is read), the mutated-in-place message when the stored seal differs from the recomputed one (a missing attribute or a non-encodable value counts as mutation), else None; is_loader_issued is manifest_trust_error(...) is None. tools/obs/audit.py audit_pace calls manifest_trust_error first and raises EventLogError with its text, before any manifest attribute is read.
tests/tools/obs/test_manifest_trust_and_types.py: test_object_setattr_on_any_authenticated_field_is_detected (7 fields), test_replacing_a_trusted_field_with_any_other_type_is_detected, test_deleting_a_trusted_field_in_place_is_detected, test_a_mutated_manifest_cannot_authenticate_a_fabricated_event_log, test_the_gate_runs_before_any_manifest_attribute_is_read, test_a_genuine_manifest_has_no_trust_error_and_its_seal_lives_off_the_instance, test_forgeries_still_report_the_not_supplied_reason, test_restoring_the_original_value_leaves_the_manifest_unchanged_and_trusted
Stated limits: the seal covers VALUES, so restoring a field to its original value leaves no net change (pinned by a test); the registries are module-level, so code that can write _ISSUED or _SEALS directly can still forge trust. Mutation spot check (own, not the frozen 16-mutant run): disabling the seal comparison, storing a wrong seal, dropping event_log_head from the sealed fields, or removing the audit gate makes 16, 84, 6 and 27 tests fail; all restored.

Eighth remediation round (immutable validated snapshot; no TOCTOU)
#
Finding
Change
Regression tests
1
audit_pace validated the manifest and then re-read attributes from the mutable instance, so it could be changed between check and use
tools/obs/runstore.py: ManifestSnapshot (frozen dataclass of the seven authenticated fields) and validate_and_snapshot_manifest(candidate), which checks exact type, WeakSet identity and the off-instance seal and returns the snapshot, raising ManifestTrustError (a ManifestError) otherwise. Each field is read exactly once (_read_trusted_values, which also requires exact int/str types); the seal is recomputed from those same values and the snapshot is built from them, so what was checked is what is returned. manifest_trust_error and is_loader_issued are wrappers. tools/obs/audit.py audit_pace uses only snapshot.record_count, records_digest, event_count and event_log_head, and converts a list event log to a tuple; audit_run takes manifest_count from a snapshot.
tests/tools/obs/test_manifest_trust_and_types.py: test_the_audit_uses_only_the_snapshot_even_if_the_instance_changes_after_validation (all authenticated fields are changed right after the check; the audit still passes), test_tampering_after_validation_cannot_rescue_a_fabricated_log_either, test_the_snapshot_is_an_immutable_copy_of_exactly_the_seven_authenticated_fields, test_a_snapshot_cannot_be_passed_off_as_an_authenticated_manifest, test_validation_raises_for_forgeries_and_for_mutation, test_a_wrongly_typed_field_is_never_snapshotted, test_audit_run_reads_the_manifest_counts_from_the_snapshot_and_rejects_a_mutated_instance, test_audit_run_fails_closed_when_the_instance_changes_between_its_two_validations
Stated limits: audit_run validates twice (its own snapshot for manifest_count, then audit_pace), so a change between the two fails closed rather than being tolerated. The records sequence and the event log's LogEvent objects are not snapshotted (LogEvent is frozen; the list is frozen into a tuple). Mutation spot check (own, not the frozen 16-mutant run): reading event_log_head, record_count/records_digest or event_count from the raw manifest instead of the snapshot, or dropping the seal comparison, makes 2, 1, 1 and 14 tests fail; replacing audit_run's manifest_count with a raw read is behaviourally equivalent (audit_pace re-validates and fails closed), so no test can distinguish it.

Ninth remediation round (records snapshot at the audit boundary)
#
Finding
Change
Regression tests
1
audit_pace took the records as a mutable sequence: a list changed between the digest check and later decisions could change the audit outcome
tools/obs/audit.py audit_pace: first statements freeze the inputs: records = tuple(records) (RequestRecord is a frozen dataclass of immutable fields, bytes body and tuple headers, so the tuple is a stable snapshot), skips = dict(skips), boundary_skips = dict(boundary_skips), expected_boundaries = tuple(expected_boundaries). Every later use, including records_digest(records), verify_event_log, the integrity and pacing checks, _audit_groups and validate_decision_evidence, reads these frozen objects. A generator of records is consumed exactly once.
tests/tools/obs/test_records_snapshot.py (28 tests): test_a_list_mutated_after_the_audit_began_cannot_change_the_outcome (4 hook points inside the audit, namely after the manifest snapshot, after the digest check, after the event-log verification and after the abort derivation, times 6 mutations: clear, append, reverse, delete first, tamper last record, replace with empty; the outcome and failures equal the unmutated baseline), test_the_snapshot_preserves_a_failing_verdict_too, test_mutating_the_list_before_the_audit_is_still_caught_by_the_digest, test_skips_and_boundary_mappings_are_frozen_at_entry_too, test_a_generator_of_records_is_consumed_exactly_once
Stated limits: the mutation is simulated deterministically by hooks that run inside the audit (no real threads are used, so a genuine data race is not exercised); records are protected by immutability of their fields, so a caller who mutates a record's contents through object.__setattr__ before the call is caught only by the manifest digest. Mutation spot check (own, not the frozen 16-mutant run): removing the records snapshot makes 26 tests fail; removing the skips snapshot makes 1 fail; both restored.

Tenth remediation round (fail-closed snapshot construction)
#
Finding
Change
Regression tests
1
The input snapshots (tuple(records), dict(skips), ...) were built outside any error handling, so a container that failed while being copied could raise out of audit_pace
tools/obs/audit.py audit_pace: all snapshot conversions (records, skips, expected_boundaries, boundary_skips and a list/tuple event_log) run in one try block that catches Exception and returns AuditResult with a single check (a) failure naming the input and the exception ("input snapshot failed for <input>: <type>: <message>"). Exception is used deliberately because the copy executes arbitrary caller code (iterators, __iter__, mapping access); KeyboardInterrupt and SystemExit are not caught. The event-log conversion moved from the manifest block into this boundary, so a failing list subclass is handled too.
tests/tools/obs/test_snapshot_failure.py (27 tests): records failing during the copy (6 exception types), skips and boundary_skips mappings failing during key iteration (6 types each), a mapping entry vanishing between listing and reading, expected_boundaries and event_log failing mid-copy, a generator that raises part-way, a container that mutates itself while copied, KeyboardInterrupt still propagating, and a control that ordinary inputs audit normally
Stated limits: the failures are simulated with containers that raise from __iter__ or __getitem__; plain list and dict copies are atomic in CPython and cannot be made to fail by another thread, so these tests cover the controlled-failure path, not a genuine race. A custom container whose copy is slow or never ends is not bounded by this change. Mutation spot check (own, not the frozen 16-mutant run): narrowing the handler to RuntimeError makes 19 tests fail; moving the event-log conversion out of the boundary makes 3 fail; both restored.

