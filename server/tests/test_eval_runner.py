import copy
import io
import urllib.error
import urllib.request

import pytest

import evals.run_eval as runner
from evals.run_eval import (
    _batch_summary,
    _call_tool,
    _claim_summary,
    _common_summary,
    _extract_structured_result,
    _rank_summary,
    _selection_summary,
    _signal_matrix_summary,
    _validate_tool_runs,
)


RECEIPT_ID = "5fd6ccab-7fda-45bc-a979-250250270000"


def _telemetry() -> dict[str, object]:
    return {
        "model": "jev-1.13.0",
        "latency_ms": 1.0,
        "usage": {"input_tokens": 10, "output_tokens": 2},
        "estimated_input_cost_usd": 0.000001,
        "request_fingerprint": "a" * 64,
        "upstream_attempts": 1,
        "receipt_id": RECEIPT_ID,
    }


def _rank_fixture(tool: str = "jev_rank") -> dict[str, object]:
    fixture: dict[str, object] = {
        "name": "rank-fixture",
        "tool": tool,
        "data_class": "synthetic",
        "candidates": [
            {"id": "a", "text": "A"},
            {"id": "b", "text": "B"},
            {"id": "c", "text": "C"},
        ],
        "top_k": 2,
    }
    if tool == "jev_rank":
        fixture["goal"] = "Prioritize review"
    else:
        fixture["predicate"] = "Needs review"
    return fixture


def _rank_run(tool: str = "jev_rank") -> dict[str, object]:
    score_key = "relevance" if tool == "jev_rank" else "probability"
    result: dict[str, object] = {
        **_telemetry(),
        "ranked": [
            {"id": "a", score_key: 0.9},
            {"id": "b", score_key: 0.8},
            {"id": "c", score_key: 0.8},
        ],
        "all_ids": ["a", "b", "c"],
        "top_ids": ["a", "b", "c"],
        "requested_top_k": 2,
        "effective_top_k": 3,
        "cutoff_probability": 0.8,
        "cutoff_tie_ids": ["b", "c"],
        "tie_at_cutoff": True,
        "all_candidates_preserved": True,
        "candidate_count": 3,
    }
    if tool == "jev_batch_check":
        result["match_exists"] = 0.95
    return result


def _decide_fixture() -> dict[str, object]:
    return {
        "name": "decide-fixture",
        "tool": "jev_decide",
        "data_class": "synthetic",
        "state": "Synthetic state",
        "questions": {
            "relevant": {"type": "noul", "instructions": "Relevant?"},
            "route": {
                "type": "choice",
                "instructions": "Which route?",
                "criteria": {"review": "Review", "background": "Background"},
            },
            "risk": {
                "type": "score",
                "instructions": "How risky?",
                "criteria": ["low", "medium", "high"],
            },
        },
    }


def _decide_run() -> dict[str, object]:
    return {
        **_telemetry(),
        "answers": {
            "relevant": {"type": "noul", "noul": 0.9},
            "route": {
                "type": "choice",
                "choice": "review",
                "probabilities": {"review": 0.8, "background": 0.2},
                "confidence": 0.7,
            },
            "risk": {
                "type": "score",
                "score": 1.2,
                "legend": {"0": "low", "1": "medium", "2": "high"},
                "probabilities": {"0": 0.1, "1": 0.6, "2": 0.3},
                "confidence": 0.6,
            },
        },
    }


def test_eval_runner_fails_loudly_on_tool_error() -> None:
    private_detail = "response-body-content-must-not-escape"
    body = {"result": {"isError": True, "content": [{"type": "text", "text": private_detail}]}}
    with pytest.raises(RuntimeError, match="MCP tool returned an error") as error:
        _extract_structured_result(body)
    assert private_detail not in str(error.value)


def test_eval_runner_never_echoes_http_error_body(monkeypatch: pytest.MonkeyPatch) -> None:
    private_detail = b"response-body-content-must-not-escape"

    def fail(*args: object, **kwargs: object) -> object:
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8765/mcp",
            500,
            "server error",
            {},
            io.BytesIO(private_detail),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(RuntimeError, match="MCP HTTP 500") as error:
        _call_tool("http://127.0.0.1:8765/mcp", "jev_rank", {})
    assert private_detail.decode() not in str(error.value)


