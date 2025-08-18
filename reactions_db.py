import sqlite3
import json
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

from config import BASE_DIR

DB_PATH = Path("reactions.db")

TABLE_CATEGORY = {
    5: "water radiolysis radicals",
    6: "solvated electron",
    7: "hydrogen atom (H•)",
    8: "hydroxyl radical (OH•)",
    9: "oxide/superoxide (O•−)",
}

def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
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

CREATE TABLE IF NOT EXISTS reactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  table_no INTEGER NOT NULL,
  table_category TEXT NOT NULL,
  buxton_reaction_number TEXT,
  reaction_name TEXT,
  formula_latex TEXT NOT NULL,
  formula_canonical TEXT NOT NULL,
  reactants TEXT NOT NULL,
  products TEXT NOT NULL,
  reactant_species TEXT,
  product_species TEXT,
  notes TEXT,
  validated INTEGER NOT NULL DEFAULT 0,
  source_path TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS references_map (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  buxton_code TEXT UNIQUE,
  citation_text TEXT,
  doi TEXT UNIQUE,
  doi_status TEXT NOT NULL DEFAULT 'unknown',
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS measurements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reaction_id INTEGER NOT NULL REFERENCES reactions(id) ON DELETE CASCADE,
  pH TEXT,
  temperature_C REAL,
  rate_value TEXT NOT NULL,
  rate_value_num REAL,
  rate_units TEXT,
  method TEXT,
  conditions TEXT,
  reference_id INTEGER REFERENCES references_map(id) ON DELETE SET NULL,
  source_path TEXT,
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
    return con

# ---------------- Canonicalization -----------------

_math_delims = [(r"$", r"$"), (r"\(", r"\)"), (r"\[", r"\]")]

_ce_re = re.compile(r"\\ce\{(.+?)\}")
_sup_re = re.compile(r"\^\{([^}]+)\}|\^([A-Za-z0-9+\-]+)")
_sub_re = re.compile(r"_\{([^}]+)\}|_([A-Za-z0-9+\-]+)")
_spaces_re = re.compile(r"\s+")

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

def latex_to_canonical(formula_latex: str) -> Tuple[str, str, str, List[str], List[str]]:
    """Return (canonical, reactants, products, reactant_species, product_species)."""
    core = strip_math(formula_latex)
    # Extract inside \ce{...} if present
    m = _ce_re.search(core)
    if m:
        core = m.group(1)
    # normalize arrows
    core = re.sub(r"\\rightarrow|\\to|\-\>", "->", core)
    # normalize radicals and charges inline
    core = core.replace("^{.-}", "•-").replace("^{.+}", "•+")
    core = core.replace("\\cdot", "•").replace("\\bullet", "•")
    # simplify superscripts/subscripts
    core = _sup_re.sub(lambda mo: f"^{mo.group(1) or mo.group(2)}", core)
    core = _sub_re.sub(lambda mo: f"_{mo.group(1) or mo.group(2)}", core)
    # collapse spaces
    core = _spaces_re.sub(" ", core).strip()
    # Split reactants/products
    parts = [p.strip() for p in core.split("->", 1)]
    reactants = parts[0] if parts else ""
    products = parts[1] if len(parts) > 1 else ""
    # Tokenize species by +
    def toks(side: str) -> List[str]:
        if not side:
            return []
        return [re.sub(r"\s+", " ", t.strip()) for t in side.split("+")]
    r_species = toks(reactants)
    p_species = toks(products)
    canonical = f"{reactants} -> {products}" if products else reactants
    return canonical, reactants, products, r_species, p_species

# ---------------- Upserts & Search -----------------

def upsert_reference(con: sqlite3.Connection, buxton_code: Optional[str], citation_text: Optional[str], doi: Optional[str]) -> Optional[int]:
    if not any([buxton_code, citation_text, doi]):
        return None
    row = con.execute(
        "SELECT id FROM references_map WHERE (buxton_code IS ? OR buxton_code = ?) OR (doi IS ? OR doi = ?) LIMIT 1",
        (buxton_code, buxton_code, doi, doi)
    ).fetchone()
    if row:
        ref_id = row[0]
        # update citation or doi if provided
        con.execute(
            "UPDATE references_map SET citation_text = COALESCE(?, citation_text), doi = COALESCE(?, doi), updated_at = datetime('now') WHERE id = ?",
            (citation_text, doi, ref_id)
        )
        return ref_id
    cur = con.execute(
        "INSERT INTO references_map(buxton_code, citation_text, doi) VALUES (?,?,?)",
        (buxton_code, citation_text, doi)
    )
    return cur.lastrowid


def get_or_create_reaction(con: sqlite3.Connection, *, table_no: int, buxton_reaction_number: Optional[str], reaction_name: Optional[str], formula_latex: str, notes: Optional[str], source_path: Optional[str]) -> int:
    category = TABLE_CATEGORY.get(table_no, str(table_no))
    canonical, reactants, products, r_species, p_species = latex_to_canonical(formula_latex)
    # dedup by table_no + canonical
    row = con.execute(
        "SELECT id FROM reactions WHERE table_no = ? AND formula_canonical = ?",
        (table_no, canonical)
    ).fetchone()
    if row:
        rid = row[0]
        con.execute(
            "UPDATE reactions SET reaction_name = COALESCE(?, reaction_name), notes = COALESCE(?, notes), source_path = COALESCE(?, source_path), updated_at = datetime('now') WHERE id = ?",
            (reaction_name, notes, source_path, rid)
        )
        return rid
    cur = con.execute(
        "INSERT INTO reactions(table_no, table_category, buxton_reaction_number, reaction_name, formula_latex, formula_canonical, reactants, products, reactant_species, product_species, notes, source_path) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            table_no,
            category,
            buxton_reaction_number,
            reaction_name,
            formula_latex,
            canonical,
            reactants,
            products,
            json.dumps(r_species, ensure_ascii=False),
            json.dumps(p_species, ensure_ascii=False),
            notes,
            source_path,
        ),
    )
    return cur.lastrowid


