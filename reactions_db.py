import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from config import BASE_DIR

DB_PATH = BASE_DIR / "reactions.db"

TABLE_CATEGORY = {
    5: "Rate constants for radical-radical reactions",
    6: "Rate constants for reactions of hydrated electrons in aqueous solution",
    7: "Rate constants for reactions of hydrogen atoms in aqueous solution",
    8: "Rate constants for reactions of hydroxyl radicals in aqueous solution",
    9: "Rate constants for reactions of the oxide radical ion in aqueous solution",
}


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    # Reduce 'database is locked' errors by waiting up to 5s for locks
    try:
        con.execute("PRAGMA busy_timeout = 5000")
    except Exception:
        pass
    try:
        con.execute("PRAGMA journal_mode = WAL")
    except Exception:
        pass
    return con


SCHEMA_SQL = r"""
BEGIN;
CREATE TABLE IF NOT EXISTS schema_migrations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Reactions: one per PNG image (a reaction). May or may not have an associated CSV.
CREATE TABLE IF NOT EXISTS reactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  table_no INTEGER NOT NULL,
  table_category TEXT NOT NULL,
  buxton_reaction_number TEXT,
  reaction_name TEXT,
  formula_latex TEXT,
  formula_canonical TEXT,
  reactants TEXT,
  products TEXT,
  reactant_species TEXT,
  product_species TEXT,
  notes TEXT,
  png_path TEXT UNIQUE,
  source_path TEXT, -- path to CSV if present (kept for compatibility)
  validated INTEGER NOT NULL DEFAULT 0,
  validated_by TEXT,
  validated_at TEXT,
  skipped INTEGER NOT NULL DEFAULT 0,
  skipped_by TEXT,
  skipped_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- References table (existing), augmented to store raw text from CSV when available
CREATE TABLE IF NOT EXISTS references_map (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  buxton_code TEXT UNIQUE,
  citation_text TEXT,
  doi TEXT UNIQUE,
  doi_status TEXT NOT NULL DEFAULT 'unknown',
  raw_text TEXT,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Measurements: multiple per reaction (rows from CSV)
CREATE TABLE IF NOT EXISTS measurements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reaction_id INTEGER NOT NULL REFERENCES reactions(id) ON DELETE CASCADE,
  pH TEXT,
  temperature_C REAL,
  rate_value TEXT NOT NULL,
  rate_value_num REAL,
  rate_units TEXT,
  method TEXT,
  conditions TEXT, -- use for comments
  reference_id INTEGER REFERENCES references_map(id) ON DELETE SET NULL, -- first/primary ref
  references_raw TEXT, -- full raw references field from CSV (may include many)
  source_path TEXT, -- CSV path
  page_info TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- FTS over selected reaction fields
CREATE VIRTUAL TABLE IF NOT EXISTS reactions_fts USING fts5(
  reaction_name, formula_canonical, notes, content='reactions', content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS reactions_ai AFTER INSERT ON reactions BEGIN
  INSERT INTO reactions_fts(rowid, reaction_name, formula_canonical, notes)
  VALUES (new.id, new.reaction_name, new.formula_canonical, new.notes);
END;
CREATE TRIGGER IF NOT EXISTS reactions_ad AFTER DELETE ON reactions BEGIN
  INSERT INTO reactions_fts(reactions_fts, rowid, reaction_name, formula_canonical, notes)
  VALUES ('delete', old.id, old.reaction_name, old.formula_canonical, old.notes);
END;
CREATE TRIGGER IF NOT EXISTS reactions_au AFTER UPDATE ON reactions BEGIN
  INSERT INTO reactions_fts(reactions_fts, rowid, reaction_name, formula_canonical, notes)
  VALUES ('delete', old.id, old.reaction_name, old.formula_canonical, old.notes);
  INSERT INTO reactions_fts(rowid, reaction_name, formula_canonical, notes)
  VALUES (new.id, new.reaction_name, new.formula_canonical, new.notes);
END;
COMMIT;
"""

MIGRATION_NAME_INIT = "001_init"


