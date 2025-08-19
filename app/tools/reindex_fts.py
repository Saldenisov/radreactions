from app.reactions_db import ensure_db

def rebuild_fts():
    con = ensure_db()
    try:
        con.execute("INSERT INTO reactions_fts(reactions_fts) VALUES('rebuild')")
        con.commit()
        cnt = con.execute('SELECT COUNT(*) FROM reactions').fetchone()[0]
        print(f"[FTS] Rebuilt index; reactions={cnt}")
    except Exception as e:
        print(f"[FTS][ERROR] {e}")

if __name__ == "__main__":
    rebuild_fts()

