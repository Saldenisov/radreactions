import math
from pathlib import Path
from typing import Any

from app.config import AVAILABLE_TABLES, get_table_paths
from app.db_utils import load_db
from app.import_reactions import import_single_csv_idempotent
from app.reactions_db import ensure_db, set_validated_by_source

CHUNK_SIZE = 50


def collect_sources(tables: list[str]) -> list[tuple[int, Path, dict[str, Any]]]:
    sources: list[tuple[int, Path, dict[str, Any]]] = []
    for t in tables:
        try:
            tno = int(t.replace("table", ""))
        except Exception:
            continue
        IMAGE_DIR, PDF_DIR, TSV_DIR, DB_JSON_PATH = get_table_paths(t)
        if not DB_JSON_PATH.exists():
            print(f"[SKIP] {t} has no validation_db.json at {DB_JSON_PATH}")
            continue
        try:
            db = load_db(DB_JSON_PATH, IMAGE_DIR)
        except Exception as e:
            print(f"[WARN] Failed to load {DB_JSON_PATH}: {e}")
            continue
        for img, meta in db.items():
            # normalize meta
            if isinstance(meta, bool):
                meta = {"validated": bool(meta), "by": None, "at": None}
            stem = Path(img).stem
            csv_path = TSV_DIR / f"{stem}.csv"
            tsv_path = TSV_DIR / f"{stem}.tsv"
            source = csv_path if csv_path.exists() else (tsv_path if tsv_path.exists() else None)
            if source is None:
                print(f"[MISS] {t} image {img}: no TSV/CSV at {csv_path} or {tsv_path}")
                continue
            sources.append((tno, source, meta))
    return sources


def rebuild_db_from_validations(chunk_size: int = CHUNK_SIZE):
    con = ensure_db()
    cur = con.cursor()
    # Clean all tables (fresh start) without dropping schema
    for tbl in ["measurements", "reactions_fts", "reactions", "references_map"]:
        cur.execute(f"DELETE FROM {tbl}")
    con.commit()

    tasks = collect_sources(AVAILABLE_TABLES)
    total = len(tasks)
    if total == 0:
        print("[INFO] No sources discovered from validation_db.json. Nothing to import.")
        return

    chunks = math.ceil(total / chunk_size)
    processed = 0
    print(f"[START] Importing {total} sources in {chunks} chunks (chunk_size={chunk_size})")

    for i in range(chunks):
        start = i * chunk_size
        end = min(start + chunk_size, total)
        batch = tasks[start:end]
        batch_imported = 0
        batch_validated_updates = 0
        for tno, source, meta in batch:
            try:
                rcount, _ = import_single_csv_idempotent(source, tno)
                batch_imported += rcount or 0
            except Exception as e:
                print(f"[ERR][IMPORT] table={tno} source={source}: {e}")
                continue
            try:
                updated = set_validated_by_source(
                    con,
                    str(source),
                    bool(meta.get("validated", False)),
                    by=meta.get("by"),
                    at_iso=meta.get("at"),
                )
                batch_validated_updates += updated
            except Exception as e:
                print(f"[ERR][VALIDATE] table={tno} source={source}: {e}")
        processed = end
        pct = processed * 100.0 / total
        print(
            f"[PROGRESS] {processed}/{total} ({pct:.1f}%) | batch_imported={batch_imported} batch_validated_updates={batch_validated_updates}"
        )

    # Reindex FTS5
    try:
        con.execute("INSERT INTO reactions_fts(reactions_fts) VALUES('rebuild')")
        con.commit()
        print("[FTS] Rebuilt reactions_fts index")
    except Exception as e:
        print(f"[FTS][WARN] Failed to rebuild FTS: {e}")

    # Summary
    rcount = con.execute("SELECT COUNT(*) FROM reactions").fetchone()[0]
    mcount = con.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    print(f"[DONE] Recreated DB. reactions={rcount}, measurements={mcount}")


if __name__ == "__main__":
    rebuild_db_from_validations()
