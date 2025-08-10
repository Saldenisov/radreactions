import json

def load_db(path, image_dir):
    if path.exists():
        return json.loads(path.read_text())
    imgs = sorted([f.name for f in image_dir.iterdir() if f.suffix.lower()=='.png'])
    db_init = {img: False for img in imgs}
    path.write_text(json.dumps(db_init, indent=2))
    return db_init

def get_stats_for_table(db):
    total = len(db)
    validated = sum(1 for v in db.values() if v)
    percent = 100 * validated / total if total > 0 else 0
    return total, validated, percent

def aggregate_stats(available_tables, get_table_paths):
    total = 0
    validated = 0
    for table in available_tables:
        _, _, _, db_path = get_table_paths(table)
        if db_path.exists():
            try:
                db = json.loads(db_path.read_text(encoding="utf-8"))
                total += len(db)
                validated += sum(1 for v in db.values() if v)
            except Exception:
                continue
    percent = 100 * validated / total if total > 0 else 0
    return total, validated, percent
