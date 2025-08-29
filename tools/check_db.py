import sqlite3
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "reactions.db"
con = sqlite3.connect(path)
con.row_factory = sqlite3.Row
cur = con.cursor()
rows = cur.execute("select count(*) from reactions").fetchone()[0]
bad = cur.execute(
    "select count(*) from reactions where formula_canonical like '%^{.%' and formula_canonical not like '%^{.}%' "
).fetchone()[0]
with_brace = cur.execute(
    "select count(*) from reactions where formula_canonical like '%^{.}%' "
).fetchone()[0]
print({"rows": rows, "bad_no_brace": bad, "with_brace": with_brace})
for r in cur.execute(
    "select id, formula_latex, formula_canonical from reactions where formula_canonical like '%^{.}%' limit 3"
).fetchall():
    print(r["id"], "|", r["formula_latex"], "=>", r["formula_canonical"])
