from tools.summarize_traceability import classify, main


def test_classification_counts_each_class(tmp_path):
    report = tmp_path / "t.txt"
    report.write_text(
        "FAIL: 4 traceability error(s)\n"
        " - A-01: nodeid failed: tests/x.py::t\n"
        " - A-01: nodeid did not pass: tests/x.py::t\n"
        " - LIVE-01: missing live JUnit evidence\n"
        " - B-02: test lacks requirement marker\n",
        encoding="utf-8",
    )
    counts = classify(report.read_text(encoding="utf-8"))
    assert (counts["expected_red"], counts["missing_evidence"], counts["structural"]) == (2, 1, 1)
    assert main(["x", str(report)]) == 1


def test_no_structural_errors_exits_zero(tmp_path):
    report = tmp_path / "t.txt"
    report.write_text(" - A-01: nodeid failed: tests/x.py::t\n", encoding="utf-8")
    assert main(["x", str(report)]) == 0


def test_missing_report_fails(tmp_path):
    assert main(["x", str(tmp_path / "absent.txt")]) == 1
