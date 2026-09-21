import asyncio
from datetime import date
import json
import os
import re
from pathlib import Path

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

import server


BEARER_MARKER = "Authorization:" + " Bearer "
PRIVATE_KEY_MARKER = "-----BEGIN " + "PRIVATE KEY-----"


def _configure_runtime_test_stores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> server.DailyBudget:
    monkeypatch.setenv("TYPESAFE_API_KEY", "provider-key-for-runtime-tests")
    monkeypatch.setenv(
        "JEV_RECEIPT_HMAC_KEY", "receipt-integrity-key-for-runtime-tests"
    )
    monkeypatch.setenv("JEV_RECEIPT_DIR", str(tmp_path / "receipts"))
    monkeypatch.setenv("JEV_DAILY_BUDGET_USD", "1.0")
    daily_budget = server.DailyBudget()
    daily_budget.path = tmp_path / "usage.json"
    monkeypatch.setattr(server, "budget", daily_budget)
    monkeypatch.setattr(server, "_receipt_ledger_instance", None)
    monkeypatch.setattr(server, "_runtime_store_failure", None)
    monkeypatch.setattr(server, "paid_call_lock", asyncio.Lock())
    return daily_budget


def _install_provider_json_stub(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, object]
) -> list[httpx.Request]:
    requests: list[httpx.Request] = []
    real_async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(handler)

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        return real_async_client(
            transport=transport,
            timeout=kwargs.get("timeout", 30.0),
            trust_env=False,
        )

    monkeypatch.setattr(server.httpx, "AsyncClient", client_factory)
    return requests


def test_pyproject_pins_explicit_modules_and_pip_dev_extra() -> None:
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text()
    assert "[tool.setuptools]" in pyproject
    assert 'py-modules = ["server", "receipt_ledger"]' in pyproject
    assert "[project.optional-dependencies]" in pyproject
    assert "pytest==9.0.3" in pyproject


def test_sensitive_screen_rejects_common_secrets() -> None:
    assert server._contains_sensitive(BEARER_MARKER + "secretvalue123456789")
    assert server._contains_sensitive("api_key=secretvalue123456789")
    assert server._contains_sensitive(PRIVATE_KEY_MARKER)


def test_sensitive_screen_allows_synthetic_security_language() -> None:
    assert not server._contains_sensitive(
        "Synthetic Android method crosses an authorization boundary without carrying a credential."
    )
    assert not server._contains_sensitive(
        {"schema": {"password": False, "description": "Whether a password field exists"}}
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"request": {"password": "nested-secret-value"}},
        {"items": [{"client-secret": "nested-secret-value"}]},
        [{"metadata": {"api key": "nested-secret-value"}}],
        {"metadata": {"apiKey": "nested-secret-value"}},
        {"headers": [{"authorization": "Bearer nested-secret-value"}]},
        {"notes": [BEARER_MARKER + "nested-secret-value"]},
    ],
)
def test_sensitive_screen_rejects_structured_nested_secret_fields(payload: object) -> None:
    assert server._contains_sensitive(payload)


def test_bind_host_accepts_only_explicit_private_or_loopback_ip() -> None:
    assert server._validate_bind_host("127.0.0.1") == "127.0.0.1"
    assert server._validate_bind_host("10.42.0.8") == "10.42.0.8"
    assert server._validate_bind_host("fd00::8") == "fd00::8"
    with pytest.raises(ValueError):
        server._validate_bind_host("0.0.0.0")
    with pytest.raises(ValueError):
        server._validate_bind_host("8.8.8.8")
    with pytest.raises(ValueError):
        server._validate_bind_host("169.254.10.20")
    with pytest.raises(ValueError):
        server._validate_bind_host("192.0.2.1")
    with pytest.raises(ValueError):
        server._validate_bind_host("mcp.example.com")


def test_port_and_allowed_hosts_are_derived_from_runtime_configuration() -> None:
    assert server._validate_port("8765") == 8765
    assert server._allowed_hosts_for_bind("127.0.0.1", 8765) == ["127.0.0.1:8765"]
    assert server._allowed_hosts_for_bind("10.42.0.8", 9443) == ["10.42.0.8:9443"]
    assert server._allowed_hosts_for_bind("fd00::8", 8765) == ["[fd00::8]:8765"]

    for value in (0, 65_536, "not-a-port", True):
        with pytest.raises(ValueError, match="1 through 65535"):
            server._validate_port(value)


def test_default_runtime_paths_are_platform_relative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JEV_RECEIPT_DIR", raising=False)
    assert server._receipt_base_path() == Path("runtime/receipts-v2")


def test_receipt_hmac_key_is_stable_across_provider_key_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stable_key = "receipt-integrity-key-with-at-least-32-bytes"
    monkeypatch.setenv("JEV_RECEIPT_HMAC_KEY", stable_key)
    monkeypatch.setenv("TYPESAFE_API_KEY", "first-provider-key-123456789")
    first = server._receipt_hmac_key()
    monkeypatch.setenv("TYPESAFE_API_KEY", "second-provider-key-987654321")

    assert server._receipt_hmac_key() == first == stable_key.encode()

    monkeypatch.setenv("JEV_RECEIPT_HMAC_KEY", "too-short")
    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        server._receipt_hmac_key()


def test_receipt_summary_and_budget_roll_over_on_the_utc_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_utc_today", lambda: date(2030, 1, 2))
    monkeypatch.setenv("JEV_RECEIPT_DIR", str(tmp_path / "missing-receipts"))
    assert server._receipt_summary_today()["date"] == "2030-01-02"

    usage = tmp_path / "usage.json"
    usage.write_text('{"date":"2030-01-01","spent_usd":0.09,"requests":4}\n')
    daily_budget = server.DailyBudget()
    daily_budget.path = usage
    assert daily_budget._load() == {
        "date": "2030-01-02",
        "spent_usd": 0.0,
        "requests": 0,
    }


def test_question_validation() -> None:
    server._validate_questions(
        {
            "ingress": {"type": "noul", "instructions": "Is there an external ingress?"},
            "boundary": {
                "type": "choice",
                "instructions": "Which boundary?",
                "criteria": {"ipc": "Android IPC", "none": "No boundary"},
            },
            "priority": {
                "type": "score",
                "instructions": "How urgent?",
                "criteria": ["low", "medium", "high"],
            },
        }
    )


def test_question_validation_rejects_missing_choice_criteria() -> None:
    with pytest.raises(ValueError):
        server._validate_questions(
            {"boundary": {"type": "choice", "instructions": "Which boundary?", "criteria": {}}}
        )


