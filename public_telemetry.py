"""Privacy-preserving, bounded usage telemetry for public app."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

LEGACY_DEFAULT_HASH_SALT = "radreactions-public-usage"
DEFAULT_RETENTION_DAYS = 90
MAX_RETENTION_DAYS = 365
QUERY_KEYS = {"q", "query", "search_query"}


def configured_hash_salt(value: str | None) -> str | None:
    """Return an explicitly configured non-legacy salt, else ``None``."""
    salt = (value or "").strip()
    if not salt or salt == LEGACY_DEFAULT_HASH_SALT:
        return None
    return salt


def hash_identifier(value: str, salt: str | None) -> str:
    """Hash an identifier only when a deployment-specific salt is configured."""
    normalized_salt = configured_hash_salt(salt)
    clean = value.strip()
    if not clean or not normalized_salt:
        return ""
    return hashlib.sha256(f"{normalized_salt}:{clean}".encode()).hexdigest()


def retention_days(value: str | None) -> int:
    """Return a safe telemetry retention period."""
    try:
        days = int(value or DEFAULT_RETENTION_DAYS)
    except ValueError:
        return DEFAULT_RETENTION_DAYS
    return min(max(days, 1), MAX_RETENTION_DAYS)


def _without_query_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_query_fields(item)
            for key, item in value.items()
            if key.lower() not in QUERY_KEYS
        }
    if isinstance(value, list):
        return [_without_query_fields(item) for item in value]
    return value


def connect(path: Path, *, retention_days_value: int = DEFAULT_RETENTION_DAYS) -> sqlite3.Connection:
    """Open telemetry DB, ensure schema, and prune expired records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 5000")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          event_type TEXT NOT NULL,
          page TEXT NOT NULL DEFAULT '',
          item_key TEXT NOT NULL DEFAULT '',
          ip_hash TEXT NOT NULL DEFAULT '',
          user_agent_hash TEXT NOT NULL DEFAULT '',
          metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_usage_events_type ON usage_events(event_type)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_usage_events_created ON usage_events(created_at)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_usage_events_ip ON usage_events(ip_hash)")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_schema_migrations (
          name TEXT PRIMARY KEY,
          applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    scrub_migration = "001_scrub_search_queries"
    if con.execute(
        "SELECT 1 FROM usage_schema_migrations WHERE name = ?", (scrub_migration,)
    ).fetchone() is None:
        rows = con.execute(
            "SELECT id, metadata_json FROM usage_events WHERE event_type = 'search'"
        ).fetchall()
        for row in rows:
            try:
                metadata = json.loads(str(row["metadata_json"] or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                metadata = {}
            safe_metadata = _without_query_fields(metadata)
            con.execute(
                "UPDATE usage_events SET metadata_json = ? WHERE id = ?",
                (json.dumps(safe_metadata, ensure_ascii=False, sort_keys=True), row["id"]),
            )
        con.execute("INSERT INTO usage_schema_migrations(name) VALUES (?)", (scrub_migration,))
    con.execute(
        "DELETE FROM usage_events WHERE julianday(created_at) < julianday('now', ?)",
        (f"-{retention_days_value} days",),
    )
    con.commit()
    return con


def write_event(
    con: sqlite3.Connection,
    *,
    created_at: str,
    event_type: str,
    page: str,
    item_key: str = "",
    ip_hash: str = "",
    user_agent_hash: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Write one event after removing raw search query fields from metadata."""
    safe_metadata = _without_query_fields(metadata or {})
    con.execute(
        """
        INSERT INTO usage_events (
            created_at, event_type, page, item_key, ip_hash,
            user_agent_hash, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            created_at,
            event_type,
            page,
            item_key,
            ip_hash,
            user_agent_hash,
            json.dumps(safe_metadata, ensure_ascii=False, sort_keys=True),
        ),
    )
    con.commit()


def summary(con: sqlite3.Connection) -> dict[str, int]:
    """Return aggregate counters without exposing personal identifiers."""
    row = con.execute(
        """
        SELECT
          SUM(CASE WHEN event_type = 'visit' THEN 1 ELSE 0 END) AS visits,
          SUM(CASE WHEN event_type = 'search' THEN 1 ELSE 0 END) AS searches,
          SUM(CASE WHEN event_type = 'download' THEN 1 ELSE 0 END) AS downloads,
          COUNT(DISTINCT NULLIF(ip_hash, '')) AS unique_ips
        FROM usage_events
        """
    ).fetchone()
    return {
        "visits": int(row["visits"] or 0),
        "searches": int(row["searches"] or 0),
        "unique_ips": int(row["unique_ips"] or 0),
        "downloads": int(row["downloads"] or 0),
    }