def ensure_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    con = connect(db_path)
    # check migration applied
    con.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    cur = con.execute("SELECT 1 FROM schema_migrations WHERE name = ?", (MIGRATION_NAME_INIT,))
    if cur.fetchone() is None:
        con.executescript(SCHEMA_SQL)
        con.execute("INSERT INTO schema_migrations(name) VALUES (?)", (MIGRATION_NAME_INIT,))
        con.commit()
    # Lightweight migrations for added columns/indexes if DB already existed
    try:
        cols_r = {row[1] for row in con.execute("PRAGMA table_info(reactions)").fetchall()}
        if "png_path" not in cols_r:
            con.execute("ALTER TABLE reactions ADD COLUMN png_path TEXT")
            con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_reactions_png_path ON reactions(png_path)"
            )
        if "source_path" not in cols_r:
            con.execute("ALTER TABLE reactions ADD COLUMN source_path TEXT")
        if "validated_by" not in cols_r:
            con.execute("ALTER TABLE reactions ADD COLUMN validated_by TEXT")
        if "validated_at" not in cols_r:
            con.execute("ALTER TABLE reactions ADD COLUMN validated_at TEXT")
        if "skipped" not in cols_r:
            con.execute("ALTER TABLE reactions ADD COLUMN skipped INTEGER NOT NULL DEFAULT 0")
        if "skipped_by" not in cols_r:
            con.execute("ALTER TABLE reactions ADD COLUMN skipped_by TEXT")
        if "skipped_at" not in cols_r:
            con.execute("ALTER TABLE reactions ADD COLUMN skipped_at TEXT")
        cols_m = {row[1] for row in con.execute("PRAGMA table_info(measurements)").fetchall()}
        if "references_raw" not in cols_m:
            con.execute("ALTER TABLE measurements ADD COLUMN references_raw TEXT")
        cols_ref = {row[1] for row in con.execute("PRAGMA table_info(references_map)").fetchall()}
        if "raw_text" not in cols_ref:
            con.execute("ALTER TABLE references_map ADD COLUMN raw_text TEXT")
        con.commit()
    except Exception:
        pass

    # Migration: update table_category strings per TABLE_CATEGORY mapping
    try:
        for tno, cat in TABLE_CATEGORY.items():
            con.execute("UPDATE reactions SET table_category = ? WHERE table_no = ?", (cat, tno))
        con.commit()
    except Exception:
        pass

    # Ensure performance indexes exist
    try:
        index_statements = [
            "CREATE INDEX IF NOT EXISTS idx_reactions_source_path ON reactions(source_path)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_reactions_png_path ON reactions(png_path)",
            "CREATE INDEX IF NOT EXISTS idx_reactions_validated ON reactions(validated)",
            "CREATE INDEX IF NOT EXISTS idx_reactions_skipped ON reactions(skipped)",
            "CREATE INDEX IF NOT EXISTS idx_reactions_table_no ON reactions(table_no)",
            "CREATE INDEX IF NOT EXISTS idx_measurements_reaction_source ON measurements(reaction_id, source_path)",
        ]
        for stmt in index_statements:
            try:
                con.execute(stmt)
            except Exception:
                pass
        con.commit()
    except Exception:
        pass

    return con


# ---------------- Canonicalization -----------------

_math_delims = [(r"$", r"$"), (r"\(", r"\)"), (r"\[", r"\]")]

# Note: Do NOT use a naive regex for \\ce{...} content; it may contain nested braces.
# We implement a balanced-brace extractor below.
_sup_re = re.compile(r"\^\{([^}]+)\}|\^([A-Za-z0-9+\-\.•]+)")
_sub_re = re.compile(r"_\{([^}]+)\}|_([A-Za-z0-9+\-\.]+)")
_spaces_re = re.compile(r"\s+")


def _extract_ce_payload(s: str) -> str | None:
    """Extract the payload inside the first \ce{...} block, preserving nested braces.

    Returns the inner text without the outer braces, or None if no \ce{...} found.
    Handles escaped characters and nested { } pairs.
    """
    try:
        start = s.find(r"\\ce{")
        if start == -1:
            return None
        i = start + 4  # position after "\\ce{"
        n = len(s)
        depth = 1
        j = i
        while j < n and depth > 0:
            c = s[j]
            if c == "\\":
                # Skip escaped char
                j += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            j += 1
        if depth == 0:
            # j now points just after the matching closing '}'
            return s[i : j - 1]
        # Fallback: unbalanced braces; capture until first closing brace as last resort
        m = re.search(r"\\ce\{([^}]*)\}", s)
        return m.group(1) if m else None
    except Exception:
        return None


radical_map = {
    r"\\cdot": "•",
    r"\\bullet": "•",
    ".": "•",
}
charge_map = {
    r"^{.-}": "•-",
    r"^{.+}": "•+",
}

arrow_map = {
    r"\-\>": "->",
    r"\rightarrow": "->",
}

phase_map = {
    "aq": "aq",
}


def strip_math(s: str) -> str:
    # remove outer math delimiters if present
    s = s.strip()
    if s.startswith("$") and s.endswith("$"):
        return s[1:-1]
    if s.startswith("\\(") and s.endswith("\\)"):
        return s[2:-2]
    if s.startswith("\\[") and s.endswith("\\]"):
        return s[2:-2]
    return s


_defuse_backslashes_re = re.compile(r"\\(rightarrow|ce|cdot|bullet)")


