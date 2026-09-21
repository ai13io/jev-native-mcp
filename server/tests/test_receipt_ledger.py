from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import stat
from uuid import UUID

import pytest

import receipt_ledger as receipt_ledger_module
from receipt_ledger import LedgerCorruptionError, ReceiptLedger


HMAC_KEY = b"0123456789abcdef0123456789abcdef"


def decision_args(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "tool": "jev_batch_check",
        "data_class": "public",
        "model_version": "jev-1.13.0",
        "server_version": "0.3.0",
        "backend_version": "typesafe-v1",
        "contract_version": "batch-v1",
        "candidate_count": 4,
        "question_count": 5,
        "input_tokens": 120,
        "output_tokens": 30,
        "cost": 0.00000504,
        "latency": 0.42,
        "attempts": 1,
        "status": "success",
        "cache_hit": False,
        "canonical_request": b'{"public":"request"}',
    }
    values.update(overrides)
    return values


def today_path(base: Path) -> Path:
    day = datetime.now(timezone.utc).date().isoformat()
    return base / f"{day}.jsonl"


def new_ledger(base: Path) -> ReceiptLedger:
    return ReceiptLedger(base, HMAC_KEY)


def test_decision_receipt_never_stores_request_content(tmp_path: Path) -> None:
    marker = b"UNIQUE-SHOULD-NEVER-APPEAR-IN-THE-LEDGER-7a192f"
    ledger = new_ledger(tmp_path / "receipts")

    receipt_id = ledger.record_decision(
        **decision_args(canonical_request=b'{"prompt":"' + marker + b'"}')
    )

    raw = today_path(tmp_path / "receipts").read_bytes()
    assert marker not in raw
    assert b"prompt" not in raw
    assert receipt_id.encode() in raw
    record = json.loads(raw)
    assert len(record["request_hmac"]) == 64
    assert "canonical_request" not in record
    assert "hmac_key" not in record


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits are not available")
def test_storage_permissions_are_private_and_never_auto_repaired(tmp_path: Path) -> None:
    base = tmp_path / "receipts"
    ledger = new_ledger(base)
    assert stat.S_IMODE(base.stat().st_mode) == 0o700

    ledger.record_decision(**decision_args())
    path = today_path(base)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    os.chmod(base, 0o755)
    with pytest.raises(ValueError, match="permissions are not 0700"):
        ledger.record_decision(**decision_args())
    assert stat.S_IMODE(base.stat().st_mode) == 0o755


def test_windows_permission_path_does_not_require_chmod_or_fchmod(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(receipt_ledger_module, "_uses_posix_permissions", lambda: False)

    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("POSIX permission function called")

    monkeypatch.setattr(receipt_ledger_module.os, "chmod", fail_if_called)
    monkeypatch.setattr(receipt_ledger_module.os, "fchmod", fail_if_called, raising=False)

    base = tmp_path / "windows-receipts"
    ledger = new_ledger(base)
    receipt_id = ledger.record_decision(**decision_args())
    assert receipt_id
    reopened = new_ledger(base)
    assert reopened.summary(datetime.now(timezone.utc).date())["counts"]["decisions"] == 1


def test_append_writes_separate_decision_and_outcome_events(tmp_path: Path) -> None:
    ledger = new_ledger(tmp_path / "receipts")
    receipt_id = ledger.record_decision(**decision_args())
    ledger.record_outcome(receipt_id, "useful_hit", "human", 4, 2, 90.0)

    records = [json.loads(line) for line in today_path(tmp_path / "receipts").read_text().splitlines()]
    assert [record["event"] for record in records] == ["decision", "outcome"]
    assert records[0]["receipt_id"] == receipt_id
    assert records[1]["event"] == "outcome"
    assert records[1]["items_reviewed"] == 4
    assert records[1]["outcome"] == "useful_hit"
    assert records[1]["verification"] == "human"
    assert records[1]["receipt_id"] == receipt_id
    assert records[1]["seconds_saved"] == 90.0
    assert records[1]["useful_items"] == 2
    assert records[1]["previous_event_hmac"] == records[0]["event_hmac"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tool", "other_tool"),
        ("data_class", "private"),
        ("status", "maybe"),
        ("cost", -0.1),
        ("latency", math.inf),
        ("input_tokens", -1),
        ("attempts", True),
        ("canonical_request", "not-bytes"),
        ("model_version", "version with spaces"),
        ("backend_version", "../../secret"),
    ],
)
def test_invalid_decision_is_rejected(tmp_path: Path, field: str, value: object) -> None:
    ledger = new_ledger(tmp_path / "receipts")
    with pytest.raises(ValueError):
        ledger.record_decision(**decision_args(**{field: value}))


def test_ledger_rejects_short_hmac_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        ReceiptLedger(tmp_path / "receipts", b"short")


