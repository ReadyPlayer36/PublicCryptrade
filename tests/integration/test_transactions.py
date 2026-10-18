"""Transaction shape: BEGIN IMMEDIATE, ordering of network/validation vs the write, and explicit ROLLBACK."""
import pytest

from tests.fixtures.klines import make_rows
from tests.fixtures.service_env import I, S0, Env, ok_responses
from trading_app.data.repository import CandleConflictError
from trading_app.data.validator import DataValidationError


def collapse(env):
    """SQLite-level BEGIN/INSERT/COMMIT/ROLLBACK statements, with per-row INSERTs collapsed per table."""
    out = []
    for statement in env.sqlite("BEGIN", "INSERT", "COMMIT", "ROLLBACK"):
        words = statement.split()
        head = words[0].upper()
        label = f"INSERT {words[2]}" if head == "INSERT" else " ".join(w.upper() for w in words[:2]) if head == "BEGIN" else head
        if not out or out[-1] != label:
            out.append(label)
    return out


def network_inside_a_write_transaction(timeline):
    """True if any network request was made between a SQLite BEGIN IMMEDIATE and its COMMIT/ROLLBACK."""
    open_tx = False
    for event in timeline:
        if event[0] == "sqlite" and event[1].upper().startswith("BEGIN"):
            open_tx = True
        elif event[0] == "sqlite" and event[1].upper() in ("COMMIT", "ROLLBACK"):
            open_tx = False
        elif event[0] == "net" and open_tx:
            return True
    return False


@pytest.mark.requirement("TX-01")
def test_begin_immediate_captured():
    env = Env(ok_responses(3))
    env.run(3)
    assert collapse(env) == ["BEGIN IMMEDIATE", "INSERT candles", "INSERT data_fetches", "COMMIT"]     # one atomic transaction
    statements = env.sqlite("BEGIN", "SELECT", "INSERT", "COMMIT")
    assert statements[0] == "BEGIN IMMEDIATE"
    assert statements.index(next(s for s in statements if s.upper().startswith("SELECT"))) > 0       # the lookups run INSIDE the transaction
    assert not env.sqlite("ROLLBACK")                                                                # a clean run never rolls back


@pytest.mark.requirement("TX-02")
def test_begin_immediate_statement_captured():
    env = Env(ok_responses(3))
    env.run(3)
    emitted = [e[1] for e in env.timeline if e[0] == "sa-exec"]
    assert emitted[0] == "BEGIN IMMEDIATE"                                       # SQLAlchemy itself emitted the actual statement
    assert emitted.count("BEGIN IMMEDIATE") == 1
    kinds = [e[0] for e in env.timeline if e[0] in ("sa-exec", "sa-commit", "sa-rollback")]
    assert kinds[-1] == "sa-commit" and "sa-rollback" not in kinds               # committed exactly once, at the end
    assert kinds.count("sa-commit") == 1


@pytest.mark.requirement("TX-09")
def test_network_and_validation_before_begin_immediate():
    env = Env(ok_responses(3))
    env.run(3)
    timeline = env.timeline
    last_network = max(i for i, e in enumerate(timeline) if e[0] == "net")
    first_begin = next(i for i, e in enumerate(timeline) if e[0] == "sqlite" and e[1].upper() == "BEGIN IMMEDIATE")
    assert last_network < first_begin                                           # every request finished before the write began
    assert [e[1] for e in timeline if e[0] == "net"] == ["https://data-api.binance.vision/api/v3/time", "https://data-api.binance.vision/api/v3/klines"]
    assert not network_inside_a_write_transaction(timeline)


@pytest.mark.requirement("TX-09")
def test_validation_failure_never_opens_a_candle_write_transaction():
    gap = [make_rows(S0, 1)[0], make_rows(S0 + 2 * I, 1)[0]]
    env = Env(ok_responses(3, rows=gap))
    with pytest.raises(DataValidationError):
        env.run(3)
    assert collapse(env) == ["BEGIN IMMEDIATE", "INSERT data_fetches", "COMMIT"]   # only the short failure-audit transaction
    assert not [s for s in env.sqlite("INSERT") if "candles" in s]
    assert not network_inside_a_write_transaction(env.timeline)


@pytest.mark.requirement("TX-09")
def test_hashing_and_conversion_failures_also_happen_before_the_transaction(monkeypatch):
    from trading_app.data import service as service_module
    def boom(records):
        raise ValueError("hash failure")
    monkeypatch.setattr(service_module, "hash_candles", boom)
    env = Env(ok_responses(3))
    with pytest.raises(ValueError, match="hash failure"):
        env.run(3)
    assert not [s for s in env.sqlite("INSERT") if "candles" in s] and env.repo.count() == 0


@pytest.mark.requirement("TX-01")
def test_conflict_issues_an_explicit_rollback_before_the_failure_audit():
    changed = make_rows(S0, 3)
    changed[1][5] = "999"
    env = Env(ok_responses(3) + ok_responses(3, rows=changed))
    env.run(3)
    env.timeline.clear()
    with pytest.raises(CandleConflictError):
        env.run(3)
    timeline = env.timeline
    explicit_rollbacks = [i for i, e in enumerate(timeline) if e == ("sa-rollback",)]
    assert len(explicit_rollbacks) == 1                                          # SQLAlchemy rolled the transaction back exactly once
    assert env.sqlite("ROLLBACK") == ["ROLLBACK"]                                # and SQLite really executed a ROLLBACK statement
    begins = [i for i, e in enumerate(timeline) if e[0] == "sqlite" and e[1].upper() == "BEGIN IMMEDIATE"]
    assert len(begins) == 2 and begins[0] < explicit_rollbacks[0] < begins[1]    # candle tx -> ROLLBACK -> separate failure-audit tx
    assert collapse(env) == ["BEGIN IMMEDIATE", "ROLLBACK", "BEGIN IMMEDIATE", "INSERT data_fetches", "COMMIT"]
    assert not network_inside_a_write_transaction(timeline)


@pytest.mark.requirement("TX-01")
def test_a_clean_run_issues_no_explicit_rollback():
    env = Env(ok_responses(3))
    env.run(3)
    assert ("sa-rollback",) not in env.timeline and ("sa-commit",) in env.timeline


@pytest.mark.requirement("TX-01")
def test_write_lock_is_released_after_a_failed_fetch():
    changed = make_rows(S0, 3)
    changed[1][5] = "999"
    env = Env(ok_responses(3) + ok_responses(3, rows=changed) + ok_responses(4, rows=make_rows(S0, 4)))
    env.run(3)
    with pytest.raises(CandleConflictError):
        env.run(3)
    assert env.run(4) == 1                                                       # the next fetch can write immediately