def latex_to_canonical(
    formula_latex: str,
) -> tuple[str, str, str, list[str], list[str]]:
    """Return (canonical, reactants, products, reactant_species, product_species)."""
    core = strip_math(formula_latex)
    # Extract inside \\ce{...} if present (support nested braces)
    payload = _extract_ce_payload(core)
    if payload is not None:
        core = payload
    # normalize arrows
    core = re.sub(r"\\rightarrow|\\to|\-\\>", "->", core)
    # Fix common malformed braces for radical dot: turn '^{.' (missing closing) into '^{.}'
    core = re.sub(r"\^\{\.(?!\})", "^{.}", core)
    # Within an already braced superscript, drop inner '^.' to avoid nested braces like '^{2-^{.}}' -> '^{2-.}'
    core = re.sub(r"(\^\{[^}]*?)\^\.?", r"\1.", core)
    # Collapse a nested braced dot inside a braced superscript: '^{2-^{.}}' -> '^{2-.}' (explicit form)
    core = re.sub(r"\^\{([^}]*)\^\{?\.([^}]*)\}", r"^{\1.\2}", core)
    # normalize radicals and charges inline
    core = core.replace("^{.-}", "•-").replace("^{.+}", "•+")
    core = core.replace("\\cdot", "•").replace("\\bullet", "•")
    # simplify superscripts/subscripts and ALWAYS keep braces in output
    core = _sup_re.sub(lambda mo: f"^{{{mo.group(1) or mo.group(2)}}}", core)
    core = _sub_re.sub(lambda mo: f"_{{{mo.group(1) or mo.group(2)}}}", core)
    # collapse spaces
    core = _spaces_re.sub(" ", core).strip()
    # Split reactants/products
    parts = [p.strip() for p in core.split("->", 1)]
    reactants = parts[0] if parts else ""
    products = parts[1] if len(parts) > 1 else ""

    # Tokenize species by +
    def toks(side: str) -> list[str]:
        if not side:
            return []
        return [re.sub(r"\s+", " ", t.strip()) for t in side.split("+")]

    r_species = toks(reactants)
    p_species = toks(products)
    canonical = f"{reactants} -> {products}" if products else reactants
    return canonical, reactants, products, r_species, p_species


# ---------------- Upserts & Search -----------------


def upsert_reference(
    con: sqlite3.Connection,
    buxton_code: str | None,
    citation_text: str | None,
    doi: str | None,
    raw_text: str | None = None,
) -> int | None:
    if not any([buxton_code, citation_text, doi, raw_text]):
        return None
    row = con.execute(
        "SELECT id FROM references_map WHERE (buxton_code IS ? OR buxton_code = ?) OR (doi IS ? OR doi = ?) OR (raw_text IS ? OR raw_text = ?) LIMIT 1",
        (buxton_code, buxton_code, doi, doi, raw_text, raw_text),
    ).fetchone()
    if row:
        ref_id = row[0]
        # update fields if provided
        con.execute(
            "UPDATE references_map SET citation_text = COALESCE(?, citation_text), doi = COALESCE(?, doi), raw_text = COALESCE(?, raw_text), updated_at = datetime('now') WHERE id = ?",
            (citation_text, doi, raw_text, ref_id),
        )
        return ref_id
    cur = con.execute(
        "INSERT INTO references_map(buxton_code, citation_text, doi, raw_text) VALUES (?,?,?,?)",
        (buxton_code, citation_text, doi, raw_text),
    )
    return cur.lastrowid


def get_or_create_reaction(
    con: sqlite3.Connection,
    *,
    table_no: int,
    buxton_reaction_number: str | None,
    reaction_name: str | None,
    formula_latex: str | None,
    notes: str | None,
    source_path: str | None,
    png_path: str | None,
) -> int:
    """Create or update a reaction row for a given PNG (one reaction per PNG).

    Deduplicate primarily by png_path. If formula is present, also compute canonical
    representation for search and display.
    """
    category = TABLE_CATEGORY.get(table_no, str(table_no))
    # Canonicalize paths
    src_canon = canonicalize_source_path(source_path) if source_path else None
    png_canon = canonicalize_source_path(png_path) if png_path else None

    # Compute canonical fields if we have a formula
    if formula_latex:
        canonical, reactants, products, r_species, p_species = latex_to_canonical(formula_latex)
    else:
        canonical, reactants, products, r_species, p_species = (None, "", "", [], [])

    # Dedup ONLY by png_path (each PNG is a distinct reaction)
    row = None
    if png_canon:
        row = con.execute(
            "SELECT id FROM reactions WHERE png_path = ?",
            (png_canon,),
        ).fetchone()

    if row:
        rid = row[0]
        con.execute(
            """
            UPDATE reactions
            SET reaction_name = COALESCE(?, reaction_name),
                formula_latex = COALESCE(?, formula_latex),
                formula_canonical = COALESCE(?, formula_canonical),
                reactants = COALESCE(?, reactants),
                products = COALESCE(?, products),
                reactant_species = COALESCE(?, reactant_species),
                product_species = COALESCE(?, product_species),
                notes = COALESCE(?, notes),
                source_path = COALESCE(?, source_path),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                reaction_name,
                formula_latex,
                canonical,
                reactants,
                products,
                json.dumps(r_species, ensure_ascii=False) if r_species else None,
                json.dumps(p_species, ensure_ascii=False) if p_species else None,
                notes,
                src_canon,
                rid,
            ),
        )
        return rid

    cur = con.execute(
        """
        INSERT INTO reactions(
          table_no, table_category, buxton_reaction_number, reaction_name,
          formula_latex, formula_canonical, reactants, products,
          reactant_species, product_species, notes, png_path, source_path
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            table_no,
            category,
            buxton_reaction_number,
            reaction_name,
            formula_latex,
            canonical,
            reactants,
            products,
            json.dumps(r_species, ensure_ascii=False) if r_species else None,
            json.dumps(p_species, ensure_ascii=False) if p_species else None,
            notes,
            png_canon,
            src_canon,
        ),
    )
    assert cur.lastrowid is not None
    return cur.lastrowid