@pytest.mark.parametrize(
    "args",
    [
        ("not-a-uuid", "useful_hit", "human", 1, 1, 1.0),
        ("5fd6ccab-7fda-45bc-a979-250250270000", "unknown", "human", 1, 1, 1.0),
        ("5fd6ccab-7fda-45bc-a979-250250270000", "useful_hit", "unknown", 1, 1, 1.0),
        ("5fd6ccab-7fda-45bc-a979-250250270000", "useful_hit", "human", -1, 0, 1.0),
        ("5fd6ccab-7fda-45bc-a979-250250270000", "useful_hit", "human", 1, 2, 1.0),
        ("5fd6ccab-7fda-45bc-a979-250250270000", "useful_hit", "human", 1, 1, math.nan),
    ],
)
def test_invalid_outcome_is_rejected(tmp_path: Path, args: tuple[object, ...]) -> None:
    ledger = new_ledger(tmp_path / "receipts")
    with pytest.raises(ValueError):
        ledger.record_outcome(*args)  # type: ignore[arg-type]


def test_outcome_requires_existing_decision_and_is_single_assignment(tmp_path: Path) -> None:
    ledger = new_ledger(tmp_path / "receipts")
    unknown = "5fd6ccab-7fda-45bc-a979-250250270000"
    with pytest.raises(ValueError, match="recorded decision"):
        ledger.record_outcome(unknown, "unverified", "unverified", 0, 0, 0.0)

    receipt_id = ledger.record_decision(**decision_args())
    ledger.record_outcome(receipt_id, "no_value", "deterministic", 4, 0, 0.0)
    with pytest.raises(ValueError, match="already has an outcome"):
        ledger.record_outcome(receipt_id, "useful_hit", "human", 4, 1, 10.0)

    failed_receipt = ledger.record_decision(
        **decision_args(status="provider_error", attempts=1)
    )
    with pytest.raises(ValueError, match="successful decision"):
        ledger.record_outcome(
            failed_receipt, "unverified", "unverified", 0, 0, 0.0
        )


def test_summary_returns_aggregates_without_rows(tmp_path: Path) -> None:
    ledger = new_ledger(tmp_path / "receipts")
    first = ledger.record_decision(**decision_args(cost=0.1, input_tokens=10, output_tokens=2))
    ledger.record_decision(
        **decision_args(
            tool="jev_claim_audit",
            cost=0.2,
            input_tokens=20,
            output_tokens=4,
            candidate_count=1,
            question_count=1,
        )
    )
    ledger.record_outcome(first, "useful_hit", "human", 4, 1, 30.0)

    day = datetime.now(timezone.utc).date().isoformat()
    summary = ledger.summary(day)

    assert summary["date"] == day
    assert summary["counts"] == {
        "decisions": 2,
        "outcome_events": 1,
        "input_tokens": 30,
        "output_tokens": 6,
        "items_reviewed": 4,
        "useful_items": 1,
        "seconds_saved": 30.0,
    }
    assert summary["cost"] == pytest.approx(0.3)
    assert summary["by_tool"]["jev_batch_check"]["decisions"] == 1
    assert summary["by_tool"]["jev_claim_audit"]["cost"] == pytest.approx(0.2)
    assert summary["outcomes"]["useful_hit"] == 1
    assert summary["by_verification"]["human"] == 1
    assert "records" not in summary
    assert first not in json.dumps(summary)


def test_corrupt_ledger_fails_loudly(tmp_path: Path) -> None:
    base = tmp_path / "receipts"
    base.mkdir(mode=0o700)
    path = today_path(base)
    path.write_text('{"event":"decision","payload":"leak"}\n')
    os.chmod(path, 0o600)

    with pytest.raises(LedgerCorruptionError):
        new_ledger(base)


def test_authenticated_chain_rejects_metadata_tampering(tmp_path: Path) -> None:
    base = tmp_path / "receipts"
    ledger = new_ledger(base)
    ledger.record_decision(**decision_args())
    path = today_path(base)
    record = json.loads(path.read_text())
    record["cost"] = 999.0
    path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    os.chmod(path, 0o600)

    with pytest.raises(LedgerCorruptionError, match="invalid schema"):
        new_ledger(base)


def test_concurrent_records_are_unique_and_valid_jsonl(tmp_path: Path) -> None:
    ledger = new_ledger(tmp_path / "receipts")

    def record(index: int) -> str:
        return ledger.record_decision(
            **decision_args(canonical_request=f'{{"index":{index}}}'.encode())
        )

    with ThreadPoolExecutor(max_workers=12) as executor:
        receipt_ids = list(executor.map(record, range(60)))

    assert len(receipt_ids) == len(set(receipt_ids)) == 60
    assert all(str(UUID(receipt_id)) == receipt_id for receipt_id in receipt_ids)
    records = [json.loads(line) for line in today_path(tmp_path / "receipts").read_text().splitlines()]
    assert len(records) == 60
    assert {record["receipt_id"] for record in records} == set(receipt_ids)
    # Reopening validates every complete event and newline.
    new_ledger(tmp_path / "receipts")
