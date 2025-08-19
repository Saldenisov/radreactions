import json

def load_db(path, image_dir):
    """Load validation DB and normalize schema.

    New schema per image:
      { "validated": bool, "by": str|None, "at": ISO8601 str|None }

    Backward compatible with legacy bool values.
    """
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        # Legacy format: { "image.png": true/false }
        for k, v in list(raw.items()):
            if isinstance(v, bool):
                raw[k] = {"validated": v, "by": None, "at": None}
                changed = True
            elif isinstance(v, dict):
                # ensure keys exist
                v.setdefault("validated", bool(v.get("validated", False)))
                v.setdefault("by", v.get("by"))
                v.setdefault("at", v.get("at"))
            else:
                # unknown type, coerce to not validated
                raw[k] = {"validated": False, "by": None, "at": None}
                changed = True
        if changed:
            path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        return raw
    imgs = sorted([f.name for f in image_dir.iterdir() if f.suffix.lower()=='.png'])
    db_init = {img: {"validated": False, "by": None, "at": None} for img in imgs}
    path.write_text(json.dumps(db_init, indent=2, ensure_ascii=False), encoding="utf-8")
    return db_init

def get_stats_for_table(db):
    total = len(db)
    def _is_valid(v):
        return (v is True) or (isinstance(v, dict) and bool(v.get("validated", False)))
    validated = sum(1 for v in db.values() if _is_valid(v))
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
                for v in db.values():
                    if (v is True) or (isinstance(v, dict) and bool(v.get("validated", False))):
                        validated += 1
            except Exception:
                continue
    percent = 100 * validated / total if total > 0 else 0
    return total, validated, percent
