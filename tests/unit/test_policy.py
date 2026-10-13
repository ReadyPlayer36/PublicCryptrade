from tests.fixtures.policy import frozen_policy, retry_policy, cooldown_policy, finality_policy

def test_retry_attempt_cap_is_read_from_frozen_yaml():
    matrix=frozen_policy()
    assert retry_policy()["attempts_total"] == matrix["retry"]["attempts_total"]

def test_sleep_budget_is_read_from_frozen_yaml():
    matrix=frozen_policy()
    assert retry_policy()["sleep_budget_seconds"] == matrix["retry"]["sleep_budget_seconds"]

def test_cooldown_minimums_are_read_from_frozen_yaml():
    matrix=frozen_policy()
    assert cooldown_policy()["durations"] == matrix["cooldown"]["durations"]
    assert set(cooldown_policy()["durations"]) == set(matrix["cooldown"]["durations"])

def test_finality_lag_policy_is_read_from_frozen_yaml():
    matrix=frozen_policy()
    assert finality_policy()["lag_default"] == matrix["finality"]["lag_default"]
    assert finality_policy()["local_clock_fallback"] == matrix["finality"]["local_clock_fallback"]
