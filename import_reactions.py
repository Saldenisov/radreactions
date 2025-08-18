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

