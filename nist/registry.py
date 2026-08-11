"""SQLite registry with immutable attempts and derived canonical Detail state."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .classifier import classify_detail_response
from .client import is_allowed_solution_url
from .models import DetailStatus, HttpResponse, ResponseClassification, ResponseKind

SCHEMA_VERSION = 1


class DailyLimitReached(RuntimeError):
    pass


class MinimumDelayNotElapsed(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _utc_date(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).date().isoformat()


def _canonical_fields(fields: dict[str, str] | None) -> str:
    return json.dumps(fields or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class NistRegistry:
    """Registry whose only mutable records are reservations and canonical state."""

    def __init__(self, path: Path, archive_root: Path) -> None:
        self.path = Path(path)
        self.archive_root = Path(archive_root)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS request_reservations (
                    id INTEGER PRIMARY KEY,
                    token TEXT NOT NULL UNIQUE,
                    method TEXT NOT NULL,
                    url TEXT NOT NULL,
                    fields_json TEXT NOT NULL,
                    expected_kind TEXT NOT NULL,
                    reserved_at TEXT NOT NULL,
                    reserved_date TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_reservation_date
                    ON request_reservations(reserved_date);
                CREATE TABLE IF NOT EXISTS response_blobs (
                    sha256 TEXT PRIMARY KEY,
                    relative_path TEXT NOT NULL UNIQUE,
                    byte_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS request_attempts (
                    id INTEGER PRIMARY KEY,
                    reservation_token TEXT NOT NULL UNIQUE,
                    method TEXT NOT NULL,
                    url TEXT NOT NULL,
                    fields_json TEXT NOT NULL,
                    expected_kind TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    status_code INTEGER,
                    content_type TEXT NOT NULL DEFAULT '',
                    body_sha256 TEXT REFERENCES response_blobs(sha256),
                    classifier_outcome TEXT NOT NULL CHECK (
                        classifier_outcome IN (
                            'accepted', 'confirmed_empty', 'retryable', 'blocked', 'invalid'
                        )
                    ),
                    classifier_reason TEXT NOT NULL,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_attempt_date ON request_attempts(started_at);
                CREATE INDEX IF NOT EXISTS idx_attempt_url ON request_attempts(url);
                CREATE TABLE IF NOT EXISTS details (
                    detail_url TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK (
                        status IN (
                            'queued', 'accepted', 'confirmed_empty',
                            'retryable', 'blocked', 'invalid'
                        )
                    ),
                    accepted_attempt_id INTEGER REFERENCES request_attempts(id),
                    source_sha256 TEXT REFERENCES response_blobs(sha256),
                    last_attempt_id INTEGER REFERENCES request_attempts(id),
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_details_status ON details(status);
                CREATE TABLE IF NOT EXISTS discovery_queries (
                    query_key TEXT PRIMARY KEY,
                    method TEXT NOT NULL,
                    url TEXT NOT NULL,
                    fields_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS query_candidates (
                    query_key TEXT NOT NULL REFERENCES discovery_queries(query_key),
                    detail_url TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    PRIMARY KEY (query_key, detail_url)
                );
                """
            )
            conn.execute(
                "INSERT INTO schema_metadata(key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(SCHEMA_VERSION),),
            )

    def register_query(
        self,
        *,
        query_key: str,
        method: str,
        url: str,
        fields: dict[str, str] | None = None,
    ) -> None:
        if not query_key.strip():
            raise ValueError("NIST discovery query key must not be empty")
        normalized_method = method.strip().upper()
        if normalized_method not in {"GET", "POST"}:
            raise ValueError("NIST discovery method must be GET or POST")
        if not is_allowed_solution_url(url):
            raise ValueError(f"Discovery URL is outside allowed public interface: {url}")
        fields_json = _canonical_fields(fields)
        self.initialize()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO discovery_queries(query_key, method, url, fields_json, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(query_key) DO NOTHING""",
                (query_key, normalized_method, url, fields_json, _utc_now()),
            )
            stored = conn.execute(
                "SELECT method, url, fields_json FROM discovery_queries WHERE query_key = ?",
                (query_key,),
            ).fetchone()
            if tuple(stored) != (normalized_method, url, fields_json):
                raise ValueError(f"Discovery query key has conflicting provenance: {query_key}")

    def add_candidate(self, *, query_key: str, detail_url: str) -> None:
        if not is_allowed_solution_url(detail_url):
            raise ValueError(f"Detail URL is outside allowed public interface: {detail_url}")
        self.initialize()
        now = _utc_now()
        with self.connect() as conn:
            if conn.execute(
                "SELECT 1 FROM discovery_queries WHERE query_key = ?", (query_key,)
            ).fetchone() is None:
                raise KeyError(f"Unknown discovery query: {query_key}")
            conn.execute(
                """INSERT OR IGNORE INTO query_candidates(
                    query_key, detail_url, discovered_at
                ) VALUES (?, ?, ?)""",
                (query_key, detail_url, now),
            )
            conn.execute(
                """INSERT INTO details(detail_url, status, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(detail_url) DO NOTHING""",
                (detail_url, DetailStatus.QUEUED.value, now),
            )

    def reserve_detail(
        self,
        detail_url: str,
        *,
        daily_limit: int,
        min_delay_seconds: float = 0,
    ) -> str:
        """Reserve one request atomically before a network attempt."""

        if not is_allowed_solution_url(detail_url):
            raise ValueError(f"Detail URL is outside allowed public interface: {detail_url}")
        if not 1 <= daily_limit <= 100:
            raise ValueError("daily_limit must be in 1..100")
        if min_delay_seconds < 0:
            raise ValueError("min_delay_seconds must be non-negative")
        self.initialize()
        now = _utc_now()
        now_dt = datetime.fromisoformat(now)
        day = _utc_date(now)
        token = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute(
                "SELECT 1 FROM query_candidates WHERE detail_url = ?", (detail_url,)
            ).fetchone() is None:
                raise KeyError(f"Detail URL has no discovery provenance: {detail_url}")
            last_started = conn.execute(
                """
                SELECT MAX(started_at)
                FROM (
                    SELECT started_at FROM request_attempts
                    UNION ALL
                    SELECT reserved_at AS started_at FROM request_reservations
                )
                """
            ).fetchone()[0]
            if last_started:
                next_allowed = datetime.fromisoformat(str(last_started)) + timedelta(
                    seconds=min_delay_seconds
                )
                if now_dt < next_allowed:
                    remaining = (next_allowed - now_dt).total_seconds()
                    raise MinimumDelayNotElapsed(
                        f"NIST minimum delay not elapsed: {remaining:.1f} seconds remaining"
                    )
            attempt_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM request_attempts WHERE substr(started_at, 1, 10) = ?",
                    (day,),
                ).fetchone()[0]
            )
            reservation_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM request_reservations WHERE reserved_date = ?", (day,)
                ).fetchone()[0]
            )
            if attempt_count + reservation_count >= daily_limit:
                raise DailyLimitReached(
                    f"NIST daily limit reached: {attempt_count + reservation_count}/{daily_limit}"
                )
            conn.execute(
                """INSERT INTO request_reservations(
                    token, method, url, fields_json, expected_kind, reserved_at, reserved_date
                ) VALUES (?, 'GET', ?, '{}', 'detail', ?, ?)""",
                (token, detail_url, now, day),
            )
        return token

    def _archive_body(self, body: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(body).hexdigest()
        relative = Path(digest[:2]) / f"{digest}.html"
        target = self.archive_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=target.parent, prefix=".nist-", suffix=".part", delete=False
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary_path, target)
            except FileExistsError as exc:
                if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                    raise RuntimeError(
                        f"Existing archive path has mismatched SHA-256: {target}"
                    ) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Existing archive path has mismatched SHA-256: {target}")
        return digest, relative.as_posix()

    def finalize_detail(
        self,
        token: str,
        response: HttpResponse | None,
        *,
        transport_error: str | None = None,
    ) -> ResponseClassification:
        """Append a completed immutable attempt, then derive Detail state."""

        self.initialize()
        completed_at = _utc_now()
        with self.connect() as conn:
            reservation_exists = conn.execute(
                "SELECT 1 FROM request_reservations WHERE token = ?", (token,)
            ).fetchone()
        if reservation_exists is None:
            raise KeyError(f"Unknown or already finalized reservation: {token}")
        if response is None:
            classification = ResponseClassification(
                ResponseKind.RETRYABLE, "transport failure without HTTP response"
            )
            body_sha256 = None
            content_type = ""
            status_code = None
        else:
            html = response.body.decode("utf-8", errors="replace")
            classification = classify_detail_response(status_code=response.status_code, html=html)
            body_sha256, relative_path = self._archive_body(response.body)
            content_type = response.content_type
            status_code = response.status_code
            completed_at = response.fetched_at
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            reservation = conn.execute(
                "SELECT * FROM request_reservations WHERE token = ?", (token,)
            ).fetchone()
            if reservation is None:
                raise KeyError(f"Unknown or already finalized reservation: {token}")
            if response is not None:
                conn.execute(
                    """INSERT OR IGNORE INTO response_blobs(
                        sha256, relative_path, byte_count, created_at
                    )
                       VALUES (?, ?, ?, ?)""",
                    (body_sha256, relative_path, len(response.body), completed_at),
                )
            cursor = conn.execute(
                """INSERT INTO request_attempts(
                    reservation_token, method, url, fields_json, expected_kind,
                    started_at, completed_at, status_code, content_type, body_sha256,
                    classifier_outcome, classifier_reason, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    token,
                    reservation["method"],
                    reservation["url"],
                    reservation["fields_json"],
                    reservation["expected_kind"],
                    reservation["reserved_at"],
                    completed_at,
                    status_code,
                    content_type,
                    body_sha256,
                    classification.kind.value,
                    classification.reason,
                    transport_error,
                ),
            )
            attempt_id = int(cursor.lastrowid)
            self._derive_detail(
                conn,
                detail_url=str(reservation["url"]),
                attempt_id=attempt_id,
                classification=classification,
                body_sha256=body_sha256,
                now=completed_at,
            )
            conn.execute("DELETE FROM request_reservations WHERE token = ?", (token,))
        return classification

    @staticmethod
    def _derive_detail(
        conn: sqlite3.Connection,
        *,
        detail_url: str,
        attempt_id: int,
        classification: ResponseClassification,
        body_sha256: str | None,
        now: str,
    ) -> None:
        current = conn.execute(
            "SELECT status, accepted_attempt_id FROM details WHERE detail_url = ?", (detail_url,)
        ).fetchone()
        current_status = str(current["status"]) if current else DetailStatus.QUEUED.value
        if (
            current_status == DetailStatus.ACCEPTED.value
            and classification.kind is not ResponseKind.ACCEPTED
        ):
            status = DetailStatus.ACCEPTED.value
            accepted_attempt_id = current["accepted_attempt_id"]
            source_sha256 = conn.execute(
                "SELECT source_sha256 FROM details WHERE detail_url = ?", (detail_url,)
            ).fetchone()[0]
        else:
            status = classification.kind.value
            accepted_attempt_id = (
                attempt_id if classification.kind is ResponseKind.ACCEPTED else None
            )
            source_sha256 = body_sha256 if classification.kind is ResponseKind.ACCEPTED else None
        conn.execute(
            """INSERT INTO details(
                detail_url, status, accepted_attempt_id, source_sha256,
                last_attempt_id, updated_at
            )
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(detail_url) DO UPDATE SET
                   status = excluded.status,
                   accepted_attempt_id = excluded.accepted_attempt_id,
                   source_sha256 = excluded.source_sha256,
                   last_attempt_id = excluded.last_attempt_id,
                   updated_at = excluded.updated_at""",
            (detail_url, status, accepted_attempt_id, source_sha256, attempt_id, now),
        )

    def pending_details(self, *, limit: int) -> list[str]:
        if not 1 <= limit <= 5:
            raise ValueError("limit must be in 1..5")
        self.initialize()
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT detail_url FROM details
                   WHERE status IN (?, ?)
                   ORDER BY updated_at, detail_url LIMIT ?""",
                (DetailStatus.QUEUED.value, DetailStatus.RETRYABLE.value, limit),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def recount(self) -> dict[str, int]:
        self.initialize()
        with self.connect() as conn:
            counts = {status.value: 0 for status in DetailStatus}
            for row in conn.execute(
                "SELECT status, COUNT(*) AS count FROM details GROUP BY status"
            ):
                counts[str(row["status"])] = int(row["count"])
            unknown = set(counts).difference(status.value for status in DetailStatus)
            if unknown:
                raise RuntimeError(f"unknown Detail statuses: {sorted(unknown)}")
            invalid_accepted = int(
                conn.execute(
                    """SELECT COUNT(*) FROM details d
                       LEFT JOIN request_attempts a ON a.id = d.accepted_attempt_id
                       WHERE d.status = ? AND (
                           a.id IS NULL OR a.status_code != 200 OR a.classifier_outcome != ?
                           OR d.source_sha256 IS NULL OR d.source_sha256 != a.body_sha256
                       )""",
                    (DetailStatus.ACCEPTED.value, ResponseKind.ACCEPTED.value),
                ).fetchone()[0]
            )
            if invalid_accepted:
                raise RuntimeError(f"accepted Detail invariant failed for {invalid_accepted} rows")
            total = sum(counts.values())
            unresolved = sum(
                counts[item.value]
                for item in (
                    DetailStatus.QUEUED,
                    DetailStatus.RETRYABLE,
                    DetailStatus.BLOCKED,
                    DetailStatus.INVALID,
                )
            )
            return {
                "total": total,
                "accepted": counts[DetailStatus.ACCEPTED.value],
                "unresolved": unresolved,
                **counts,
            }

    def reconcile_stale_reservations(
        self,
        *,
        min_age_hours: float = 24.0,
        apply: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Plan or append retryable attempts for stale, unfinished reservations."""

        if min_age_hours < 0:
            raise ValueError("min_age_hours must be non-negative")
        self.initialize()
        current = now or datetime.now(UTC)
        cutoff = current - timedelta(hours=min_age_hours)
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM request_reservations ORDER BY id").fetchall()
        stale = []
        for row in rows:
            reserved_at = datetime.fromisoformat(str(row["reserved_at"]).replace("Z", "+00:00"))
            if reserved_at.astimezone(UTC) <= cutoff:
                stale.append(dict(row))
        result: dict[str, Any] = {
            "mode": "apply" if apply else "dry_run",
            "stale_reservations": len(stale),
            "tokens": [row["token"] for row in stale],
        }
        if not apply:
            return result
        for row in stale:
            self.finalize_detail(
                str(row["token"]), None, transport_error="reconciled stale reservation"
            )
        result["reconciled"] = len(stale)
        return result