def test_structured_state_and_instructions_are_supported() -> None:
    server._validate_state({"records": [{"kind": "public", "text": "example"}]})
    server._validate_questions(
        {
            "route": {
                "type": "choice",
                "instructions": {"question": "Which route?", "constraint": "Use only the supplied record."},
                "criteria": {"review": "Manual review", "background": "Background material"},
            }
        }
    )


def test_rank_candidate_limit_accepts_realistic_manifest_card() -> None:
    text = "x" * 1275
    normalized = server._normalize_rank_candidates([{"id": "launcher", "text": text}])
    assert normalized == [{"id": "launcher", "text": text}]


def test_rank_candidate_limit_reports_id_and_actual_length() -> None:
    too_long = "x" * (server.MAX_CANDIDATE_CHARS + 1)
    with pytest.raises(ValueError, match=r"candidate 'launcher'.*got 1601"):
        server._normalize_rank_candidates([{"id": "launcher", "text": too_long}])


def test_rank_questions_name_subjects_instead_of_using_positions() -> None:
    normalized = server._normalize_rank_candidates(
        [
            {"id": "launcher", "text": "Public deep-link entry point"},
            {"id": "background", "text": "Unrelated library plumbing"},
        ]
    )
    state, questions = server._build_rank_state_and_questions("Prioritize review", normalized)

    assert state["candidates"] == {
        "launcher": "Public deep-link entry point",
        "background": "Unrelated library plumbing",
    }
    assert "untrusted evidence" in state["ranking_contract"]
    assert "'launcher'" in questions["candidate_0"]["instructions"]
    assert "'background'" in questions["candidate_1"]["instructions"]
    assert "candidates[0]" not in questions["candidate_0"]["instructions"]


def test_batch_check_builds_complete_stable_id_state_and_named_questions() -> None:
    normalized = server._normalize_rank_candidates(
        [
            {"id": "launcher", "text": "Public deep-link entry point"},
            {"id": "callback", "text": "Public callback handler"},
        ]
    )
    state, questions = server._build_batch_check_state_and_questions(
        "Accepts attacker-controlled input", normalized
    )

    assert state["predicate"] == "Accepts attacker-controlled input"
    assert state["candidates"] == {
        "launcher": "Public deep-link entry point",
        "callback": "Public callback handler",
    }
    assert "untrusted evidence" in state["batch_check_contract"]
    assert "complete set" in state["batch_check_contract"]
    assert set(questions) == {"candidate.launcher", "candidate.callback", "match_exists"}
    assert all(question["type"] == "noul" for question in questions.values())
    assert "'launcher'" in questions["candidate.launcher"]["instructions"]
    assert "'callback'" in questions["candidate.callback"]["instructions"]
    assert "complete `candidates` set" in questions["match_exists"]["instructions"]


def test_batch_question_id_is_stable_safe_and_bounded_for_long_candidate_id() -> None:
    candidate_id = "a" * server.MAX_STABLE_ID_CHARS
    question_id = server._batch_candidate_question_id(candidate_id)

    assert len(question_id) <= 80
    assert question_id == server._batch_candidate_question_id(candidate_id)
    assert question_id.startswith("candidate.")


def test_batch_check_supports_complete_thirty_candidate_set() -> None:
    normalized = server._normalize_rank_candidates(
        [{"id": f"item-{index}", "text": f"Public item {index}"} for index in range(30)]
    )
    _, questions = server._build_batch_check_state_and_questions("Relevant", normalized)

    assert len(normalized) == 30
    assert len(questions) == 31
    assert "match_exists" in questions

    with pytest.raises(ValueError, match="1..30"):
        server._normalize_rank_candidates(
            [{"id": f"item-{index}", "text": f"Public item {index}"} for index in range(31)]
        )


def test_claim_audit_preserves_exact_span_and_has_meaningful_joint_choice() -> None:
    exact_span = "  Line one.\nLine two stays exact.  "
    state, questions = server._build_claim_audit_state_and_questions(
        "The handler checks caller identity.", exact_span, "src.handler-17"
    )

    assert state["evidence"] == {
        "source_id": "src.handler-17",
        "exact_span": exact_span,
    }
    assert "outside facts" in state["claim_audit_contract"]
    assert set(questions) == {"relation"}
    relation = questions["relation"]
    assert relation["type"] == "choice"
    assert set(relation["criteria"]) == {"supports", "contradicts", "insufficient"}
    assert "every material part" in relation["criteria"]["supports"]
    assert "directly conflicts" in relation["criteria"]["contradicts"]
    assert "missing context" in relation["criteria"]["insufficient"]


def test_new_tool_text_and_id_bounds_are_strict() -> None:
    assert server._validate_bounded_text("x", "predicate", server.MAX_PREDICATE_CHARS) == "x"
    assert (
        server._validate_bounded_text(
            "x" * server.MAX_EVIDENCE_CHARS, "evidence", server.MAX_EVIDENCE_CHARS
        )
        == "x" * server.MAX_EVIDENCE_CHARS
    )
    assert server._validate_stable_id("source.v1-2", "source_id") == "source.v1-2"

    with pytest.raises(ValueError, match=r"predicate must contain 1..1000.*got 0"):
        server._validate_bounded_text("", "predicate", server.MAX_PREDICATE_CHARS)
    with pytest.raises(ValueError, match=r"claim must contain 1..2000.*got 2001"):
        server._validate_bounded_text("x" * 2001, "claim", server.MAX_CLAIM_CHARS)
    with pytest.raises(ValueError, match=r"evidence must contain 1..12000.*got 12001"):
        server._validate_bounded_text("x" * 12001, "evidence", server.MAX_EVIDENCE_CHARS)
    with pytest.raises(ValueError, match="safe identifier"):
        server._validate_stable_id("source/id", "source_id")


def test_answer_validation_rejects_missing_or_invalid_noul() -> None:
    questions = {"candidate_0": {"type": "noul", "instructions": "Relevant?"}}

    with pytest.raises(ValueError, match="answers must contain exactly"):
        server._validate_answers(questions, {})
    with pytest.raises(ValueError, match="finite probability"):
        server._validate_answers(
            questions,
            {"candidate_0": {"type": "noul", "noul": "0.9"}},
        )
    with pytest.raises(ValueError, match="within 0..1"):
        server._validate_answers(
            questions,
            {"candidate_0": {"type": "noul", "noul": 1.1}},
        )


