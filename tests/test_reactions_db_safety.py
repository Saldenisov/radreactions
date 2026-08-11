from pathlib import Path

import pytest


def _reactions_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "runtime-data"))
    import reactions_db

    return reactions_db


def test_reading_missing_database_fails_without_creating_it(monkeypatch, tmp_path):
    reactions_db = _reactions_db(monkeypatch, tmp_path)
    path = tmp_path / "missing" / "reactions.db"

    with pytest.raises(reactions_db.ReactionDatabaseUnavailable, match="unavailable"):
        reactions_db.ensure_db(path)
    assert not path.exists()


def test_explicit_initialization_and_single_backslash_ce_parsing(monkeypatch, tmp_path):
    reactions_db = _reactions_db(monkeypatch, tmp_path)
    path = tmp_path / "scientific" / "reactions.db"

    writable = reactions_db.initialize_db(path)
    try:
        reaction_id = reactions_db.get_or_create_reaction(
            writable,
            table_no=8,
            buxton_reaction_number="1",
            reaction_name="water",
            formula_latex=r"\ce{H2O -> OH}",
            notes=None,
            source_path="table8/reaction-1.csv",
            png_path="table8/reaction-1.png",
        )
        writable.commit()
    finally:
        writable.close()

    readonly = reactions_db.ensure_db(path)
    try:
        row = readonly.execute(
            "SELECT formula_canonical FROM reactions WHERE id = ?", (reaction_id,)
        ).fetchone()
    finally:
        readonly.close()
    assert row[0] == "H2O -> OH"


def test_explicit_initialization_includes_public_export_columns(monkeypatch, tmp_path):
    reactions_db = _reactions_db(monkeypatch, tmp_path)
    con = reactions_db.initialize_db(tmp_path / "scientific" / "reactions.db")
    try:
        columns = {row[1] for row in con.execute("PRAGMA table_info(references_map)")}
    finally:
        con.close()
    assert "bibtex" in columns
    assert "source_url" in columns


def test_malformed_fts_query_is_safe(monkeypatch, tmp_path):
    reactions_db = _reactions_db(monkeypatch, tmp_path)
    path = tmp_path / "scientific" / "reactions.db"
    con = reactions_db.initialize_db(path)
    try:
        reactions_db.get_or_create_reaction(
            con,
            table_no=8,
            buxton_reaction_number="1",
            reaction_name="Hydroxyl",
            formula_latex=r"\ce{OH + H2O -> H2O2}",
            notes=None,
            source_path="table8/reaction-1.csv",
            png_path="table8/reaction-1.png",
        )
        con.commit()
        assert reactions_db.search_reactions(con, '" OR *') == []
    finally:
        con.close()


def test_source_mutation_requires_exact_canonical_path(monkeypatch, tmp_path):
    reactions_db = _reactions_db(monkeypatch, tmp_path)
    con = reactions_db.initialize_db(tmp_path / "scientific" / "reactions.db")
    try:
        for directory in ("one", "two"):
            source = Path(tmp_path / directory / "same-name.csv")
            reactions_db.get_or_create_reaction(
                con,
                table_no=8,
                buxton_reaction_number=directory,
                reaction_name=directory,
                formula_latex=r"\ce{OH -> H2O}",
                notes=None,
                source_path=str(source),
                png_path=str(source.with_suffix(".png")),
            )
        con.commit()
        assert reactions_db.set_validated_by_source(
            con, str(tmp_path / "other" / "same-name.csv"), True
        ) == 0
        assert con.execute("SELECT COUNT(*) FROM reactions WHERE validated = 1").fetchone()[0] == 0
    finally:
        con.close()
