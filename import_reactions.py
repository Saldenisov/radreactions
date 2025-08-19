import csv
import re
from pathlib import Path
from typing import Optional

from config import AVAILABLE_TABLES, get_table_paths
from reactions_db import ensure_db, get_or_create_reaction, add_measurement, upsert_reference

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
            return base * (10 ** exp)
        if "×10^" in s:
            parts = s.split("×10^")
            base = float(parts[0])
            exp = int(parts[1])
            return base * (10 ** exp)
        return float(s)
    except Exception:
        return None

def import_single_csv(csv_path: Path, table_no: int):
    """Import a single tab-delimited CSV (TSV content with .csv extension) into reactions.db."""
    con = ensure_db()
    inserted_reactions = 0
    inserted_measurements = 0
    try:
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='\t')
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
                inserted_measurements += 1
    except Exception as e:
        print(f"[IMPORT_ONE] Error processing {csv_path}: {e}")
    con.commit()
    return inserted_reactions, inserted_measurements


def import_from_csvs(base_dir: Optional[Path] = None, table_numbers=(5,6,7,8,9)):
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
                with open(csv_path, newline='', encoding='utf-8') as f:
                    reader = csv.reader(f, delimiter='\t')
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
                        inserted_measurements += 1
            except Exception as e:
                print(f"[IMPORT] Error processing {csv_path}: {e}")
                continue
    con.commit()
    print(f"[IMPORT] Done. reactions~{inserted_reactions}, measurements={inserted_measurements}")


def sync_validations_to_db(table_numbers=(5,6,7,8,9)):
    """Read each table's validation_db.json and update reactions.validated flags.

    For each image with validated true, find csv/tsv by stem and mark all reactions
    whose source_path matches that file as validated.
    """
    con = ensure_db()
    updated_total = 0
    for tno in table_numbers:
        table_name = f"table{tno}"
        IMAGE_DIR, PDF_DIR, TSV_DIR, DB_PATH = get_table_paths(table_name)
        if not DB_PATH.exists():
            continue
        try:
            from db_utils import load_db
            db = load_db(DB_PATH, IMAGE_DIR)
        except Exception as e:
            print(f"[SYNC] Failed to load {DB_PATH}: {e}")
            continue
        for img, meta in db.items():
            is_valid = meta if isinstance(meta, bool) else bool(meta.get('validated', False))
            stem = Path(img).stem
            csv_candidate = TSV_DIR / f"{stem}.csv"
            tsv_candidate = TSV_DIR / f"{stem}.tsv"
            source_file = None
            if csv_candidate.exists():
                source_file = str(csv_candidate)
            elif tsv_candidate.exists():
                source_file = str(tsv_candidate)
            if source_file is None:
                continue
            try:
                from reactions_db import set_validated_by_source
                updated = set_validated_by_source(con, source_file, bool(is_valid))
                updated_total += updated
            except Exception as e:
                print(f"[SYNC] Failed to update {source_file}: {e}")
    print(f"[SYNC] Updated validated flags for {updated_total} reaction rows")

import csv
import re
from pathlib import Path
from typing import Optional

from config import AVAILABLE_TABLES, get_table_paths
from reactions_db import ensure_db, get_or_create_reaction, add_measurement, upsert_reference

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
            return base * (10 ** exp)
        if "×10^" in s:
            parts = s.split("×10^")
            base = float(parts[0])
            exp = int(parts[1])
            return base * (10 ** exp)
        return float(s)
    except Exception:
        return None

def import_from_csvs(base_dir: Optional[Path] = None, table_numbers=(5,6,7,8,9)):
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
                with open(csv_path, newline='', encoding='utf-8') as f:
                    reader = csv.reader(f, delimiter='\t')
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
                        inserted_measurements += 1
            except Exception as e:
                print(f"[IMPORT] Error processing {csv_path}: {e}")
                continue
    con.commit()
    print(f"[IMPORT] Done. reactions~{inserted_reactions}, measurements={inserted_measurements}")


def sync_validations_to_db(table_numbers=(5,6,7,8,9)):
    """Read each table's validation_db.json and update reactions.validated flags.

    For each image with validated true, find csv/tsv by stem and mark all reactions
    whose source_path matches that file as validated.
    """
    con = ensure_db()
    updated_total = 0
    for tno in table_numbers:
        table_name = f"table{tno}"
        IMAGE_DIR, PDF_DIR, TSV_DIR, DB_PATH = get_table_paths(table_name)
        if not DB_PATH.exists():
            continue
        try:
            from db_utils import load_db
            db = load_db(DB_PATH, IMAGE_DIR)
        except Exception as e:
            print(f"[SYNC] Failed to load {DB_PATH}: {e}")
            continue
        for img, meta in db.items():
            is_valid = meta if isinstance(meta, bool) else bool(meta.get('validated', False))
            stem = Path(img).stem
            csv_candidate = TSV_DIR / f"{stem}.csv"
            tsv_candidate = TSV_DIR / f"{stem}.tsv"
            source_file = None
            if csv_candidate.exists():
                source_file = str(csv_candidate)
            elif tsv_candidate.exists():
                source_file = str(tsv_candidate)
            if source_file is None:
                continue
            try:
                from reactions_db import set_validated_by_source
                updated = set_validated_by_source(con, source_file, bool(is_valid))
                updated_total += updated
            except Exception as e:
                print(f"[SYNC] Failed to update {source_file}: {e}")
    print(f"[SYNC] Updated validated flags for {updated_total} reaction rows")

