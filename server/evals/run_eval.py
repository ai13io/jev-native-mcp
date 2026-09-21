from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from uuid import UUID

DEFAULT_MCP_URL = "http://127.0.0.1:8765/mcp"
# The server may make three sequential 30-second upstream attempts plus bounded
# backoff and local validation. Keep the client beyond that worst-case window.
MCP_CALL_TIMEOUT_SECONDS = 120.0
PROBABILITY_SUM_TOLERANCE = 0.02
SCORE_EXPECTED_VALUE_ABS_TOLERANCE = 1e-6


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _extract_structured_result(body: dict[str, Any]) -> dict[str, Any]:
    result = body.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("MCP response has no result object")
    if result.get("isError"):
        raise RuntimeError("MCP tool returned an error")
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        raise RuntimeError("MCP response has no structuredContent; refusing to treat missing fields as a result")
    return structured


def _call_tool(url: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    request = urllib.request.Request(
        url,
        data=_canonical(payload),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=MCP_CALL_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        exc.close()
        raise RuntimeError(f"MCP HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"MCP connection failed: {exc.reason}") from exc
    return _extract_structured_result(body)


def _pairwise_jaccard(sets: list[set[str]]) -> list[float]:
    scores: list[float] = []
    for left_index, left in enumerate(sets):
        for right in sets[left_index + 1 :]:
            union = left | right
            scores.append(len(left & right) / len(union) if union else 1.0)
    return scores


def _probability(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise RuntimeError(f"{label} must be a finite probability within 0..1")
    return float(value)


def _fixture_ids(fixture: dict[str, Any], field: str) -> list[str]:
    records = fixture.get(field)
    if not isinstance(records, list) or not records:
        raise RuntimeError(f"fixture {field} must be a non-empty list")
    ids: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise RuntimeError(f"fixture {field}[{index}] is missing a string id")
        ids.append(record["id"])
    if len(ids) != len(set(ids)):
        raise RuntimeError(f"fixture {field} contains duplicate IDs")
    return ids


def _distribution(value: Any, expected: set[str], label: str) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != expected:
        raise RuntimeError(f"{label} must contain exactly the declared options")
    probabilities = {
        option: _probability(probability, f"{label}.{option}")
        for option, probability in value.items()
    }
    if not math.isclose(
        sum(probabilities.values()),
        1.0,
        rel_tol=0.0,
        abs_tol=PROBABILITY_SUM_TOLERANCE,
    ):
        raise RuntimeError(f"{label} probabilities must sum to one")
    return probabilities


def _validate_common_run(run: dict[str, Any], index: int) -> None:
    model = run.get("model")
    if not isinstance(model, str) or not model:
        raise RuntimeError(f"run {index} is missing model telemetry")
    _non_negative_number(run.get("latency_ms"), f"run {index}.latency_ms")
    usage = run.get("usage")
    if not isinstance(usage, dict):
        raise RuntimeError(f"run {index} is missing usage telemetry")
    _non_negative_int(usage.get("input_tokens"), f"run {index}.usage.input_tokens")
    _non_negative_int(usage.get("output_tokens"), f"run {index}.usage.output_tokens")
    _non_negative_number(
        run.get("estimated_input_cost_usd"),
        f"run {index}.estimated_input_cost_usd",
    )
    fingerprint = run.get("request_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise RuntimeError(f"run {index} is missing request_fingerprint")
    attempts = run.get("upstream_attempts")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
        raise RuntimeError(f"run {index}.upstream_attempts must be a positive integer")
    receipt_id = run.get("receipt_id")
    try:
        valid_receipt = (
            isinstance(receipt_id, str)
            and str(UUID(receipt_id)) == receipt_id.lower()
        )
    except (ValueError, AttributeError):
        valid_receipt = False
    if not valid_receipt:
        raise RuntimeError(f"run {index} is missing a canonical receipt_id")


def _validate_ranked_run(
    fixture: dict[str, Any],
    run: dict[str, Any],
    index: int,
    score_key: str,
) -> None:
    expected_ids = _fixture_ids(fixture, "candidates")
    expected_set = set(expected_ids)
    ranked = run.get("ranked")
    if not isinstance(ranked, list) or len(ranked) != len(expected_ids):
        raise RuntimeError(f"run {index}.ranked has the wrong cardinality")
    ranked_ids: list[str] = []
    scores: list[float] = []
    for item_index, item in enumerate(ranked):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise RuntimeError(f"run {index}.ranked[{item_index}] is malformed")
        ranked_ids.append(item["id"])
        scores.append(
            _probability(
                item.get(score_key),
                f"run {index}.ranked[{item_index}].{score_key}",
            )
        )
    if len(ranked_ids) != len(set(ranked_ids)) or set(ranked_ids) != expected_set:
        raise RuntimeError(f"run {index}.ranked candidate IDs are not exact and unique")
    if any(left < right for left, right in zip(scores, scores[1:])):
        raise RuntimeError(f"run {index}.ranked is not in descending probability order")
    if run.get("all_ids") != ranked_ids:
        raise RuntimeError(f"run {index}.all_ids must match the complete ranked order")
    if run.get("all_candidates_preserved") is not True:
        raise RuntimeError(f"run {index} did not preserve every candidate")
    if run.get("candidate_count") != len(expected_ids):
        raise RuntimeError(f"run {index}.candidate_count differs from the fixture")

    requested_top_k = fixture.get("top_k")
    if (
        isinstance(requested_top_k, bool)
        or not isinstance(requested_top_k, int)
        or not 1 <= requested_top_k <= len(expected_ids)
        or run.get("requested_top_k") != requested_top_k
    ):
        raise RuntimeError(f"run {index}.requested_top_k is invalid")
    cutoff = _probability(run.get("cutoff_probability"), f"run {index}.cutoff_probability")
    expected_cutoff = scores[requested_top_k - 1]
    if not math.isclose(cutoff, expected_cutoff, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError(f"run {index}.cutoff_probability is inconsistent")
    expected_ties = [
        candidate_id
        for candidate_id, score in zip(ranked_ids, scores)
        if score == expected_cutoff
    ]
    if run.get("cutoff_tie_ids") != expected_ties:
        raise RuntimeError(f"run {index}.cutoff_tie_ids are inconsistent")
    expected_top = [
        candidate_id
        for candidate_id, score in zip(ranked_ids, scores)
        if score >= expected_cutoff
    ]
    if run.get("top_ids") != expected_top:
        raise RuntimeError(f"run {index}.top_ids are not the tie-safe ranked prefix")
    if run.get("effective_top_k") != len(expected_top):
        raise RuntimeError(f"run {index}.effective_top_k is inconsistent")
    expected_tie = len(expected_top) > requested_top_k
    if run.get("tie_at_cutoff") is not expected_tie:
        raise RuntimeError(f"run {index}.tie_at_cutoff is inconsistent")


def _validate_selection_run(fixture: dict[str, Any], run: dict[str, Any], index: int) -> None:
    option_ids = _fixture_ids(fixture, "options")
    expected = set(option_ids) | {"none", "needs_review"}
    probabilities = _distribution(
        run.get("probabilities"), expected, f"run {index}.probabilities"
    )
    selected = run.get("selected_id")
    if selected not in expected:
        raise RuntimeError(f"run {index}.selected_id is outside the declared options")
    if probabilities[selected] + 1e-9 < max(probabilities.values()):
        raise RuntimeError(f"run {index}.selected_id is not a maximum-probability option")
    _probability(run.get("confidence"), f"run {index}.confidence")
    if run.get("option_count") != len(option_ids):
        raise RuntimeError(f"run {index}.option_count differs from the fixture")
    if run.get("all_options_preserved") is not True:
        raise RuntimeError(f"run {index} did not preserve every option")
    if (
        run.get("advisory_only") is not True
        or run.get("authorized") is not False
        or run.get("executed") is not False
    ):
        raise RuntimeError(f"run {index} implied authority or execution")


def _validate_claim_run(fixture: dict[str, Any], run: dict[str, Any], index: int) -> None:
    expected = {"supports", "contradicts", "insufficient"}
    probabilities = _distribution(
        run.get("probabilities"), expected, f"run {index}.probabilities"
    )
    relation = run.get("relation")
    if relation not in expected:
        raise RuntimeError(f"run {index}.relation is invalid")
    if probabilities[relation] + 1e-9 < max(probabilities.values()):
        raise RuntimeError(f"run {index}.relation is not a maximum-probability option")
    _probability(run.get("confidence"), f"run {index}.confidence")
    if run.get("source_id") != fixture.get("source_id"):
        raise RuntimeError(f"run {index}.source_id differs from the fixture")
    if run.get("advisory_only") is not True:
        raise RuntimeError(f"run {index} is missing advisory_only")


def _validate_decide_run(fixture: dict[str, Any], run: dict[str, Any], index: int) -> None:
    questions = fixture.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise RuntimeError("fixture questions must be a non-empty object")
    question_ids = list(questions)
    if any(not isinstance(question_id, str) or not question_id for question_id in question_ids):
        raise RuntimeError("fixture question IDs must be non-empty strings")
    answers = run.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(question_ids):
        raise RuntimeError(f"run {index}.answers must contain exactly the fixture question IDs")

    for question_id in question_ids:
        question = questions[question_id]
        answer = answers[question_id]
        if not isinstance(question, dict) or not isinstance(answer, dict):
            raise RuntimeError(f"run {index}.answers.{question_id} is malformed")
        qtype = question.get("type")
        if not isinstance(qtype, str) or qtype not in {"noul", "choice", "score"}:
            raise RuntimeError(f"fixture question {question_id!r} has an invalid type")
        if answer.get("type") != qtype:
            raise RuntimeError(f"run {index}.answers.{question_id}.type is invalid")

        if qtype == "noul":
            if set(answer) != {"type", "noul"}:
                raise RuntimeError(f"run {index}.answers.{question_id} has unexpected fields")
            _probability(answer.get("noul"), f"run {index}.answers.{question_id}.noul")
            continue

        required = (
            {"type", "choice", "probabilities", "confidence"}
            if qtype == "choice"
            else {"type", "score", "legend", "probabilities", "confidence"}
        )
        if set(answer) != required:
            raise RuntimeError(f"run {index}.answers.{question_id} has unexpected fields")
        _probability(answer.get("confidence"), f"run {index}.answers.{question_id}.confidence")

        if qtype == "choice":
            criteria = question.get("criteria")
            if not isinstance(criteria, dict) or len(criteria) < 2 or any(
                not isinstance(option, str) or not option for option in criteria
            ):
                raise RuntimeError(f"fixture question {question_id!r} has invalid choice criteria")
            expected_options = set(criteria)
            probabilities = _distribution(
                answer.get("probabilities"),
                expected_options,
                f"run {index}.answers.{question_id}.probabilities",
            )
            choice = answer.get("choice")
            if not isinstance(choice, str) or choice not in expected_options:
                raise RuntimeError(f"run {index}.answers.{question_id}.choice is not declared")
            if probabilities[choice] + 1e-9 < max(probabilities.values()):
                raise RuntimeError(
                    f"run {index}.answers.{question_id}.choice is not a maximum-probability option"
                )
            continue

        criteria = question.get("criteria")
        if not isinstance(criteria, list) or not 2 <= len(criteria) <= 10:
            raise RuntimeError(f"fixture question {question_id!r} has invalid score criteria")
        expected_levels = {str(level) for level in range(len(criteria))}
        probabilities = _distribution(
            answer.get("probabilities"),
            expected_levels,
            f"run {index}.answers.{question_id}.probabilities",
        )
        expected_legend = {str(level): criterion for level, criterion in enumerate(criteria)}
        if answer.get("legend") != expected_legend:
            raise RuntimeError(f"run {index}.answers.{question_id}.legend is inconsistent")
        score = answer.get("score")
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
            or not 0.0 <= float(score) <= len(criteria) - 1
        ):
            raise RuntimeError(f"run {index}.answers.{question_id}.score is invalid")
        expected_score = math.fsum(
            int(level) * probability for level, probability in probabilities.items()
        )
        if not math.isclose(
            float(score),
            expected_score,
            rel_tol=0.0,
            abs_tol=SCORE_EXPECTED_VALUE_ABS_TOLERANCE,
        ):
            raise RuntimeError(
                f"run {index}.answers.{question_id}.score is not the probability-weighted expected value"
            )


def _validate_matrix_run(fixture: dict[str, Any], run: dict[str, Any], index: int) -> None:
    candidate_ids = _fixture_ids(fixture, "candidates")
    signal_ids = _fixture_ids(fixture, "signals")
    if run.get("candidate_ids") != candidate_ids:
        raise RuntimeError(f"run {index}.candidate_ids are not exact and unique")
    if run.get("signal_ids") != signal_ids:
        raise RuntimeError(f"run {index}.signal_ids are not exact and unique")
    matrix = run.get("matrix")
    if not isinstance(matrix, list) or len(matrix) != len(candidate_ids):
        raise RuntimeError(f"run {index}.matrix has the wrong cardinality")
    row_ids: list[str] = []
    expected_signals = set(signal_ids)
    for row_index, row in enumerate(matrix):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise RuntimeError(f"run {index}.matrix[{row_index}] is malformed")
        row_ids.append(row["id"])
        signals = row.get("signals")
        if not isinstance(signals, dict) or set(signals) != expected_signals:
            raise RuntimeError(f"run {index}.matrix[{row_index}] has an incomplete signal set")
        for signal_id, probability in signals.items():
            _probability(
                probability,
                f"run {index}.matrix[{row_index}].signals.{signal_id}",
            )
    if row_ids != candidate_ids or len(row_ids) != len(set(row_ids)):
        raise RuntimeError(f"run {index}.matrix candidate IDs are not exact and unique")
    if run.get("candidate_count") != len(candidate_ids):
        raise RuntimeError(f"run {index}.candidate_count differs from the fixture")
    if run.get("signal_count") != len(signal_ids):
        raise RuntimeError(f"run {index}.signal_count differs from the fixture")
    if run.get("cell_count") != len(candidate_ids) * len(signal_ids):
        raise RuntimeError(f"run {index}.cell_count differs from the fixture")
    if (
        run.get("all_candidates_preserved") is not True
        or run.get("all_signals_preserved") is not True
        or run.get("all_cells_preserved") is not True
        or run.get("advisory_only") is not True
    ):
        raise RuntimeError(f"run {index} is missing matrix preservation or advisory flags")


def _validate_tool_runs(fixture: dict[str, Any], runs: list[dict[str, Any]]) -> None:
    if not runs:
        raise RuntimeError("evaluation produced no runs")
    tool = fixture.get("tool")
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            raise RuntimeError(f"run {index} is not an object")
        _validate_common_run(run, index)
        if tool == "jev_rank":
            _validate_ranked_run(fixture, run, index, "relevance")
        elif tool == "jev_decide":
            _validate_decide_run(fixture, run, index)
        elif tool == "jev_batch_check":
            _validate_ranked_run(fixture, run, index, "probability")
            _probability(run.get("match_exists"), f"run {index}.match_exists")
        elif tool == "jev_select":
            _validate_selection_run(fixture, run, index)
        elif tool == "jev_claim_audit":
            _validate_claim_run(fixture, run, index)
        elif tool == "jev_signal_matrix":
            _validate_matrix_run(fixture, run, index)


def _rank_summary(fixture: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_ids = {candidate["id"] for candidate in fixture["candidates"]}
    top_runs = [run.get("top_ids") for run in runs]
    if any(not isinstance(top_ids, list) for top_ids in top_runs):
        raise RuntimeError("rank result is missing top_ids")
    if any(run.get("all_candidates_preserved") is not True for run in runs):
        raise RuntimeError("rank result did not preserve every candidate")
    for run in runs:
        ranked_ids = {item["id"] for item in run.get("ranked", [])}
        if ranked_ids != candidate_ids:
            raise RuntimeError("rank result candidate set differs from the fixture")

    top_sets = [set(top_ids) for top_ids in top_runs]
    pairwise = _pairwise_jaccard(top_sets)
    relevance: dict[str, list[float]] = {candidate_id: [] for candidate_id in candidate_ids}
    for run in runs:
        for item in run["ranked"]:
            relevance[item["id"]].append(float(item["relevance"]))

    baseline = fixture.get("baseline_top_ids") or []
    baseline_set = set(baseline)
    overlaps = [len(top_set & baseline_set) for top_set in top_sets] if baseline else []
    return {
        "top_ids_by_run": top_runs,
        "stable_top_set": all(top_set == top_sets[0] for top_set in top_sets[1:]),
        "pairwise_top_set_jaccard": pairwise,
        "baseline_top_ids": baseline or None,
        "baseline_overlap_by_run": overlaps or None,
        "relevance": {
            candidate_id: {
                "mean": round(statistics.fmean(values), 4),
                "min": min(values),
                "max": max(values),
                "spread": round(max(values) - min(values), 4),
            }
            for candidate_id, values in sorted(relevance.items())
        },
        "requested_top_k_by_run": [run.get("requested_top_k") for run in runs],
        "effective_top_k_by_run": [run.get("effective_top_k") for run in runs],
        "cutoff_probability_by_run": [run.get("cutoff_probability") for run in runs],
        "cutoff_tie_ids_by_run": [run.get("cutoff_tie_ids") for run in runs],
        "tie_at_cutoff_by_run": [run.get("tie_at_cutoff") for run in runs],
    }


def _batch_summary(fixture: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_ids = {candidate["id"] for candidate in fixture["candidates"]}
    top_runs = [run.get("top_ids") for run in runs]
    if any(not isinstance(top_ids, list) for top_ids in top_runs):
        raise RuntimeError("batch result is missing top_ids")
    if any(run.get("all_candidates_preserved") is not True for run in runs):
        raise RuntimeError("batch result did not preserve every candidate")

    probabilities: dict[str, list[float]] = {candidate_id: [] for candidate_id in candidate_ids}
    for run in runs:
        ranked = run.get("ranked")
        if not isinstance(ranked, list):
            raise RuntimeError("batch result is missing ranked items")
        ranked_ids = {item["id"] for item in ranked}
        if ranked_ids != candidate_ids:
            raise RuntimeError("batch result candidate set differs from the fixture")
        for item in ranked:
            probabilities[item["id"]].append(float(item["probability"]))

    top_sets = [set(top_ids) for top_ids in top_runs]
    pairwise = _pairwise_jaccard(top_sets)
    expected = fixture.get("expected_top_ids") or []
    expected_set = set(expected)
    return {
        "top_ids_by_run": top_runs,
        "stable_top_set": all(top_set == top_sets[0] for top_set in top_sets[1:]),
        "pairwise_top_set_jaccard": pairwise,
        "expected_top_ids": expected or None,
        "expected_overlap_by_run": (
            [len(top_set & expected_set) for top_set in top_sets] if expected else None
        ),
        "match_exists_by_run": [float(run["match_exists"]) for run in runs],
        "probabilities": {
            candidate_id: {
                "mean": round(statistics.fmean(values), 4),
                "min": min(values),
                "max": max(values),
                "spread": round(max(values) - min(values), 4),
            }
            for candidate_id, values in sorted(probabilities.items())
        },
        "requested_top_k_by_run": [run.get("requested_top_k") for run in runs],
        "effective_top_k_by_run": [run.get("effective_top_k") for run in runs],
        "cutoff_probability_by_run": [run.get("cutoff_probability") for run in runs],
        "cutoff_tie_ids_by_run": [run.get("cutoff_tie_ids") for run in runs],
        "tie_at_cutoff_by_run": [run.get("tie_at_cutoff") for run in runs],
    }


def _claim_summary(fixture: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    relations = [run.get("relation") for run in runs]
    if any(relation not in {"supports", "contradicts", "insufficient"} for relation in relations):
        raise RuntimeError("claim result has an invalid relation")
    if any(run.get("advisory_only") is not True for run in runs):
        raise RuntimeError("claim result is missing advisory_only")
    if any(run.get("source_id") != fixture["source_id"] for run in runs):
        raise RuntimeError("claim result source_id differs from the fixture")
    return {
        "relations_by_run": relations,
        "stable_relation": len(set(relations)) == 1,
        "expected_relation": fixture.get("expected_relation"),
        "expected_matches": (
            [relation == fixture["expected_relation"] for relation in relations]
            if fixture.get("expected_relation")
            else None
        ),
        "confidence_by_run": [float(run["confidence"]) for run in runs],
        "probabilities_by_run": [run["probabilities"] for run in runs],
    }


def _selection_summary(fixture: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    allowed = {option["id"] for option in fixture["options"]} | {"none", "needs_review"}
    selected = [run.get("selected_id") for run in runs]
    if any(item not in allowed for item in selected):
        raise RuntimeError("selection result is outside the declared option set")
    if any(run.get("advisory_only") is not True for run in runs):
        raise RuntimeError("selection result is missing advisory_only")
    if any(run.get("authorized") is not False or run.get("executed") is not False for run in runs):
        raise RuntimeError("selection result implied authority or execution")
    return {
        "selected_ids_by_run": selected,
        "stable_selection": len(set(selected)) == 1,
        "expected_selected_id": fixture.get("expected_selected_id"),
        "expected_matches": (
            [item == fixture["expected_selected_id"] for item in selected]
            if fixture.get("expected_selected_id")
            else None
        ),
        "probabilities_by_run": [run.get("probabilities") for run in runs],
        "confidence_by_run": [run.get("confidence") for run in runs],
    }


def _signal_matrix_summary(
    fixture: dict[str, Any], runs: list[dict[str, Any]]
) -> dict[str, Any]:
    candidate_ids = {candidate["id"] for candidate in fixture["candidates"]}
    signal_ids = {signal["id"] for signal in fixture["signals"]}
    cells_by_run: list[dict[str, float]] = []
    for run in runs:
        if run.get("all_cells_preserved") is not True:
            raise RuntimeError("signal matrix did not preserve every cell")
        matrix = run.get("matrix")
        if not isinstance(matrix, list) or {row.get("id") for row in matrix} != candidate_ids:
            raise RuntimeError("signal matrix candidate set differs from the fixture")
        cells: dict[str, float] = {}
        for row in matrix:
            values = row.get("signals")
            if not isinstance(values, dict) or set(values) != signal_ids:
                raise RuntimeError("signal matrix signal set differs from the fixture")
            for signal_id, probability in values.items():
                cells[f"{row['id']}::{signal_id}"] = float(probability)
        cells_by_run.append(cells)
    return {
        "candidate_ids": sorted(candidate_ids),
        "signal_ids": sorted(signal_ids),
        "cell_count": len(candidate_ids) * len(signal_ids),
        "cells_by_run": cells_by_run,
    }


def _non_negative_number(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise RuntimeError(f"{label} must be a finite non-negative number")
    return float(value)


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeError(f"{label} must be a non-negative integer")
    return value


def _common_summary(fixture: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        raise RuntimeError("evaluation produced no runs")

    latencies: list[float] = []
    input_tokens: list[int] = []
    costs: list[float] = []
    fingerprints: list[str] = []
    models: list[str] = []
    upstream_attempts: list[int] = []
    for index, run in enumerate(runs):
        model = run.get("model")
        if not isinstance(model, str) or not model:
            raise RuntimeError(f"run {index} is missing model telemetry")
        models.append(model)
        latencies.append(_non_negative_number(run.get("latency_ms"), f"run {index}.latency_ms"))
        usage = run.get("usage")
        if not isinstance(usage, dict):
            raise RuntimeError(f"run {index} is missing usage telemetry")
        input_tokens.append(
            _non_negative_int(usage.get("input_tokens"), f"run {index}.usage.input_tokens")
        )
        _non_negative_int(usage.get("output_tokens"), f"run {index}.usage.output_tokens")
        costs.append(
            _non_negative_number(
                run.get("estimated_input_cost_usd"),
                f"run {index}.estimated_input_cost_usd",
            )
        )
        fingerprint = run.get("request_fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise RuntimeError(f"run {index} is missing request_fingerprint")
        fingerprints.append(fingerprint)
        attempts = run.get("upstream_attempts")
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
            raise RuntimeError(f"run {index}.upstream_attempts must be a positive integer")
        upstream_attempts.append(attempts)

    receipt_ids = [run.get("receipt_id") for run in runs]
    try:
        receipts_valid = all(
            isinstance(value, str) and str(UUID(value)) == value.lower()
            for value in receipt_ids
        )
    except (ValueError, AttributeError):
        receipts_valid = False
    if not receipts_valid:
        raise RuntimeError("decision result is missing a canonical receipt_id")
    return {
        "fixture": fixture.get("name"),
        "fixture_sha256": hashlib.sha256(_canonical(fixture)).hexdigest(),
        "tool": fixture["tool"],
        "repeats": len(runs),
        "models": models,
        "same_request_fingerprint": len(set(fingerprints)) == 1,
        "request_fingerprint": fingerprints[0] if len(set(fingerprints)) == 1 else fingerprints,
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 1),
            "min": min(latencies),
            "max": max(latencies),
        },
        "input_tokens_total": sum(input_tokens),
        "estimated_input_cost_usd_total": round(sum(costs), 10),
        "upstream_attempts": upstream_attempts,
        "receipt_ids": receipt_ids,
    }


def run_fixture(fixture: dict[str, Any], url: str, repeats: int) -> dict[str, Any]:
    tool = fixture.get("tool")
    if tool == "jev_rank":
        arguments = {
            "data_class": fixture["data_class"],
            "goal": fixture["goal"],
            "candidates": fixture["candidates"],
            "top_k": fixture["top_k"],
        }
    elif tool == "jev_decide":
        arguments = {
            "data_class": fixture["data_class"],
            "state": fixture["state"],
            "questions": fixture["questions"],
        }
    elif tool == "jev_batch_check":
        arguments = {
            "data_class": fixture["data_class"],
            "predicate": fixture["predicate"],
            "candidates": fixture["candidates"],
            "top_k": fixture["top_k"],
        }
    elif tool == "jev_claim_audit":
        arguments = {
            "data_class": fixture["data_class"],
            "claim": fixture["claim"],
            "evidence": fixture["evidence"],
            "source_id": fixture["source_id"],
        }
    elif tool == "jev_select":
        arguments = {
            "data_class": fixture["data_class"],
            "goal": fixture["goal"],
            "options": fixture["options"],
        }
    elif tool == "jev_signal_matrix":
        arguments = {
            "data_class": fixture["data_class"],
            "candidates": fixture["candidates"],
            "signals": fixture["signals"],
        }
    else:
        raise ValueError(
            "fixture tool must be jev_rank, jev_decide, jev_batch_check, jev_claim_audit, "
            "jev_select, or jev_signal_matrix"
        )

    runs = [_call_tool(url, tool, arguments) for _ in range(repeats)]

    # Validate each complete tool contract before computing any stability or
    # aggregate metric. This deliberately does not import server runtime code.
    _validate_tool_runs(fixture, runs)
    summary = _common_summary(fixture, runs)
    if tool == "jev_rank":
        summary["rank"] = _rank_summary(fixture, runs)
    elif tool == "jev_batch_check":
        summary["batch"] = _batch_summary(fixture, runs)
    elif tool == "jev_claim_audit":
        summary["claim"] = _claim_summary(fixture, runs)
    elif tool == "jev_select":
        summary["selection"] = _selection_summary(fixture, runs)
    elif tool == "jev_signal_matrix":
        summary["signal_matrix"] = _signal_matrix_summary(fixture, runs)
    else:
        summary["answers_by_run"] = [run.get("answers") for run in runs]
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a fail-loud Jev Native evaluation fixture.")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--url", default=DEFAULT_MCP_URL)
    parser.add_argument("--repeats", type=int)
    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text())
    repeats = args.repeats if args.repeats is not None else int(fixture.get("repeats", 3))
    if not 1 <= repeats <= 20:
        raise SystemExit("repeats must be within 1..20")
    print(json.dumps(run_fixture(fixture, args.url, repeats), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
