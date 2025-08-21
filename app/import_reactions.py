import csv
import re
from pathlib import Path
from typing import Any

from app.config import get_table_paths
from app.reactions_db import (
    add_measurement,
    ensure_db,
    get_or_create_reaction,
    upsert_reference,
)

RATE_UNIT_PATTERN = re.compile(r"(\d(?:[\d\.\sx×\*\^\-\+]+)?)\s*(.*)")


def parse_rate_value(raw: str):
    raw = raw.strip()
    # Very naive numeric extraction to float if simple like 5.5 x 10^9
    try:
        # replace LaTeX times and formatting
        s = raw.replace("\\times", "x").replace(" ", "")
        if "x10^" in s:
            parts = s.split("x10^")
            base = float(parts[0])
            exp = int(parts[1])
            return base * (10**exp)
        if "×10^" in s:
            parts = s.split("×10^")
            base = float(parts[0])
            exp = int(parts[1])
            return base * (10**exp)
        return float(s)
    except Exception:
        return None


def import_single_csv(csv_path: Path, table_no: int):
    """Import a single tab-delimited CSV (TSV content with .csv extension) into reactions.db.

    Note: This function appends measurements every time it is called. Use
    import_single_csv_idempotent for an idempotent update that refreshes
    measurements from this source.
    """
    con = ensure_db()
    inserted_reactions = 0
    inserted_measurements = 0
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in reader:
                row = row + [""] * (7 - len(row))
                buxton_no = row[0].strip() or None
                reaction_name = row[1].strip() or None
                formula_latex = row[2].strip() or None
                pH = row[3].strip() or None
                rate_value = row[4].strip() or None
                method_or_notes = row[5].strip() or None
                reference_code = row[6].strip() or None
                if not formula_latex:
                    continue
                rid = get_or_create_reaction(
                    con,
                    table_no=table_no,
                    buxton_reaction_number=buxton_no,
                    reaction_name=reaction_name,
                    formula_latex=formula_latex,
                    notes=method_or_notes,
                    source_path=str(csv_path),
                )
                inserted_reactions += 1
                ref_id = upsert_reference(
                    con, buxton_code=reference_code, citation_text=None, doi=None
                )
                rate_num = parse_rate_value(rate_value) if rate_value else None
                add_measurement(
                    con,
                    rid,
                    pH=pH,
                    temperature_C=None,
                    rate_value=rate_value or "",
                    rate_value_num=rate_num,
                    rate_units=None,
                    method=None,
                    conditions=method_or_notes,
                    reference_id=ref_id,
                    source_path=str(csv_path),
                    page_info=None,
                )
                inserted_measurements += 1
    except Exception as e:
        print(f"[IMPORT_ONE] Error processing {csv_path}: {e}")
    con.commit()
    return inserted_reactions, inserted_measurements


def import_single_csv_idempotent(csv_path: Path, table_no: int):
    """Idempotent import for a single CSV/TSV.

    - Ensures reaction exists/updated via get_or_create_reaction.
    - Replaces measurements originating from this source (source_path == csv_path)
      for each reaction with the newly parsed ones to avoid duplicates and to
      reflect TSV updates.
    """
    con = ensure_db()
    inserted_reactions = 0
    replaced_measurements = 0
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            rows = [r for r in reader]
        for row in rows:
            row = row + [""] * (7 - len(row))
            buxton_no = row[0].strip() or None
            reaction_name = row[1].strip() or None
            formula_latex = row[2].strip() or None
            pH = row[3].strip() or None
            rate_value = row[4].strip() or None
            method_or_notes = row[5].strip() or None
            reference_code = row[6].strip() or None
            if not formula_latex:
                continue
            rid = get_or_create_reaction(
                con,
                table_no=table_no,
                buxton_reaction_number=buxton_no,
                reaction_name=reaction_name,
                formula_latex=formula_latex,
                notes=method_or_notes,
                source_path=str(csv_path),
            )
            inserted_reactions += 1
            # Remove prior measurements from this source for this reaction
            con.execute(
                "DELETE FROM measurements WHERE reaction_id = ? AND source_path = ?",
                (rid, str(csv_path)),
            )
            ref_id = upsert_reference(con, buxton_code=reference_code, citation_text=None, doi=None)
            rate_num = parse_rate_value(rate_value) if rate_value else None
            add_measurement(
                con,
                rid,
                pH=pH,
                temperature_C=None,
                rate_value=rate_value or "",
                rate_value_num=rate_num,
                rate_units=None,
                method=None,
                conditions=method_or_notes,
                reference_id=ref_id,
                source_path=str(csv_path),
                page_info=None,
            )
            replaced_measurements += 1
    except Exception as e:
        print(f"[IMPORT_ONE_IDEM] Error processing {csv_path}: {e}")
    con.commit()
    return inserted_reactions, replaced_measurements


