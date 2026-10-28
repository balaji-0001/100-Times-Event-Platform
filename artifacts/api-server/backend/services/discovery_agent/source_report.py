"""Per-run execution record of every selected discovery source.

States are kept separate on purpose: a source can be selected but not
configured, configured but skipped (budget, geography, target already met),
executed and failed, or executed successfully with zero results — and the
summary counts each state from what actually happened in the run, never from
the settings alone.

Kinds: search_provider | adapter | aggregator | custom_website | api.
Status: pending -> skipped | succeeded | failed (a source with some failed
and some successful calls is "succeeded" with its errors kept).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SourceRecord:
    id: str
    name: str
    channel: str
    kind: str
    configured: bool = True
    available: bool = True  # configured and its prerequisites met when the run started
    status: str = "pending"
    reason: str | None = None  # skip reason
    jobs: int = 0
    jobs_ok: int = 0
    jobs_failed: int = 0
    candidates: int = 0
    off_sector: int = 0
    duplicates: int = 0
    rejected: int = 0
    verified: int = 0
    needs_review: int = 0
    duration_ms: float = 0.0
    started_at: str | None = None
    finished_at: str | None = None
    errors: list[str] = field(default_factory=list)
    # Search providers only.
    calls: int = 0
    results: int = 0
    zero_result_calls: int = 0
    rate_limited: int = 0
    cost_usd: float | None = None
    skipped_reasons: dict[str, int] = field(default_factory=dict)
    purposes: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        out = dict(self.__dict__)
        out["duration_ms"] = round(self.duration_ms, 1)
        return out


class RunSourceReport:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.records: dict[str, SourceRecord] = {}

    def add(self, source_id: str, name: str, channel: str, kind: str, configured: bool = True, available: bool | None = None) -> SourceRecord:
        with self._lock:
            record = self.records.get(source_id)
            if record is None:
                record = self.records[source_id] = SourceRecord(
                    id=source_id, name=name, channel=channel, kind=kind, configured=configured,
                    available=configured if available is None else (configured and available),
                )
            return record

    def skip(self, source_id: str, name: str, channel: str, kind: str, reason: str, configured: bool = True, available: bool | None = None) -> None:
        record = self.add(source_id, name, channel, kind, configured, available)
        with self._lock:
            if record.status == "pending":
                record.status, record.reason = "skipped", reason

    def started(self, source_id: str) -> float:
        with self._lock:
            record = self.records.get(source_id)
            if record is not None and record.started_at is None:
                record.started_at = _now()
        return time.perf_counter()

    def finished(self, source_id: str, t0: float, *, ok: bool, candidates: int = 0, error: str | None = None) -> None:
        with self._lock:
            record = self.records.get(source_id)
            if record is None:
                return
            record.jobs += 1
            record.duration_ms += (time.perf_counter() - t0) * 1000
            record.finished_at = _now()
            if ok:
                record.jobs_ok += 1
                record.candidates += candidates
            else:
                record.jobs_failed += 1
                if error and len(record.errors) < 3 and error not in record.errors:
                    record.errors.append(error[:300])
            record.status = "succeeded" if record.jobs_ok else "failed"
            record.reason = None

    def outcome(self, source_id: str | None, field_name: str, amount: int = 1) -> None:
        """Count what happened downstream to a candidate from this source."""
        if not source_id or not amount:
            return
        with self._lock:
            record = self.records.get(source_id)
            if record is not None:
                setattr(record, field_name, getattr(record, field_name) + amount)

    def add_candidates(self, source_id: str | None, amount: int) -> None:
        self.outcome(source_id, "candidates", amount)

    def merge_search_stats(self, snapshot: dict[str, dict[str, Any]]) -> None:
        """Fold the run's per-provider search accounting into provider records."""
        with self._lock:
            for pid, row in snapshot.items():
                record = self.records.get(pid)
                if record is None:
                    continue
                record.calls = row["calls"]
                record.results = row["results"]
                record.zero_result_calls = row["zero_result_calls"]
                record.rate_limited = row["rate_limited"]
                record.cost_usd = row["cost_usd"]
                record.skipped_reasons = row["skipped"]
                record.purposes = row["purposes"]
                record.duration_ms = row["latency_ms"]
                record.started_at, record.finished_at = row["first_call_at"], row["last_call_at"]
                record.jobs, record.jobs_ok, record.jobs_failed = row["calls"], row["successes"], row["failures"]
                if row["last_error"] and row["last_error"] not in record.errors:
                    record.errors.append(row["last_error"][:300])
                if row["calls"]:
                    record.status = "succeeded" if row["successes"] else "failed"
                    record.reason = None
                elif record.status == "pending":
                    record.status = "skipped"
                    reasons = row["skipped"]
                    record.reason = max(reasons, key=reasons.get) if reasons else "not needed in this run"

    def close(self, stop_reason: str | None) -> None:
        """Anything still pending never ran: say why."""
        why = {
            "target_reached": "not reached: the verified-event target was met first",
            "time_budget": "not reached: the run's time budget ran out",
            "candidate_ceiling": "not reached: the run's candidate/daily limit was hit",
            "cancelled": "not reached: the run was stopped",
        }.get(stop_reason or "", "not reached before the run ended")
        with self._lock:
            for record in self.records.values():
                if record.status == "pending":
                    record.status, record.reason = "skipped", why

    def summary(self) -> dict[str, Any]:
        with self._lock:
            records = [r.as_dict() for r in self.records.values()]
        executed = [r for r in records if r["jobs"]]
        return {
            "counts": {
                "selected": len(records),
                "configured": sum(1 for r in records if r["configured"]),
                "available": sum(1 for r in records if r["available"]),
                "executed": len(executed),
                "successful": sum(1 for r in executed if r["jobs_ok"]),
                "returned_candidates": sum(r["candidates"] for r in records),
                "sources_with_candidates": sum(1 for r in records if r["candidates"]),
                "succeeded_zero_results": sum(1 for r in executed if r["jobs_ok"] and not r["candidates"] and not r["results"]),
                "failed": sum(1 for r in executed if not r["jobs_ok"]),
                "skipped": sum(1 for r in records if r["status"] == "skipped"),
                "verified": sum(r["verified"] for r in records),
            },
            "sources": sorted(records, key=lambda r: (_CHANNEL_ORDER.get(r["channel"], 9), r["status"] != "succeeded", r["name"].lower())),
        }


_CHANNEL_ORDER = {"web": 0, "directories": 1, "aggregators": 2, "custom": 3, "apis": 4}
