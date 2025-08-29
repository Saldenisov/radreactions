def test_rebuild_db_from_validations_creates_db_and_reaction(data_env, tmp_path):
    base = data_env["base_dir"]
    mods = data_env["mods"]

    # Create one validated item in table5
    from tests.conftest import make_table_with_item

    make_table_with_item(base, "table5", "img001")

    # Run rebuild
    mods["tools_rebuild_db"].rebuild_db_from_validations()

    # Verify DB contents using reactions_db against the same BASE_DIR
    con = mods["reactions_db"].ensure_db()
    try:
        # Counts
        rcount = con.execute("SELECT COUNT(*) FROM reactions").fetchone()[0]
        mcount = con.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
        assert rcount == 1
        assert mcount == 1
        # Reactants/products not truncated
        row = con.execute("SELECT reactants, products, formula_canonical FROM reactions").fetchone()
        reactants, products, canonical = row[0], row[1], row[2]
        assert "e_{aq}^{-}" in reactants
        assert "O_{2}" in reactants
        assert canonical.startswith("e_{aq}^{-} + O_{2} -> ")
    finally:
        con.close()