def test_eval_runner_rejects_missing_structured_content() -> None:
    with pytest.raises(RuntimeError, match="structuredContent"):
        _extract_structured_result({"result": {"isError": False, "content": []}})


def test_rank_summary_requires_all_candidates() -> None:
    fixture = {
        "candidates": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
        "baseline_top_ids": ["a"],
    }
    runs = [
        {
            "top_ids": ["a"],
            "all_candidates_preserved": True,
            "ranked": [{"id": "a", "relevance": 0.9}],
        }
    ]
    with pytest.raises(RuntimeError, match="candidate set"):
        _rank_summary(fixture, runs)


def test_batch_summary_requires_all_candidates() -> None:
    fixture = {
        "candidates": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
        "expected_top_ids": ["a"],
    }
    runs = [
        {
            "top_ids": ["a"],
            "all_candidates_preserved": True,
            "ranked": [{"id": "a", "probability": 0.9}],
            "match_exists": 0.9,
        }
    ]
    with pytest.raises(RuntimeError, match="candidate set"):
        _batch_summary(fixture, runs)


def test_claim_summary_requires_advisory_marker() -> None:
    fixture = {"source_id": "source-1", "expected_relation": "supports"}
    runs = [
        {
            "relation": "supports",
            "advisory_only": False,
            "source_id": "source-1",
            "confidence": 0.9,
            "probabilities": {"supports": 0.9, "contradicts": 0.05, "insufficient": 0.05},
        }
    ]
    with pytest.raises(RuntimeError, match="advisory_only"):
        _claim_summary(fixture, runs)


def test_selection_summary_rejects_authority_or_execution() -> None:
    fixture = {"options": [{"id": "inspect", "text": "Inspect"}]}
    runs = [
        {
            "selected_id": "inspect",
            "advisory_only": True,
            "authorized": True,
            "executed": False,
        }
    ]
    with pytest.raises(RuntimeError, match="authority or execution"):
        _selection_summary(fixture, runs)


def test_signal_matrix_summary_requires_every_signal_cell() -> None:
    fixture = {
        "candidates": [{"id": "a", "text": "A"}],
        "signals": [
            {"id": "one", "instructions": "One"},
            {"id": "two", "instructions": "Two"},
        ],
    }
    runs = [
        {
            "all_cells_preserved": True,
            "matrix": [{"id": "a", "signals": {"one": 0.5}}],
        }
    ]
    with pytest.raises(RuntimeError, match="signal set"):
        _signal_matrix_summary(fixture, runs)


def test_common_summary_rejects_missing_telemetry_and_fingerprint() -> None:
    valid = {
        "model": "jev-1.13.0",
        "latency_ms": 1.0,
        "usage": {"input_tokens": 10, "output_tokens": 2},
        "estimated_input_cost_usd": 0.000001,
        "request_fingerprint": "a" * 64,
        "upstream_attempts": 1,
        "receipt_id": "5fd6ccab-7fda-45bc-a979-250250270000",
    }
    missing_cases = []
    for field in (
        "model",
        "latency_ms",
        "usage",
        "estimated_input_cost_usd",
        "request_fingerprint",
        "upstream_attempts",
    ):
        candidate = dict(valid)
        candidate.pop(field)
        missing_cases.append(candidate)
    missing_input_tokens = {**valid, "usage": {"output_tokens": 2}}
    missing_cases.append(missing_input_tokens)

    for candidate in missing_cases:
        with pytest.raises(RuntimeError):
            _common_summary({"name": "fixture", "tool": "jev_rank"}, [candidate])


