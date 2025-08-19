import json

from app.reactions_db import ensure_db, latex_to_canonical


def recompute_all():
    con = ensure_db()
    cur = con.cursor()
    cur.execute("SELECT id, formula_latex FROM reactions")
    rows = cur.fetchall()
    updated = 0
    for rid, formula_latex in rows:
        canonical, reactants, products, r_species, p_species = latex_to_canonical(formula_latex)
        cur.execute(
            "UPDATE reactions SET formula_canonical = ?, reactants = ?, products = ?, reactant_species = ?, product_species = ?, updated_at = datetime('now') WHERE id = ?",
            (
                canonical,
                reactants,
                products,
                json.dumps(r_species, ensure_ascii=False),
                json.dumps(p_species, ensure_ascii=False),
                rid,
            ),
        )
        updated += 1
    con.commit()
    print({"updated": updated})


if __name__ == "__main__":
    recompute_all()
