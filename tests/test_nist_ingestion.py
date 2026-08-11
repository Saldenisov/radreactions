from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nist.classifier import classify_detail_response
from nist.cli import main as cli_main
from nist.client import is_allowed_solution_url
from nist.models import HttpResponse, ResponseKind
from nist.registry import DailyLimitReached, MinimumDelayNotElapsed, NistRegistry

DETAIL_URL = "https://kinetics.nist.gov/solution/Detail?id=TEST/1:1"
DETAIL_URL_2 = "https://kinetics.nist.gov/solution/Detail?id=TEST/2:1"
VALID_DETAIL = b"<th>Reaction</th><b>Squib:</b><th>Rate constant</th>"


def registry(tmp_path: Path) -> NistRegistry:
    value = NistRegistry(tmp_path / "registry.sqlite", tmp_path / "raw")
    value.initialize()
    value.register_query(
        query_key="reactant:OH",
        method="POST",
        url="https://kinetics.nist.gov/solution/SearchForm",
        fields={"REACTANT1": "OH"},
    )
    value.add_candidate(query_key="reactant:OH", detail_url=DETAIL_URL)
    return value


def response(status_code: int | None, body: bytes = VALID_DETAIL) -> HttpResponse:
    return HttpResponse(
        status_code=status_code,
        body=body,
        content_type="text/html",
        fetched_at="2026-08-11T10:00:00+00:00",
    )


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (500, b"server error", ResponseKind.RETRYABLE),
        (502, b"bad gateway", ResponseKind.RETRYABLE),
        (503, b"unavailable", ResponseKind.RETRYABLE),
        (403, b"forbidden", ResponseKind.BLOCKED),
        (429, b"slow down", ResponseKind.BLOCKED),
        (200, b"Cannot get a connection from the pool" + VALID_DETAIL, ResponseKind.RETRYABLE),
        (200, b"Search returned 0 records", ResponseKind.CONFIRMED_EMPTY),
        (200, b"<html>unexpected page</html>", ResponseKind.INVALID),
        (200, VALID_DETAIL, ResponseKind.ACCEPTED),
    ],
)
def test_classifier_has_no_false_acceptance_or_empty(
    status: int, body: bytes, expected: ResponseKind
):
    result = classify_detail_response(status_code=status, html=body.decode())

    assert result.kind is expected


def test_allowlist_is_exact_to_official_solution_interface():
    assert is_allowed_solution_url(DETAIL_URL)
    assert not is_allowed_solution_url("http://kinetics.nist.gov/solution/Detail?id=1")
    assert not is_allowed_solution_url("https://example.com/solution/Detail?id=1")
    assert not is_allowed_solution_url("https://kinetics.nist.gov:444/solution/Detail?id=1")
    assert not is_allowed_solution_url("https://user@kinetics.nist.gov/solution/Detail?id=1")
    assert not is_allowed_solution_url("https://kinetics.nist.gov:bad/solution/Detail?id=1")
    assert not is_allowed_solution_url("https://kinetics.nist.gov/kinetics/Detail?id=1")


def test_registry_refuses_external_candidate_urls(tmp_path: Path):
    value = registry(tmp_path)

    with pytest.raises(ValueError, match="outside allowed"):
        value.add_candidate(
            query_key="reactant:OH", detail_url="https://example.com/solution/Detail?id=1"
        )


def test_registry_refuses_unprovenanced_queries_and_details(tmp_path: Path):
    value = NistRegistry(tmp_path / "registry.sqlite", tmp_path / "raw")
    with pytest.raises(ValueError, match="outside allowed"):
        value.register_query(
            query_key="external",
            method="POST",
            url="https://example.com/solution/SearchForm",
        )
    with pytest.raises(KeyError, match="no discovery provenance"):
        value.reserve_detail(DETAIL_URL, daily_limit=100)


def test_query_key_cannot_hide_conflicting_provenance(tmp_path: Path):
    value = registry(tmp_path)

    with pytest.raises(ValueError, match="conflicting provenance"):
        value.register_query(
            query_key="reactant:OH",
            method="POST",
            url="https://kinetics.nist.gov/solution/SearchForm",
            fields={"REACTANT1": "H"},
        )