def test_decide_schema_accepts_exact_typed_answers_and_rejects_malformed_values() -> None:
    fixture = _decide_fixture()
    valid = _decide_run()
    _validate_tool_runs(fixture, [valid])

    malformed: list[dict[str, object]] = []

    missing_answer = copy.deepcopy(valid)
    missing_answer["answers"].pop("route")
    malformed.append(missing_answer)

    extra_answer = copy.deepcopy(valid)
    extra_answer["answers"]["extra"] = {"type": "noul", "noul": 0.5}
    malformed.append(extra_answer)

    wrong_noul = copy.deepcopy(valid)
    wrong_noul["answers"]["relevant"]["noul"] = []
    malformed.append(wrong_noul)

    unhashable_type = copy.deepcopy(valid)
    unhashable_type["answers"]["route"]["type"] = []
    malformed.append(unhashable_type)

    unhashable_choice = copy.deepcopy(valid)
    unhashable_choice["answers"]["route"]["choice"] = []
    malformed.append(unhashable_choice)

    incomplete_choice = copy.deepcopy(valid)
    incomplete_choice["answers"]["route"]["probabilities"] = {"review": 1.0}
    malformed.append(incomplete_choice)

    non_argmax_choice = copy.deepcopy(valid)
    non_argmax_choice["answers"]["route"]["choice"] = "background"
    malformed.append(non_argmax_choice)

    wrong_legend = copy.deepcopy(valid)
    wrong_legend["answers"]["risk"]["legend"] = {
        "0": "high",
        "1": "medium",
        "2": "low",
    }
    malformed.append(wrong_legend)

    wrong_score = copy.deepcopy(valid)
    wrong_score["answers"]["risk"]["score"] = 1.1
    malformed.append(wrong_score)

    wrong_probability_type = copy.deepcopy(valid)
    wrong_probability_type["answers"]["risk"]["probabilities"]["2"] = {}
    malformed.append(wrong_probability_type)

    non_finite_confidence = copy.deepcopy(valid)
    non_finite_confidence["answers"]["risk"]["confidence"] = float("nan")
    malformed.append(non_finite_confidence)

    extra_field = copy.deepcopy(valid)
    extra_field["answers"]["risk"]["explanation"] = "not declared"
    malformed.append(extra_field)

    for candidate in malformed:
        with pytest.raises(RuntimeError):
            _validate_tool_runs(fixture, [candidate])

    malformed_fixture = copy.deepcopy(fixture)
    malformed_fixture["questions"]["route"]["type"] = []
    with pytest.raises(RuntimeError, match="invalid type"):
        _validate_tool_runs(malformed_fixture, [valid])


def test_rank_schema_accepts_tie_safe_top_and_rejects_malformed_rankings() -> None:
    fixture = _rank_fixture()
    valid = _rank_run()
    _validate_tool_runs(fixture, [valid])

    unsorted = {**valid, "ranked": list(reversed(valid["ranked"]))}
    with pytest.raises(RuntimeError, match="descending"):
        _validate_tool_runs(fixture, [unsorted])

    missing_cutoff = dict(valid)
    missing_cutoff.pop("cutoff_tie_ids")
    with pytest.raises(RuntimeError, match="cutoff_tie_ids"):
        _validate_tool_runs(fixture, [missing_cutoff])

    duplicate = {**valid, "ranked": [valid["ranked"][0], valid["ranked"][0], valid["ranked"][2]]}
    with pytest.raises(RuntimeError, match="candidate IDs"):
        _validate_tool_runs(fixture, [duplicate])


def test_batch_schema_rejects_non_finite_probability_before_metrics() -> None:
    fixture = _rank_fixture("jev_batch_check")
    malformed = {**_rank_run("jev_batch_check"), "match_exists": float("nan")}
    with pytest.raises(RuntimeError, match="match_exists"):
        _validate_tool_runs(fixture, [malformed])


