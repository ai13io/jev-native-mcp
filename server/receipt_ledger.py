"""Request-body-free, locally authenticated decision receipts for Jev.

The ledger stores a keyed digest of each canonical request plus a closed set of
operational metadata. Its HMAC-linked events detect modification or reordering
when the file is read from the beginning. There is no authenticated external
head, so deletion of an entire file or truncation of its final events is outside
that guarantee. The implementation is synchronous so the MCP server can call it
while holding its paid-request lock.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date as date_type
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
from typing import Any, Iterable
from uuid import UUID, uuid4


ALLOWED_TOOLS = frozenset(
    {
        "jev_decide",
        "jev_rank",
        "jev_batch_check",
        "jev_claim_audit",
        "jev_select",
        "jev_signal_matrix",
    }
)
ALLOWED_DATA_CLASSES = frozenset({"public", "synthetic"})
ALLOWED_STATUSES = frozenset(
    {
        "success",
        "validation_error",
        "provider_error",
        "budget_rejected",
        "internal_error",
    }
)
ALLOWED_OUTCOMES = frozenset(
    {"useful_hit", "false_positive", "false_negative", "no_value", "unverified"}
)
ALLOWED_VERIFICATIONS = frozenset(
    {"human", "deterministic", "runtime", "frontier_review", "unverified"}
)

_VERSION_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+@-]{0,127}$")
_HMAC_HEX = re.compile(r"^[0-9a-f]{64}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_DECISION_KEYS = frozenset(
    {
        "schema_version",
        "event",
        "timestamp",
        "receipt_id",
        "request_hmac",
        "tool",
        "data_class",
        "model_version",
        "server_version",
        "backend_version",
        "contract_version",
        "candidate_count",
        "question_count",
        "input_tokens",
        "output_tokens",
        "cost",
        "latency",
        "attempts",
        "status",
        "cache_hit",
        "previous_event_hmac",
        "event_hmac",
    }
)
_OUTCOME_KEYS = frozenset(
    {
        "schema_version",
        "event",
        "timestamp",
        "receipt_id",
        "outcome",
        "verification",
        "items_reviewed",
        "useful_items",
        "seconds_saved",
        "previous_event_hmac",
        "event_hmac",
    }
)


class LedgerCorruptionError(RuntimeError):
    """Raised when an existing ledger is not a valid receipt event stream."""


def _require_enum(value: object, allowed: frozenset[str], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{field} must be one of: {', '.join(sorted(allowed))}")
    return value


def _require_version_token(value: object, field: str) -> str:
    if not isinstance(value, str) or _VERSION_TOKEN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a bounded version token")
    return value


def _require_nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _require_nonnegative_finite(value: object, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a non-negative finite number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field} must be a non-negative finite number")
    return value


def _require_uuid(value: object, field: str = "receipt_id") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a UUID string")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{field} must be a UUID string") from exc
    if str(parsed) != value.lower():
        raise ValueError(f"{field} must use canonical UUID form")
    return str(parsed)


def _require_timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise LedgerCorruptionError("ledger timestamp is not a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LedgerCorruptionError("ledger timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise LedgerCorruptionError("ledger timestamp lacks a timezone")
    return value


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _date_string(value: str | date_type) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date_type):
        return value.isoformat()
    if not isinstance(value, str) or _DATE.fullmatch(value) is None:
        raise ValueError("date must be YYYY-MM-DD")
    try:
        parsed = date_type.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError("date must be YYYY-MM-DD")
    return value


def _uses_posix_permissions() -> bool:
    return os.name == "posix"


class ReceiptLedger:
    """Synchronous HMAC-linked ledger that stores no request or evidence body."""

    def __init__(self, base_dir: str | os.PathLike[str], hmac_key: bytes) -> None:
        self.base_dir = Path(base_dir)
        if not isinstance(hmac_key, bytes) or len(hmac_key) < 32:
            raise ValueError("hmac_key must contain at least 32 bytes")
        self._hmac_key = hmac_key
        self._lock = threading.RLock()
        self._ensure_base_dir()
        # Fail immediately if a pre-existing ledger is corrupt.
        with self._lock:
            for path in sorted(self.base_dir.glob("*.jsonl")):
                self._validate_filename(path)
                tuple(self._read_records(path))

    def record_decision(
        self,
        *,
        tool: str,
        data_class: str,
        model_version: str,
        server_version: str,
        backend_version: str,
        contract_version: str,
        candidate_count: int,
        question_count: int,
        input_tokens: int,
        output_tokens: int,
        cost: int | float,
        latency: int | float,
        attempts: int,
        status: str,
        cache_hit: bool,
        canonical_request: bytes,
    ) -> str:
        """Append one decision receipt and return its generated receipt UUID."""

        tool = _require_enum(tool, ALLOWED_TOOLS, "tool")
        data_class = _require_enum(data_class, ALLOWED_DATA_CLASSES, "data_class")
        status = _require_enum(status, ALLOWED_STATUSES, "status")
        model_version = _require_version_token(model_version, "model_version")
        server_version = _require_version_token(server_version, "server_version")
        backend_version = _require_version_token(backend_version, "backend_version")
        contract_version = _require_version_token(contract_version, "contract_version")
        candidate_count = _require_nonnegative_int(candidate_count, "candidate_count")
        question_count = _require_nonnegative_int(question_count, "question_count")
        input_tokens = _require_nonnegative_int(input_tokens, "input_tokens")
        output_tokens = _require_nonnegative_int(output_tokens, "output_tokens")
        cost = _require_nonnegative_finite(cost, "cost")
        latency = _require_nonnegative_finite(latency, "latency")
        attempts = _require_nonnegative_int(attempts, "attempts")
        if not isinstance(cache_hit, bool):
            raise ValueError("cache_hit must be a boolean")
        if not isinstance(canonical_request, bytes):
            raise ValueError("canonical_request must be bytes")

        receipt_id = str(uuid4())
        event = {
            "event": "decision",
            "timestamp": _utc_timestamp(),
            "receipt_id": receipt_id,
            "request_hmac": hmac.new(
                self._hmac_key, canonical_request, hashlib.sha256
            ).hexdigest(),
            "tool": tool,
            "data_class": data_class,
            "model_version": model_version,
            "server_version": server_version,
            "backend_version": backend_version,
            "contract_version": contract_version,
            "candidate_count": candidate_count,
            "question_count": question_count,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "latency": latency,
            "attempts": attempts,
            "status": status,
            "cache_hit": cache_hit,
        }
        self._append(event)
        return receipt_id

    def record_outcome(
        self,
        receipt_id: str,
        outcome: str,
        verification: str,
        items_reviewed: int,
        useful_items: int,
        seconds_saved: int | float,
    ) -> None:
        """Append a structured human-review outcome without any free text."""

        receipt_id = _require_uuid(receipt_id)
        outcome = _require_enum(outcome, ALLOWED_OUTCOMES, "outcome")
        verification = _require_enum(
            verification, ALLOWED_VERIFICATIONS, "verification"
        )
        items_reviewed = _require_nonnegative_int(items_reviewed, "items_reviewed")
        useful_items = _require_nonnegative_int(useful_items, "useful_items")
        if useful_items > items_reviewed:
            raise ValueError("useful_items cannot exceed items_reviewed")
        seconds_saved = _require_nonnegative_finite(seconds_saved, "seconds_saved")

        with self._lock:
            decision_exists = False
            successful_decision_exists = False
            outcome_exists = False
            for path in sorted(self.base_dir.glob("*.jsonl")):
                for record in self._read_records(path):
                    if record["receipt_id"] != receipt_id:
                        continue
                    decision_exists |= record["event"] == "decision"
                    successful_decision_exists |= (
                        record["event"] == "decision" and record["status"] == "success"
                    )
                    outcome_exists |= record["event"] == "outcome"
            if not decision_exists:
                raise ValueError("receipt_id does not reference a recorded decision")
            if not successful_decision_exists:
                raise ValueError("receipt_id does not reference a successful decision")
            if outcome_exists:
                raise ValueError("receipt_id already has an outcome")
            self._append(
                {
                    "event": "outcome",
                    "timestamp": _utc_timestamp(),
                    "receipt_id": receipt_id,
                    "outcome": outcome,
                    "verification": verification,
                    "items_reviewed": items_reviewed,
                    "useful_items": useful_items,
                    "seconds_saved": seconds_saved,
                }
            )

    def summary(self, date: str | date_type) -> dict[str, Any]:
        """Return aggregates for a UTC calendar date without returning ledger rows."""

        day = _date_string(date)
        path = self.base_dir / f"{day}.jsonl"
        with self._lock:
            records = tuple(self._read_records(path)) if path.exists() else ()

        decisions = 0
        total_cost_values: list[float] = []
        input_tokens = 0
        output_tokens = 0
        by_tool: dict[str, dict[str, int | float]] = defaultdict(
            lambda: {
                "decisions": 0,
                "cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
            }
        )
        outcomes = Counter({name: 0 for name in sorted(ALLOWED_OUTCOMES)})
        by_verification = Counter(
            {name: 0 for name in sorted(ALLOWED_VERIFICATIONS)}
        )
        outcome_events = 0
        items_reviewed = 0
        useful_items = 0
        seconds_saved_values: list[float] = []

        for record in records:
            if record["event"] == "decision":
                decisions += 1
                total_cost_values.append(float(record["cost"]))
                input_tokens += record["input_tokens"]
                output_tokens += record["output_tokens"]
                tool_summary = by_tool[record["tool"]]
                tool_summary["decisions"] += 1
                tool_summary["cost"] += float(record["cost"])
                tool_summary["input_tokens"] += record["input_tokens"]
                tool_summary["output_tokens"] += record["output_tokens"]
            else:
                outcome_events += 1
                outcomes[record["outcome"]] += 1
                by_verification[record["verification"]] += 1
                items_reviewed += record["items_reviewed"]
                useful_items += record["useful_items"]
                seconds_saved_values.append(float(record["seconds_saved"]))

        normalized_by_tool = {
            tool: {
                **values,
                "cost": round(float(values["cost"]), 10),
            }
            for tool, values in sorted(by_tool.items())
        }
        return {
            "date": day,
            "counts": {
                "decisions": decisions,
                "outcome_events": outcome_events,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "items_reviewed": items_reviewed,
                "useful_items": useful_items,
                "seconds_saved": round(math.fsum(seconds_saved_values), 3),
            },
            "cost": round(math.fsum(total_cost_values), 10),
            "by_tool": normalized_by_tool,
            "outcomes": dict(sorted(outcomes.items())),
            "by_verification": dict(sorted(by_verification.items())),
        }

    def validate_store(self) -> None:
        """Validate existing ledgers and prove the directory accepts a new file."""

        with self._lock:
            self._ensure_base_dir()
            for path in sorted(self.base_dir.glob("*.jsonl")):
                self._validate_filename(path)
                tuple(self._read_records(path))
            probe = self.base_dir / f".write-probe-{uuid4().hex}"
            descriptor: int | None = None
            try:
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
                flags |= getattr(os, "O_CLOEXEC", 0)
                flags |= getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(probe, flags, 0o600)
                if _uses_posix_permissions():
                    os.fchmod(descriptor, 0o600)
                os.fsync(descriptor)
            finally:
                if descriptor is not None:
                    os.close(descriptor)
                probe.unlink(missing_ok=True)

    def _ensure_base_dir(self) -> None:
        if self.base_dir.is_symlink():
            raise ValueError("ledger base directory must not be a symlink")
        existed = self.base_dir.exists()
        self.base_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.base_dir.is_symlink() or not self.base_dir.is_dir():
            raise ValueError("ledger base path must be a directory")
        if _uses_posix_permissions():
            mode = stat.S_IMODE(self.base_dir.stat().st_mode)
            if existed and mode != 0o700:
                raise ValueError("ledger base directory permissions are not 0700")
            if not existed:
                os.chmod(self.base_dir, 0o700)

    def _path_for_now(self) -> Path:
        return self.base_dir / f"{datetime.now(timezone.utc).date().isoformat()}.jsonl"

    def _append(self, event: dict[str, Any]) -> None:
        path = self._path_for_now()
        with self._lock:
            self._ensure_base_dir()
            existing: tuple[dict[str, Any], ...] = ()
            if path.exists():
                existing = tuple(self._read_records(path))
            if path.is_symlink():
                raise ValueError("ledger file must not be a symlink")
            previous_event_hmac = (
                existing[-1]["event_hmac"] if existing else "0" * 64
            )
            authenticated_event = {
                "schema_version": 2,
                **event,
                "previous_event_hmac": previous_event_hmac,
            }
            authenticated_event["event_hmac"] = hmac.new(
                self._hmac_key,
                json.dumps(
                    authenticated_event,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            encoded = (
                json.dumps(
                    authenticated_event,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
            flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags, 0o600)
            try:
                if _uses_posix_permissions():
                    os.fchmod(descriptor, 0o600)
                written = os.write(descriptor, encoded)
                if written != len(encoded):
                    raise OSError("short ledger append")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    @staticmethod
    def _validate_filename(path: Path) -> None:
        if path.is_symlink() or not path.is_file():
            raise LedgerCorruptionError("ledger entry is not a regular file")
        if _DATE.fullmatch(path.stem) is None:
            raise LedgerCorruptionError("ledger filename is not a UTC date")
        try:
            if date_type.fromisoformat(path.stem).isoformat() != path.stem:
                raise ValueError
        except ValueError as exc:
            raise LedgerCorruptionError("ledger filename is not a UTC date") from exc

    def _read_records(self, path: Path) -> Iterable[dict[str, Any]]:
        self._validate_filename(path)
        if _uses_posix_permissions():
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode != 0o600:
                raise LedgerCorruptionError("ledger file permissions are not 0600")
        previous_event_hmac = "0" * 64
        with path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if not raw_line.endswith(b"\n"):
                    raise LedgerCorruptionError(
                        f"ledger line {line_number} is not newline-terminated"
                    )
                try:
                    record = json.loads(raw_line)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise LedgerCorruptionError(
                        f"ledger line {line_number} is not valid JSON"
                    ) from exc
                try:
                    self._validate_record(record, previous_event_hmac)
                except (TypeError, ValueError, LedgerCorruptionError) as exc:
                    raise LedgerCorruptionError(
                        f"ledger line {line_number} has an invalid schema"
                    ) from exc
                previous_event_hmac = record["event_hmac"]
                yield record

    def _validate_record(self, record: object, expected_previous_hmac: str) -> None:
        if not isinstance(record, dict):
            raise LedgerCorruptionError("ledger event is not an object")
        if record.get("schema_version") != 2:
            raise LedgerCorruptionError("ledger schema_version is not 2")
        previous_event_hmac = record.get("previous_event_hmac")
        event_hmac = record.get("event_hmac")
        if (
            not isinstance(previous_event_hmac, str)
            or _HMAC_HEX.fullmatch(previous_event_hmac) is None
            or previous_event_hmac != expected_previous_hmac
        ):
            raise LedgerCorruptionError("ledger HMAC chain is broken")
        if not isinstance(event_hmac, str) or _HMAC_HEX.fullmatch(event_hmac) is None:
            raise LedgerCorruptionError("event_hmac is invalid")
        authenticated = {key: value for key, value in record.items() if key != "event_hmac"}
        expected_event_hmac = hmac.new(
            self._hmac_key,
            json.dumps(
                authenticated,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(event_hmac, expected_event_hmac):
            raise LedgerCorruptionError("ledger event HMAC does not verify")
        event_type = record.get("event")
        if event_type == "decision":
            if frozenset(record) != _DECISION_KEYS:
                raise LedgerCorruptionError("decision event fields do not match schema")
            _require_timestamp(record["timestamp"])
            _require_uuid(record["receipt_id"])
            if not isinstance(record["request_hmac"], str) or _HMAC_HEX.fullmatch(
                record["request_hmac"]
            ) is None:
                raise LedgerCorruptionError("request_hmac is invalid")
            _require_enum(record["tool"], ALLOWED_TOOLS, "tool")
            _require_enum(record["data_class"], ALLOWED_DATA_CLASSES, "data_class")
            _require_enum(record["status"], ALLOWED_STATUSES, "status")
            for field in (
                "model_version",
                "server_version",
                "backend_version",
                "contract_version",
            ):
                _require_version_token(record[field], field)
            for field in (
                "candidate_count",
                "question_count",
                "input_tokens",
                "output_tokens",
                "attempts",
            ):
                _require_nonnegative_int(record[field], field)
            _require_nonnegative_finite(record["cost"], "cost")
            _require_nonnegative_finite(record["latency"], "latency")
            if not isinstance(record["cache_hit"], bool):
                raise ValueError("cache_hit must be a boolean")
            return
        if event_type == "outcome":
            if frozenset(record) != _OUTCOME_KEYS:
                raise LedgerCorruptionError("outcome event fields do not match schema")
            _require_timestamp(record["timestamp"])
            _require_uuid(record["receipt_id"])
            _require_enum(record["outcome"], ALLOWED_OUTCOMES, "outcome")
            _require_enum(
                record["verification"], ALLOWED_VERIFICATIONS, "verification"
            )
            reviewed = _require_nonnegative_int(record["items_reviewed"], "items_reviewed")
            useful = _require_nonnegative_int(record["useful_items"], "useful_items")
            if useful > reviewed:
                raise ValueError("useful_items cannot exceed items_reviewed")
            _require_nonnegative_finite(record["seconds_saved"], "seconds_saved")
            return
        raise LedgerCorruptionError("unknown ledger event type")
