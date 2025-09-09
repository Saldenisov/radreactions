import csv
import re
from pathlib import Path
from typing import Any

from config import get_table_paths
from reactions_db import (
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

    Each CSV row is a measurement. The reaction is determined by the PNG with the same stem.
    If reaction does not exist yet, it will be created with the minimal info available.
    """
    con = ensure_db()
    inserted_reactions = 0
    inserted_measurements = 0
    try:
        stem = csv_path.stem
        # Derive PNG path
        # Locate image dir from table number
        from config import get_table_paths

        IMAGE_DIR, _, TSV_DIR, _ = get_table_paths(f"table{table_no}")
        png_path = IMAGE_DIR / f"{stem}.png"
        png_path_str = str(png_path) if png_path.exists() else None

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in reader:
                row = row + [""] * (7 - len(row))
                buxton_no = row[0].strip() or None
                reaction_name = row[1].strip() or None
                formula_latex = row[2].strip() or None
                pH = row[3].strip() or None
                rate_value = row[4].strip() or None
                comments = row[5].strip() or None
                references_field = row[6].strip() or None

                rid = get_or_create_reaction(
                    con,
                    table_no=table_no,
                    buxton_reaction_number=buxton_no,
                    reaction_name=reaction_name,
                    formula_latex=formula_latex,
                    notes=None,
                    source_path=str(csv_path),
                    png_path=png_path_str,
                )
                inserted_reactions += 1

                # Upsert a primary reference if a single code present; also store raw text
                ref_id = upsert_reference(
                    con,
                    buxton_code=references_field
                    if references_field and "," not in references_field
                    else None,
                    citation_text=None,
                    doi=None,
                    raw_text=references_field,
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
                    conditions=comments,
                    reference_id=ref_id,
                    references_raw=references_field,
                    source_path=str(csv_path),
                    page_info=None,
                )
                inserted_measurements += 1
    except Exception as e:
        print(f"[IMPORT_ONE] Error processing {csv_path}: {e}")
    con.commit()
    return inserted_reactions, inserted_measurements


def import_single_csv_idempotent(csv_path: Path, table_no: int):
    """Idempotent import for a single CSV.

    - Ensures reaction exists/updated via get_or_create_reaction (one reaction per PNG by stem).
    - Replaces measurements originating from this source for that reaction.
    """
    con = ensure_db()
    inserted_reactions = 0
    replaced_measurements = 0
    try:
        from config import get_table_paths

        stem = csv_path.stem
        IMAGE_DIR, _, TSV_DIR, _ = get_table_paths(f"table{table_no}")
        png_path = IMAGE_DIR / f"{stem}.png"
        png_path_str = str(png_path) if png_path.exists() else None

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            rows = [r for r in reader]
        # Prepare reaction from the first row's metadata if available
        if rows:
            r0 = rows[0] + [""] * (7 - len(rows[0]))
            buxton_no = r0[0].strip() or None
            reaction_name = r0[1].strip() or None
            formula_latex = r0[2].strip() or None
        else:
            buxton_no = reaction_name = formula_latex = None

        rid = get_or_create_reaction(
            con,
            table_no=table_no,
            buxton_reaction_number=buxton_no,
            reaction_name=reaction_name,
            formula_latex=formula_latex,
            notes=None,
            source_path=str(csv_path),
            png_path=png_path_str,
        )
        inserted_reactions += 1

        # Remove all prior measurements for this reaction to avoid duplicates across source_path variants
        con.execute(
            "DELETE FROM measurements WHERE reaction_id = ?",
            (rid,),
        )

        for row in rows:
            row = row + [""] * (7 - len(row))
            buxton_no = row[0].strip() or None
            reaction_name = row[1].strip() or None
            formula_latex = row[2].strip() or None
            pH = row[3].strip() or None
            rate_value = row[4].strip() or None
            comments = row[5].strip() or None
            references_field = row[6].strip() or None

            ref_id = upsert_reference(
                con,
                buxton_code=references_field
                if references_field and "," not in references_field
                else None,
                citation_text=None,
                doi=None,
                raw_text=references_field,
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
                conditions=comments,
                reference_id=ref_id,
                references_raw=references_field,
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
        # Prefer .csv over .tsv for the same stem
        seen: set[str] = set()
        for csv_path in sorted(csv_dir.glob("*.csv")):
            seen.add(csv_path.stem)
            try:
                # Derive PNG by stem
                stem = csv_path.stem
                png_path = IMAGE_DIR / f"{stem}.png"
                png_path_str = str(png_path) if png_path.exists() else None
                with open(csv_path, newline="", encoding="utf-8") as f:
                    reader = csv.reader(f, delimiter="\t")
                    rows = [r for r in reader]
                if not rows:
                    continue
                r0 = rows[0] + [""] * (7 - len(rows[0]))
                buxton_no = r0[0].strip() or None
                reaction_name = r0[1].strip() or None
                formula_latex = r0[2].strip() or None
                rid = get_or_create_reaction(
                    con,
                    table_no=tno,
                    buxton_reaction_number=buxton_no,
                    reaction_name=reaction_name,
                    formula_latex=formula_latex,
                    notes=None,
                    source_path=str(csv_path),
                    png_path=png_path_str,
                )
                inserted_reactions += 1  # upper bound; duplicates are updated not inserted
                # Remove all prior measurements for this reaction to ensure idempotency
                con.execute(
                    "DELETE FROM measurements WHERE reaction_id = ?",
                    (rid,),
                )
                for row in rows:
                    row = row + [""] * (7 - len(row))
                    pH = row[3].strip() or None
                    rate_value = row[4].strip() or None
                    comments = row[5].strip() or None
                    references_field = row[6].strip() or None
                    ref_id = upsert_reference(
                        con,
                        buxton_code=references_field
                        if references_field and "," not in references_field
                        else None,
                        citation_text=None,
                        doi=None,
                        raw_text=references_field,
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
                        conditions=comments,
                        reference_id=ref_id,
                        references_raw=references_field,
                        source_path=str(csv_path),
                        page_info=None,
                    )
                    inserted_measurements += 1
            except Exception as e:
                print(f"[IMPORT] Error processing {csv_path}: {e}")
                continue
        for tsv_path in sorted(csv_dir.glob("*.tsv")):
            if tsv_path.stem in seen:
                continue
            try:
                stem = tsv_path.stem
                png_path = IMAGE_DIR / f"{stem}.png"
                png_path_str = str(png_path) if png_path.exists() else None
                with open(tsv_path, newline="", encoding="utf-8") as f:
                    reader = csv.reader(f, delimiter="\t")
                    rows = [r for r in reader]
                if not rows:
                    continue
                r0 = rows[0] + [""] * (7 - len(rows[0]))
                buxton_no = r0[0].strip() or None
                reaction_name = r0[1].strip() or None
                formula_latex = r0[2].strip() or None
                rid = get_or_create_reaction(
                    con,
                    table_no=tno,
                    buxton_reaction_number=buxton_no,
                    reaction_name=reaction_name,
                    formula_latex=formula_latex,
                    notes=None,
                    source_path=str(tsv_path),
                    png_path=png_path_str,
                )
                inserted_reactions += 1
                con.execute(
                    "DELETE FROM measurements WHERE reaction_id = ?",
                    (rid,),
                )
                for row in rows:
                    row = row + [""] * (7 - len(row))
                    pH = row[3].strip() or None
                    rate_value = row[4].strip() or None
                    comments = row[5].strip() or None
                    references_field = row[6].strip() or None
                    ref_id = upsert_reference(
                        con,
                        buxton_code=references_field
                        if references_field and "," not in references_field
                        else None,
                        citation_text=None,
                        doi=None,
                        raw_text=references_field,
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
                        conditions=comments,
                        reference_id=ref_id,
                        references_raw=references_field,
                        source_path=str(tsv_path),
                        page_info=None,
                    )
                    inserted_measurements += 1
            except Exception as e:
                print(f"[IMPORT] Error processing {tsv_path}: {e}")
                continue
    con.commit()
    print(f"[IMPORT] Done. reactions~{inserted_reactions}, measurements={inserted_measurements}")


def list_all_sources_for_table(table_no: int) -> list[Path]:
    """List all .csv/.tsv sources for a table, preferring .csv when both exist."""
    table_name = f"table{table_no}"
    IMAGE_DIR, PDF_DIR, TSV_DIR, DB_PATH = get_table_paths(table_name)
    sources: list[Path] = []
    if not TSV_DIR.exists():
        return sources
    seen: set[str] = set()
    for p in sorted(TSV_DIR.glob("*.csv")):
        sources.append(p)
        seen.add(p.stem)
    for p in sorted(TSV_DIR.glob("*.tsv")):
        if p.stem not in seen:
            sources.append(p)
    return sources


def list_validated_sources_for_table(table_no: int) -> list[Path]:
    """List sources for entries marked validated in validation_db.json (existing files only)."""
    table_name = f"table{table_no}"
    IMAGE_DIR, PDF_DIR, TSV_DIR, DB_JSON_PATH = get_table_paths(table_name)
    sources: list[Path] = []
    if not DB_JSON_PATH.exists():
        return sources
    try:
        from db_utils import load_db

        db = load_db(DB_JSON_PATH, IMAGE_DIR)
    except Exception:
        return sources
    for img, meta in db.items():
        if isinstance(meta, bool):
            is_valid = bool(meta)
        else:
            is_valid = bool(meta.get("validated", False))
        if not is_valid:
            continue
        stem = Path(img).stem
        csv_candidate = TSV_DIR / f"{stem}.csv"
        tsv_candidate = TSV_DIR / f"{stem}.tsv"
        source_path = (
            csv_candidate
            if csv_candidate.exists()
            else (tsv_candidate if tsv_candidate.exists() else None)
        )
        if source_path is not None:
            sources.append(source_path)
    return sources


def reimport_table_all_sources(table_no: int) -> dict[str, int]:
    """Delete nothing; import all sources for table into DB (idempotently).

    Returns: {'sources': int, 'reactions_imported': int, 'measurements_imported': int}
    """
    con = ensure_db()
    sources = list_all_sources_for_table(table_no)
    reactions_total = 0
    measurements_total = 0
    for src in sources:
        try:
            rcount, mcount = import_single_csv_idempotent(src, table_no)
            reactions_total += rcount or 0
            measurements_total += mcount or 0
        except Exception as e:
            print(f"[REIMPORT_ALL] Failed {src}: {e}")
            continue
    con.commit()
    return {
        "sources": len(sources),
        "reactions_imported": reactions_total,
        "measurements_imported": measurements_total,
    }


def sync_validations_to_db(table_numbers=(5, 6, 7, 8, 9), dry_run: bool = False) -> dict[str, Any]:
    """Read each table's validation_db.json and update reactions DB accordingly.

    Behavior change:
    - Only validated=true entries are imported.
    - If an entry is validated=false and exists in DB, it is removed entirely.

    Returns a dict with summary and any issues discovered for UI display.
    If dry_run=True, only scans for missing TSV/CSV and reports issues, no DB writes.
    """
    con = ensure_db()
    updated_total = 0
    imported_total = 0
    deleted_total = 0
    issues: list[dict[str, Any]] = []

    for tno in table_numbers:
        table_name = f"table{tno}"
        IMAGE_DIR, PDF_DIR, TSV_DIR, DB_JSON_PATH = get_table_paths(table_name)
        if not DB_JSON_PATH.exists():
            continue
        try:
            from db_utils import load_db

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
                # If this image is marked validated, it's an issue not to find TSV/CSV
                if is_valid:
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
                # If not validated and no source file, nothing to import or delete by path
                continue
            if dry_run:
                # Do not modify DB in dry-run
                continue
            if is_valid:
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
                    from reactions_db import set_validated_by_source

                    updated = set_validated_by_source(con, str(source_path), True, by=by, at_iso=at)
                    if updated == 0:
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
            else:
                # Not validated: remove any existing entries from this source
                try:
                    from reactions_db import delete_reactions_by_source

                    deleted = delete_reactions_by_source(con, str(source_path))
                    deleted_total += deleted
                except Exception as e:
                    issues.append(
                        {
                            "table_no": tno,
                            "image": str(img),
                            "source_path": str(source_path),
                            "issue": "delete_failed",
                            "message": f"Failed to delete unvalidated entries: {e}",
                        }
                    )
    summary = {
        "updated_total": updated_total,
        "imported_total": imported_total,
        "deleted_total": deleted_total,
        "issues": issues,
        "tables": list(table_numbers),
    }
    print(
        f"[SYNC] Imported/updated TSVs={imported_total}; set validated rows={updated_total}; deleted unvalidated rows={deleted_total}; issues={len(issues)} (tables {table_numbers})"
    )
    return summary