def test_answer_validation_accepts_complete_typed_answers() -> None:
    questions = {
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
    }
    answers = {
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
    }
    assert server._validate_answers(questions, answers) is answers


def test_score_answer_requires_exact_legend_expected_value_and_fields() -> None:
    questions = {
        "risk": {
            "type": "score",
            "instructions": "How risky?",
            "criteria": ["low", "medium", "high"],
        }
    }
    valid = {
        "type": "score",
        "score": 1.2,
        "legend": {"0": "low", "1": "medium", "2": "high"},
        "probabilities": {"0": 0.1, "1": 0.6, "2": 0.3},
        "confidence": 0.6,
    }

    wrong_legend = {**valid, "legend": {"0": "high", "1": "medium", "2": "low"}}
    with pytest.raises(ValueError, match="exactly match"):
        server._validate_answers(questions, {"risk": wrong_legend})

    wrong_score = {**valid, "score": 1.1}
    with pytest.raises(ValueError, match="probability-weighted expected value"):
        server._validate_answers(questions, {"risk": wrong_score})

    extra_field = {**valid, "explanation": "not part of the contract"}
    with pytest.raises(ValueError, match="unexpected fields"):
        server._validate_answers(questions, {"risk": extra_field})


def test_provider_result_requires_the_exact_pinned_model() -> None:
    payload = {
        "questions": {"answer": {"type": "noul", "instructions": "Answer?"}}
    }
    result = {
        "model": server.PINNED_MODEL,
        "answers": {"answer": {"type": "noul", "noul": 0.5}},
        "usage": {"input_tokens": 1, "output_tokens": 0},
    }
    assert server._validate_provider_result(payload, result) == result["usage"]

    with pytest.raises(server.JevProviderSchemaFailure, match="failed schema validation"):
        server._validate_provider_result(payload, {**result, "model": "jev-latest"})


def test_health_accepts_documented_alias_only_model_listings() -> None:
    assert server._models_endpoint_supports_jev([server.PINNED_MODEL])
    assert server._models_endpoint_supports_jev(["jev-latest", "jev-preview"])
    assert not server._models_endpoint_supports_jev(["unrelated-model"])


def test_answer_validation_rejects_non_argmax_choice() -> None:
    questions = {
        "route": {
            "type": "choice",
            "instructions": "Which route?",
            "criteria": {"review": "Review", "background": "Background"},
        }
    }
    with pytest.raises(ValueError, match="maximum-probability"):
        server._validate_answers(
            questions,
            {
                "route": {
                    "type": "choice",
                    "choice": "background",
                    "probabilities": {"review": 0.8, "background": 0.2},
                    "confidence": 0.7,
                }
            },
        )


def test_batch_answer_validation_requires_every_candidate_and_match_exists() -> None:
    normalized = server._normalize_rank_candidates(
        [
            {"id": "one", "text": "First"},
            {"id": "two", "text": "Second"},
        ]
    )
    _, questions = server._build_batch_check_state_and_questions("Matches", normalized)

    with pytest.raises(ValueError, match="answers must contain exactly"):
        server._validate_answers(
            questions,
            {
                "candidate.one": {"type": "noul", "noul": 0.8},
                "candidate.two": {"type": "noul", "noul": 0.2},
            },
        )
    with pytest.raises(ValueError, match="finite probability"):
        server._validate_answers(
            questions,
            {
                "candidate.one": {"type": "noul", "noul": 0.8},
                "candidate.two": {"type": "noul", "noul": 0.2},
                "match_exists": {"type": "noul", "noul": None},
            },
        )


def test_claim_answer_validation_rejects_incomplete_distribution() -> None:
    _, questions = server._build_claim_audit_state_and_questions("Claim", "Evidence", "source-1")

    with pytest.raises(ValueError, match="must contain exactly"):
        server._validate_answers(
            questions,
            {
                "relation": {
                    "type": "choice",
                    "choice": "supports",
                    "probabilities": {"supports": 0.8, "insufficient": 0.2},
                    "confidence": 0.7,
                }
            },
        )


def test_batch_check_returns_exact_advisory_probability_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call(payload: dict[str, object]) -> dict[str, object]:
        captured["payload"] = payload
        return {
            "model": "jev-test",
            "answers": {
                "candidate.launcher": {"type": "noul", "noul": 0.91},
                "candidate.background": {"type": "noul", "noul": 0.12},
                "match_exists": {"type": "noul", "noul": 0.94},
            },
            "usage": {"input_tokens": 321, "output_tokens": 0},
            "latency_ms": 12.3,
            "estimated_input_cost_usd": 0.000013482,
            "request_fingerprint": "fingerprint-1",
            "upstream_attempts": 1,
        }

    monkeypatch.setattr(server, "_call_jev", fake_call)
    result = asyncio.run(
        server.jev_batch_check(
            "synthetic",
            "Accepts attacker-controlled input",
            [
                {"id": "background", "text": "Unrelated library plumbing"},
                {"id": "launcher", "text": "Public deep-link entry point"},
            ],
            1,
        )
    )

    assert result == {
        "model": "jev-test",
        "usage": {"input_tokens": 321, "output_tokens": 0},
        "latency_ms": 12.3,
        "estimated_input_cost_usd": 0.000013482,
        "request_fingerprint": "fingerprint-1",
        "upstream_attempts": 1,
        "ranked": [
            {"id": "launcher", "probability": 0.91},
            {"id": "background", "probability": 0.12},
        ],
        "match_exists": 0.94,
        "all_ids": ["launcher", "background"],
        "requested_top_k": 1,
        "cutoff_probability": 0.91,
        "cutoff_tie_ids": ["launcher"],
        "tie_at_cutoff": False,
        "top_ids": ["launcher"],
        "effective_top_k": 1,
        "all_candidates_preserved": True,
        "candidate_count": 2,
    }
    assert "threshold" not in result
    assert "verdict" not in result
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == server.PINNED_MODEL
    assert set(payload["questions"]) == {
        "candidate.background",
        "candidate.launcher",
        "match_exists",
    }


