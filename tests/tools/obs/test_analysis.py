"""Golden-vector and rejection tests for the pure OBS analysis (protocol v0.5 sections 7-8).

Vectors come from tests/fixtures/vectors/obs_analysis_vectors.json, produced by an independent generator that does not
import the harness. Tests call `analysis.<name>` at call time so the degenerate-double meta-test can patch the module.
Vector-driven tests are named test_vector_* (the meta-test relies on that prefix).
"""
import ast
import dataclasses
import importlib.util
import inspect
import json
from pathlib import Path

import pytest

from tools.obs import analysis
from tools.obs.runstore import ManifestError

VECTORS = Path(__file__).resolve().parents[2] / "fixtures" / "vectors"
V = json.loads((VECTORS / "obs_analysis_vectors.json").read_text())
STABILITY = {s["name"]: s for s in V["stability"]}


def decode(value):
    if isinstance(value, dict) and set(value) == {"$float"}:
        return float(value["$float"])
    if isinstance(value, list):
        return [decode(x) for x in value]
    return value


def make_sample(spec) -> "analysis.SampleInput":
    return analysis.SampleInput(spec["timeframe"], spec["boundary_ms"], tuple(spec["observations"]),
                                tuple(spec["bounds_ms"]), spec["reference"])


def call(fn_name, args):
    args = {k: decode(v) for k, v in args.items()}
    if fn_name == "SampleInput":
        return analysis.SampleInput(args["timeframe"], args["boundary_ms"], tuple(args["observations"]),
                                    tuple(args["bounds_ms"]), args["reference"])
    if fn_name == "analyze_samples":
        samples = args["samples"]
        if isinstance(samples, dict) and "$repeat_sample" in samples:
            samples = [make_sample(V["stability"][0])] * samples["$repeat_sample"]
        return analysis.analyze_samples(samples)
    return getattr(analysis, fn_name)(**args)


