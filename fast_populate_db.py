#!/usr/bin/env python3
"""Fast bulk DB population optimized for speed."""

import csv
import json
import sqlite3
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import get_table_paths
from app.reactions_db import (
    MIGRATION_NAME_INIT,
    SCHEMA_SQL,
    TABLE_CATEGORY,
    canonicalize_source_path,
    latex_to_canonical,
)


def parse_rate_value_fast(raw: str) -> float | None:
    """Fast rate value parsing."""
    if not raw:
        return None
    try:
        s = raw.replace("\\times", "x").replace(" ", "")
        if "x10^" in s:
            parts = s.split("x10^", 1)
            return float(parts[0]) * (10 ** int(parts[1]))
        if "×10^" in s:
            parts = s.split("×10^", 1)
            return float(parts[0]) * (10 ** int(parts[1]))
        return float(s)
    except Exception:
        return None


def bulk_import_validated_sources() -> None:
    """Fast bulk import of all validated sources."""
    print("[FAST] Starting bulk import...")

    # Reset DB completely for clean slate
    db_path = Path("reactions.db")
    if db_path.exists():
        db_path.unlink()

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")  # Faster than FULL
    con.execute("PRAGMA cache_size = 10000")  # Larger cache
    con.execute("PRAGMA temp_store = MEMORY")  # Use memory for temp

    # Create schema
    con.executescript(SCHEMA_SQL)
    con.execute("INSERT INTO schema_migrations(name) VALUES (?)", (MIGRATION_NAME_INIT,))
    con.commit()

    # Collect all validated sources first
    sources_to_import = []
    validation_updates = []

    print("[FAST] Collecting validated sources...")
    for tno in [5, 6, 7, 8, 9]:
        table_name = f"table{tno}"
        IMAGE_DIR, PDF_DIR, TSV_DIR, DB_JSON_PATH = get_table_paths(table_name)

        if not DB_JSON_PATH.exists():
            continue

        try:
            # Load validation data
            raw_data = json.loads(DB_JSON_PATH.read_text(encoding="utf-8"))
            for img, meta in raw_data.items():
                if isinstance(meta, bool):
                    is_valid, by, at = bool(meta), None, None
                else:
                    is_valid = bool(meta.get("validated", False))
                    by = meta.get("by")
                    at = meta.get("at")

                if not is_valid:
                    continue  # Skip non-validated

                stem = Path(img).stem
                csv_path = TSV_DIR / f"{stem}.csv"
                tsv_path = TSV_DIR / f"{stem}.tsv"
                source_path = (
                    csv_path if csv_path.exists() else (tsv_path if tsv_path.exists() else None)
                )

                if source_path:
                    sources_to_import.append((tno, source_path))
                    validation_updates.append((str(source_path), is_valid, by, at))

        except Exception as e:
            print(f"[FAST] Error loading {DB_JSON_PATH}: {e}")

    print(f"[FAST] Found {len(sources_to_import)} validated sources to import")

    if not sources_to_import:
        print("[FAST] No sources to import")
        return

    # Bulk import all TSV/CSV files
    reactions_data: list[
        tuple[int, str, str | None, str | None, str, str, str, str, str, str, str | None, str]
    ] = []
    measurements_data: list[
        tuple[
            int, str | None, None, str, float | None, None, None, str | None, int | None, str, None
        ]
    ] = []
    references_data: list[tuple[str, str | None, str | None]] = []
    ref_map: dict[str, int] = {}  # buxton_code -> ref_id

    print("[FAST] Processing TSV/CSV files...")
    for i, (tno, source_path) in enumerate(sources_to_import):
        if i % 100 == 0:
            print(f"[FAST] Processing {i}/{len(sources_to_import)}...")

        try:
            with open(source_path, newline="", encoding="utf-8") as f:
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

                    # Process reaction
                    category = TABLE_CATEGORY.get(tno, str(tno))
                    canonical, reactants, products, r_species, p_species = latex_to_canonical(
                        formula_latex
                    )
                    src_canon = canonicalize_source_path(str(source_path))

                    reaction_data = (
                        tno,
                        category,
                        buxton_no,
                        reaction_name,
                        formula_latex,
                        canonical,
                        reactants,
                        products,
                        json.dumps(r_species, ensure_ascii=False),
                        json.dumps(p_species, ensure_ascii=False),
                        method_or_notes,
                        src_canon,
                    )
                    reactions_data.append(reaction_data)
                    reaction_idx = len(reactions_data)  # 1-based index for later reference

                    # Handle reference
                    ref_id = None
                    if reference_code:
                        if reference_code not in ref_map:
                            ref_id = len(references_data) + 1
                            ref_map[reference_code] = ref_id
                            references_data.append((reference_code, None, None))
                        else:
                            ref_id = ref_map[reference_code]

                    # Process measurement
                    rate_num = parse_rate_value_fast(rate_value) if rate_value else None
                    measurement_data = (
                        reaction_idx,
                        pH,
                        None,
                        rate_value or "",
                        rate_num,
                        None,
                        None,
                        method_or_notes,
                        ref_id,
                        src_canon,
                        None,
                    )
                    measurements_data.append(measurement_data)

        except Exception as e:
            print(f"[FAST] Error processing {source_path}: {e}")

    print(
        f"[FAST] Prepared {len(reactions_data)} reactions, {len(measurements_data)} measurements, {len(references_data)} references"
    )

    # Bulk insert everything
    print("[FAST] Bulk inserting data...")

    # References first
    if references_data:
        con.executemany(
            "INSERT INTO references_map(buxton_code, citation_text, doi) VALUES (?,?,?)",
            references_data,
        )

    # Reactions
    con.executemany(
        """INSERT INTO reactions(table_no, table_category, buxton_reaction_number, reaction_name,
           formula_latex, formula_canonical, reactants, products, reactant_species,
           product_species, notes, source_path) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        reactions_data,
    )

    # Measurements (need to map reaction_idx to actual IDs)
    measurements_final = []
    for measurement in measurements_data:
        reaction_idx = measurement[0]
        # reaction_idx is 1-based, so actual DB ID is also reaction_idx
        measurement_fixed = (reaction_idx,) + measurement[1:]
        measurements_final.append(measurement_fixed)

    con.executemany(
        """INSERT INTO measurements(reaction_id, pH, temperature_C, rate_value, rate_value_num,
           rate_units, method, conditions, reference_id, source_path, page_info)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        measurements_final,
    )

    # Bulk update validation flags
    print("[FAST] Setting validation flags...")
    for source_path, _is_valid, by, at in validation_updates:
        # validation_updates only contains validated=True entries in this fast path
        src_canon = canonicalize_source_path(source_path)
        con.execute(
            "UPDATE reactions SET validated = 1, validated_by = ?, validated_at = ? WHERE source_path = ?",
            (by, at, src_canon),
        )

    con.commit()

    # Rebuild FTS
    print("[FAST] Rebuilding FTS index...")
    con.execute("INSERT INTO reactions_fts(reactions_fts) VALUES('rebuild')")
    con.commit()

    # Final counts
    rcount = con.execute("SELECT COUNT(*) FROM reactions").fetchone()[0]
    mcount = con.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    vcount = con.execute("SELECT COUNT(*) FROM reactions WHERE validated = 1").fetchone()[0]

    print(f"[FAST] DONE! reactions={rcount}, measurements={mcount}, validated={vcount}")
    con.close()


if __name__ == "__main__":
    bulk_import_validated_sources()
