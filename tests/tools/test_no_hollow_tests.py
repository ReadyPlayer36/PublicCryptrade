"""Ratchet against hollow acceptance tests (tests with no meaningful assertion)."""
from pathlib import Path

import pytest

from tools.hollow_scan import hollow_tests, load_allowlist

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = ROOT / "tests" / "hollow_allowlist.txt"

# The complete set of placeholders that existed when the ratchet was introduced. The allowlist may
# only shrink: it must always be a subset of this tuple, and extending the tuple is a code change
# that shows up in review.
PINNED_ORIGINAL = (
    "tests/integration/test_audit.py::test_failure_audit_contents",
    "tests/integration/test_audit.py::test_failure_audit_write_cannot_mask_original_exception",
    "tests/integration/test_concurrency.py::test_conflict_rolls_back_entire_transaction",
    "tests/integration/test_concurrency.py::test_no_duplicate_rows_after_overlap",
    "tests/integration/test_concurrency.py::test_two_processes_overlap_without_duplicates",
    "tests/integration/test_metadata.py::test_data_fetch_metadata_fields",
    "tests/integration/test_service.py::test_repeatable_ingestion_is_idempotent",
    "tests/integration/test_sqlite_verification.py::test_direct_sqlite_verification_procedure",
    "tests/integration/test_sqlite_verification.py::test_invalid_volume_query",
    "tests/integration/test_sqlite_verification.py::test_ohlc_correctness_query",
    "tests/integration/test_sqlite_verification.py::test_stored_data_verification_queries",
    "tests/integration/test_sqlite_verification.py::test_suspicious_data_query",
    "tests/integration/test_sqlite_verification.py::test_timestamp_continuity_query",
    "tests/integration/test_transactions.py::test_begin_immediate_captured",
    "tests/integration/test_transactions.py::test_begin_immediate_statement_captured",
    "tests/integration/test_transactions.py::test_network_and_validation_before_begin_immediate",
    "tests/unit/test_verification_sql.py::test_decimal_string_safe_comparisons",
    "tests/unit/test_verification_sql.py::test_no_cast_as_real",
)


@pytest.mark.requirement("HYGIENE-02")
def test_no_new_hollow_tests_may_be_added():
    new = hollow_tests(ROOT) - load_allowlist(ALLOWLIST)
    assert not new, f"assertion-free tests are not allowed: {sorted(new)}"


@pytest.mark.requirement("HYGIENE-02")
def test_allowlist_only_shrinks():
    entries = load_allowlist(ALLOWLIST)
    assert entries <= set(PINNED_ORIGINAL), f"allowlist grew: {sorted(entries - set(PINNED_ORIGINAL))}"
    stale = entries - hollow_tests(ROOT)
    assert not stale, f"remove these now-real tests from tests/hollow_allowlist.txt: {sorted(stale)}"
    assert len(entries) <= len(PINNED_ORIGINAL)


@pytest.mark.requirement("HYGIENE-02")
def test_detector_flags_hollow_trivial_and_accepts_real_tests(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(
        "import pytest\n"
        "def test_hollow():\n    call()\n"
        "def test_trivial_true():\n    call()\n    assert True\n"
        "def test_trivial_one():\n    assert 1\n"
        "def test_comment_only():\n    # assert something later\n    call()\n"
        "def test_string_mentions_assert():\n    note = 'assert x'\n    call()\n"
        "def test_real():\n    assert call() == 1\n"
        "def test_raises():\n    with pytest.raises(ValueError):\n        f()\n"
        "def test_helper():\n    assert_valid_klines([])\n"
        "async def test_async_hollow():\n    await call()\n"
        "async def test_async_trivial():\n    await call()\n    assert True\n"
        "async def test_async_real():\n    assert await call() == 1\n"
        "def test_unused_nested_assert():\n    def helper():\n        assert call() == 1\n    call()\n"
        "def test_nested_assert_never_called_by_name():\n    def helper():\n        assert call() == 1\n    other = helper\n"
        "def test_called_nested_helper():\n    def check():\n        assert call() == 1\n    check()\n"
        "def test_nested_class_assert_only():\n    class Inner:\n        def m(self):\n            assert 1 == 1\n    call()\n"
        "def test_lambda_hides_raises():\n    f = lambda: pytest.raises(ValueError)\n"
        "async def test_unawaited_async_helper():\n    async def check():\n        assert call() == 1\n    check()\n"
        "async def test_awaited_async_helper():\n    async def check():\n        assert call() == 1\n    await check()\n"
        "def test_unconsumed_generator_helper():\n    def check():\n        assert call() == 1\n        yield\n    check()\n"
        "def test_consumed_generator_helper_is_not_trusted():\n    def check():\n        assert call() == 1\n        yield\n    list(check())\n"
        "def test_sync_helper_calling_in_async_test_is_fine():\n    def check():\n        assert call() == 1\n    check()\n"
        "class TestGroup:\n    def test_method_hollow(self):\n        call()\n    def test_method_real(self):\n        assert call() == 1\n"
    )
    assert hollow_tests(tmp_path) == {f"tests/test_x.py::{n}" for n in (
        "test_hollow", "test_trivial_true", "test_trivial_one", "test_comment_only", "test_string_mentions_assert",
        "test_async_hollow", "test_async_trivial", "test_method_hollow",
        "test_unused_nested_assert", "test_nested_assert_never_called_by_name", "test_nested_class_assert_only", "test_lambda_hides_raises",
        "test_unawaited_async_helper", "test_unconsumed_generator_helper", "test_consumed_generator_helper_is_not_trusted")}


@pytest.mark.requirement("HYGIENE-02")
@pytest.mark.parametrize("content", ["tests/x.py::not_a_test\n", "garbage\n", "tests/x.py::test_a extra\n"])
def test_malformed_allowlist_fails_closed(tmp_path, content):
    path = tmp_path / "list.txt"
    path.write_text(content)
    with pytest.raises(ValueError, match="malformed"):
        load_allowlist(path)


@pytest.mark.requirement("HYGIENE-02")
def test_missing_allowlist_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="missing"):
        load_allowlist(tmp_path / "absent.txt")
