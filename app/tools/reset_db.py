from app.reactions_db import DB_PATH, SCHEMA_SQL, connect


def reset_db():
    con = connect(DB_PATH)
    cur = con.cursor()
    # Drop triggers first (safe even if not existing)
    for trig in ["reactions_ai", "reactions_ad", "reactions_au"]:
        try:
            cur.execute(f"DROP TRIGGER IF EXISTS {trig}")
        except Exception:
            pass
    # Drop tables (order: children first)
    for tbl in [
        "measurements",
        "reactions_fts",
        "reactions",
        "references_map",
        "schema_migrations",
    ]:
        try:
            cur.execute(f"DROP TABLE IF EXISTS {tbl}")
        except Exception:
            pass
    con.commit()
    # Recreate schema
    con.executescript(SCHEMA_SQL)
    con.execute("INSERT OR IGNORE INTO schema_migrations(name) VALUES (?)", ("001_init",))
    con.commit()


if __name__ == "__main__":
    reset_db()
    print("reset-complete")