def add_measurement(con: sqlite3.Connection, reaction_id: int, *, pH: Optional[str], temperature_C: Optional[float], rate_value: str, rate_value_num: Optional[float], rate_units: Optional[str], method: Optional[str], conditions: Optional[str], reference_id: Optional[int], source_path: Optional[str], page_info: Optional[str]) -> int:
    cur = con.execute(
        """
        INSERT INTO measurements(reaction_id, pH, temperature_C, rate_value, rate_value_num, rate_units, method, conditions, reference_id, source_path, page_info)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (reaction_id, pH, temperature_C, rate_value, rate_value_num, rate_units, method, conditions, reference_id, source_path, page_info)
    )
    return cur.lastrowid


def search_reactions(con: sqlite3.Connection, query: str, *, table_no: Optional[int] = None, limit: int = 50) -> List[sqlite3.Row]:
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


def list_reactions(con: sqlite3.Connection, *, name_filter: Optional[str] = None, limit: int = 1000) -> List[sqlite3.Row]:
    """List reactions ordered A->Z by name (fallback to canonical)."""
    if name_filter:
        like = f"%{name_filter.lower()}%"
        sql = (
            "SELECT * FROM reactions WHERE lower(COALESCE(reaction_name, formula_canonical)) LIKE ? "
            "ORDER BY lower(COALESCE(reaction_name, formula_canonical)) ASC LIMIT ?"
        )
        return con.execute(sql, (like, limit)).fetchall()
    sql = (
        "SELECT * FROM reactions ORDER BY lower(COALESCE(reaction_name, formula_canonical)) ASC LIMIT ?"
    )
    return con.execute(sql, (limit,)).fetchall()


def get_reaction_with_measurements(con: sqlite3.Connection, reaction_id: int) -> Dict[str, Any]:
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
        (reaction_id,)
    ).fetchall()
    return {"reaction": r, "measurements": ms}

