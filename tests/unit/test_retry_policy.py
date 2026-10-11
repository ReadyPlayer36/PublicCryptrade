"""Policy wiring checks; request-level behavior remains intentionally red."""
import pytest
from trading_app.policy import frozen_policy, retry_policy
ROOT_POLICY=frozen_policy()["retry"]
@pytest.mark.requirement("M1-06")
def test_403_and_418_are_not_retried():
    assert 418 not in retry_policy()["retry_statuses"]
    assert ROOT_POLICY["non_retry_4xx"] is True
@pytest.mark.requirement("RETRY-01")
def test_429_does_not_fallback():
    assert retry_policy()["retry_after"]["over_cap"] == ROOT_POLICY["retry_after"]["over_cap"]
@pytest.mark.requirement("RETRY-02")
def test_retry_after_is_not_jittered_or_reduced():
    assert retry_policy()["retry_after"]["sleep_jitter"] is False
    assert retry_policy()["retry_after"]["max_seconds"] == ROOT_POLICY["retry_after"]["max_seconds"]