# ------------------------------------------------------------------------------------------------ generator hygiene
@pytest.mark.requirement("OBS-02")
def test_vectors_are_reproduced_by_the_independent_generator():
    spec = importlib.util.spec_from_file_location("generate_obs_analysis_vectors", VECTORS / "generate_obs_analysis_vectors.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.build() == V
    text = (VECTORS / "generate_obs_analysis_vectors.py").read_text()
    assert "import tools" not in text and "from tools" not in text and "import analysis" not in text


@pytest.mark.requirement("OBS-02")
def test_fixture_covers_every_interval_and_boundary_triple():
    seen = {(v["timeframe"], v["offset_from_B"]) for v in V["finality"]}
    assert seen == {(tf, d) for tf in ("5m", "15m", "1h", "4h") for d in (-1, 0, 1)}
    assert {s["boundary_ms"] % 300_000 for s in V["stability"]} == {0}


# ------------------------------------------------------------------------------------------------ finality
@pytest.mark.requirement("OBS-02")
@pytest.mark.parametrize("case", V["finality"], ids=lambda c: f"{c['timeframe']}-L{c['lag_ms']}-B{c['offset_from_B']:+d}")
def test_vector_finality_boundary_triples(case):
    result = analysis.is_final(case["close_time_ms"], case["server_time_ms"], case["lag_ms"])
    assert result is case["final"]
    assert case["final"] is (case["offset_from_B"] < 0)           # B-1 final; B and B+1 are not (strict <)


def _all_defaults_in_source():
    """Every default of every def/lambda/method in the module source, found by AST (public, private, nested)."""
    tree = ast.parse(Path(analysis.__file__).read_text())
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
            found += [(getattr(node, "name", "<lambda>"), ast.unparse(d)) for d in defaults]
        if isinstance(node, ast.ClassDef):                     # dataclass field defaults would also be defaults
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and item.value is not None:
                    found.append((f"{node.name}.{ast.unparse(item.target)}", ast.unparse(item.value)))
    return found


@pytest.mark.requirement("LAG-01")
def test_no_default_arguments_anywhere_in_the_module_source():
    assert _all_defaults_in_source() == []


@pytest.mark.requirement("LAG-01")
def test_no_default_arguments_on_any_runtime_callable():
    checked = []
    for name, obj in vars(analysis).items():
        if getattr(obj, "__module__", None) != analysis.__name__:
            continue
        targets = [obj]
        if inspect.isclass(obj):
            targets = [m for _, m in inspect.getmembers(obj, inspect.isfunction)]
            assert all(f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
                       for f in getattr(obj, "__dataclass_fields__", {}).values()), name
        for target in targets:
            signature = inspect.signature(target)
            assert all(p.default is inspect.Parameter.empty for p in signature.parameters.values()), (name, str(signature))
            checked.append(name)
    assert {"is_final", "bound_k_ms", "lag_candidate", "validate_row", "rows_equal", "stable_from", "analyze_samples",
            "_int", "_check_row_shape", "_check_indices", "_equal", "_check_label", "SampleInput", "AnalysisResult"} <= set(checked)


@pytest.mark.requirement("LAG-01")
def test_omitting_any_argument_is_a_python_error_not_a_silent_default():
    for fn, argc in ((analysis.is_final, 3), (analysis.bound_k_ms, 4), (analysis.lag_candidate, 1), (analysis.rows_equal, 3),
                     (analysis.stable_from, 3), (analysis.analyze_samples, 1)):
        for omit in range(argc):
            args = [None] * argc
            with pytest.raises(TypeError):
                fn(*(args[:omit] + args[omit + 1:]))
    with pytest.raises(TypeError):
        analysis.validate_row([], expected_open_ms=0, interval_ms=1)               # label omitted
    with pytest.raises(TypeError):
        analysis._int("x", 1)                                                       # minimum omitted


@pytest.mark.requirement("LAG-01")
def test_no_default_lag_constant_and_no_approval_surface():
    forbidden = [n for n in dir(analysis) if "default" in n.lower() or n.startswith("APPROVED") or n in {"LAG", "LAG_MS", "L_MS"}]
    assert forbidden == []
    assert not hasattr(analysis, "approve_lag") and not hasattr(analysis, "choose_lag")
    assert not hasattr(analysis.LagCandidate, "approved") and "approved" not in analysis.LagCandidate.__dataclass_fields__


@pytest.mark.requirement("LAG-01")
def test_module_reads_no_clock_and_does_no_io():
    source = Path(analysis.__file__).read_text()
    for token in ("import time", "from time", "datetime", "import os", "open(", "socket", "httpx", "import random", "environ"):
        assert token not in source, token
    assert analysis.is_final(10, 10_000, 0) is True                      # result depends only on arguments


# ------------------------------------------------------------------------------------------------ bound_k
@pytest.mark.requirement("OBS-02")
@pytest.mark.parametrize("case", V["bound_k"], ids=lambda c: c["name"])
def test_vector_bound_k(case):
    got = analysis.bound_k_ms(case["s1_ms"], case["boundary_ms"], case["mono_start_s1_ns"], case["mono_end_k_ns"])
    assert got == case["bound_ms"]


@pytest.mark.requirement("OBS-02")
def test_bound_k_exact_ceiling_edges():
    by = {c["name"]: c["bound_ms"] for c in V["bound_k"]}
    assert by["one ns below exact"] == by["exactly representable 10000 ms"] == by["one ns above exact"] - 1
    assert by["zero elapsed"] == 1 and by["sub-ms elapsed"] == 2


# ------------------------------------------------------------------------------------------------ lag formula
@pytest.mark.requirement("OBS-02")
@pytest.mark.parametrize("case", V["lag"], ids=lambda c: f"Lobs{c['l_obs_ms']}")
def test_vector_lag_formula(case):
    got = analysis.lag_candidate(case["l_obs_ms"])
    exp = case["expected"]
    if exp is None:
        assert got is None
    else:
        assert (got.l_obs_ms, got.pad_ms, got.l_raw_ms, got.l_ms) == (exp["l_obs_ms"], exp["pad_ms"], exp["l_raw_ms"], exp["l_ms"])
        assert got.l_ms % 1000 == 0 and got.l_ms >= 2000 and got.l_ms >= got.l_raw_ms and got.l_ms - got.l_raw_ms < 1000


@pytest.mark.requirement("OBS-02")
def test_lag_threshold_sides_are_exact():
    assert analysis.lag_candidate(2000).l_ms == 4000 and analysis.lag_candidate(2001).l_ms == 5000
    assert analysis.lag_candidate(10_000).l_ms == 20_000 and analysis.lag_candidate(10_001).l_ms == 21_000
    assert analysis.lag_candidate(60_000).l_ms == 120_000 and analysis.lag_candidate(60_001) is None
    assert analysis.lag_candidate(0).l_ms == 2000


# ------------------------------------------------------------------------------------------------ stability
@pytest.mark.requirement("OBS-02")
@pytest.mark.parametrize("case", V["stability"], ids=lambda c: c["name"])
def test_vector_stability_per_tuple(case):
    for name, indices in analysis.TUPLES.items():
        got = analysis.stable_from(tuple(case["observations"]), case["reference"], indices)
        assert got == case["expected"][name]["stable_from"], name
    sample = make_sample(case)                                           # structurally valid sample constructs
    for name in analysis.TUPLES:
        agg = analysis.analyze_samples([sample]).by_name(name)
        exp = case["expected"][name]["bound_ms"]
        assert agg.l_obs_ms == exp and (agg.unbounded_count == 1) is (exp is None)


@pytest.mark.requirement("OBS-02")
@pytest.mark.parametrize("case", V["rows_equal"], ids=lambda c: c["name"])
def test_vector_rows_equal(case):
    got = analysis.rows_equal(case["left"], case["right"], case["indices"])
    assert got is case["expected"]


@pytest.mark.requirement("OBS-02")
def test_text_only_difference_is_not_instability_and_numeric_difference_is():
    assert STABILITY["raw text only difference is stable"]["expected"]["T_all"]["stable_from"] == 0
    assert STABILITY["unbounded"]["expected"]["T_matrix"]["stable_from"] is None


@pytest.mark.requirement("OBS-02")
@pytest.mark.parametrize("case", V["aggregation"], ids=lambda c: c["name"])
def test_vector_aggregation(case):
    samples = [make_sample(STABILITY[n]) for n in case["sample_names"]]
    result = analysis.analyze_samples(samples)
    assert [r.name for r in result.results] == ["T_matrix", "T_app", "T_all"]
    for name, exp in case["expected"].items():
        got = result.by_name(name)
        assert got.l_obs_ms == exp["l_obs_ms"] and got.unbounded_count == exp["unbounded"] and got.sample_count == len(samples)
        if exp["candidate"] is None:
            assert got.candidate is None
        else:
            assert got.candidate.l_ms == exp["candidate"]["l_ms"] and got.candidate.l_raw_ms == exp["candidate"]["l_raw_ms"]


@pytest.mark.requirement("OBS-02")
def test_sample_size_limits_single_min_and_max():
    one = make_sample(V["stability"][0])
    assert analysis.analyze_samples([one]).by_name("T_app").sample_count == V["sizes"]["min_samples"] == 1
    assert analysis.analyze_samples([one] * V["sizes"]["max_samples"]).by_name("T_app").sample_count == V["sizes"]["max_samples"]
    assert analysis.analyze_samples(tuple([one] * 3)).by_name("T_app").sample_count == 3
    assert V["sizes"]["max_samples"] == analysis.MAX_SAMPLES == 126


@pytest.mark.requirement("OBS-02")
def test_missing_reference_is_never_stable_and_never_defaulted():
    ref = V["stability"][0]["reference"]
    with pytest.raises(analysis.ReferenceMissingError):
        analysis.stable_from((ref,) * 4, None, (1, 2, 3, 4))


@pytest.mark.requirement("OBS-02")
def test_analysis_never_approves_a_lag():
    result = analysis.analyze_samples([make_sample(V["stability"][0])])
    candidate = result.by_name("T_app").candidate
    assert isinstance(candidate, analysis.LagCandidate)
    assert set(candidate.__dataclass_fields__) == {"l_obs_ms", "pad_ms", "l_raw_ms", "l_ms"}
    with pytest.raises(Exception):
        candidate.l_ms = 1                                               # frozen


# ------------------------------------------------------------------------------------------------ immutable snapshot
def _fresh_sample_spec(name):
    spec = json.loads(json.dumps(STABILITY[name]))                      # private deep copy of lists the test may mutate
    return spec


@pytest.mark.requirement("OBS-02")
def test_snapshot_rows_are_plain_tuples_copied_from_the_inputs_and_none_is_preserved():
    spec = _fresh_sample_spec("empty response at 0 then stable")        # observation 0 is None
    sample = make_sample(spec)
    assert type(sample.reference) is tuple and sample.reference is not spec["reference"]
    assert sample.observations[0] is None
    for stored, original in zip(sample.observations[1:], spec["observations"][1:]):
        assert type(stored) is tuple and stored is not original and list(stored) == original
    assert type(sample.observations) is tuple and type(sample.bounds_ms) is tuple
    hash(sample)                                                         # fully immutable data is hashable


@pytest.mark.requirement("OBS-02")
def test_mutating_original_observation_lists_after_construction_does_not_alter_the_sample():
    spec = _fresh_sample_spec("stable from 0")
    sample = make_sample(spec)
    before = sample.observations
    for row in spec["observations"]:
        row[1] = "999.0"                                                 # would make observations differ from the reference
        row[8] = -5
    spec["observations"][0] = None
    spec["observations"].append(["junk"])
    assert sample.observations == before
    assert all(row is not None and row[1] == "100.0" and row[8] == 100 for row in sample.observations)


@pytest.mark.requirement("OBS-02")
def test_mutating_the_original_reference_list_after_construction_does_not_alter_the_sample():
    spec = _fresh_sample_spec("stable from 0")
    sample = make_sample(spec)
    spec["reference"][1] = "999.0"
    spec["reference"].clear()
    assert len(sample.reference) == 12 and sample.reference[1] == "100.0"


@pytest.mark.requirement("OBS-02")
def test_mutation_through_sample_observations_is_rejected():
    sample = make_sample(_fresh_sample_spec("stable from 0"))
    before = sample.observations
    with pytest.raises(TypeError):
        sample.observations[1][1] = "999.0"
    with pytest.raises(TypeError):
        sample.observations[1][1:3] = ("1", "2")
    with pytest.raises(TypeError):
        sample.observations[0] = None
    with pytest.raises(AttributeError):
        sample.observations[1].append("x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        sample.observations = ()
    assert sample.observations == before


@pytest.mark.requirement("OBS-02")
def test_mutation_through_sample_reference_is_rejected():
    sample = make_sample(_fresh_sample_spec("stable from 0"))
    before = sample.reference
    with pytest.raises(TypeError):
        sample.reference[1] = "999.0"
    with pytest.raises(TypeError):
        del sample.reference[0]
    with pytest.raises(AttributeError):
        sample.reference.append("x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        sample.reference = None
    with pytest.raises(dataclasses.FrozenInstanceError):
        sample.bounds_ms = (0, 0, 0, 0)
    assert sample.reference == before


@pytest.mark.requirement("OBS-02")
@pytest.mark.parametrize("name", ["stable from 0", "stable from 2", "unbounded", "empty response at 0 then stable", "flap: equal, differ, equal, equal"])
def test_analysis_results_unchanged_after_attempted_external_mutation(name):
    spec = _fresh_sample_spec(name)
    sample = make_sample(spec)
    expected = analysis.analyze_samples([sample])
    for row in spec["observations"]:
        if row is not None:
            row[1] = "999.0"
            row[8] = 7
    spec["reference"][1] = "999.0"
    spec["reference"][8] = 7
    for attempt in (lambda: sample.reference.__setitem__(1, "1.0"), lambda: sample.observations.__setitem__(0, None),
                    lambda: setattr(sample, "reference", None)):
        with pytest.raises((TypeError, AttributeError)):
            attempt()
    assert analysis.analyze_samples([sample]) == expected
    for tname in analysis.TUPLES:
        assert expected.by_name(tname).l_obs_ms == STABILITY[name]["expected"][tname]["bound_ms"]


@pytest.mark.requirement("OBS-02")
def test_snapshot_does_not_change_validation_of_mutable_inputs_or_error_precedence():
    spec = _fresh_sample_spec("stable from 0")
    spec["reference"] = "x" * 12                                          # not a list/tuple: reported, not iterated into chars
    with pytest.raises(analysis.MalformedRowError) as info:
        make_sample(spec)
    assert str(info.value) == "reference must be a list or tuple, not str"
    spec = _fresh_sample_spec("stable from 0")
    spec["observations"][2] = {"a": 1}
    with pytest.raises(analysis.MalformedRowError) as info:
        make_sample(spec)
    assert str(info.value) == "observations[2] must be a list or tuple, not dict"


# ------------------------------------------------------------------------------------------------ rejections
@pytest.mark.requirement("OBS-02")
@pytest.mark.parametrize("case", V["rejections"], ids=lambda c: c["name"])
def test_vector_rejections_have_exact_type_and_message(case):
    expected = getattr(analysis, case["exc"])
    with pytest.raises(ManifestError) as info:
        call(case["fn"], case["args"])
    assert type(info.value) is expected, (type(info.value), expected)
    assert str(info.value) == case["message"]
    assert issubclass(expected, analysis.AnalysisError) and issubclass(analysis.AnalysisError, ManifestError)


@pytest.mark.requirement("OBS-02")
def test_every_rule_family_has_a_rejection_vector():
    names = {c["exc"] for c in V["rejections"]}
    fns = {c["fn"] for c in V["rejections"]}
    assert {"is_final", "bound_k_ms", "lag_candidate", "SampleInput", "analyze_samples", "stable_from", "rows_equal", "validate_row"} <= fns
    assert names == {"MissingValueError", "InvalidTypeError", "InvalidValueError", "NonMonotonicError", "EmptySampleError",
                     "SampleCountError", "ReferenceMissingError", "MalformedRowError"}
