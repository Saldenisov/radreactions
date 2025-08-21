#!/usr/bin/env python3
import json
from pathlib import Path


def check_table(table_name="table9"):
    base = Path(r"E:\ICP_notebooks\Buxton\radreactions\data-full")
    t = table_name
    json_path = base / t / "sub_tables_images" / "validation_db.json"
    csv_dir = base / t / "sub_tables_images" / "csv"

    print(f"json_path exists: {json_path.exists()} -> {json_path}")
    print(f"csv_dir exists: {csv_dir.exists()} -> {csv_dir}")

    if not json_path.exists():
        print("ERROR: validation_db.json not found")
        return

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR reading JSON: {e}")
        return

    validated = []
    for k, v in data.items():
        ok = (v is True) or (isinstance(v, dict) and bool(v.get("validated", False)))
        if ok:
            validated.append(Path(k).stem)

    with_file = []
    missing = []
    for stem in validated:
        csv_file = csv_dir / f"{stem}.csv"
        tsv_file = csv_dir / f"{stem}.tsv"
        if csv_file.exists() or tsv_file.exists():
            with_file.append(stem)
        else:
            missing.append(stem)

    summary = {
        "table": t,
        "validated_images": len(validated),
        "with_tsv_or_csv": len(with_file),
        "missing_files": len(missing),
    }

    print(json.dumps(summary, indent=2))

    if missing:
        print("\nMISSING STEMS:")
        for i, s in enumerate(missing[:10]):  # Show first 10
            print(f"  {i + 1}. {s}")
        if len(missing) > 10:
            print(f"  ... and {len(missing) - 10} more")


if __name__ == "__main__":
    import sys

    table = sys.argv[1] if len(sys.argv) > 1 else "table9"
    check_table(table)
