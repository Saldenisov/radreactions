from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from public_telemetry import (
    DEFAULT_RETENTION_DAYS,
    LEGACY_DEFAULT_HASH_SALT,
    configured_hash_salt,
    connect,
    hash_identifier,
    retention_days,
    summary,
    write_event,
)


def test_hashing_requires_explicit_non_legacy_salt() -> None:
    assert configured_hash_salt(None) is None
    assert configured_hash_salt(LEGACY_DEFAULT_HASH_SALT) is None
    assert hash_identifier("198.51.100.8", None) == ""
    assert hash_identifier("198.51.100.8", LEGACY_DEFAULT_HASH_SALT) == ""
    assert hash_identifier("198.51.100.8", "deployment-secret")


def test_retention_days_is_bounded() -> None:
    assert retention_days(None) == DEFAULT_RETENTION_DAYS
    assert retention_days("0") == 1
    assert retention_days("1000") == 365
    assert retention_days("invalid") == DEFAULT_RETENTION_DAYS


def test_connect_prunes_expired_events_and_keeps_aggregate_counts(tmp_path) -> None:
    path = tmp_path / "usage.db"
    con = connect(path, retention_days_value=7)
    try:
        write_event(
            con,
            created_at=(datetime.now(UTC) - timedelta(days=8)).isoformat(),
            event_type="visit",
            page="home",
            ip_hash="expired",
        )
        write_event(
            con,
            created_at=datetime.now(UTC).isoformat(),
            event_type="search",
            page="home",
            ip_hash="active",
            metadata={
                "query": "sensitive search term",
                "database": "buxton",
                "scope": "reactants",
            },
        )
    finally:
        con.close()

    con = connect(path, retention_days_value=7)
    try:
        assert summary(con) == {"visits": 0, "searches": 1, "unique_ips": 1, "downloads": 0}
        metadata = con.execute("SELECT metadata_json FROM usage_events").fetchone()[0]
        assert "query" not in metadata
        assert "sensitive search term" not in metadata
    finally:
        con.close()