def test_selection_schema_accepts_abstention_and_requires_full_argmax_distribution() -> None:
    fixture = {
        "tool": "jev_select",
        "options": [{"id": "inspect", "text": "Inspect"}],
    }
    valid = {
        **_telemetry(),
        "selected_id": "needs_review",
        "probabilities": {"inspect": 0.1, "none": 0.2, "needs_review": 0.7},
        "confidence": 0.7,
        "all_options_preserved": True,
        "option_count": 1,
        "advisory_only": True,
        "authorized": False,
        "executed": False,
    }
    _validate_tool_runs(fixture, [valid])

    incomplete = {**valid, "probabilities": {"inspect": 0.3, "needs_review": 0.7}}
    with pytest.raises(RuntimeError, match="declared options"):
        _validate_tool_runs(fixture, [incomplete])

    non_argmax = {**valid, "selected_id": "inspect"}
    with pytest.raises(RuntimeError, match="maximum-probability"):
        _validate_tool_runs(fixture, [non_argmax])


def test_claim_schema_requires_full_argmax_distribution_and_advisory_marker() -> None:
    fixture = {"tool": "jev_claim_audit", "source_id": "source-1"}
    valid = {
        **_telemetry(),
        "relation": "insufficient",
        "probabilities": {"supports": 0.1, "contradicts": 0.2, "insufficient": 0.7},
        "confidence": 0.7,
        "source_id": "source-1",
        "advisory_only": True,
    }
    _validate_tool_runs(fixture, [valid])

    non_argmax = {**valid, "relation": "supports"}
    with pytest.raises(RuntimeError, match="maximum-probability"):
        _validate_tool_runs(fixture, [non_argmax])

    not_advisory = {**valid, "advisory_only": False}
    with pytest.raises(RuntimeError, match="advisory_only"):
        _validate_tool_runs(fixture, [not_advisory])


def test_matrix_schema_requires_unique_complete_finite_cells_and_flags() -> None:
    fixture = {
        "tool": "jev_signal_matrix",
        "candidates": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
        "signals": [{"id": "one", "instructions": "One"}, {"id": "two", "instructions": "Two"}],
    }
    valid = {
        **_telemetry(),
        "matrix": [
            {"id": "a", "signals": {"one": 0.1, "two": 0.2}},
            {"id": "b", "signals": {"one": 0.3, "two": 0.4}},
        ],
        "candidate_ids": ["a", "b"],
        "signal_ids": ["one", "two"],
        "candidate_count": 2,
        "signal_count": 2,
        "cell_count": 4,
        "all_candidates_preserved": True,
        "all_signals_preserved": True,
        "all_cells_preserved": True,
        "advisory_only": True,
    }
    _validate_tool_runs(fixture, [valid])

    duplicate = {**valid, "matrix": [valid["matrix"][0], valid["matrix"][0]]}
    with pytest.raises(RuntimeError, match="candidate IDs"):
        _validate_tool_runs(fixture, [duplicate])

    non_finite = {
        **valid,
        "matrix": [valid["matrix"][0], {"id": "b", "signals": {"one": float("inf"), "two": 0.4}}],
    }
    with pytest.raises(RuntimeError, match="finite probability"):
        _validate_tool_runs(fixture, [non_finite])

    not_advisory = {**valid, "advisory_only": False}
    with pytest.raises(RuntimeError, match="preservation or advisory flags"):
        _validate_tool_runs(fixture, [not_advisory])


def test_run_fixture_rejects_malformed_result_before_summary_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _rank_fixture()
    malformed = {**_rank_run(), "ranked": list(reversed(_rank_run()["ranked"]))}
    monkeypatch.setattr(runner, "_call_tool", lambda *args, **kwargs: malformed)
    monkeypatch.setattr(
        runner,
        "_common_summary",
        lambda *args, **kwargs: pytest.fail("summary metrics ran before schema validation"),
    )

    with pytest.raises(RuntimeError, match="descending"):
        runner.run_fixture(fixture, "http://127.0.0.1:8765/mcp", 1)


def test_eval_http_timeout_covers_server_retry_window(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, float] = {}

    def fail(*args: object, **kwargs: object) -> object:
        observed["timeout"] = float(kwargs["timeout"])
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(RuntimeError, match="connection failed"):
        _call_tool("http://127.0.0.1:8765/mcp", "jev_rank", {})
    assert observed["timeout"] == runner.MCP_CALL_TIMEOUT_SECONDS == 120.0