def test_cli_reconcile_defaults_to_dry_run_without_network(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    code = cli_main(
        [
            "reconcile",
            "--registry",
            str(tmp_path / "registry.sqlite"),
            "--archive-root",
            str(tmp_path / "raw"),
            "--dry-run",
        ]
    )

    assert code == 0
    assert '"mode": "dry_run"' in capsys.readouterr().out


@pytest.mark.parametrize(
    "args", [["--limit", "6"], ["--min-delay", "179"], ["--daily-limit", "101"]]
)
def test_cli_fetch_refuses_unsafe_bounds_before_network(tmp_path: Path, args: list[str]):
    with pytest.raises(SystemExit):
        cli_main(
            [
                "fetch-details",
                "--registry",
                str(tmp_path / "registry.sqlite"),
                "--archive-root",
                str(tmp_path / "raw"),
                *args,
            ]
        )


def test_accepted_detail_requires_200_signature_and_preserves_later_failure(tmp_path: Path):
    value = registry(tmp_path)
    token = value.reserve_detail(DETAIL_URL, daily_limit=100)

    result = value.finalize_detail(token, response(200))

    assert result.kind is ResponseKind.ACCEPTED
    assert value.recount() == {
        "total": 1,
        "accepted": 1,
        "unresolved": 0,
        "queued": 0,
        "confirmed_empty": 0,
        "retryable": 0,
        "blocked": 0,
        "invalid": 0,
    }
    token = value.reserve_detail(DETAIL_URL, daily_limit=100)
    value.finalize_detail(token, response(500, b"server error"))

    with value.connect() as conn:
        detail = conn.execute("SELECT status, source_sha256 FROM details").fetchone()
        attempts = conn.execute(
            "SELECT classifier_outcome FROM request_attempts ORDER BY id"
        ).fetchall()
    assert detail["status"] == "accepted"
    assert detail["source_sha256"]
    assert [row[0] for row in attempts] == ["accepted", "retryable"]


def test_archive_is_content_addressed_and_never_overwrites(tmp_path: Path):
    value = registry(tmp_path)
    first = value.reserve_detail(DETAIL_URL, daily_limit=100)
    second_url = DETAIL_URL_2
    value.add_candidate(query_key="reactant:OH", detail_url=second_url)
    second = value.reserve_detail(second_url, daily_limit=100)

    value.finalize_detail(first, response(200))
    value.finalize_detail(second, response(200))

    files = list((tmp_path / "raw").rglob("*.html"))
    with value.connect() as conn:
        blob_count = conn.execute("SELECT COUNT(*) FROM response_blobs").fetchone()[0]
        attempt_count = conn.execute("SELECT COUNT(*) FROM request_attempts").fetchone()[0]
    assert len(files) == 1
    assert blob_count == 1
    assert attempt_count == 2
    assert files[0].read_bytes() == VALID_DETAIL


def test_archive_refuses_corrupt_existing_digest_path(tmp_path: Path):
    value = registry(tmp_path)
    digest = hashlib.sha256(VALID_DETAIL).hexdigest()
    target = tmp_path / "raw" / digest[:2] / f"{digest}.html"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"corrupt")
    token = value.reserve_detail(DETAIL_URL, daily_limit=100)

    with pytest.raises(RuntimeError, match="mismatched SHA-256"):
        value.finalize_detail(token, response(200))

    assert target.read_bytes() == b"corrupt"


def test_stale_reservation_reconciliation_is_dry_run_then_append_only(tmp_path: Path):
    value = registry(tmp_path)
    token = value.reserve_detail(DETAIL_URL, daily_limit=100)
    old = datetime.now(UTC) - timedelta(hours=25)
    with value.connect() as conn:
        conn.execute(
            "UPDATE request_reservations SET reserved_at = ? WHERE token = ?",
            (old.isoformat(), token),
        )

    dry_run = value.reconcile_stale_reservations(min_age_hours=24, apply=False)

    assert dry_run["mode"] == "dry_run"
    assert dry_run["stale_reservations"] == 1
    with value.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM request_attempts").fetchone()[0] == 0

    applied = value.reconcile_stale_reservations(min_age_hours=24, apply=True)

    assert applied["reconciled"] == 1
    assert value.recount()["retryable"] == 1
    with value.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM request_reservations").fetchone()[0] == 0
        row = conn.execute("SELECT classifier_outcome, error FROM request_attempts").fetchone()
    assert tuple(row) == ("retryable", "reconciled stale reservation")


def test_daily_limit_counts_reservations_and_final_attempts(tmp_path: Path):
    value = registry(tmp_path)
    token = value.reserve_detail(DETAIL_URL, daily_limit=1)
    value.add_candidate(query_key="reactant:OH", detail_url=DETAIL_URL_2)

    with pytest.raises(DailyLimitReached):
        value.reserve_detail(DETAIL_URL_2, daily_limit=1)

    value.finalize_detail(token, response(200))
    with pytest.raises(DailyLimitReached):
        value.reserve_detail(DETAIL_URL_2, daily_limit=1)


def test_minimum_delay_is_enforced_across_process_invocations(tmp_path: Path):
    value = registry(tmp_path)
    value.add_candidate(query_key="reactant:OH", detail_url=DETAIL_URL_2)
    value.reserve_detail(DETAIL_URL, daily_limit=100, min_delay_seconds=180)

    with pytest.raises(MinimumDelayNotElapsed, match="minimum delay"):
        value.reserve_detail(DETAIL_URL_2, daily_limit=100, min_delay_seconds=180)


def test_five_record_batch_preserves_query_provenance_and_outcomes(tmp_path: Path):
    value = registry(tmp_path)
    urls = [
        f"https://kinetics.nist.gov/solution/Detail?id=TEST/{index}:1" for index in range(10, 15)
    ]
    outcomes = [
        response(200),
        response(200, b"Search returned 0 records"),
        response(500, b"error"),
        response(403, b"blocked"),
        response(200, b"<html>wrong page</html>"),
    ]
    for url in urls:
        value.add_candidate(query_key="reactant:OH", detail_url=url)
    for url, item in zip(urls, outcomes, strict=True):
        value.finalize_detail(value.reserve_detail(url, daily_limit=100), item)

    counts = value.recount()
    with value.connect() as conn:
        links = conn.execute(
            "SELECT COUNT(*) FROM query_candidates WHERE query_key = 'reactant:OH'"
        ).fetchone()[0]
        attempts = conn.execute("SELECT COUNT(*) FROM request_attempts").fetchone()[0]
    assert counts["total"] == 6  # Includes fixture candidate created by registry().
    assert counts["accepted"] == 1
    assert counts["queued"] == 1
    assert counts["unresolved"] == 4
    assert counts["confirmed_empty"] == 1
    assert counts["retryable"] == 1
    assert counts["blocked"] == 1
    assert counts["invalid"] == 1
    assert links == 6
    assert attempts == 5
