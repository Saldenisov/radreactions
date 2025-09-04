import csv
import re
from pathlib import Path
from typing import Any
import msvcrt
import sys
import time

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


def check_for_stop():
    """Check if user wants to stop execution by pressing 'q' key"""
    if msvcrt.kbhit():
        key = msvcrt.getch().decode('utf-8').lower()
        if key == 'q':
            print("\n>>> User requested stop. Exiting...")
            return True
    return False


def import_single_csv_with_stop(csv_path: Path, table_no: int):
    """Import a single CSV with user stop capability"""
    con = ensure_db()
    inserted_reactions = 0
    inserted_measurements = 0
    
    try:
        stem = csv_path.stem
        # Derive PNG path
        from config import get_table_paths
        
        IMAGE_DIR, _, TSV_DIR, _ = get_table_paths(f"table{table_no}")
        png_path = IMAGE_DIR / f"{stem}.png"
        png_path_str = str(png_path) if png_path.exists() else None
        
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            for row_idx, row in enumerate(reader):
                # Check for user stop request every row
                if check_for_stop():
                    con.commit()
                    return inserted_reactions, inserted_measurements, True
                
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
    return inserted_reactions, inserted_measurements, False


def import_first_10_reactions():
    """Import only the first 10 reactions from table8 sub_tables_images with user stop capability"""
    print("Starting import of first 10 reactions from table8_exported/sub_tables_images/csv")
    print("Press 'q' at any time to stop execution")
    print("-" * 60)
    
    con = ensure_db()
    total_reactions = 0
    total_measurements = 0
    
    # Path to the CSV directory
    csv_dir = Path("E:/ICP_notebooks/Buxton/table8_exported/sub_tables_images/csv")
    
    if not csv_dir.exists():
        print(f"Error: Directory {csv_dir} does not exist!")
        return
    
    # Get all CSV files and sort them
    csv_files = sorted(list(csv_dir.glob("*.csv")))
    
    if not csv_files:
        print("No CSV files found in the directory!")
        return
    
    print(f"Found {len(csv_files)} CSV files. Processing first 10...")
    
    # Process only first 10 files
    for i, csv_path in enumerate(csv_files[:10], 1):
        print(f"\nProcessing [{i}/10]: {csv_path.name}")
        
        # Check for stop before processing each file
        if check_for_stop():
            print("\n>>> User requested stop. Exiting...")
            break
        
        try:
            reactions, measurements, stopped = import_single_csv_with_stop(csv_path, 8)
            total_reactions += reactions
            total_measurements += measurements
            
            print(f"  ✓ Processed: {reactions} reactions, {measurements} measurements")
            
            if stopped:
                break
                
            # Small delay to allow user to press 'q'
            time.sleep(0.1)
            
        except Exception as e:
            print(f"  ✗ Error processing {csv_path.name}: {e}")
            continue
    
    print(f"\n" + "="*60)
    print(f"Import completed!")
    print(f"Total reactions processed: {total_reactions}")
    print(f"Total measurements processed: {total_measurements}")
    print(f"Files processed: {min(10, len(csv_files))}/{len(csv_files)} available")


if __name__ == "__main__":
    import_first_10_reactions()
