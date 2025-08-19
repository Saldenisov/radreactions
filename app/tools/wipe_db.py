from app.reactions_db import ensure_db


def wipe_all():
    con = ensure_db()
    cur = con.cursor()
    # order matters due to FKs
    cur.execute("DELETE FROM measurements")
    cur.execute("DELETE FROM reactions_fts")
    cur.execute("DELETE FROM reactions")
    cur.execute("DELETE FROM references_map")
    con.commit()


if __name__ == "__main__":
    wipe_all()
    print("wiped")
