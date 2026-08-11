"""Bounded operational commands for NIST ingestion.

The fetch command is intentionally limited to five Detail requests, 180 seconds
minimum spacing, 100 requests/day, and stops after first retryable response by
default. It is never run implicitly by imports or tests.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .client import NistTransportError, fetch_detail
from .models import ResponseKind
from .registry import DailyLimitReached, NistRegistry


def _registry(args: argparse.Namespace) -> NistRegistry:
    return NistRegistry(args.registry, args.archive_root)


def _fetch_details(args: argparse.Namespace) -> int:
    if not 1 <= args.limit <= 5:
        raise SystemExit("--limit must be in 1..5")
    if args.min_delay < 180:
        raise SystemExit("--min-delay must be >= 180")
    if not 1 <= args.daily_limit <= 100:
        raise SystemExit("--daily-limit must be in 1..100")
    registry = _registry(args)
    outcomes: list[dict[str, object]] = []
    for index, url in enumerate(registry.pending_details(limit=args.limit)):
        if index:
            time.sleep(args.min_delay)
        token = registry.reserve_detail(
            url,
            daily_limit=args.daily_limit,
            min_delay_seconds=args.min_delay,
        )
        try:
            response = fetch_detail(url, timeout_seconds=args.timeout)
            classification = registry.finalize_detail(token, response)
        except NistTransportError as exc:
            classification = registry.finalize_detail(token, None, transport_error=repr(exc))
        except DailyLimitReached:
            raise
        outcomes.append(
            {"url": url, "outcome": classification.kind.value, "reason": classification.reason}
        )
        if classification.kind is ResponseKind.BLOCKED or (
            args.stop_on_first_retryable and classification.kind is ResponseKind.RETRYABLE
        ):
            break
    print(json.dumps({"attempts": outcomes, "counts": registry.recount()}, sort_keys=True))
    return 0


def _reconcile(args: argparse.Namespace) -> int:
    registry = _registry(args)
    result = registry.reconcile_stale_reservations(
        min_age_hours=args.pending_min_age_hours,
        apply=args.apply,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m nist.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch-details", "reconcile"):
        child = subparsers.add_parser(name)
        child.add_argument("--registry", type=Path, required=True)
        child.add_argument("--archive-root", type=Path, required=True)
    fetch = subparsers.choices["fetch-details"]
    fetch.add_argument("--limit", type=int, default=5)
    fetch.add_argument("--min-delay", type=float, default=180.0)
    fetch.add_argument("--daily-limit", type=int, default=100)
    fetch.add_argument("--timeout", type=int, default=30)
    fetch.add_argument(
        "--stop-on-first-retryable", action=argparse.BooleanOptionalAction, default=True
    )
    reconcile = subparsers.choices["reconcile"]
    reconcile.add_argument("--pending-min-age-hours", type=float, default=24.0)
    reconcile.add_argument(
        "--dry-run", action="store_true", help="Explicitly report only; this is the default."
    )
    reconcile.add_argument(
        "--apply", action="store_true", help="Append retryable attempts for stale reservations."
    )
    args = parser.parse_args(argv)
    if args.command == "reconcile" and args.dry_run and args.apply:
        raise SystemExit("--dry-run and --apply cannot be combined")
    return _fetch_details(args) if args.command == "fetch-details" else _reconcile(args)


if __name__ == "__main__":
    raise SystemExit(main())
