def test_canonicalize_source_path_relative_to_base(data_env):
    base = data_env["base_dir"]
    mods = data_env["mods"]

    # Create a path under BASE_DIR
    p = base / "table6" / "sub_tables_images" / "csv" / "img001.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")

    rel = mods["reactions_db"].canonicalize_source_path(str(p))
    assert rel == "table6/sub_tables_images/csv/img001.csv"


def test_list_and_search_reactions(data_env):
    mods = data_env["mods"]
    # Create a DB and add a reaction
    con = mods["reactions_db"].ensure_db()
    try:
        rid = mods["reactions_db"].get_or_create_reaction(
            con,
            table_no=6,
            buxton_reaction_number="6-002",
            reaction_name="Hydrated electron with oxygen",
            formula_latex=r"$\ce{e_{aq}^{-} + O_2 -> O_2^{.-}}$",
            notes=None,
            source_path="table6/sub_tables_images/csv/img002.csv",
            png_path="table6/sub_tables_images/img002.png",
        )
        con.commit()

        # List
        rows = mods["reactions_db"].list_reactions(con, name_filter="electron", limit=10)
        assert any(r["id"] == rid for r in rows)

        # Search via FTS (match by name)
        hits = mods["reactions_db"].search_reactions(con, "electron", table_no=None, limit=10)
        assert any(h["id"] == rid for h in hits)
    finally:
        con.close()
