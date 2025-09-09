#!/usr/bin/env python3
"""
Sync the database with validated TSV/CSV sources.

- Imports or refreshes all entries marked validated=true in validation_db.json files
  for the selected tables (default: 5–9), ensuring full reaction updates and
  replacing measurements.
- Removes entries for sources marked validated=false.
- Use --dry-run to only report issues and planned actions.

Usage (PowerShell):
  python tools/sync_validated.py --tables 5 6 7 8 9
  python tools/sync_validated.py --dry-run

"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

from import_reactions import sync_validations_to_db


def _parse_tables(values: Sequence[str] | None) -> tuple[int, ...]:
    if not values:
        return (5, 6, 7, 8, 9)
    out: list[int] = []
    for v in values:
        v = v.strip()
        if not v:
            continue
        try:
            out.append(int(v))
        except ValueError:
            raise SystemExit(f"Invalid table number: {v}") from None
    if not out:
        return (5, 6, 7, 8, 9)
    return tuple(out)


def main() -> None:
    p = argparse.ArgumentParser(description="Sync DB with validated TSV/CSV sources.")
    p.add_argument(
        "--tables",
        nargs="*",
        help="Table numbers to include (default: 5 6 7 8 9)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and report issues without making DB changes",
    )
    args = p.parse_args()

    tables = _parse_tables(args.tables)
    summary = sync_validations_to_db(table_numbers=tables, dry_run=bool(args.dry_run))

    print("=== Sync Summary ===")
    print(f"Tables: {summary['tables']}")
    print(f"Imported/updated validated sources: {summary['imported_total']}")
    print(f"Set validation flags updated rows: {summary['updated_total']}")
    print(f"Deleted rows for unvalidated sources: {summary['deleted_total']}")
    if summary.get("issues"):
        print(f"Issues ({len(summary['issues'])}):")
        for issue in summary["issues"]:
            print("-", issue)


if __name__ == "__main__":
    main()