def test_claim_audit_returns_exact_advisory_distribution_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    exact_span = "  The handler compares caller.id with owner.id.\n"
    captured: dict[str, object] = {}

    async def fake_call(payload: dict[str, object]) -> dict[str, object]:
        captured["payload"] = payload
        return {
            "model": "jev-test",
            "answers": {
                "relation": {
                    "type": "choice",
                    "choice": "supports",
                    "probabilities": {
                        "supports": 0.82,
                        "contradicts": 0.03,
                        "insufficient": 0.15,
                    },
                    "confidence": 0.76,
                }
            },
            "usage": {"input_tokens": 222, "output_tokens": 0},
            "latency_ms": 10.0,
            "estimated_input_cost_usd": 0.000009324,
            "request_fingerprint": "fingerprint-2",
            "upstream_attempts": 1,
        }

    monkeypatch.setattr(server, "_call_jev", fake_call)
    result = asyncio.run(
        server.jev_claim_audit(
            "public",
            "The handler checks caller identity.",
            exact_span,
            "src.handler-17",
        )
    )

    assert result == {
        "model": "jev-test",
        "usage": {"input_tokens": 222, "output_tokens": 0},
        "latency_ms": 10.0,
        "estimated_input_cost_usd": 0.000009324,
        "request_fingerprint": "fingerprint-2",
        "upstream_attempts": 1,
        "relation": "supports",
        "probabilities": {
            "supports": 0.82,
            "contradicts": 0.03,
            "insufficient": 0.15,
        },
        "confidence": 0.76,
        "source_id": "src.handler-17",
        "advisory_only": True,
    }
    assert "verified" not in result
    assert "verdict" not in result
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["state"]["evidence"]["exact_span"] == exact_span


def test_new_tools_reject_missing_or_malformed_upstream_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def missing_batch_answer(payload: dict[str, object]) -> dict[str, object]:
        return {
            "model": "jev-test",
            "answers": {
                "candidate.one": {"type": "noul", "noul": 0.5},
            },
            "usage": {"input_tokens": 1, "output_tokens": 0},
            "request_fingerprint": "fingerprint",
        }

    monkeypatch.setattr(server, "_call_jev", missing_batch_answer)
    with pytest.raises(ToolError, match="answers must contain exactly"):
        asyncio.run(
            server.jev_batch_check(
                "synthetic",
                "Matches",
                [{"id": "one", "text": "Candidate"}],
                1,
            )
        )

    async def malformed_claim_answer(payload: dict[str, object]) -> dict[str, object]:
        return {
            "model": "jev-test",
            "answers": {
                "relation": {
                    "type": "choice",
                    "choice": "supports",
                    "probabilities": {
                        "supports": 0.8,
                        "contradicts": 0.1,
                        "insufficient": 0.1,
                    },
                    "confidence": "high",
                }
            },
            "usage": {"input_tokens": 1, "output_tokens": 0},
            "request_fingerprint": "fingerprint",
        }

    monkeypatch.setattr(server, "_call_jev", malformed_claim_answer)
    with pytest.raises(ToolError, match="finite probability"):
        asyncio.run(server.jev_claim_audit("synthetic", "Claim", "Evidence", "source-1"))


def test_rank_tool_surfaces_validation_detail_to_mcp_client() -> None:
    too_long = "x" * (server.MAX_CANDIDATE_CHARS + 1)
    with pytest.raises(ToolError, match=r"candidate 'launcher'.*got 1601"):
        asyncio.run(
            server.mcp.call_tool(
                "jev_rank",
                {
                    "data_class": "synthetic",
                    "goal": "Limit regression",
                    "candidates": [{"id": "launcher", "text": too_long}],
                    "top_k": 1,
                },
            )
        )


def test_tie_safe_top_expands_the_entire_cutoff_group() -> None:
    ranked = [
        {"id": "a", "probability": 0.9},
        {"id": "b", "probability": 0.7},
        {"id": "c", "probability": 0.7},
        {"id": "d", "probability": 0.2},
    ]

    assert server._tie_safe_top(ranked, "probability", 2) == {
        "requested_top_k": 2,
        "cutoff_probability": 0.7,
        "cutoff_tie_ids": ["b", "c"],
        "tie_at_cutoff": True,
        "top_ids": ["a", "b", "c"],
        "effective_top_k": 3,
    }
    complete_tie = server._tie_safe_top(ranked, "probability", 3)
    assert complete_tie["cutoff_tie_ids"] == ["b", "c"]
    assert complete_tie["tie_at_cutoff"] is False
    assert complete_tie["effective_top_k"] == 3


def test_omitted_top_k_uses_candidate_count_up_to_ten_and_schema_stays_integer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call(payload: dict[str, object]) -> dict[str, object]:
        questions = payload["questions"]
        assert isinstance(questions, dict)
        answers = {
            question_id: {"type": "noul", "noul": 0.5}
            for question_id in questions
        }
        return {
            "model": "jev-test",
            "answers": answers,
            "usage": {"input_tokens": 1, "output_tokens": 0},
            "request_fingerprint": "omitted-top-k",
        }

    monkeypatch.setattr(server, "_call_jev", fake_call)
    candidates = [{"id": "a", "text": "First"}, {"id": "b", "text": "Second"}]
    rank = asyncio.run(server.jev_rank("synthetic", "Rank", candidates))
    batch = asyncio.run(server.jev_batch_check("synthetic", "Match", candidates))

    assert rank["requested_top_k"] == 2
    assert batch["requested_top_k"] == 2
    assert server._resolve_top_k(None, 30) == 10
    for tool_name in ("jev_rank", "jev_batch_check"):
        tool = server.mcp._tool_manager.get_tool(tool_name)
        top_schema = tool.parameters["properties"]["top_k"]
        assert top_schema["type"] == "integer"
        assert "default" not in top_schema
        assert "top_k" not in tool.parameters.get("required", [])


@pytest.mark.parametrize("value", [True, False, "1", 1.0, 0, -1, 3])
def test_explicit_invalid_top_k_fails(value: object) -> None:
    with pytest.raises(ValueError, match="within the candidate count"):
        server._resolve_top_k(value, 2)


@pytest.mark.parametrize("value", [None, True, "1"])
def test_mcp_schema_rejects_explicit_non_integer_top_k(value: object) -> None:
    with pytest.raises(ToolError):
        asyncio.run(
            server.mcp.call_tool(
                "jev_rank",
                {
                    "data_class": "synthetic",
                    "goal": "Rank",
                    "candidates": [{"id": "a", "text": "First"}],
                    "top_k": value,
                },
            )
        )


