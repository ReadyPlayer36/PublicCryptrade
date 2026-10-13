"""Tooling/hygiene check: independently supplied vectors must not drift from frozen policy."""
import json
from pathlib import Path
from tests.fixtures.policy import frozen_policy, cooldown_policy

ROOT = Path(__file__).resolve().parents[2]

def test_retry_cooldown_vectors_match_frozen_yaml():
    vectors = json.loads((ROOT / "tests/fixtures/vectors/retry_cooldown_vectors.json").read_text(encoding="utf-8"))
    policy = frozen_policy()
    actual = vectors["policy_from_frozen_yaml"]
    assert actual == {
        "attempts_total": policy["retry"]["attempts_total"],
        "backoff_base_s": policy["retry"]["backoff"]["base_seconds"],
        "factor": policy["retry"]["backoff"]["factor"],
        "cap_s": policy["retry"]["backoff"]["cap_seconds"],
        "jitter_max_s": policy["retry"]["backoff"]["jitter_max_seconds"],
        "budget_s": policy["retry"]["sleep_budget_seconds"],
        "retry_after_cap_s": policy["retry"]["retry_after"]["max_seconds"],
    }
    by_name = {case["name"]: case for case in vectors["cases"]}
    assert "429_RA10_x4" in by_name and "429_RA11" in by_name
    cooldown = cooldown_policy()["durations"]
    assert by_name["418_no_retry_after"]["expected_cooldown_s"] == 600
    assert by_name["418_retry_after_900"]["expected_cooldown_s"] == 900
    assert by_name["429_RA10_x4"]["expected_cooldown_s"] == 300
    assert by_name["429_RA11"]["expected_cooldown_s"] == 600
    assert by_name["429_RA61"]["expected_cooldown_s"] == 600
    assert by_name["429_RA45"]["expected_cooldown_s"] == 600
    assert by_name["429_no_header_x4"]["expected_cooldown_s"] == 300
    assert cooldown["418"] == "max(supplied_retry_after,600)"
    assert cooldown["429_exhausted"] == "max(supplied_retry_after,300)"
    assert cooldown["429_retry_after_over_60"] == "max(supplied_retry_after,600)"
    assert cooldown["429_retry_after_exceeds_sleep_budget"] == "max(supplied_retry_after,600)"
