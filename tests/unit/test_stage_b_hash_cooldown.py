"""Stage B1 regression and adversarial tests for hashing and cooldown (no network)."""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from tests.fixtures.policy import cooldown_policy
from trading_app.data import cooldown as cd
from trading_app.data.hashing import hash_candles

VECTORS = json.loads((Path(__file__).resolve().parents[1] / "fixtures/vectors/golden_hash_vectors.json").read_text())
R1, R2 = VECTORS["two_records"]["records"]


@pytest.mark.requirement("HASH-01")
def test_decimal_objects_and_strings_hash_identically():
    as_decimals = [{**r, **{k: Decimal(r[k]) for k in ("open", "high", "low", "close", "volume", "quote_volume")}} for r in (R1, R2)]
    assert hash_candles(as_decimals) == VECTORS["two_records"]["sha256"]


@pytest.mark.requirement("HASH-01")
def test_scientific_notation_is_not_hashed():
    # Decimal("0E-8") must serialize as 0.00000000, not 0E-8
    assert hash_candles([R1, {**R2, "volume": Decimal("0E-8"), "quote_volume": Decimal("1E-8")}]) == VECTORS["two_records"]["sha256"]
    assert hash_candles([R1, R2]) != VECTORS["negative_control_scientific_notation"]["sha256_with_str_decimal"]


@pytest.mark.requirement("HASH-01")
@pytest.mark.parametrize("records", [[R2, R1], [R1, R1]], ids=["descending", "duplicate"])
def test_unsorted_or_duplicate_records_are_rejected_not_repaired(records):
    with pytest.raises(ValueError, match="ascending"):
        hash_candles(records)


@pytest.mark.requirement("HASH-01")
@pytest.mark.parametrize("field,bad", [("open", 100.1), ("open", float("nan")), ("volume", "Infinity"),
                                       ("trade_count", 1.0), ("trade_count", True), ("open_time_ms", "1"),
                                       ("symbol", ""), ("symbol", "BTC\x1fUSDT")])
def test_invalid_field_values_are_rejected(field, bad):
    with pytest.raises(ValueError):
        hash_candles([{**R1, field: bad}])


@pytest.mark.requirement("HASH-01")
def test_missing_field_is_rejected_and_extra_fields_are_ignored():
    with pytest.raises(ValueError, match="missing"):
        hash_candles([{k: v for k, v in R1.items() if k != "close"}])
    assert hash_candles([{**R1, "created_at_ms": 999}]) == VECTORS["one_record"]["sha256"]


@pytest.mark.requirement("COOLDOWN-02")
def test_cooldown_minimums_match_frozen_policy():
    durations = cooldown_policy()["durations"]
    for trigger, minimum in cd.COOLDOWN_MINIMUM_S.items():
        if trigger in durations:
            assert durations[trigger] == f"max(supplied_retry_after,{minimum})"
    assert set(cooldown_policy()["triggers"]) == {"418", "429_exhausted", "429_retry_after_over_60", "429_retry_after_exceeds_sleep_budget"} == set(cd.COOLDOWN_MINIMUM_S)


@pytest.mark.requirement("COOLDOWN-02")
@pytest.mark.parametrize("trigger,retry_after,expected", [
    ("418", None, 600), ("418", 900, 900), ("418", 10, 600),
    ("429_exhausted", 10, 300), ("429_exhausted", 301, 301),
    ("429_retry_after_over_60", 61, 600), ("429_retry_after_exceeds_sleep_budget", 11, 600),
    ("429_retry_after_exceeds_sleep_budget", 700.2, 701),
])
def test_cooldown_duration_is_max_of_supplied_and_minimum(trigger, retry_after, expected):
    assert cd.cooldown_duration_s(trigger, retry_after) == expected


@pytest.mark.requirement("COOLDOWN-02")
def test_cooldown_duration_rejects_unknown_trigger_and_negative_retry_after():
    with pytest.raises(ValueError):
        cd.cooldown_duration_s("500", None)
    with pytest.raises(ValueError):
        cd.cooldown_duration_s("418", -1)


@pytest.mark.requirement("COOLDOWN-03")
def test_write_replaces_existing_state_atomically_and_creates_parent(tmp_path):
    path = tmp_path / "nested" / "binance_cooldown.json"
    cd.write_cooldown(path, {"until_ms": 1, "reason": "418"})
    cd.write_cooldown(path, {"until_ms": 2, "reason": "429_exhausted"})
    assert cd.read_cooldown(path) == {"until_ms": 2, "reason": "429_exhausted"}
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.requirement("COOLDOWN-03")
def test_failed_write_keeps_old_state_and_leaves_no_temp_file(tmp_path, monkeypatch):
    path = tmp_path / "c.json"
    cd.write_cooldown(path, {"until_ms": 5, "reason": "418"})
    monkeypatch.setattr(cd.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        cd.write_cooldown(path, {"until_ms": 9, "reason": "418"})
    monkeypatch.undo()
    assert cd.read_cooldown(path)["until_ms"] == 5
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.requirement("COOLDOWN-05")
@pytest.mark.parametrize("state", [{"until_ms": 1.5, "reason": "x"}, {"until_ms": True, "reason": "x"},
                                   {"until_ms": 1, "reason": ""}, {"until_ms": 1, "reason": "x", "extra": 1}, [], None])
def test_invalid_state_is_rejected_on_write_and_read(tmp_path, state):
    path = tmp_path / "c.json"
    with pytest.raises(cd.CorruptCooldownError):
        cd.write_cooldown(path, state)
    assert not path.exists()
    path.write_text(json.dumps(state))
    with pytest.raises(cd.CorruptCooldownError):
        cd.read_cooldown(path)
