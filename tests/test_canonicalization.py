import sqlite3
from pathlib import Path

import pytest

from reactions_db import (
    ensure_db,
    get_or_create_reaction,
    get_reaction_with_measurements,
    latex_to_canonical,
)


@pytest.fixture()
def tmp_db(tmp_path: Path):
    db_path = tmp_path / "test_reactions.db"
    con = ensure_db(db_path)
    try:
        yield con
    finally:
        try:
            con.close()
        except Exception:
            pass


def test_latex_to_canonical_e_aq_nested_braces():
    # Ensure nested braces inside \ce{...} are fully captured (no truncation like 'e_{aq')
    formula = r"\ce{e_{aq}^{-} + O_2 -> O_2^{.-}}"
    canonical, reactants, products, r_species, p_species = latex_to_canonical(formula)

    assert reactants == "e_{aq}^{-} + O_{2}"
    # The code maps ^{.-} to a bullet form; ensure the bullet-minus info is preserved
    assert "O_{2}" in products
    assert "-" in products  # charge kept
    assert len(r_species) == 2
    assert r_species[0] == "e_{aq}^{-}"
    assert r_species[1] == "O_{2}"
    assert len(p_species) == 1
    assert "O_{2}" in p_species[0]
    assert canonical.startswith("e_{aq}^{-} + O_{2} -> ")


def test_latex_to_canonical_ce_extraction_from_wrapped_text():
    # \ce{...} embedded in surrounding text should be extracted correctly
    formula = r"prefix \ce{A_{x}^{y} + B -> C_{2}} suffix"
    canonical, reactants, products, r_species, p_species = latex_to_canonical(formula)

    assert reactants == "A_{x}^{y} + B"
    assert products == "C_{2}"
    assert r_species == ["A_{x}^{y}", "B"]
    assert p_species == ["C_{2}"]
    assert canonical == "A_{x}^{y} + B -> C_{2}"


def test_db_insert_and_fetch(tmp_db: sqlite3.Connection):
    # Insert a reaction and ensure fields are set and retrievable
    rid = get_or_create_reaction(
        tmp_db,
        table_no=6,
        buxton_reaction_number="6-001",
        reaction_name="Hydrated electron with oxygen",
        formula_latex=r"$\ce{e_{aq}^{-} + O_2 -> O_2^{.-}}$",
        notes=None,
        source_path="tests/data/t6_001.tsv",
        png_path="tests/data/t6_001.png",
    )

    data = get_reaction_with_measurements(tmp_db, rid)
    rec = data.get("reaction")
    assert rec is not None
    # Ensure canonicalization populated these fields
    assert rec["reactants"] == "e_{aq}^{-} + O_{2}"
    assert rec["products"].startswith("O_{2}")
    assert rec["formula_canonical"].startswith("e_{aq}^{-} + O_{2} -> ")