def import_from_csvs(base_dir: Path | None = None, table_numbers=(5, 6, 7, 8, 9)):
    con = ensure_db()
    inserted_reactions = 0
    inserted_measurements = 0

    for tno in table_numbers:
        table_name = f"table{tno}"
        IMAGE_DIR, PDF_DIR, TSV_DIR, DB_PATH = get_table_paths(table_name)
        csv_dir = TSV_DIR
        if not csv_dir.exists():
            continue
        for csv_path in csv_dir.glob("*.csv"):
            try:
                with open(csv_path, newline="", encoding="utf-8") as f:
                    reader = csv.reader(f, delimiter="\t")
                    for row in reader:
                        # Pad to 7 columns
                        row = row + [""] * (7 - len(row))
                        buxton_no = row[0].strip() or None
                        reaction_name = row[1].strip() or None
                        formula_latex = row[2].strip() or None
                        pH = row[3].strip() or None
                        rate_value = row[4].strip() or None
                        method_or_notes = row[5].strip() or None
                        reference_code = row[6].strip() or None
                        if not formula_latex:
                            continue
                        rid = get_or_create_reaction(
                            con,
                            table_no=tno,
                            buxton_reaction_number=buxton_no,
                            reaction_name=reaction_name,
                            formula_latex=formula_latex,
                            notes=method_or_notes,
                            source_path=str(csv_path),
                        )
                        inserted_reactions += 1  # upper bound; duplicates are updated not inserted
                        ref_id = upsert_reference(
                            con,
                            buxton_code=reference_code,
                            citation_text=None,
                            doi=None,
                        )
                        rate_num = parse_rate_value(rate_value) if rate_value else None
                        add_measurement(
                            con,
                            rid,
                            pH=pH,
                            temperature_C=None,
                            rate_value=rate_value or "",
                            rate_value_num=rate_num,
                            rate_units=None,
                            method=None,
                            conditions=method_or_notes,
                            reference_id=ref_id,
                            source_path=str(csv_path),
                            page_info=None,
                        )
                        inserted_measurements += 1
            except Exception as e:
                print(f"[IMPORT] Error processing {csv_path}: {e}")
                continue
    con.commit()
    print(f"[IMPORT] Done. reactions~{inserted_reactions}, measurements={inserted_measurements}")


def sync_validations_to_db(table_numbers=(5, 6, 7, 8, 9), dry_run: bool = False) -> dict[str, Any]:
    """Read each table's validation_db.json and update reactions DB accordingly.

    For each image with validated=true in validation_db.json:
      - Ensure corresponding TSV/CSV is imported idempotently (create or refresh entries)
      - Set validated flag and metadata (by, at) for reactions from that source
    For validated=false: clear validated flags for that source.

    Returns a dict with summary and any issues discovered for UI display.
    If dry_run=True, only scans for missing TSV/CSV and reports issues, no DB writes.
    """
    con = ensure_db()
    updated_total = 0
    imported_total = 0
    issues: list[dict[str, Any]] = []

    for tno in table_numbers:
        table_name = f"table{tno}"
        IMAGE_DIR, PDF_DIR, TSV_DIR, DB_JSON_PATH = get_table_paths(table_name)
        if not DB_JSON_PATH.exists():
            continue
        try:
            from app.db_utils import load_db

            db = load_db(DB_JSON_PATH, IMAGE_DIR)
        except Exception as e:
            issues.append(
                {
                    "table_no": tno,
                    "issue": "load_failed",
                    "message": f"Failed to load {DB_JSON_PATH}: {e}",
                }
            )
            continue
        for img, meta in db.items():
            if isinstance(meta, bool):
                is_valid = bool(meta)
                by = None
                at = None
            else:
                is_valid = bool(meta.get("validated", False))
                by = meta.get("by")
                at = meta.get("at")
            stem = Path(img).stem
            csv_candidate = TSV_DIR / f"{stem}.csv"
            tsv_candidate = TSV_DIR / f"{stem}.tsv"
            source_path = (
                csv_candidate
                if csv_candidate.exists()
                else (tsv_candidate if tsv_candidate.exists() else None)
            )
            if source_path is None:
                issues.append(
                    {
                        "table_no": tno,
                        "image": str(img),
                        "stem": stem,
                        "candidates": [str(csv_candidate), str(tsv_candidate)],
                        "issue": "missing_source_file",
                        "message": "Validated image but no TSV/CSV found by stem.",
                    }
                )
                continue
            if dry_run:
                # Do not modify DB in dry-run
                continue
            # Import idempotently to ensure entries exist and are refreshed
            try:
                rcount, _ = import_single_csv_idempotent(source_path, tno)
                imported_total += rcount or 0
            except Exception as e:
                issues.append(
                    {
                        "table_no": tno,
                        "image": str(img),
                        "source_path": str(source_path),
                        "issue": "import_failed",
                        "message": f"Import failed: {e}",
                    }
                )
                continue
            try:
                from app.reactions_db import set_validated_by_source

                updated = set_validated_by_source(con, str(source_path), is_valid, by=by, at_iso=at)
                if updated == 0 and is_valid:
                    issues.append(
                        {
                            "table_no": tno,
                            "image": str(img),
                            "source_path": str(source_path),
                            "issue": "no_rows_updated",
                            "message": "No DB rows were updated for this source. Possible path mismatch.",
                        }
                    )
                updated_total += updated
            except Exception as e:
                issues.append(
                    {
                        "table_no": tno,
                        "image": str(img),
                        "source_path": str(source_path),
                        "issue": "update_failed",
                        "message": f"Failed to set validated flag: {e}",
                    }
                )
    summary = {
        "updated_total": updated_total,
        "imported_total": imported_total,
        "issues": issues,
        "tables": list(table_numbers),
    }
    print(
        f"[SYNC] Imported/updated TSVs; set validated for {updated_total} reactions; issues={len(issues)} (tables {table_numbers})"
    )
    return summary
