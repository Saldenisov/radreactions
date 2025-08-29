def test_fast_populate_db_inserts_validated_items(data_env):
    base = data_env["base_dir"]
    mods = data_env["mods"]

    from tests.conftest import make_table_with_item

    # Create two validated items in table9
    make_table_with_item(base, "table9", "imgA")
    make_table_with_item(base, "table9", "imgB")

    # Build into a temporary DB path
    target_db = base / "reactions_build.db"
    mods["fast_populate_db"].bulk_import_validated_sources(target_db)

    # Verify
    import sqlite3

    con = sqlite3.connect(str(target_db))
    try:
        con.row_factory = sqlite3.Row
        rcount = con.execute("SELECT COUNT(*) FROM reactions").fetchone()[0]
        vcount = con.execute("SELECT COUNT(*) FROM reactions WHERE validated = 1").fetchone()[0]
        assert rcount == 2
        assert vcount == 2
        row = con.execute("SELECT reactants FROM reactions LIMIT 1").fetchone()
        assert "e_{aq}^{-}" in row[0]
    finally:
        con.close()
