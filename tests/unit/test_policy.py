"""Meaningful structural and invariant checks for the test-side frozen-policy reader."""
from __future__ import annotations

import yaml
import pytest

from tests.fixtures import policy as policy_reader
from tests.fixtures.policy import cooldown_policy, finality_policy, frozen_policy, retry_policy


def test_frozen_policy_reader_loads_supported_matrix_version():
    matrix = frozen_policy()
    assert isinstance(matrix, dict)
    assert matrix["schema_version"] == "2.9"
    assert {"retry", "cooldown", "finality", "storage"} <= matrix.keys()


def test_retry_policy_has_valid_types_and_consistent_scopes():
    retry = retry_policy()
    attempts = retry["attempts_total"]
    budget = retry["sleep_budget_seconds"]
    backoff = retry["backoff"]
    retry_after = retry["retry_after"]

    assert isinstance(attempts, int) and not isinstance(attempts, bool)
    assert attempts >= 1
    assert isinstance(budget, (int, float)) and not isinstance(budget, bool)
    assert budget >= 0
    assert retry["attempts_scope"] == "per_request"
    assert retry["sleep_budget_scope"] == "per_fetch"

    for key in ("base_seconds", "factor", "jitter_max_seconds", "cap_seconds"):
        value = backoff[key]
        assert isinstance(value, (int, float)) and not isinstance(value, bool)
        assert value >= 0
    assert backoff["factor"] >= 1
    assert backoff["cap_seconds"] >= backoff["base_seconds"]
    assert retry_after["max_seconds"] >= 0
    assert isinstance(retry["retry_statuses"], list)
    assert isinstance(retry["retry_errors"], list)
    assert retry["non_retry_4xx"] is True


def test_cooldown_policy_covers_every_declared_trigger():
    cooldown = cooldown_policy()
    triggers = set(cooldown["triggers"])
    durations = cooldown["durations"]

    assert triggers
    assert triggers == set(durations)
    assert cooldown["scope"] == "global_across_allowed_hosts"
    assert cooldown["path"]
    assert cooldown["atomic_write"] == "temp+fsync+os.replace"
    assert all(isinstance(rule, str) and rule.strip() for rule in durations.values())


def test_finality_policy_fails_closed_without_approved_lag():
    finality = finality_policy()

    assert finality["rule"] == "close_time_ms < B"
    assert finality["effective_end"].startswith("min(")
    assert finality["local_clock_fallback"] is False
    assert finality["lag_default"] is None
    lag_min = finality["lag_min_ms"]
    assert isinstance(lag_min, int) and not isinstance(lag_min, bool)
    assert lag_min >= 0


def test_frozen_policy_reader_rejects_unsupported_schema_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    matrix_path = tmp_path / "matrix.yaml"
    matrix_path.write_text(
        yaml.safe_dump({"schema_version": "999", "retry": {}}),
        encoding="utf-8",
    )
    policy_reader.frozen_policy.cache_clear()
    monkeypatch.setattr(policy_reader, "MATRIX_PATH", matrix_path)

    with pytest.raises(AssertionError, match="unexpected frozen specification version"):
        policy_reader.frozen_policy()

    policy_reader.frozen_policy.cache_clear()