def add_measurement(
    con: sqlite3.Connection,
    reaction_id: int,
    *,
    pH: str | None,
    temperature_C: float | None,
    rate_value: str,
    rate_value_num: float | None,
    rate_units: str | None,
    method: str | None,
    conditions: str | None,
    reference_id: int | None,
    references_raw: str | None,
    source_path: str | None,
    page_info: str | None,
) -> int:
    cur = con.execute(
        """
        INSERT INTO measurements(
          reaction_id, pH, temperature_C, rate_value, rate_value_num, rate_units,
          method, conditions, reference_id, references_raw, source_path, page_info
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            reaction_id,
            pH,
            temperature_C,
            rate_value,
            rate_value_num,
            rate_units,
            method,
            conditions,
            reference_id,
            references_raw,
            source_path,
            page_info,
        ),
    )
    assert cur.lastrowid is not None
    return cur.lastrowid


def search_reactions(
    con: sqlite3.Connection,
    query: str,
    *,
    table_no: int | None = None,
    limit: int = 50,
) -> list[sqlite3.Row]:
    if not query:
        return []
    q = query.strip()
    if table_no is None:
        sql = (
            "SELECT r.* FROM reactions r JOIN reactions_fts f ON r.id = f.rowid "
            "WHERE f.reactions_fts MATCH ? ORDER BY r.table_no, r.id LIMIT ?"
        )
        return con.execute(sql, (q, limit)).fetchall()
    else:
        sql = (
            "SELECT r.* FROM reactions r JOIN reactions_fts f ON r.id = f.rowid "
            "WHERE r.table_no = ? AND f.reactions_fts MATCH ? ORDER BY r.id LIMIT ?"
        )
        return con.execute(sql, (table_no, q, limit)).fetchall()


def count_reactions(con: sqlite3.Connection) -> int:
    row = con.execute("SELECT COUNT(*) FROM reactions").fetchone()
    return int(row[0]) if row else 0


def get_database_stats(con: sqlite3.Connection) -> dict[str, Any]:
    """Return overall and per-table statistics for the reactions DB.

    Structure:
      {
        'totals': {
            'reactions_total': int,
            'reactions_validated': int,
            'reactions_unvalidated': int,
            'measurements_total': int,
            'references_total': int,
            'references_with_doi': int,
            'references_without_doi': int,
            'last_reaction_updated_at': str|None,
            'last_measurement_updated_at': str|None,
            'orphan_measurements': int,
        },
        'per_table': [
            {
              'table_no': int,
              'table_category': str,
              'reactions_total': int,
              'reactions_validated': int,
              'reactions_unvalidated': int,
              'measurements_total': int
            }, ...
        ]
      }
    """
    totals: dict[str, Any] = {}
    # Overall counts
    totals["reactions_total"] = int(con.execute("SELECT COUNT(*) FROM reactions").fetchone()[0])
    totals["reactions_validated"] = int(
        con.execute("SELECT COUNT(*) FROM reactions WHERE validated = 1").fetchone()[0]
    )
    totals["reactions_unvalidated"] = totals["reactions_total"] - totals["reactions_validated"]
    totals["measurements_total"] = int(
        con.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    )
    totals["references_total"] = int(
        con.execute("SELECT COUNT(*) FROM references_map").fetchone()[0]
    )
    totals["references_with_doi"] = int(
        con.execute(
            "SELECT COUNT(*) FROM references_map WHERE doi IS NOT NULL AND TRIM(doi) <> ''"
        ).fetchone()[0]
    )
    totals["references_without_doi"] = totals["references_total"] - totals["references_with_doi"]

    # Last updated timestamps
    lr = con.execute("SELECT MAX(updated_at) FROM reactions").fetchone()[0]
    lm = con.execute("SELECT MAX(updated_at) FROM measurements").fetchone()[0]
    totals["last_reaction_updated_at"] = lr
    totals["last_measurement_updated_at"] = lm

    # Orphan measurements (should be 0 due to FK CASCADE)
    orphan_sql = (
        "SELECT COUNT(*) FROM measurements m "
        "LEFT JOIN reactions r ON r.id = m.reaction_id WHERE r.id IS NULL"
    )
    totals["orphan_measurements"] = int(con.execute(orphan_sql).fetchone()[0])

    # Per table stats
    per_table: list[dict[str, Any]] = []
    for tno, tcat in TABLE_CATEGORY.items():
        row_total = con.execute(
            "SELECT COUNT(*) FROM reactions WHERE table_no = ?", (tno,)
        ).fetchone()[0]
        row_val = con.execute(
            "SELECT COUNT(*) FROM reactions WHERE table_no = ? AND validated = 1", (tno,)
        ).fetchone()[0]
        row_meas = con.execute(
            "SELECT COUNT(*) FROM measurements m JOIN reactions r ON r.id = m.reaction_id WHERE r.table_no = ?",
            (tno,),
        ).fetchone()[0]
        per_table.append(
            {
                "table_no": tno,
                "table_category": tcat,
                "reactions_total": int(row_total),
                "reactions_validated": int(row_val),
                "reactions_unvalidated": int(row_total) - int(row_val),
                "measurements_total": int(row_meas),
            }
        )

    return {"totals": totals, "per_table": per_table}


# ---------------- Admin helper operations -----------------

def bulk_unvalidate_table(con: sqlite3.Connection, table_no: int) -> int:
    """Set validated=0 and clear metadata for all reactions in a given table.

    Returns the number of reaction rows updated.
    """
    cur = con.execute(
        "UPDATE reactions SET validated = 0, validated_by = NULL, validated_at = NULL, updated_at = datetime('now') WHERE table_no = ?",
        (table_no,),
    )
    con.commit()
    return cur.rowcount


def delete_table_data(con: sqlite3.Connection, table_no: int) -> dict[str, int]:
    """Delete all reactions (and cascading measurements) for a table.

    Returns a dict with counts: {'reactions_deleted': int, 'measurements_deleted_estimate': int}
    The measurements count is estimated from a pre-delete join and may differ slightly if constraints change.
    """
    # Estimate measurements count before deletion
    try:
        mcount = int(
            con.execute(
                "SELECT COUNT(*) FROM measurements m JOIN reactions r ON r.id = m.reaction_id WHERE r.table_no = ?",
                (table_no,),
            ).fetchone()[0]
        )
    except Exception:
        mcount = 0

    cur = con.execute("DELETE FROM reactions WHERE table_no = ?", (table_no,))
    rcount = cur.rowcount
    con.commit()
    return {"reactions_deleted": int(rcount or 0), "measurements_deleted_estimate": mcount}


def get_table_row_counts(con: sqlite3.Connection, table_no: int) -> dict[str, int]:
    """Return current counts for a table without modifying anything.

    Returns: {'reactions': int, 'measurements': int}
    """
    try:
        reactions = int(
            con.execute("SELECT COUNT(*) FROM reactions WHERE table_no = ?", (table_no,)).fetchone()[0]
        )
    except Exception:
        reactions = 0
    try:
        measurements = int(
            con.execute(
                "SELECT COUNT(*) FROM measurements m JOIN reactions r ON r.id = m.reaction_id WHERE r.table_no = ?",
                (table_no,),
            ).fetchone()[0]
        )
    except Exception:
        measurements = 0
    return {"reactions": reactions, "measurements": measurements}


def canonicalize_source_path(p: str) -> str:
    try:
        base = Path(BASE_DIR).resolve()
        pp = Path(p).resolve()
        try:
            rel = pp.relative_to(base)
            return str(rel).replace("\\", "/")
        except Exception:
            return pp.name  # fallback to filename-only
    except Exception:
        return Path(p).name


def set_validated_by_source(
    con: sqlite3.Connection,
    source_path: str,
    validated: bool,
    *,
    by: str | None = None,
    at_iso: str | None = None,
) -> int:
    """Set validated flag and metadata for all reactions from a given source path."""
    src_canon = canonicalize_source_path(source_path)
    # First try exact canonical match
    if validated:
        cur = con.execute(
            "UPDATE reactions SET validated = 1, validated_by = ?, validated_at = ?, updated_at = datetime('now') WHERE source_path = ?",
            (by, at_iso, src_canon),
        )
    else:
        cur = con.execute(
            "UPDATE reactions SET validated = 0, validated_by = NULL, validated_at = NULL, updated_at = datetime('now') WHERE source_path = ?",
            (src_canon,),
        )
    updated = cur.rowcount
    if updated == 0:
        # Fallback: match by filename suffix to handle legacy absolute paths
        filename = Path(source_path).name
        if validated:
            cur = con.execute(
                "UPDATE reactions SET validated = 1, validated_by = ?, validated_at = ?, updated_at = datetime('now') WHERE source_path LIKE '%' || ?",
                (by, at_iso, filename),
            )
        else:
            cur = con.execute(
                "UPDATE reactions SET validated = 0, validated_by = NULL, validated_at = NULL, updated_at = datetime('now') WHERE source_path LIKE '%' || ?",
                (filename,),
            )
        updated = cur.rowcount
    con.commit()
    return updated


def delete_reactions_by_source(
    con: sqlite3.Connection,
    source_path: str,
) -> int:
    """Delete reactions (and cascading measurements) for a given source path.

    Matches by canonical relative path; if 0 deleted, falls back to filename suffix match.
    Returns number of reaction rows deleted.
    """
    src_canon = canonicalize_source_path(source_path)
    cur = con.execute("DELETE FROM reactions WHERE source_path = ?", (src_canon,))
    deleted = cur.rowcount
    if deleted == 0:
        filename = Path(source_path).name
        cur = con.execute("DELETE FROM reactions WHERE source_path LIKE '%' || ?", (filename,))
        deleted = cur.rowcount
    con.commit()
    return deleted


def list_reactions(
    con: sqlite3.Connection,
    *,
    name_filter: str | None = None,
    limit: int = 1000,
    validated_only: bool | None = None,
) -> list[sqlite3.Row]:
    """List reactions ordered A->Z by name (fallback to canonical).

    Args:
        con: sqlite connection
        name_filter: optional case-insensitive filter on name or canonical formula
        limit: max rows
        validated_only: if True, only validated=1; if False, only validated=0; if None, no filter
    """
    where = []
    params: list[Any] = []

    if name_filter:
        where.append("lower(COALESCE(reaction_name, formula_canonical)) LIKE ?")
        params.append(f"%{name_filter.lower()}%")

    if validated_only is True:
        where.append("validated = 1")
    elif validated_only is False:
        where.append("validated = 0")

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    sql = (
        "SELECT * FROM reactions"
        + where_sql
        + " ORDER BY lower(COALESCE(reaction_name, formula_canonical)) ASC LIMIT ?"
    )
    params.append(limit)
    return con.execute(sql, tuple(params)).fetchall()


def get_reaction_with_measurements(con: sqlite3.Connection, reaction_id: int) -> dict[str, Any]:
    r = con.execute("SELECT * FROM reactions WHERE id = ?", (reaction_id,)).fetchone()
    if not r:
        return {}
    ms = con.execute(
        """
        SELECT m.*, re.buxton_code, re.citation_text, re.doi, re.doi_status
        FROM measurements m
        LEFT JOIN references_map re ON m.reference_id = re.id
        WHERE m.reaction_id = ?
        ORDER BY m.id ASC
        """,
        (reaction_id,),
    ).fetchall()
    return {"reaction": r, "measurements": ms}


def get_validation_meta_by_source(con: sqlite3.Connection, source_path: str) -> dict[str, Any]:
    """Return validation/skip metadata for a given source path.

    Structure: {'validated': bool, 'by': str|None, 'at': str|None, 'skipped': bool, 'skipped_by': str|None, 'skipped_at': str|None}

    Attempts exact canonical match first, then falls back to filename match.
    If multiple rows exist for the same source, prefer any row with validated=1,
    otherwise return the first row's metadata (likely None).
    """
    src_canon = canonicalize_source_path(source_path)
    row = con.execute(
        "SELECT validated, validated_by, validated_at, skipped, skipped_by, skipped_at FROM reactions WHERE source_path = ? ORDER BY validated DESC, skipped DESC LIMIT 1",
        (src_canon,),
    ).fetchone()
    if not row:
        filename = Path(source_path).name
        row = con.execute(
            "SELECT validated, validated_by, validated_at, skipped, skipped_by, skipped_at FROM reactions WHERE source_path LIKE '%' || ? ORDER BY validated DESC, skipped DESC LIMIT 1",
            (filename,),
        ).fetchone()
    if not row:
        return {
            "validated": False,
            "by": None,
            "at": None,
            "skipped": False,
            "skipped_by": None,
            "skipped_at": None,
        }
    return {
        "validated": bool(row[0]),
        "by": row[1],
        "at": row[2],
        "skipped": bool(row[3]),
        "skipped_by": row[4],
        "skipped_at": row[5],
    }


def get_validation_meta_by_image(con: sqlite3.Connection, png_path: str) -> dict[str, Any]:
    """Return validation/skip metadata for a given PNG path.

    Structure: {'validated': bool, 'by': str|None, 'at': str|None, 'skipped': bool, 'skipped_by': str|None, 'skipped_at': str|None}
    """
    src_canon = canonicalize_source_path(png_path)
    row = con.execute(
        "SELECT validated, validated_by, validated_at, skipped, skipped_by, skipped_at FROM reactions WHERE png_path = ? ORDER BY validated DESC, skipped DESC LIMIT 1",
        (src_canon,),
    ).fetchone()
    if not row:
        filename = Path(png_path).name
        row = con.execute(
            "SELECT validated, validated_by, validated_at, skipped, skipped_by, skipped_at FROM reactions WHERE png_path LIKE '%' || ? ORDER BY validated DESC, skipped DESC LIMIT 1",
            (filename,),
        ).fetchone()
    if not row:
        return {
            "validated": False,
            "by": None,
            "at": None,
            "skipped": False,
            "skipped_by": None,
            "skipped_at": None,
        }
    return {
        "validated": bool(row[0]),
        "by": row[1],
        "at": row[2],
        "skipped": bool(row[3]),
        "skipped_by": row[4],
        "skipped_at": row[5],
    }


def set_validated_by_image(
    con: sqlite3.Connection,
    png_path: str,
    validated: bool,
    *,
    by: str | None = None,
    at_iso: str | None = None,
) -> int:
    """Set validated flag for a single reaction identified by its PNG path."""
    src_canon = canonicalize_source_path(png_path)
    if validated:
        cur = con.execute(
            "UPDATE reactions SET validated = 1, validated_by = ?, validated_at = ?, updated_at = datetime('now') WHERE png_path = ?",
            (by, at_iso, src_canon),
        )
    else:
        cur = con.execute(
            "UPDATE reactions SET validated = 0, validated_by = NULL, validated_at = NULL, updated_at = datetime('now') WHERE png_path = ?",
            (src_canon,),
        )
    updated = cur.rowcount
    if updated == 0:
        filename = Path(png_path).name
        if validated:
            cur = con.execute(
                "UPDATE reactions SET validated = 1, validated_by = ?, validated_at = ?, updated_at = datetime('now') WHERE png_path LIKE '%' || ?",
                (by, at_iso, filename),
            )
        else:
            cur = con.execute(
                "UPDATE reactions SET validated = 0, validated_by = NULL, validated_at = NULL, updated_at = datetime('now') WHERE png_path LIKE '%' || ?",
                (filename,),
            )
        updated = cur.rowcount
    con.commit()
    return updated


def set_skipped_by_source(
    con: sqlite3.Connection,
    source_path: str,
    skipped: bool,
    *,
    by: str | None = None,
    at_iso: str | None = None,
) -> int:
    """Set skipped flag and metadata for all reactions from a given source path."""
    src_canon = canonicalize_source_path(source_path)
    # First try exact canonical match
    if skipped:
        cur = con.execute(
            "UPDATE reactions SET skipped = 1, skipped_by = ?, skipped_at = ?, updated_at = datetime('now') WHERE source_path = ?",
            (by, at_iso, src_canon),
        )
    else:
        cur = con.execute(
            "UPDATE reactions SET skipped = 0, skipped_by = NULL, skipped_at = NULL, updated_at = datetime('now') WHERE source_path = ?",
            (src_canon,),
        )
    updated = cur.rowcount
    if updated == 0:
        # Fallback: match by filename suffix
        filename = Path(source_path).name
        if skipped:
            cur = con.execute(
                "UPDATE reactions SET skipped = 1, skipped_by = ?, skipped_at = ?, updated_at = datetime('now') WHERE source_path LIKE '%' || ?",
                (by, at_iso, filename),
            )
        else:
            cur = con.execute(
                "UPDATE reactions SET skipped = 0, skipped_by = NULL, skipped_at = NULL, updated_at = datetime('now') WHERE source_path LIKE '%' || ?",
                (filename,),
            )
        updated = cur.rowcount
    con.commit()
    return updated


def set_skipped_by_image(
    con: sqlite3.Connection,
    png_path: str,
    skipped: bool,
    *,
    by: str | None = None,
    at_iso: str | None = None,
) -> int:
    """Set skipped flag for a single reaction identified by its PNG path."""
    src_canon = canonicalize_source_path(png_path)
    if skipped:
        cur = con.execute(
            "UPDATE reactions SET skipped = 1, skipped_by = ?, skipped_at = ?, updated_at = datetime('now') WHERE png_path = ?",
            (by, at_iso, src_canon),
        )
    else:
        cur = con.execute(
            "UPDATE reactions SET skipped = 0, skipped_by = NULL, skipped_at = NULL, updated_at = datetime('now') WHERE png_path = ?",
            (src_canon,),
        )
    updated = cur.rowcount
    if updated == 0:
        filename = Path(png_path).name
        if skipped:
            cur = con.execute(
                "UPDATE reactions SET skipped = 1, skipped_by = ?, skipped_at = ?, updated_at = datetime('now') WHERE png_path LIKE '%' || ?",
                (by, at_iso, filename),
            )
        else:
            cur = con.execute(
                "UPDATE reactions SET skipped = 0, skipped_by = NULL, skipped_at = NULL, updated_at = datetime('now') WHERE png_path LIKE '%' || ?",
                (filename,),
            )
        updated = cur.rowcount
    con.commit()
    return updated


def get_validation_meta_bulk(
    con: sqlite3.Connection, source_paths: list[str]
) -> dict[str, dict[str, Any]]:
    """Bulk fetch validation metadata for multiple source paths efficiently.

    Returns a dict mapping source_path -> validation_metadata.
    This is much faster than calling get_validation_meta_by_source repeatedly.
    """
    if not source_paths:
        return {}

    result = {}
    # Canonicalize all paths first
    path_mapping = {canonicalize_source_path(p): p for p in source_paths}
    canonical_paths = list(path_mapping.keys())

    # Bulk query for exact matches
    placeholders = ",".join("?" * len(canonical_paths))
    rows = con.execute(
        f"SELECT source_path, validated, validated_by, validated_at FROM reactions WHERE source_path IN ({placeholders}) ORDER BY source_path, validated DESC",
        canonical_paths,
    ).fetchall()

    # Process exact matches (prefer validated=1 rows)
    found_sources = set()
    for row in rows:
        orig_path = path_mapping[row[0]]
        if orig_path not in result:  # First match (highest validated due to ORDER BY)
            result[orig_path] = {"validated": bool(row[1]), "by": row[2], "at": row[3]}
            found_sources.add(orig_path)

    # For unmatched paths, try filename fallback (batch by unique filenames)
    unmatched = [p for p in source_paths if p not in found_sources]
    if unmatched:
        filename_to_paths: dict[str, list[str]] = {}
        for path in unmatched:
            filename = Path(path).name
            if filename not in filename_to_paths:
                filename_to_paths[filename] = []
            filename_to_paths[filename].append(path)

        for filename, paths in filename_to_paths.items():
            row = con.execute(
                "SELECT validated, validated_by, validated_at FROM reactions WHERE source_path LIKE '%' || ? ORDER BY validated DESC LIMIT 1",
                (filename,),
            ).fetchone()

            meta = (
                {"validated": bool(row[0]), "by": row[1], "at": row[2]}
                if row
                else {"validated": False, "by": None, "at": None}
            )
            for path in paths:
                result[path] = meta

    # Fill in any remaining paths with default values
    for path in source_paths:
        if path not in result:
            result[path] = {"validated": False, "by": None, "at": None}

    return result


def ensure_reaction_for_png(
    con: sqlite3.Connection,
    *,
    table_no: int,
    png_path: str,
    csv_path: str | None = None,
    buxton_reaction_number: str | None = None,
    reaction_name: str | None = None,
    formula_latex: str | None = None,
) -> int:
    """Ensure a reaction row exists for a given PNG, creating a minimal one if needed."""
    return get_or_create_reaction(
        con,
        table_no=table_no,
        buxton_reaction_number=buxton_reaction_number,
        reaction_name=reaction_name,
        formula_latex=formula_latex,
        notes=None,
        source_path=csv_path,
        png_path=png_path,
    )


def natural_key(s: str):
    """Natural sort: split digits and non-digits so 'img2.png' < 'img10.png'"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def get_validation_statistics(con: sqlite3.Connection) -> dict[str, Any]:
    """Get comprehensive validation statistics from the database.

    This reads directly from the database and reflects real-time validation status.
    Stats will update immediately when users validate/unvalidate reactions.

    Optimized version uses bulk queries to reduce database load.
    """
    from config import AVAILABLE_TABLES, get_table_paths

    def table_images(table_name):
        img_dir, _, tsv_dir, _ = get_table_paths(table_name)
        imgs = sorted([p.name for p in img_dir.glob("*.png")], key=natural_key)
        return imgs, tsv_dir

    # Collect all source files first
    all_source_paths = []
    table_source_mapping = {}

    for table_name in AVAILABLE_TABLES:
        imgs, tsv_dir = table_images(table_name)
        table_sources = []

        for img in imgs:
            stem = Path(img).stem
            src_csv = tsv_dir / f"{stem}.csv"
            src_tsv = tsv_dir / f"{stem}.tsv"
            source_file = (
                str(src_csv if src_csv.exists() else src_tsv)
                if (src_csv.exists() or src_tsv.exists())
                else None
            )
            if source_file:
                all_source_paths.append(source_file)
                table_sources.append((img, source_file))
            else:
                table_sources.append((img, ""))

        table_source_mapping[table_name] = (imgs, table_sources)

    # Single bulk query for all validation metadata
    validation_cache = get_validation_meta_bulk(con, all_source_paths)

    # Calculate statistics using cached data
    agg_total = 0
    agg_validated = 0
    table_stats = []

    for table_name in AVAILABLE_TABLES:
        imgs, table_sources = table_source_mapping[table_name]
        table_total = len(imgs)
        table_validated = 0

        for _img, source_file in table_sources:
            if source_file and validation_cache.get(source_file, {}).get("validated"):
                table_validated += 1

        table_percent = (100 * table_validated / table_total) if table_total else 0.0
        table_stats.append(
            {
                "table": table_name,
                "table_no": int(table_name.replace("table", "")),
                "total_images": table_total,
                "validated_images": table_validated,
                "unvalidated_images": table_total - table_validated,
                "validation_percentage": table_percent,
            }
        )

        agg_total += table_total
        agg_validated += table_validated

    agg_percent = (100 * agg_validated / agg_total) if agg_total else 0.0

    # Database-level stats
    db_total_reactions = con.execute("SELECT COUNT(*) FROM reactions").fetchone()[0]
    db_validated_reactions = con.execute(
        "SELECT COUNT(*) FROM reactions WHERE validated = 1"
    ).fetchone()[0]
    db_total_measurements = con.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]

    return {
        "global": {
            "total_images": agg_total,
            "validated_images": agg_validated,
            "unvalidated_images": agg_total - agg_validated,
            "validation_percentage": agg_percent,
        },
        "database": {
            "total_reactions": db_total_reactions,
            "validated_reactions": db_validated_reactions,
            "unvalidated_reactions": db_total_reactions - db_validated_reactions,
            "total_measurements": db_total_measurements,
        },
        "tables": table_stats,
    }