def test_rank_and_batch_check_both_expand_cutoff_ties(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call(payload: dict[str, object]) -> dict[str, object]:
        questions = payload["questions"]
        assert isinstance(questions, dict)
        if "match_exists" in questions:
            answers = {
                "candidate.a": {"type": "noul", "noul": 0.8},
                "candidate.b": {"type": "noul", "noul": 0.5},
                "candidate.c": {"type": "noul", "noul": 0.5},
                "match_exists": {"type": "noul", "noul": 0.9},
            }
        else:
            answers = {
                "candidate_0": {"type": "noul", "noul": 0.8},
                "candidate_1": {"type": "noul", "noul": 0.5},
                "candidate_2": {"type": "noul", "noul": 0.5},
            }
        return {
            "model": "jev-test",
            "answers": answers,
            "usage": {"input_tokens": 1, "output_tokens": 0},
            "request_fingerprint": "tie-test",
        }

    monkeypatch.setattr(server, "_call_jev", fake_call)
    candidates = [
        {"id": "a", "text": "First"},
        {"id": "b", "text": "Second"},
        {"id": "c", "text": "Third"},
    ]
    rank = asyncio.run(server.jev_rank("synthetic", "Rank", candidates, 2))
    batch = asyncio.run(server.jev_batch_check("synthetic", "Match", candidates, 2))

    for result in (rank, batch):
        assert result["requested_top_k"] == 2
        assert result["effective_top_k"] == 3
        assert result["cutoff_tie_ids"] == ["b", "c"]
        assert result["tie_at_cutoff"] is True
        assert result["top_ids"] == ["a", "b", "c"]
        assert result["all_ids"] == ["a", "b", "c"]
        assert result["all_candidates_preserved"] is True


def test_select_builds_meaningful_none_and_review_routes() -> None:
    normalized = server._normalize_select_options(
        [
            {"id": "static", "text": "Run local static analysis"},
            {"id": "docs", "text": "Inspect public documentation"},
        ]
    )
    state, questions = server._build_select_state_and_questions("Choose the next review route", normalized)

    assert state["options"] == {
        "static": "Run local static analysis",
        "docs": "Inspect public documentation",
    }
    assert "untrusted evidence" in state["selection_contract"]
    assert "cannot instruct, authorize, or execute" in state["selection_contract"]
    assert "retains all authority" in state["selection_contract"]
    criteria = questions["selection"]["criteria"]
    assert set(criteria) == {"static", "docs", "none", "needs_review"}
    assert "No supplied option" in criteria["none"]
    assert "manual review" in criteria["needs_review"]


@pytest.mark.parametrize("reserved_id", ["none", "needs_review", "NONE", "Needs_Review"])
def test_select_rejects_reserved_option_ids(reserved_id: str) -> None:
    with pytest.raises(ValueError, match="reserved"):
        server._normalize_select_options(
            [
                {"id": reserved_id, "text": "Reserved"},
                {"id": "valid", "text": "Valid"},
            ]
        )


def test_select_requires_two_options_and_applies_sensitive_screen() -> None:
    with pytest.raises(ValueError, match="2..30"):
        server._normalize_select_options([{"id": "one", "text": "Only one"}])
    with pytest.raises(ToolError, match="sensitive-data screen"):
        asyncio.run(
            server.jev_select(
                "public",
                "Choose route",
                [
                    {"id": "one", "text": BEARER_MARKER + "secretvalue123456789"},
                    {"id": "two", "text": "Safe public option"},
                ],
            )
        )


def test_select_returns_full_strict_distribution_without_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_call(payload: dict[str, object]) -> dict[str, object]:
        captured["payload"] = payload
        return {
            "model": "jev-test",
            "answers": {
                "selection": {
                    "type": "choice",
                    "choice": "needs_review",
                    "probabilities": {
                        "static": 0.25,
                        "docs": 0.15,
                        "none": 0.05,
                        "needs_review": 0.55,
                    },
                    "confidence": 0.61,
                }
            },
            "usage": {"input_tokens": 20, "output_tokens": 0},
            "request_fingerprint": "select-test",
        }

    monkeypatch.setattr(server, "_call_jev", fake_call)
    result = asyncio.run(
        server.jev_select(
            "synthetic",
            "Choose next route",
            [
                {"id": "static", "text": "Run local static analysis"},
                {"id": "docs", "text": "Inspect public documentation"},
            ],
        )
    )

    assert result["selected_id"] == "needs_review"
    assert result["probabilities"] == {
        "static": 0.25,
        "docs": 0.15,
        "none": 0.05,
        "needs_review": 0.55,
    }
    assert result["confidence"] == 0.61
    assert result["all_options_preserved"] is True
    assert result["advisory_only"] is True
    assert result["authorized"] is False
    assert result["executed"] is False
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert set(payload["questions"]["selection"]["criteria"]) == {
        "static",
        "docs",
        "none",
        "needs_review",
    }


def test_select_rejects_missing_and_non_argmax_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def missing(payload: dict[str, object]) -> dict[str, object]:
        return {"model": "jev-test", "answers": {}, "usage": {"input_tokens": 1, "output_tokens": 0}}

    monkeypatch.setattr(server, "_call_jev", missing)
    options = [{"id": "one", "text": "One"}, {"id": "two", "text": "Two"}]
    with pytest.raises(ToolError, match="answers must contain exactly"):
        asyncio.run(server.jev_select("synthetic", "Choose", options))

    async def non_argmax(payload: dict[str, object]) -> dict[str, object]:
        return {
            "model": "jev-test",
            "answers": {
                "selection": {
                    "type": "choice",
                    "choice": "one",
                    "probabilities": {"one": 0.1, "two": 0.6, "none": 0.1, "needs_review": 0.2},
                    "confidence": 0.7,
                }
            },
            "usage": {"input_tokens": 1, "output_tokens": 0},
        }

    monkeypatch.setattr(server, "_call_jev", non_argmax)
    with pytest.raises(ToolError, match="maximum-probability"):
        asyncio.run(server.jev_select("synthetic", "Choose", options))


def test_signal_matrix_question_ids_are_safe_bounded_stable_and_unique() -> None:
    candidate_a = "a" * server.MAX_STABLE_ID_CHARS
    candidate_b = "a" * (server.MAX_STABLE_ID_CHARS - 1) + "b"
    signal_a = "s" * server.MAX_STABLE_ID_CHARS
    id_a = server._matrix_question_id(candidate_a, signal_a)
    id_b = server._matrix_question_id(candidate_b, signal_a)
    ids = {id_a, id_b}

    assert len(ids) == 2
    assert id_a == server._matrix_question_id(candidate_a, signal_a)
    assert id_b == server._matrix_question_id(candidate_b, signal_a)
    assert all(len(question_id) <= 80 for question_id in ids)
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", question_id) for question_id in ids)
    assert server._matrix_question_id("a.b", "c") != server._matrix_question_id("a", "b.c")


def test_signal_matrix_builds_every_exact_pair() -> None:
    candidates = server._normalize_rank_candidates(
        [{"id": "a", "text": "First"}, {"id": "b", "text": "Second"}]
    )
    signals = server._normalize_signals(
        [
            {"id": "ingress", "instructions": "Has external ingress"},
            {"id": "auth", "instructions": "Crosses an authorization boundary"},
        ]
    )
    state, questions = server._build_signal_matrix_state_and_questions(candidates, signals)

    assert state["candidates"] == {"a": "First", "b": "Second"}
    assert state["signals"] == {
        "ingress": "Has external ingress",
        "auth": "Crosses an authorization boundary",
    }
    assert "do not apply thresholds" in state["signal_matrix_contract"]
    assert set(questions) == {
        "matrix.1.a.7.ingress",
        "matrix.1.a.4.auth",
        "matrix.1.b.7.ingress",
        "matrix.1.b.4.auth",
    }
    assert "'a'" in questions["matrix.1.a.4.auth"]["instructions"]
    assert "'auth'" in questions["matrix.1.a.4.auth"]["instructions"]


def test_signal_matrix_rejects_duplicate_signals_and_sensitive_text() -> None:
    with pytest.raises(ValueError, match="unique"):
        server._normalize_signals(
            [
                {"id": "same", "instructions": "First"},
                {"id": "same", "instructions": "Second"},
            ]
        )
    with pytest.raises(ToolError, match="sensitive-data screen"):
        asyncio.run(
            server.jev_signal_matrix(
                "synthetic",
                [{"id": "a", "text": "api_key=secretvalue123456789"}],
                [{"id": "signal", "instructions": "Check signal"}],
            )
        )


def test_signal_matrix_enforces_product_and_state_limits() -> None:
    with pytest.raises(ToolError, match="product must contain 1..60.*got 62"):
        asyncio.run(
            server.jev_signal_matrix(
                "synthetic",
                [{"id": "one", "text": "One"}, {"id": "two", "text": "Two"}],
                [{"id": f"s-{index}", "instructions": "Signal"} for index in range(31)],
            )
        )

    with pytest.raises(ToolError, match="state must contain at most"):
        asyncio.run(
            server.jev_signal_matrix(
                "synthetic",
                [
                    {"id": f"c-{index}", "text": "x" * server.MAX_CANDIDATE_CHARS}
                    for index in range(30)
                ],
                [
                    {"id": "s-one", "instructions": "x" * server.MAX_PREDICATE_CHARS},
                    {"id": "s-two", "instructions": "x" * server.MAX_PREDICATE_CHARS},
                ],
            )
        )


def test_signal_matrix_returns_complete_uncombined_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call(payload: dict[str, object]) -> dict[str, object]:
        return {
            "model": "jev-test",
            "answers": {
                "matrix.1.a.7.ingress": {"type": "noul", "noul": 0.8},
                "matrix.1.a.4.auth": {"type": "noul", "noul": 0.6},
                "matrix.1.b.7.ingress": {"type": "noul", "noul": 0.2},
                "matrix.1.b.4.auth": {"type": "noul", "noul": 0.1},
            },
            "usage": {"input_tokens": 40, "output_tokens": 0},
            "request_fingerprint": "matrix-test",
        }

    monkeypatch.setattr(server, "_call_jev", fake_call)
    result = asyncio.run(
        server.jev_signal_matrix(
            "synthetic",
            [{"id": "a", "text": "First"}, {"id": "b", "text": "Second"}],
            [
                {"id": "ingress", "instructions": "Has external ingress"},
                {"id": "auth", "instructions": "Crosses an authorization boundary"},
            ],
        )
    )

    assert result["matrix"] == [
        {"id": "a", "signals": {"ingress": 0.8, "auth": 0.6}},
        {"id": "b", "signals": {"ingress": 0.2, "auth": 0.1}},
    ]
    assert result["candidate_ids"] == ["a", "b"]
    assert result["signal_ids"] == ["ingress", "auth"]
    assert result["cell_count"] == 4
    assert result["all_candidates_preserved"] is True
    assert result["all_signals_preserved"] is True
    assert result["all_cells_preserved"] is True
    assert result["advisory_only"] is True
    assert "threshold" not in result
    assert "score" not in result
    assert "verdict" not in result


def test_signal_matrix_rejects_missing_or_malformed_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def missing(payload: dict[str, object]) -> dict[str, object]:
        return {"model": "jev-test", "answers": {}, "usage": {"input_tokens": 1, "output_tokens": 0}}

    monkeypatch.setattr(server, "_call_jev", missing)
    with pytest.raises(ToolError, match="answers must contain exactly"):
        asyncio.run(
            server.jev_signal_matrix(
                "synthetic",
                [{"id": "a", "text": "First"}],
                [{"id": "signal", "instructions": "Check signal"}],
            )
        )

    async def malformed(payload: dict[str, object]) -> dict[str, object]:
        return {
            "model": "jev-test",
            "answers": {"matrix.1.a.6.signal": {"type": "noul", "noul": "likely"}},
            "usage": {"input_tokens": 1, "output_tokens": 0},
        }

    monkeypatch.setattr(server, "_call_jev", malformed)
    with pytest.raises(ToolError, match="finite probability"):
        asyncio.run(
            server.jev_signal_matrix(
                "synthetic",
                [{"id": "a", "text": "First"}],
                [{"id": "signal", "instructions": "Check signal"}],
            )
        )


def test_hosted_decision_tools_disclose_egress_and_are_not_marked_read_only() -> None:
    health = server.mcp._tool_manager.get_tool("jev_health")
    assert health.annotations.read_only_hint is True
    for name in (
        "jev_decide",
        "jev_rank",
        "jev_batch_check",
        "jev_claim_audit",
        "jev_select",
        "jev_signal_matrix",
    ):
        tool = server.mcp._tool_manager.get_tool(name)
        assert tool is not None
        assert tool.annotations.read_only_hint is False
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.idempotent_hint is False
        assert tool.description.startswith(
            "Sends supplied public/synthetic text to hosted TypeSafe through the configured MCP endpoint."
        )
    outcome_tool = server.mcp._tool_manager.get_tool("jev_record_outcome")
    assert outcome_tool.annotations.read_only_hint is False
    assert outcome_tool.annotations.destructive_hint is False
    assert outcome_tool.annotations.open_world_hint is False


def test_record_outcome_tool_appends_only_structured_local_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = server.ReceiptLedger(
        tmp_path / "receipts", b"0123456789abcdef0123456789abcdef"
    )
    receipt_id = ledger.record_decision(
        tool="jev_select",
        data_class="synthetic",
        model_version="jev-test",
        server_version=server.VERSION,
        backend_version=server.BACKEND_VERSION,
        contract_version=server.CONTRACT_VERSION,
        candidate_count=3,
        question_count=1,
        input_tokens=10,
        output_tokens=1,
        cost=0.000001,
        latency=5.0,
        attempts=1,
        status="success",
        cache_hit=False,
        canonical_request=b'{"synthetic":"fixture"}',
    )
    monkeypatch.setattr(server, "_receipt_ledger_instance", ledger)

    result = asyncio.run(
        server.jev_record_outcome(
            receipt_id, "useful_hit", "frontier_review", 3, 2, 15.0
        )
    )

    assert result == {
        "recorded": True,
        "receipt_id": receipt_id,
        "outcome": "useful_hit",
        "verification": "frontier_review",
        "payload_stored": False,
    }
    summary = ledger.summary(server._utc_today())
    assert summary["outcomes"]["useful_hit"] == 1
    assert summary["counts"]["items_reviewed"] == 3


def test_retry_delay_honors_and_caps_retry_after() -> None:
    response = httpx.Response(429, headers={"retry-after": "2.5"})
    assert server._retry_delay_seconds(response, 0) == 2.5

    capped = httpx.Response(529, headers={"retry-after": "999"})
    assert server._retry_delay_seconds(capped, 0) == server.MAX_RETRY_DELAY_SECONDS


def test_retry_delay_falls_back_for_invalid_header() -> None:
    response = httpx.Response(429, headers={"retry-after": "later"})
    assert server._retry_delay_seconds(response, 2) == 1.0


def test_budget_preflight_reserves_projected_call_cost(tmp_path: Path) -> None:
    budget = server.DailyBudget()
    budget.path = tmp_path / "usage.json"
    budget.limit = 0.000001

    async def scenario() -> None:
        await budget.preflight(1)
        with pytest.raises(RuntimeError, match="would exceed"):
            await budget.preflight(100)

    asyncio.run(scenario())


@pytest.mark.parametrize("value", ["not-a-number", "NaN", "Infinity", "-0.01"])
def test_daily_budget_rejects_invalid_limit_environment(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JEV_DAILY_BUDGET_USD", value)
    with pytest.raises(ValueError, match="finite non-negative"):
        server.DailyBudget()


@pytest.mark.parametrize(
    "ledger_text",
    [
        "{not-json}\n",
        '{"date":"2030-01-01","spent_usd":NaN,"requests":1}\n',
        '{"date":"2030-01-01","spent_usd":1e999,"requests":1}\n',
        '{"date":"2030-01-01","spent_usd":-1,"requests":1}\n',
        '{"date":"2030-01-01","spent_usd":0.1,"requests":false}\n',
    ],
)
def test_daily_budget_rejects_malformed_or_non_finite_ledger(
    ledger_text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_utc_today", lambda: date(2030, 1, 1))
    path = tmp_path / "usage.json"
    path.write_text(ledger_text, encoding="utf-8")
    daily_budget = server.DailyBudget()
    daily_budget.path = path

    with pytest.raises(RuntimeError, match="budget ledger"):
        daily_budget._load()
    assert path.read_text(encoding="utf-8") == ledger_text


@pytest.mark.parametrize(
    ("questions", "answers", "usage"),
    [
        (
            {
                "route": {
                    "type": "choice",
                    "instructions": "Choose a route",
                    "criteria": {"one": "First", "two": "Second"},
                }
            },
            {
                "route": {
                    "type": "choice",
                    "choice": [],
                    "probabilities": {"one": 0.5, "two": 0.5},
                    "confidence": 0.5,
                }
            },
            {"input_tokens": 1, "output_tokens": 0},
        ),
        (
            {"answer": {"type": "noul", "instructions": "Answer?"}},
            {"answer": {"type": "noul", "noul": 10**1000}},
            {"input_tokens": 1, "output_tokens": 0},
        ),
        (
            {"answer": {"type": "noul", "instructions": "Answer?"}},
            {"answer": {"type": "noul", "noul": 0.5}},
            {"input_tokens": 10**100, "output_tokens": 0},
        ),
    ],
)
def test_malformed_http_2xx_is_charged_once_and_receipted_once(
    questions: dict[str, dict[str, object]],
    answers: dict[str, dict[str, object]],
    usage: dict[str, int],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daily_budget = _configure_runtime_test_stores(tmp_path, monkeypatch)
    calls = _install_provider_json_stub(
        monkeypatch,
        {
            "model": server.PINNED_MODEL,
            "answers": answers,
            "usage": usage,
        },
    )
    state = {"fixture": True}
    payload = {
        "model": server.PINNED_MODEL,
        "state": state,
        "questions": questions,
    }
    expected_input_tokens = len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )

    with pytest.raises(ToolError, match="HTTP 2xx response failed schema validation"):
        asyncio.run(server.jev_decide("synthetic", state, questions))

    assert len(calls) == 1
    usage = json.loads(daily_budget.path.read_text(encoding="utf-8"))
    assert usage["requests"] == 1
    receipt_path = next((tmp_path / "receipts").glob("*.jsonl"))
    records = [json.loads(line) for line in receipt_path.read_text().splitlines()]
    assert len(records) == 1
    receipt = records[0]
    assert receipt["status"] == "provider_error"
    assert receipt["attempts"] == 1
    assert receipt["input_tokens"] == expected_input_tokens
    assert receipt["cost"] == pytest.approx(usage["spent_usd"])


def test_malformed_http_2xx_receipt_retains_retry_attempt_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daily_budget = _configure_runtime_test_stores(tmp_path, monkeypatch)
    real_async_client = httpx.AsyncClient
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "model": server.PINNED_MODEL,
                "answers": {
                    "route": {
                        "type": "choice",
                        "choice": {},
                        "probabilities": {"one": 0.5, "two": 0.5},
                        "confidence": 0.5,
                    }
                },
                "usage": {"input_tokens": 1, "output_tokens": 0},
            },
        )

    transport = httpx.MockTransport(handler)

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        return real_async_client(transport=transport, timeout=30.0, trust_env=False)

    async def no_delay(seconds: float) -> None:
        return None

    monkeypatch.setattr(server.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(server.asyncio, "sleep", no_delay)
    questions = {
        "route": {
            "type": "choice",
            "instructions": "Choose a route",
            "criteria": {"one": "First", "two": "Second"},
        }
    }

    with pytest.raises(ToolError, match="failed schema validation"):
        asyncio.run(server.jev_decide("synthetic", "fixture", questions))

    assert len(calls) == 2
    assert json.loads(daily_budget.path.read_text())["requests"] == 1
    receipt_path = next((tmp_path / "receipts").glob("*.jsonl"))
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "provider_error"
    assert receipt["attempts"] == 2


def test_corrupt_receipt_store_blocks_upstream_without_modifying_damage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_runtime_test_stores(tmp_path, monkeypatch)
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir(mode=0o700)
    corrupt = receipt_dir / f"{server._utc_today().isoformat()}.jsonl"
    corrupt.write_bytes(b'{"corrupt":true}\n')
    os.chmod(corrupt, 0o600)
    original = corrupt.read_bytes()
    calls = _install_provider_json_stub(
        monkeypatch,
        {
            "model": server.PINNED_MODEL,
            "answers": {"answer": {"type": "noul", "noul": 0.5}},
            "usage": {"input_tokens": 1, "output_tokens": 0},
        },
    )
    questions = {"answer": {"type": "noul", "instructions": "Answer?"}}

    for _ in range(2):
        with pytest.raises(ToolError, match="runtime storage is unavailable"):
            asyncio.run(server.jev_decide("synthetic", "fixture", questions))

    assert calls == []
    assert corrupt.read_bytes() == original


def test_provider_success_receipt_failure_latches_until_explicit_reinitialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daily_budget = _configure_runtime_test_stores(tmp_path, monkeypatch)
    server._reinitialize_runtime_stores()
    ledger = server._receipt_ledger()

    def fail_receipt(*args: object, **kwargs: object) -> str:
        raise OSError("simulated receipt write failure")

    monkeypatch.setattr(ledger, "record_decision", fail_receipt)
    calls = _install_provider_json_stub(
        monkeypatch,
        {
            "model": server.PINNED_MODEL,
            "answers": {"answer": {"type": "noul", "noul": 0.5}},
            "usage": {"input_tokens": 7, "output_tokens": 1},
        },
    )
    questions = {"answer": {"type": "noul", "instructions": "Answer?"}}

    with pytest.raises(ToolError, match=r"local persistence failure.*attempts=1.*estimated_cost_usd"):
        asyncio.run(server.jev_decide("synthetic", "fixture", questions))
    assert json.loads(daily_budget.path.read_text())["requests"] == 1

    with pytest.raises(ToolError, match="runtime storage is unavailable"):
        asyncio.run(server.jev_decide("synthetic", "fixture", questions))
    assert len(calls) == 1

    server._reinitialize_runtime_stores()
    result = asyncio.run(server.jev_decide("synthetic", "fixture", questions))
    assert len(calls) == 2
    assert "receipt_id" in result
    assert json.loads(daily_budget.path.read_text())["requests"] == 2


def test_provider_success_budget_failure_records_truthful_internal_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daily_budget = _configure_runtime_test_stores(tmp_path, monkeypatch)
    server._reinitialize_runtime_stores()

    async def fail_budget_record(input_tokens: int) -> float:
        raise OSError("simulated budget write failure")

    monkeypatch.setattr(daily_budget, "record", fail_budget_record)
    calls = _install_provider_json_stub(
        monkeypatch,
        {
            "model": server.PINNED_MODEL,
            "answers": {"answer": {"type": "noul", "noul": 0.5}},
            "usage": {"input_tokens": 7, "output_tokens": 1},
        },
    )
    questions = {"answer": {"type": "noul", "instructions": "Answer?"}}

    with pytest.raises(ToolError, match=r"local persistence failure.*attempts=1"):
        asyncio.run(server.jev_decide("synthetic", "fixture", questions))

    assert len(calls) == 1
    receipt_path = next((tmp_path / "receipts").glob("*.jsonl"))
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "internal_error"
    assert receipt["attempts"] == 1
    assert receipt["input_tokens"] == 7
    assert receipt["output_tokens"] == 1
    assert receipt["cost"] == pytest.approx(7 * server.INPUT_TOKEN_COST_USD)


def test_windows_launcher_resolves_relative_python_before_changing_directory() -> None:
    launcher = (Path(__file__).parents[1] / "deploy" / "run-windows.ps1").read_text()
    assert "$PythonExecutable" in launcher
    assert launcher.index("$PythonExecutable") < launcher.index("Push-Location")
    assert "& $PythonExecutable $ServerScript" in launcher


def test_paid_call_wrapper_serializes_concurrent_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    active = 0
    maximum_active = 0

    async def fake_serialized(payload: dict[str, object]) -> dict[str, object]:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {"payload": payload}

    async def scenario() -> None:
        monkeypatch.setattr(server, "paid_call_lock", asyncio.Lock())
        monkeypatch.setattr(server, "_call_jev_serialized", fake_serialized)
        await asyncio.gather(server._call_jev({"id": 1}), server._call_jev({"id": 2}))

    asyncio.run(scenario())
    assert maximum_active == 1


def test_provider_failure_receipt_preserves_attempts_and_conservative_cost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = server.ReceiptLedger(
        tmp_path / "receipts", b"0123456789abcdef0123456789abcdef"
    )
    monkeypatch.setattr(server, "_receipt_ledger_instance", ledger)

    async def fail(payload: dict[str, object]) -> dict[str, object]:
        raise server.JevProviderFailure(
            "malformed success",
            attempts=3,
            latency_ms=17.5,
            input_tokens=321,
            cost=0.000013482,
        )

    monkeypatch.setattr(server, "_call_jev", fail)
    with pytest.raises(RuntimeError, match="malformed success"):
        asyncio.run(
            server._call_with_receipt(
                "jev_batch_check",
                "synthetic",
                2,
                {
                    "model": server.PINNED_MODEL,
                    "state": {"fixture": True},
                    "questions": {"one": {"type": "noul", "instructions": "One?"}},
                },
            )
        )

    path = next((tmp_path / "receipts").glob("*.jsonl"))
    record = json.loads(path.read_text())
    assert record["status"] == "provider_error"
    assert record["attempts"] == 3
    assert record["input_tokens"] == 321
    assert record["cost"] == pytest.approx(0.000013482)
