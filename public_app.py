import csv
import json
import os
import random
import re
import secrets
import sqlite3
import sys
from datetime import UTC, datetime
from html import escape
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PUBLIC_DATA_DIR = Path(
    os.getenv(
        "RAD_PUBLIC_DATA_DIR",
        "/data" if Path("/data").exists() else str(ROOT / "data"),
    )
)
os.environ["DATA_DIR"] = str(PUBLIC_DATA_DIR)

from config import BASE_DIR
from auth_db import auth_db, check_authentication, login_user, logout_user
from reactions_db import (
    DB_PATH,
    ensure_db,
    get_reaction_with_measurements,
    search_reactions,
)

st.set_page_config(
    page_title="Radical Reactions Platform",
    page_icon="RR",
    layout="wide",
)


TABLE_LABELS = {
    5: "Table 5 · radical-radical",
    6: "Table 6 · hydrated electrons",
    7: "Table 7 · hydrogen atoms",
    8: "Table 8 · hydroxyl radicals",
    9: "Table 9 · oxide radical ion",
    10: "Table 10 · macromolecules and heterogeneous systems",
}
PUBLIC_TABLES = [5, 6, 7, 8, 9]
SEARCH_SCOPE_OPTIONS = {
    "reactants": "Reagents only",
    "products": "Products only",
    "solvents": "Solvents only",
    "all": "All fields",
}
DATABASE_OPTIONS = {
    "buxton": "Buxton",
    "new": "New",
    "both": "Buxton + New",
}
SEARCH_ALIAS_GROUPS = {
    "hydrated_electron": [
        "hydrated electron",
        "solvated electron",
        "aqueous electron",
        "eaq",
        "eaq-",
        "e_aq",
        "e_{aq}",
        "e_{aq}^{-}",
    ],
    "hydroxyl_radical": ["hydroxyl", "hydroxyl radical", "oh", ".oh", "•oh", "^.oh"],
    "hydrogen_atom": ["hydrogen atom", "h atom", "h.", ".h", "^.h"],
    "oxide_radical_ion": ["oxide", "oxide radical", "oxide radical ion", "o-", "o.-", ".o-"],
    "oxygen": ["oxygen", "dioxygen", "o2", "o_2"],
    "hydrogen_peroxide": ["hydrogen peroxide", "h2o2", "h_2o_2"],
    "superoxide": ["superoxide", "superoxide ion", "o2-", "o2^-", "o_2^-"],
    "ozone": ["ozone", "o3", "o_3"],
    "silver": ["silver", "silver ion", "ag", "ag+"],
    "sulfite": ["sulfite", "sulfite ion", "so3^2-", "so3_2-", "so_3^2-", "so3^{2-}"],
    "sulfate": ["sulfate", "sulfate ion", "so4^2-", "so4_2-", "so_4^2-", "so4^{2-}"],
    "nitrate": ["nitrate", "nitrate ion", "no3-", "no_3-", "no3^-"],
    "nitrite": ["nitrite", "nitrite ion", "no2-", "no_2-", "no2^-"],
    "formate": ["formate", "formate ion", "hco2-", "hcoo-", "co2h-"],
    "carbonate": ["carbonate", "carbonate ion", "co3^2-", "co3_2-", "co_3^2-"],
    "bicarbonate": ["bicarbonate", "hydrogen carbonate", "hco3-", "hco_3-"],
    "chloride": ["chloride", "chloride ion", "cl-", "cl^-"],
    "bromide": ["bromide", "bromide ion", "br-", "br^-"],
    "iodide": ["iodide", "iodide ion", "i-", "i^-"],
    "benzene": ["benzene", "c6h6", "c_6h_6"],
    "phenol": ["phenol", "c6h5oh", "c_6h_5oh"],
    "nitrilotriacetate": ["nitrilotriacetate", "nta", "nta3-", "nta^3-"],
    "water": ["water", "h2o", "h_2o"],
    "heavy_water": ["heavy water", "d2o", "d_2o"],
    "methanol": ["methanol", "meoh", "ch3oh", "ch_3oh", "ch4o"],
    "ethanol": ["ethanol", "etoh", "c2h5oh", "c_2h_5oh"],
    "isopropanol": ["isopropanol", "2-propanol", "2-proh", "i-proh", "c3h8o"],
    "tert_butanol": ["tert-butanol", "t-buoh", "tert-buoh", "tbuoh"],
    "acetonitrile": ["acetonitrile", "ch3cn", "ch_3cn", "c2h3n"],
    "acetone": ["acetone", "ch3coch3", "ch_3coch_3", "c3h6o"],
    "carbon_tetrachloride": ["carbon tetrachloride", "ccl4", "ccl_4"],
    "dichloromethane": ["dichloromethane", "methylene chloride", "ch2cl2", "ch_2cl_2"],
    "chloroform": ["chloroform", "chcl3", "chcl_3"],
    "carbon_disulfide": ["carbon disulfide", "cs2", "cs_2"],
    "acetic_acid": ["acetic acid", "ch3co2h", "ch3cooh"],
    "toluene": ["toluene", "c6h5ch3", "c_6h_5ch_3"],
    "propylene_carbonate": ["propylene carbonate"],
}
BROAD_ALIAS_GROUPS = {"hydrated_electron", "hydroxyl_radical", "hydrogen_atom", "oxide_radical_ion"}
BROAD_SEARCH_ALIASES = {
    alias for group in BROAD_ALIAS_GROUPS for alias in SEARCH_ALIAS_GROUPS[group]
}
FORMULA_ONLY_SHORT_TERMS = {
    "ag",
    "br",
    "cl",
    "co",
    "co3",
    "h",
    "i",
    "no2",
    "no3",
    "nta",
    "o",
    "o2",
    "o3",
    "oh",
    "so3",
    "so4",
}
EXACT_FORMULA_ALIASES = {
    "CO": ["co", "co-", "co^-", "co^{−}", "carbon monoxide"],
    "CO2": ["co2", "co_2", "carbon dioxide"],
    "SO3_RADICAL": [
        "so3.-",
        ".so3-",
        "so3•-",
        "•so3-",
        "so3^{.-}",
        "^{.}so3-",
        "^.so3-",
        "sulfite radical",
        "sulfite radical anion",
    ],
    "CN": ["cn", "cn-", "cn^-", "cyanide", "cyanide ion"],
    "SCN": ["scn", "scn-", "scn^-", "thiocyanate", "thiocyanate ion"],
    "N3": ["n3", "n3-", "n3^-", "azide", "azide ion"],
    "ClO": ["clo", "clo-", "clo^-", "hypochlorite", "hypochlorite ion"],
    "ClO2": ["clo2", "clo2-", "clo2^-", "chlorite", "chlorite ion"],
    "ClO3": ["clo3", "clo3-", "clo3^-", "chlorate", "chlorate ion"],
    "ClO4": ["clo4", "clo4-", "clo4^-", "perchlorate", "perchlorate ion"],
    "BrO2": ["bro2", "bro2-", "bro2^-", "bromite", "bromite ion"],
    "BrO3": ["bro3", "bro3-", "bro3^-", "bromate", "bromate ion"],
    "IO3": ["io3", "io3-", "io3^-", "iodate", "iodate ion"],
}
NEUTRAL_EXACT_FORMULAS = {"CO2"}
RADICAL_EXACT_FORMULAS = {"SO3_RADICAL"}
STANDALONE_EXACT_FORMULAS = {"CO", "CO2"}
METAL_SEARCH_ALIASES = {
    "Ag": ["silver", "silver ion"],
    "Al": ["aluminium", "aluminum", "aluminium ion", "aluminum ion"],
    "Au": ["gold", "gold ion"],
    "Cd": ["cadmium", "cadmium ion"],
    "Ce": ["cerium", "cerium ion"],
    "Co": ["cobalt", "cobalt ion"],
    "Cr": ["chromium", "chromium ion"],
    "Cu": ["copper", "copper ion", "cuprous", "cupric"],
    "Fe": ["iron", "iron ion", "ferrous", "ferric"],
    "Hg": ["mercury", "mercury ion"],
    "Mn": ["manganese", "manganese ion"],
    "Ni": ["nickel", "nickel ion"],
    "Pb": ["lead", "lead ion"],
    "Pd": ["palladium", "palladium ion"],
    "Pt": ["platinum", "platinum ion"],
    "Ru": ["ruthenium", "ruthenium ion"],
    "Sn": ["tin", "tin ion"],
    "Ti": ["titanium", "titanium ion"],
    "V": ["vanadium", "vanadium ion"],
    "Zn": ["zinc", "zinc ion"],
    "Zr": ["zirconium", "zirconium ion"],
}
METAL_NAME_ALIAS_TO_SYMBOL = {
    alias.lower(): symbol
    for symbol, aliases in METAL_SEARCH_ALIASES.items()
    for alias in aliases
}
BIBTEX_DOWNLOAD_PATH = Path(
    os.getenv(
        "RAD_PUBLIC_BIBTEX",
        str(BASE_DIR / "exports" / "references" / "radreactions_references_with_doi.bib"),
    )
)
NEW_DB_PATH = Path(
    os.getenv(
        "RAD_PUBLIC_NEW_DB",
        str(BASE_DIR / "new_reactions.sqlite"),
    )
)
REPORTS_DB_PATH = Path(
    os.getenv(
        "RAD_PUBLIC_REPORTS_DB",
        "/data/public_problem_reports.db"
        if Path("/data").exists()
        else str(BASE_DIR / "public_problem_reports.db"),
    )
)
CONTACT_EMAIL = "sergey.denisov@universite-paris-saclay.fr"


def _env_path(name: str) -> Path | None:
    value = os.getenv(name, "").strip()
    return Path(value) if value else None


def _candidate_paths(env_name: str, defaults: list[Path]) -> list[Path]:
    env = _env_path(env_name)
    return ([env] if env else []) + defaults


def _iso_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@st.cache_data(ttl=3600)
def _email_image_bytes(email: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    font = None
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]:
        try:
            font = ImageFont.truetype(path, 28)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    probe = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), email, font=font)
    width = bbox[2] - bbox[0] + 28
    height = bbox[3] - bbox[1] + 24

    image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1),
        radius=8,
        fill=(248, 249, 251, 255),
        outline=(220, 225, 232, 255),
        width=1,
    )
    draw.text((14, 10 - bbox[1]), email, fill=(34, 40, 49, 255), font=font)

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


PDF_DOWNLOADS = [
    {
        "key": "clean",
        "title": "Clean validated reactions PDF",
        "description": "Compiled reaction tables without legacy source-image pages.",
        "env": "RAD_PUBLIC_CLEAN_PDF",
        "candidates": [
            BASE_DIR / "exports" / "validated_reactions" / "radreactions_validated_reactions.pdf",
            BASE_DIR
            / "exports"
            / "longtable_all_reactions_report"
            / "radreactions_all_reactions_report.pdf",
        ],
    },
    {
        "key": "dirty",
        "title": "Image-rich legacy PDF",
        "description": "Compiled PDF with old source images for visual checking.",
        "env": "RAD_PUBLIC_DIRTY_PDF",
        "candidates": [
            BASE_DIR
            / "exports"
            / "revalidated_reactions_with_images"
            / "radreactions_revalidated_reactions_with_images.pdf",
            BASE_DIR
            / "exports"
            / "longtable_all_reactions_report"
            / "radreactions_all_reactions_report.pdf",
        ],
    },
]


def _inject_seo_metadata() -> None:
    description = (
        "Radical Reactions Platform is a searchable Buxton Critical Review database "
        "for radiation chemistry rate constants, hydrated electron reactions, hydrogen "
        "atom reactions, hydroxyl radical reactions, oxide radical ion reactions, and "
        "downloadable Buxton reaction PDF compilations."
    )
    st.html(
        f"""
        <script type="application/ld+json">
        {{
          "@context": "https://schema.org",
          "@type": "Dataset",
          "name": "Radical Reactions Platform",
          "description": "{description}",
          "keywords": [
            "Buxton Critical Review",
            "radiation chemistry",
            "radical reactions",
            "hydrated electron",
            "hydroxyl radical",
            "rate constants",
            "aqueous solution"
          ],
          "isAccessibleForFree": true
        }}
        </script>
        <script>
        const head = window.parent.document.head;
        window.parent.document.title = "Radical Reactions Platform - Buxton Radical Reactions Database";
        function setMeta(name, content) {{
          let tag = head.querySelector(`meta[name="${{name}}"]`);
          if (!tag) {{
            tag = window.parent.document.createElement("meta");
            tag.setAttribute("name", name);
            head.appendChild(tag);
          }}
          tag.setAttribute("content", content);
        }}
        setMeta("description", "{description}");
        setMeta("keywords", "Buxton Critical Review, radiation chemistry, radical reactions, hydrated electron, hydroxyl radical, hydrogen atom, oxide radical ion, rate constants");
        </script>
        """,
        unsafe_allow_javascript=True,
    )
    st.markdown(
        """
        <style>
        .reaction-formula {
          font-family: "Source Sans Pro", Arial, Helvetica, sans-serif;
          font-size: 1.35rem;
          font-style: normal;
          font-weight: 500;
          line-height: 1.8;
          margin: 0.65rem 0 0.85rem;
          text-align: center;
        }
        .reaction-formula sub,
        .reaction-formula sup {
          font-size: 0.72em;
          line-height: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=30)
def _stats(db_mtime: float) -> dict[str, Any]:
    con = ensure_db()
    try:
        table_placeholders = ",".join("?" for _ in PUBLIC_TABLES)
        reactions = con.execute(
            f"""
            SELECT COUNT(*)
            FROM reactions
            WHERE validated = 1 AND table_no IN ({table_placeholders})
            """,
            tuple(PUBLIC_TABLES),
        ).fetchone()[0]
        references = con.execute("SELECT COUNT(*) FROM references_map").fetchone()[0]
        return {
            "reactions": int(reactions or 0),
            "references": int(references or 0),
            "available_tables": "Tables 5-9",
            "missing_tables": "Table 10 is not included yet.",
        }
    finally:
        con.close()


@st.cache_data(ttl=30)
def _search(query: str, table_no: int | None, search_scope: str, limit: int, db_mtime: float):
    terms = _search_terms(query)
    con = ensure_db()
    try:
        found: dict[int, dict[str, Any]] = {}

        if search_scope == "all":
            try:
                rows = search_reactions(
                    con,
                    query,
                    table_no=table_no,
                    limit=limit,
                )
                for row in rows:
                    rec = dict(row)
                    if int(rec["table_no"]) not in PUBLIC_TABLES:
                        continue
                    if int(rec.get("validated") or 0) != 1:
                        continue
                    rec["_score"] = 100
                    found[int(rec["id"])] = rec
            except (sqlite3.OperationalError, TypeError):
                pass

        table_placeholders = ",".join("?" for _ in PUBLIC_TABLES)
        where = ["validated = 1", f"table_no IN ({table_placeholders})"]
        params: list[Any] = list(PUBLIC_TABLES)
        if table_no is not None:
            where.append("table_no = ?")
            params.append(table_no)
        rows = con.execute(
            f"""
            SELECT *
            FROM reactions
            WHERE {" AND ".join(where)}
            ORDER BY table_no, id
            """,
            tuple(params),
        ).fetchall()

        for row in rows:
            rec = dict(row)
            score = _reaction_search_score(rec, terms, search_scope)
            if score <= 0:
                continue
            existing = found.get(int(rec["id"]))
            if existing:
                existing["_score"] += score
            else:
                rec["_score"] = score
                found[int(rec["id"])] = rec

        ranked = sorted(
            found.values(),
            key=lambda item: (-int(item.get("_score", 0)), int(item["table_no"]), int(item["id"])),
        )
        table_counts: dict[int, int] = {}
        for item in ranked:
            item.pop("_score", None)
            item_table = int(item["table_no"])
            table_counts[item_table] = table_counts.get(item_table, 0) + 1
        return {
            "rows": ranked[:limit],
            "total": len(ranked),
            "table_counts": table_counts,
        }
    finally:
        con.close()


@st.cache_data(ttl=30)
def _new_stats(new_mtime: float) -> dict[str, int]:
    if not _new_available():
        return {"reactions": 0, "measurements": 0, "references": 0}
    con = _new_connect()
    try:
        return {
            "reactions": int(con.execute("SELECT COUNT(*) FROM new_reactions").fetchone()[0] or 0),
            "measurements": int(con.execute("SELECT COUNT(*) FROM new_measurements").fetchone()[0] or 0),
            "references": int(con.execute("SELECT COUNT(*) FROM new_references").fetchone()[0] or 0),
        }
    finally:
        con.close()


@st.cache_data(ttl=30)
def _new_search(query: str, search_scope: str, limit: int, new_mtime: float) -> dict[str, Any]:
    if not _new_available():
        return {"rows": [], "total": 0}
    terms = _search_terms(query)
    con = _new_connect()
    try:
        rows = con.execute(
            """
            SELECT
                id, detail_url, reaction_text, reaction_latex, reaction_canonical,
                reactants_text, products_text, reactant_details_json,
                product_details_json, solvent_details_json, solvents_json,
                squib, reference_id, bibliography_url, title, authors, journal,
                year, data_type, experimental_method, analytical_technique, comment
            FROM new_reactions
            ORDER BY id
            """
        ).fetchall()
        ranked: list[dict[str, Any]] = []
        for row in rows:
            rec = dict(row)
            score = _reaction_search_score(_new_search_row(rec), terms, search_scope)
            if score <= 0:
                continue
            rec["_score"] = score
            ranked.append(rec)

        ranked.sort(key=lambda item: (-int(item.get("_score", 0)), int(item["id"])))
        for item in ranked:
            item.pop("_score", None)
        return {"rows": ranked[:limit], "total": len(ranked)}
    finally:
        con.close()


@st.cache_data(ttl=30)
def _combined_search(
    query: str,
    database: str,
    table_no: int | None,
    search_scope: str,
    limit: int,
    db_mtime: float,
    new_mtime: float,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    totals: dict[str, int] = {}
    table_counts: dict[int, int] = {}

    if database in {"buxton", "both"}:
        buxton = _search(query, table_no, search_scope, limit, db_mtime)
        totals["buxton"] = int(buxton["total"])
        table_counts = dict(buxton.get("table_counts") or {})
        rows.extend({"_source": "buxton", **row} for row in buxton["rows"])

    if database in {"new", "both"}:
        new = _new_search(query, search_scope, limit, new_mtime)
        totals["new"] = int(new["total"])
        rows.extend({"_source": "new", **row} for row in new["rows"])

    if database == "both":
        rows = rows[:limit]
    return {
        "rows": rows,
        "total": sum(totals.values()),
        "totals": totals,
        "table_counts": table_counts,
    }


def _new_search_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "formula_canonical": row.get("reaction_canonical") or "",
        "formula_latex": row.get("reaction_latex") or "",
        "reactants": row.get("reactants_text") or "",
        "products": row.get("products_text") or "",
        "reactant_species": _new_species_text(row.get("reactant_details_json")),
        "product_species": _new_species_text(row.get("product_details_json")),
        "solvents": " ".join(
            value
            for value in [
                _new_species_text(row.get("solvents_json")),
                _new_species_text(row.get("solvent_details_json")),
            ]
            if value
        ),
        "reaction_name": row.get("title") or "",
        "notes": " ".join(
            str(row.get(field) or "")
            for field in [
                "comment",
                "data_type",
                "experimental_method",
                "analytical_technique",
                "authors",
                "journal",
                "squib",
            ]
        ),
        "table_category": "New",
        "buxton_reaction_number": row.get("squib") or "",
    }


def _new_species_text(raw: Any) -> str:
    try:
        items = json.loads(str(raw or "[]"))
    except json.JSONDecodeError:
        return str(raw or "")
    values: list[str] = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            values.extend(str(item.get(key) or "") for key in ["name", "formula", "cas_number"])
    return " ".join(values)


@st.cache_data(ttl=30)
def _new_reaction_details(reaction_id: int, new_mtime: float) -> dict[str, Any]:
    con = _new_connect()
    try:
        reaction = con.execute(
            """
            SELECT r.*, ref.citation_text, ref.doi, ref.source_url, ref.volume, ref.pages,
                   ref.bibtex, ref.doi_status
            FROM new_reactions r
            LEFT JOIN new_references ref ON ref.id = r.reference_id
            WHERE r.id = ?
            """,
            (reaction_id,),
        ).fetchone()
        measurements = con.execute(
            """
            SELECT *
            FROM new_measurements
            WHERE reaction_id = ?
            ORDER BY row_index, id
            """,
            (reaction_id,),
        ).fetchall()
        return {
            "reaction": dict(reaction) if reaction else None,
            "measurements": [dict(row) for row in measurements],
        }
    finally:
        con.close()


def _search_terms(query: str) -> list[str]:
    metal_symbol = _metal_query_symbol(query)
    if metal_symbol:
        terms = {f"__metal__:{metal_symbol}"}
        terms.update(METAL_SEARCH_ALIASES.get(metal_symbol, []))
        return sorted(terms)

    exact_formula = _exact_formula_query(query)
    if exact_formula:
        terms = {f"__formula_exact__:{exact_formula}"}
        terms.update(
            alias
            for alias in EXACT_FORMULA_ALIASES.get(exact_formula, [])
            if " " in alias
        )
        return sorted(terms)

    raw = query.strip().lower()
    normalized = _normalize_user_query(query).lower()
    terms = {raw, normalized}
    formula_like = _is_formula_like_query(query)
    alias_terms = _search_alias_terms(query)
    terms.update(alias_terms)

    simple = normalized
    simple = simple.replace("^{", "").replace("}", "")
    simple = simple.replace("_{", "").replace("}", "")
    simple = simple.replace("•", ".")
    terms.add(simple)
    formula_compact = _chemical_compact_query(query)
    if formula_compact:
        terms.add(formula_compact)
    formula_no_charge = _chemical_compact_query(query, strip_charge=True)
    if formula_no_charge:
        terms.add(formula_no_charge)

    if not alias_terms or not _is_broad_alias_query(query):
        min_word_len = 3 if formula_like else 2
        words = [part for part in re.split(r"[^a-zA-Z0-9]+", raw) if len(part) >= min_word_len]
        terms.update(words)

    return sorted({term for term in terms if term})


def _alias_key(value: str) -> str:
    clean = value.strip().lower()
    clean = clean.replace("−", "-").replace("•", ".").replace("·", ".")
    clean = re.sub(r"\\ce\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", r"\1", clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean


def _search_alias_terms(query: str) -> set[str]:
    key = _alias_key(query)
    query_compact = _chemical_compact_query(query)
    query_charge = _charge_signature(query)
    matches: set[str] = set()
    for aliases in SEARCH_ALIAS_GROUPS.values():
        alias_keys = {_alias_key(alias) for alias in aliases}
        alias_compacts = {
            _chemical_compact_query(alias)
            for alias in aliases
            if _charge_signature(alias) == query_charge
        }
        if key in alias_keys or (query_compact and query_compact in alias_compacts):
            matches.update(aliases)
            matches.update(alias_keys)
            for alias in aliases:
                matches.add(_chemical_compact_query(alias))
                matches.add(_chemical_compact_query(alias, strip_charge=True))
    return {term for term in matches if term}


def _charge_signature(value: str) -> str:
    clean = value.strip().replace("−", "-")
    if re.search(r"\d*\+", clean):
        return "+"
    if re.search(r"\d*-", clean):
        return "-"
    return ""


def _is_broad_alias_query(query: str) -> bool:
    key = _alias_key(query)
    query_compact = _chemical_compact_query(query)
    for alias in BROAD_SEARCH_ALIASES:
        if key == _alias_key(alias) or (query_compact and query_compact == _chemical_compact_query(alias)):
            return True
    return False


def _is_formula_like_query(query: str) -> bool:
    clean = query.strip()
    if clean.upper() in {"OH", "HO", "H", "O"}:
        return True
    return bool(
        re.search(r"[A-Z][a-z]?\d*[_^]?\{?\d*[+\-−]", clean)
        or re.search(r"[A-Za-z0-9()]+_\{?\d+\}?\^\{?\d*[+\-−]", clean)
        or re.search(r"[A-Z][a-z]?\d+[_^]?\d*[+\-−]?", clean)
        or re.search(r"\be_?aq\b", clean, flags=re.I)
        or r"\ce" in clean
    )


def _exact_formula_query(query: str) -> str | None:
    key = _alias_key(query)
    compact = _chemical_compact_query(query, strip_charge=True)
    query_charge = _charge_signature(query)
    for formula, aliases in EXACT_FORMULA_ALIASES.items():
        if formula in NEUTRAL_EXACT_FORMULAS and query_charge:
            continue
        formula_compact = _chemical_compact_query(formula, strip_charge=True)
        alias_keys = {_alias_key(alias) for alias in aliases}
        alias_compacts = {
            _chemical_compact_query(alias, strip_charge=True)
            for alias in aliases
        }
        if formula in RADICAL_EXACT_FORMULAS:
            if key in alias_keys:
                return formula
            continue
        if key in alias_keys or compact == formula_compact or compact in alias_compacts:
            return formula
    return None


def _metal_query_symbol(query: str) -> str | None:
    clean = query.strip().replace("−", "-")
    if not clean:
        return None
    lower = clean.lower()
    if clean in METAL_SEARCH_ALIASES:
        return clean
    if lower in METAL_NAME_ALIAS_TO_SYMBOL:
        return METAL_NAME_ALIAS_TO_SYMBOL[lower]
    match = re.fullmatch(
        r"([A-Z][a-z]?)(?:\d*[+\-]|_\{?\d+\}?\^\{?\d*[+\-]\}?|\^\{?\d*[+\-]\}?)",
        clean,
    )
    if match and match.group(1) in METAL_SEARCH_ALIASES:
        return match.group(1)
    return None


def _chemical_compact_query(query: str, *, strip_charge: bool = False) -> str:
    clean = _normalize_user_query(query)
    clean = clean.replace("−", "-")
    clean = re.sub(r"\\ce\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", r"\1", clean)
    if strip_charge:
        clean = re.sub(r"_\{?(\d+)\}?\^\{?\d*[+\-]\}?", r"_\1", clean)
        clean = re.sub(r"(?<=\d)_\{?\d+[+\-]\}?", "", clean)
        clean = re.sub(r"\^\{?\d*[+\-]\}?", "", clean)
    clean = re.sub(r"_\{?(\d+)\}?\^\{?(\d*[+\-])\}?", r"\1\2", clean)
    clean = re.sub(r"(?<=\d)_\{?(\d+[+\-])\}?", r"\1", clean)
    clean = re.sub(r"\^\{?(\d*[+\-])\}?", r"\1", clean)
    clean = re.sub(r"_\{?(\d+)\}?", r"\1", clean)
    return re.sub(r"[^a-z0-9]+", "", clean.lower())


def _search_display_limit(query: str) -> int:
    return 50 if _broad_radical_kind(query) else 100


def _broad_radical_kind(query: str) -> str | None:
    clean = query.strip().lower()
    clean = clean.replace("•", ".").replace("·", ".").replace(" ", "")
    clean = clean.replace("{", "").replace("}", "").replace("_", "")
    if clean in {"oh", ".oh", "^.oh", "oh.", "hydroxyl", "hydroxylradical"}:
        return "hydroxyl"
    if clean in {"eaq", "eaq-", "eaq^-", "e-aq", "hydratedelectron", "solvatedelectron"}:
        return "hydrated_electron"
    if clean in {"h", "h.", ".h", "^.h", "hydrogenatom"}:
        return "hydrogen_atom"
    if clean in {"o-", "o.-", ".o-", "oxide", "oxideradical", "oxideradicalion"}:
        return "oxide"
    return None


def _broad_radical_advice(
    query: str,
    table_no: int | None,
    total: int,
    include_table_hint: bool = True,
) -> str | None:
    kind = _broad_radical_kind(query)
    if not kind or total <= 50:
        return None
    if kind == "hydroxyl":
        table_hint = "select Table 8"
        examples = "`SO3^2-`, `benzene`, `nitrilotriacetate`, `Ag+`"
        radical = "`OH`, `.OH`, and `•OH` all mean hydroxyl radical"
    elif kind == "hydrated_electron":
        table_hint = "select Table 6"
        examples = "`Ag+`, `SO3^2-`, `O2`, `nitrilotriacetate`"
        radical = "`eaq`, `e_aq`, and hydrated electron all mean solvated electron"
    elif kind == "hydrogen_atom":
        table_hint = "select Table 7"
        examples = "`O2`, `NO3-`, `benzene`, `SO3^2-`"
        radical = "`H` and hydrogen atom are broad radical queries"
    else:
        table_hint = "select Table 9"
        examples = "`SO3^2-`, `NO2-`, `formate`, `benzene`"
        radical = "`O-` and oxide radical ion are broad radical queries"
    table_part = "" if table_no is not None or not include_table_hint else f" First {table_hint}."
    return (
        f"{radical}. This query returns a reaction class, not a specific reagent."
        f"{table_part} For useful results, search the co-reactant/reagent name or formula, e.g. {examples}."
    )


def _normalize_user_query(query: str) -> str:
    clean = query.strip()
    lower = clean.lower()
    replacements = {
        "hydrated electron": "e_{aq}^{-}",
        "solvated electron": "e_{aq}^{-}",
        "eaq": "e_{aq}^{-}",
        "hydroxyl radical": "OH",
        "oh radical": "OH",
        "hydrogen atom": "H",
        "oxide radical": "O",
    }
    for old, new in replacements.items():
        if old in lower:
            clean = re.sub(re.escape(old), new, clean, flags=re.I)
            lower = clean.lower()
    clean = re.sub(r"\beaq[-−]?\b", "e_{aq}^{-}", clean, flags=re.I)
    clean = re.sub(r"\be[-−]\b", "e^{-}", clean)
    clean = re.sub(
        r"([A-Z][a-z]?)(\d+)([+-]+)",
        lambda match: rf"{match.group(1)}_{{{match.group(2)}}}^{{{match.group(3)}}}",
        clean,
    )
    clean = re.sub(r"([A-Z][a-z]?)([+-]+)", r"\1^{\2}", clean)
    return clean.replace("·", "•").replace(".", "•")


def _reaction_search_score(row: dict[str, Any], terms: list[str], search_scope: str = "all") -> int:
    haystack = _text_haystack(row, search_scope).lower()
    formula_haystack = _formula_haystack(row, search_scope).lower()
    compact_formula = re.sub(r"[^a-z0-9]+", "", formula_haystack)
    score = 0
    for term in terms:
        if term.startswith("__formula_exact__:"):
            score += _formula_exact_score(
                row,
                term.removeprefix("__formula_exact__:"),
                search_scope,
            )
            continue
        if term.startswith("__metal__:"):
            score += _metal_symbol_score(row, term.removeprefix("__metal__:"), search_scope)
            continue
        compact_term = re.sub(r"[^a-z0-9]+", "", term.lower())
        direct_haystack = (
            formula_haystack
            if compact_term in FORMULA_ONLY_SHORT_TERMS
            else haystack
        )
        if term in direct_haystack:
            score += 8 + min(len(term), 20)
        elif len(compact_term) >= 4 and compact_term in compact_formula:
            score += 6 + min(len(compact_term), 16)
    return score


def _text_haystack(row: dict[str, Any], search_scope: str) -> str:
    if search_scope == "reactants":
        fields = ["reactants", "reactant_species"]
    elif search_scope == "products":
        fields = ["products", "product_species"]
    elif search_scope == "solvents":
        fields = ["solvents"]
    else:
        fields = [
            "buxton_reaction_number",
            "reaction_name",
            "formula_canonical",
            "formula_latex",
            "reactants",
            "products",
            "reactant_species",
            "product_species",
            "solvents",
            "notes",
            "table_category",
        ]
    return " ".join(str(row.get(field) or "") for field in fields)


def _formula_haystack(row: dict[str, Any], search_scope: str) -> str:
    return " ".join(_formula_field_values(row, search_scope))


def _formula_field_values(row: dict[str, Any], search_scope: str) -> list[str]:
    if search_scope == "reactants":
        fields = ["reactants", "reactant_species"]
    elif search_scope == "products":
        fields = ["products", "product_species"]
    elif search_scope == "solvents":
        fields = ["solvents"]
    else:
        fields = [
            "formula_canonical",
            "formula_latex",
            "reactants",
            "products",
            "reactant_species",
            "product_species",
            "solvents",
        ]
    return [str(row.get(field) or "") for field in fields]


def _formula_exact_score(row: dict[str, Any], formula: str, search_scope: str = "all") -> int:
    pattern = _formula_exact_pattern(formula)
    for formula_text in _formula_field_values(row, search_scope):
        if re.search(pattern, formula_text):
            return 36
    return 0


def _formula_exact_pattern(formula: str) -> str:
    if formula == "SO3_RADICAL":
        radical = r"(?:\.|•|\\bullet)"
        sulfur_trioxide = r"SO\s*_?\{?3\}?"
        leading = rf"\^\{{?\s*{radical}\s*\}}?\s*{sulfur_trioxide}\s*(?:\^\{{?\s*-\s*\}}?|-(?!\d))"
        braced_leading = rf"\^\{{?\s*{radical}\s*{sulfur_trioxide}\s*\}}?\s*(?:\^\{{?\s*-\s*\}}?|-(?!\d))"
        trailing = rf"{sulfur_trioxide}\s*(?:\^\{{?\s*{radical}\s*-\s*\}}?|{radical}\s*-)"
        return rf"(?<![A-Za-z0-9])(?:{braced_leading}|{leading}|{trailing})(?=$|[^A-Za-z0-9])"

    tokens = re.findall(r"[A-Z][a-z]?|\d+", formula)
    parts: list[str] = []
    last_is_number = False
    for token in tokens:
        if token.isdigit():
            parts.append(rf"(?:{re.escape(token)}|_\{{?{re.escape(token)}\}}?)")
            last_is_number = True
        else:
            parts.append(re.escape(token))
            last_is_number = False
    if formula in STANDALONE_EXACT_FORMULAS:
        tail = r"(?=\s*(?:$|\+|->|→))"
    elif formula in NEUTRAL_EXACT_FORMULAS:
        tail = r"(?!\s*(?:\^\{?\d*[+\-−]|\{?\d*[+\-−]|[+\-−]))"
    elif last_is_number:
        tail = ""
    else:
        tail = r"(?!\s*_?\{?\d)"
    separator = r"\s*"
    head = r"(?<![A-Za-z0-9])" if formula in STANDALONE_EXACT_FORMULAS else r"(?<![A-Za-z])"
    return rf"{head}{separator.join(parts)}{tail}(?=$|[^A-Za-z0-9])"


def _metal_symbol_score(row: dict[str, Any], symbol: str, search_scope: str = "all") -> int:
    formula_text = _formula_haystack(row, search_scope)
    if re.search(rf"(?<![A-Za-z]){re.escape(symbol)}(?=$|[^a-z])", formula_text):
        return 32
    return 0


@st.cache_data(ttl=30)
def _reaction_details(reaction_id: int, db_mtime: float) -> dict[str, Any]:
    con = ensure_db()
    try:
        data = get_reaction_with_measurements(con, reaction_id)
        reaction = data.get("reaction")
        measurements = data.get("measurements", [])
        return {
            "reaction": dict(reaction) if reaction else None,
            "measurements": [dict(row) for row in measurements],
        }
    finally:
        con.close()


def _reports_connect() -> sqlite3.Connection:
    REPORTS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(REPORTS_DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 5000")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS reaction_problem_reports (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          table_no INTEGER NOT NULL,
          reaction_id INTEGER NOT NULL,
          buxton_reaction_number TEXT NOT NULL,
          reaction_label TEXT NOT NULL,
          comment TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'new'
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS article_suggestions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          doi TEXT NOT NULL,
          title TEXT NOT NULL DEFAULT '',
          year TEXT NOT NULL DEFAULT '',
          journal_info TEXT NOT NULL DEFAULT '',
          crossref_status TEXT NOT NULL DEFAULT '',
          comment TEXT NOT NULL,
          contact_email TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'new'
        )
        """
    )
    con.commit()
    return con


def _natural_key(value: str) -> list[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"([0-9]+)", value)]


@st.cache_data(ttl=60)
def _reaction_choices_for_report(table_no: int, db_mtime: float) -> list[dict[str, Any]]:
    con = ensure_db()
    try:
        rows = con.execute(
            """
            SELECT id, table_no, buxton_reaction_number, formula_canonical, reaction_name
            FROM reactions
            WHERE validated = 1 AND table_no = ?
            ORDER BY id
            """,
            (table_no,),
        ).fetchall()
        choices = []
        for row in rows:
            number = str(row["buxton_reaction_number"] or "").strip()
            if not number:
                number = f"DB-{row['id']}"
            formula = str(row["formula_canonical"] or row["reaction_name"] or "").strip()
            choices.append(
                {
                    "id": int(row["id"]),
                    "table_no": int(row["table_no"]),
                    "buxton_reaction_number": number,
                    "reaction_label": f"{number} · {formula}" if formula else number,
                }
            )
        return sorted(choices, key=lambda item: _natural_key(item["buxton_reaction_number"]))
    finally:
        con.close()


@st.cache_data(ttl=60)
def _reaction_table_for_report(reaction_id: int, db_mtime: float) -> int | None:
    con = ensure_db()
    try:
        row = con.execute(
            """
            SELECT table_no
            FROM reactions
            WHERE id = ? AND validated = 1
            """,
            (reaction_id,),
        ).fetchone()
        if not row:
            return None
        table_no = int(row["table_no"])
        return table_no if table_no in PUBLIC_TABLES else None
    finally:
        con.close()


def _save_problem_report(table_no: int, reaction: dict[str, Any], comment: str) -> int:
    con = _reports_connect()
    try:
        cur = con.execute(
            """
            INSERT INTO reaction_problem_reports (
              created_at, table_no, reaction_id, buxton_reaction_number,
              reaction_label, comment
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _iso_now(),
                table_no,
                int(reaction["id"]),
                reaction["buxton_reaction_number"],
                reaction["reaction_label"],
                comment.strip(),
            ),
        )
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


CAPTCHA_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def _new_captcha_code(length: int = 5) -> str:
    return "".join(secrets.choice(CAPTCHA_ALPHABET) for _ in range(length))


def _captcha_code(form_key: str) -> str:
    state_key = f"{form_key}_captcha_code"
    code = st.session_state.get(state_key)
    if not isinstance(code, str) or len(code) != 5:
        code = _new_captcha_code()
        st.session_state[state_key] = code
    return code


@st.cache_data(ttl=900)
def _captcha_image_bytes(code: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    rng = random.Random(code)
    width, height = 180, 58
    image = Image.new("RGB", (width, height), (248, 250, 252))
    draw = ImageDraw.Draw(image)

    for _ in range(90):
        x = rng.randrange(width)
        y = rng.randrange(height)
        color = tuple(rng.randrange(120, 230) for _ in range(3))
        draw.point((x, y), fill=color)

    for _ in range(8):
        start = (rng.randrange(width), rng.randrange(height))
        end = (rng.randrange(width), rng.randrange(height))
        color = tuple(rng.randrange(140, 210) for _ in range(3))
        draw.line([start, end], fill=color, width=rng.randrange(1, 3))

    font = None
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]:
        try:
            font = ImageFont.truetype(path, 34)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    x = 16
    for char in code:
        y = rng.randrange(5, 14)
        color = tuple(rng.randrange(20, 90) for _ in range(3))
        draw.text((x, y), char, fill=color, font=font)
        x += rng.randrange(28, 34)

    image = image.filter(ImageFilter.SMOOTH_MORE)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _captcha_input(form_key: str) -> str:
    code = _captcha_code(form_key)
    st.image(_captcha_image_bytes(code), width=180)
    return st.text_input("CAPTCHA", key=f"{form_key}_captcha_answer")


def _captcha_passed(form_key: str, answer: str) -> bool:
    expected = _captcha_code(form_key)
    clean_answer = re.sub(r"\s+", "", answer.strip()).upper()
    return clean_answer == expected


def _refresh_captcha(form_key: str) -> None:
    st.session_state.pop(f"{form_key}_captcha_code", None)


def _split_doi_list(value: str) -> list[str]:
    dois: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[,;\n]+", value):
        doi = _normalize_doi(raw)
        if doi and doi.lower() not in seen:
            dois.append(doi)
            seen.add(doi.lower())
    return dois


def _normalize_doi(value: str) -> str:
    clean = value.strip()
    clean = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", clean, flags=re.I)
    clean = re.sub(r"^doi:\s*", "", clean, flags=re.I)
    clean = clean.strip().strip(".")
    match = re.search(r"(10\.\d{4,9}/\S+)", clean, flags=re.I)
    if not match:
        return ""
    doi = match.group(1).strip()
    doi = doi.rstrip(").,;")
    return doi


def _crossref_year(message: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "published", "issued"):
        parts = message.get(key, {}).get("date-parts") or []
        if parts and parts[0]:
            return str(parts[0][0])
    return ""


def _crossref_journal_info(message: dict[str, Any]) -> str:
    parts = []
    container = (message.get("container-title") or [""])[0]
    if container:
        parts.append(str(container))
    volume = str(message.get("volume") or "").strip()
    issue = str(message.get("issue") or "").strip()
    pages = str(message.get("page") or "").strip()
    if volume:
        parts.append(f"vol. {volume}")
    if issue:
        parts.append(f"issue {issue}")
    if pages:
        parts.append(f"pp. {pages}")
    return ", ".join(parts)


@st.cache_data(ttl=86400, show_spinner=False)
def _lookup_doi_crossref(doi: str) -> dict[str, str]:
    url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
    request = Request(
        url,
        headers={
            "User-Agent": f"RadReactionsPlatform/2.0 (mailto:{CONTACT_EMAIL})",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=12) as response:
            import json

            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return {"doi": doi, "title": "", "year": "", "journal_info": "", "status": f"HTTP {exc.code}"}
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return {"doi": doi, "title": "", "year": "", "journal_info": "", "status": type(exc).__name__}

    message = data.get("message") or {}
    title = " ".join(str(part).strip() for part in message.get("title") or [] if str(part).strip())
    return {
        "doi": doi,
        "title": title,
        "year": _crossref_year(message),
        "journal_info": _crossref_journal_info(message),
        "status": "found" if title else "metadata incomplete",
    }


def _save_article_suggestions(
    suggestions: list[dict[str, str]],
    comments: dict[str, str],
    contact_email: str,
) -> int:
    con = _reports_connect()
    try:
        count = 0
        for item in suggestions:
            doi = item["doi"]
            comment = comments.get(doi, "").strip()
            if not comment:
                continue
            con.execute(
                """
                INSERT INTO article_suggestions (
                  created_at, doi, title, year, journal_info,
                  crossref_status, comment, contact_email
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _iso_now(),
                    doi,
                    item.get("title", ""),
                    item.get("year", ""),
                    item.get("journal_info", ""),
                    item.get("status", ""),
                    comment,
                    contact_email.strip(),
                ),
            )
            count += 1
        con.commit()
        return count
    finally:
        con.close()


def _report_rows(table_name: str) -> list[dict[str, Any]]:
    if table_name not in {"reaction_problem_reports", "article_suggestions"}:
        raise ValueError(f"Unsupported report table: {table_name}")
    con = _reports_connect()
    try:
        rows = con.execute(f"SELECT * FROM {table_name} ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "").strip() or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _reports_export_payload() -> dict[str, Any]:
    reaction_reports = _report_rows("reaction_problem_reports")
    article_suggestions = _report_rows("article_suggestions")
    return {
        "generated_at": _iso_now(),
        "source_db": str(REPORTS_DB_PATH),
        "summary": {
            "reaction_reports": len(reaction_reports),
            "article_suggestions": len(article_suggestions),
            "reaction_reports_by_table": _count_by(reaction_reports, "table_no"),
            "reaction_reports_by_status": _count_by(reaction_reports, "status"),
            "article_suggestions_by_status": _count_by(article_suggestions, "status"),
            "article_suggestions_by_crossref_status": _count_by(
                article_suggestions,
                "crossref_status",
            ),
        },
        "reaction_problem_reports": reaction_reports,
        "article_suggestions": article_suggestions,
    }


def _json_download_bytes(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def _csv_download_bytes(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _admin_password_configured() -> bool:
    return bool(os.getenv("RAD_PUBLIC_ADMIN_PASSWORD", "").strip())


def _admin_password_matches(value: str) -> bool:
    expected = os.getenv("RAD_PUBLIC_ADMIN_PASSWORD", "").strip()
    return bool(expected) and secrets.compare_digest(value.strip(), expected)


@st.cache_data(ttl=300)
def _read_file(path: str) -> bytes:
    return Path(path).read_bytes()


@st.cache_data(ttl=300)
def _bibtex_export(db_mtime: float) -> tuple[bytes, int]:
    con = ensure_db()
    try:
        rows = con.execute(
            """
            SELECT buxton_code, citation_text, doi, bibtex
            FROM references_map
            WHERE doi IS NOT NULL AND trim(doi) != ''
            ORDER BY buxton_code COLLATE NOCASE, doi COLLATE NOCASE
            """
        ).fetchall()
    finally:
        con.close()

    entries = []
    used_keys: set[str] = set()
    for index, row in enumerate(rows, 1):
        bibtex = str(row["bibtex"] or "").strip()
        doi = str(row["doi"] or "").strip()
        if bibtex:
            entries.append(bibtex)
            continue

        key_base = str(row["buxton_code"] or "").strip() or doi or f"ref_{index}"
        key = _bibtex_key(key_base, used_keys)
        citation = _bibtex_escape(str(row["citation_text"] or "").strip())
        entries.append(
            "\n".join(
                [
                    f"@misc{{{key},",
                    f"  title = {{{citation or key}}},",
                    f"  doi = {{{_bibtex_escape(doi)}}},",
                    f"  note = {{{_bibtex_escape('Buxton reference code: ' + str(row['buxton_code'] or 'unknown'))}}}",
                    "}",
                ]
            )
        )

    header = [
        "% Radical Reactions Platform",
        "% Buxton references with DOI",
        f"% Generated: {_iso_now()}",
        f"% Entries: {len(entries)}",
        "",
    ]
    return ("\n\n".join(["\n".join(header), *entries]) + "\n").encode("utf-8"), len(entries)


@st.cache_data(ttl=300)
def _bibtex_file_export(path: str, file_mtime: float) -> tuple[bytes, int]:
    data = Path(path).read_bytes()
    count = len(re.findall(rb"(?m)^\s*@\w+\s*\{", data))
    return data, count


def _bibtex_key(value: str, used_keys: set[str]) -> str:
    key = re.sub(r"[^A-Za-z0-9_:-]+", "_", value.strip())
    key = key.strip("_") or "reference"
    if not re.match(r"^[A-Za-z]", key):
        key = f"ref_{key}"
    candidate = key
    suffix = 2
    while candidate in used_keys:
        candidate = f"{key}_{suffix}"
        suffix += 1
    used_keys.add(candidate)
    return candidate


def _bibtex_escape(value: str) -> str:
    return value.replace("\\", "\\textbackslash{}").replace("{", "\\{").replace("}", "\\}")


def _db_mtime() -> float:
    try:
        return DB_PATH.stat().st_mtime
    except OSError:
        return 0.0


def _new_db_mtime() -> float:
    try:
        return NEW_DB_PATH.stat().st_mtime
    except OSError:
        return 0.0


def _new_available() -> bool:
    return NEW_DB_PATH.exists() and NEW_DB_PATH.is_file()


def _new_connect() -> sqlite3.Connection:
    uri = f"file:{NEW_DB_PATH}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _pdf_path(item: dict[str, Any]) -> Path | None:
    for path in _candidate_paths(item["env"], item["candidates"]):
        if path and path.exists() and path.is_file():
            return path
    return None


def _format_size(path: Path) -> str:
    size = path.stat().st_size
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists() and path.is_file():
            return path
    return None


def _reaction_pdf_path(reaction: dict[str, Any]) -> Path | None:
    table_no = reaction.get("table_no")
    png_path = reaction.get("png_path") or ""
    if not table_no or not png_path:
        return None
    stem = Path(str(png_path)).stem
    base = BASE_DIR / f"table{int(table_no)}" / "sub_tables_images" / "csv"
    return _first_existing(
        [
            base / "latex" / f"{stem}.pdf",
            base / f"{stem}.pdf",
        ]
    )


def _reaction_entry_image_path(reaction: dict[str, Any]) -> Path | None:
    pdf_path = _reaction_pdf_path(reaction)
    if not pdf_path:
        return None
    render_path = pdf_path.parent / f"{pdf_path.stem}.render.png"
    if render_path.exists() and render_path.is_file():
        return render_path
    return None


def _reaction_image_path(reaction: dict[str, Any]) -> Path | None:
    raw = reaction.get("png_path")
    if not raw:
        return None
    path = Path(str(raw))
    if path.exists():
        return path
    table_no = reaction.get("table_no")
    if table_no:
        fallback = BASE_DIR / f"table{int(table_no)}" / "sub_tables_images" / path.name
        if fallback.exists():
            return fallback
    return None


def _render_formula(reaction: dict[str, Any]) -> None:
    formula = reaction.get("formula_latex") or reaction.get("formula_canonical") or ""
    if formula:
        st.markdown(_formula_to_html_display(formula), unsafe_allow_html=True)
    else:
        st.caption("Formula unavailable.")


def _formula_to_html_display(formula: str) -> str:
    clean = _prepare_formula_for_display(formula)
    clean = re.sub(r"\\(?:text|textrm|mathrm|emph)\{([^{}]*)\}", r"\1", clean)
    clean = clean.replace(r"\rightarrow", "→").replace(r"\bullet", "•")
    clean = re.sub(r"_\{([^{}]*)\}", r"<sub>\1</sub>", clean)
    clean = re.sub(r"\^\{([^{}]*)\}", r"<sup>\1</sup>", clean)
    clean = clean.replace("{", "").replace("}", "")
    clean = clean.replace("\\", "")
    clean = escape(clean)
    clean = clean.replace("&lt;sub&gt;", "<sub>").replace("&lt;/sub&gt;", "</sub>")
    clean = clean.replace("&lt;sup&gt;", "<sup>").replace("&lt;/sup&gt;", "</sup>")
    clean = re.sub(r"_\(([^)]*)\)", r"<sub>(\1)</sub>", clean)
    clean = re.sub(r"_([A-Za-z0-9+\-]+)", r"<sub>\1</sub>", clean)
    clean = re.sub(r"\^([A-Za-z0-9+\-•]+)", r"<sup>\1</sup>", clean)
    clean = re.sub(r"(?<=[A-Za-z\)])(\d+)(?![+\-])", r"<sub>\1</sub>", clean)
    return f'<div class="reaction-formula">{clean}</div>'


def _formula_to_inline_html(formula: Any) -> str:
    html = _formula_to_html_display(str(formula or ""))
    html = re.sub(r'^<div class="reaction-formula">|</div>$', "", html)
    return f'<span class="reaction-formula-inline">{html}</span>'


def _prepare_formula_for_display(formula: str) -> str:
    clean = formula.strip()
    if clean.startswith("$") and clean.endswith("$"):
        clean = clean[1:-1].strip()
    if clean.startswith(r"\(") and clean.endswith(r"\)"):
        clean = clean[2:-2].strip()
    if clean.startswith(r"\[") and clean.endswith(r"\]"):
        clean = clean[2:-2].strip()
    if clean.startswith(r"\ce{") and clean.endswith("}"):
        clean = clean[4:-1].strip()

    replacements = {
        "→": r"\rightarrow",
        "->": r"\rightarrow",
        "•": r"\bullet",
        "^{.}-}": r"^{\bullet -}",
        "^{.}": r"^{\bullet}",
        "^{.": r"^{\bullet ",
        "^.": r"^{\bullet}",
        r"\cdot": r"\bullet",
    }
    for old, new in replacements.items():
        clean = clean.replace(old, new)
    clean = re.sub(r"(?<=[A-Za-z\)])(\d+)(?![+\-])", r"_{\1}", clean)
    clean = _upright_chemical_text(clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean


def _upright_chemical_text(formula: str) -> str:
    protected: dict[str, str] = {}

    def protect(match: re.Match[str]) -> str:
        key = f"@@CMD{len(protected)}@@"
        protected[key] = match.group(0)
        return key

    clean = re.sub(r"\\(?:text|textrm|mathrm)\{[^{}]*\}", protect, formula)
    clean = re.sub(r"(?<!\\)(?<![A-Za-z])([A-Za-z]+)(?=(_|\^|\b))", r"\\text{\1}", clean)
    for key, value in protected.items():
        clean = clean.replace(key, value)
    return clean


def _prepare_math_value(value: str) -> str:
    clean = str(value or "").strip()
    if not clean or clean == "-":
        return "-"
    if clean.startswith("$") and clean.endswith("$"):
        clean = clean[1:-1].strip()
    clean = clean.replace("×", r"\times")
    return clean


def _plain_or_dash(value: Any) -> str:
    clean = str(value or "").strip()
    return clean if clean and clean != "-" else "—"


def _looks_like_rate_constant(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return bool(
        re.search(r"(?:\\times|×|x)\s*10", text, flags=re.I)
        or re.search(r"\d(?:\.\d+)?\s*[eE][+-]?\d+", text)
    )


def _looks_like_reference_code(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    code = r"(?:\d{2}[A-Z]\d{3}|\d{6})"
    return bool(re.fullmatch(rf"{code}(?:\s*[,;]\s*{code})*", text))


def _normalize_measurement_for_display(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    rate = str(normalized.get("rate_value") or "").strip()
    ph = str(normalized.get("pH") or "").strip()
    conditions = str(normalized.get("conditions") or "").strip()

    if _looks_like_rate_constant(ph) and not _looks_like_rate_constant(rate):
        normalized["rate_value"] = ph
        normalized["pH"] = ""
        normalized["conditions"] = rate
        if _looks_like_reference_code(conditions):
            normalized["references_raw"] = normalized.get("references_raw") or conditions
            normalized["buxton_code"] = normalized.get("buxton_code") or conditions
        elif conditions:
            normalized["conditions"] = "; ".join(part for part in [rate, conditions] if part)

    return normalized


def _inline_latex_text_to_html(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text == "-":
        return "—"

    placeholders: dict[str, str] = {}

    def protect(html: str) -> str:
        key = f"@@HTML{len(placeholders)}@@"
        placeholders[key] = html
        return key

    def convert_formula(match: re.Match[str]) -> str:
        formula_html = _formula_to_html_display(rf"\ce{{{match.group(1)}}}")
        formula_html = re.sub(r'^<div class="reaction-formula">|</div>$', "", formula_html)
        return protect(formula_html)

    text = re.sub(r"\\ce\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", convert_formula, text)
    text = text.replace("$", "")
    replacements = {
        r"\times": "×",
        r"\sim": "~",
        r"\cdot": "•",
        r"\bullet": "•",
        r"\rightarrow": "→",
        r"\to": "→",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\\(?:text|textrm|mathrm|emph)\{([^{}]*)\}", r"\1", text)
    text = escape(text)
    text = re.sub(r"_\{([^{}]*)\}", r"<sub>\1</sub>", text)
    text = re.sub(r"\^\{([^{}]*)\}", r"<sup>\1</sup>", text)
    text = re.sub(r"_([A-Za-z0-9+\-]+)", r"<sub>\1</sub>", text)
    text = re.sub(r"\^([A-Za-z0-9+\-]+)", r"<sup>\1</sup>", text)
    for key, html in placeholders.items():
        text = text.replace(key, html)
    return text


def _clean_text_latex(value: Any) -> str:
    clean = str(value or "").strip()
    clean = re.sub(r"\\(?:emph|text|textrm|mathrm)\{([^{}]*)\}", r"\1", clean)
    clean = clean.replace(r"\beta", "beta")
    return clean


def _render_reaction_card(row: dict[str, Any]) -> None:
    number = row.get("buxton_reaction_number") or f"DB-{row['id']}"
    data = _reaction_details(int(row["id"]), _db_mtime())
    reaction = data.get("reaction") or row
    measurements = data.get("measurements") or []

    with st.container(border=True):
        st.caption(
            f"Table {reaction.get('table_no')} · "
            f"Reaction {reaction.get('buxton_reaction_number') or number} · "
            f"{reaction.get('table_category') or ''}"
        )
        _render_formula(reaction)
        if reaction.get("reaction_name"):
            st.markdown(f"**Name:** {_clean_text_latex(reaction['reaction_name'])}")

        with st.expander("Details", expanded=False):
            _render_reaction_details(reaction, measurements)


def _render_search_result(row: dict[str, Any]) -> None:
    source = row.get("_source", "buxton")
    if source == "new":
        _render_new_reaction_card(row)
    else:
        _render_reaction_card(row)


def _render_results_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    st.markdown(
        """
        <style>
        .reaction-formula-inline {
          font-family: "Source Sans Pro", Arial, Helvetica, sans-serif;
          font-style: normal;
          font-weight: 500;
          white-space: normal;
        }
        .reaction-formula-inline sub,
        .reaction-formula-inline sup {
          font-size: 0.72em;
          line-height: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    header = st.columns([1.45, 4.2, 0.95, 1.25, 1.45, 0.8])
    for col, label in zip(
        header,
        ["Reference", "Reaction", "Source", "Solvent(s)", "Rate constant", "Detail"],
        strict=True,
    ):
        col.markdown(f"**{label}**")
    st.divider()

    open_key = st.session_state.get("open_result_detail")
    for index, row in enumerate(rows):
        source = str(row.get("_source") or "buxton")
        values = _new_result_summary(row) if source == "new" else _buxton_result_summary(row)
        detail_key = _result_detail_key(source, int(row["id"]))
        cols = st.columns([1.45, 4.2, 0.95, 1.25, 1.45, 0.8])
        cols[0].markdown(values["reference"], unsafe_allow_html=True)
        cols[1].markdown(values["reaction"], unsafe_allow_html=True)
        cols[2].markdown(values["source"])
        cols[3].markdown(values["solvent"], unsafe_allow_html=True)
        cols[4].markdown(values["rate"], unsafe_allow_html=True)
        if cols[5].button("Detail", key=f"detail_toggle_{detail_key}_{index}", width="content"):
            st.session_state["open_result_detail"] = None if open_key == detail_key else detail_key
            st.rerun()
        if open_key == detail_key:
            _render_inline_result_detail(row, detail_key)
        st.divider()


def _result_detail_key(source: str, reaction_id: int) -> str:
    return f"{source}:{int(reaction_id)}"


def _render_inline_result_detail(row: dict[str, Any], detail_key: str) -> None:
    source = str(row.get("_source") or "buxton")
    with st.container(border=True):
        top = st.columns([8, 1])
        top[0].markdown("**Details**")
        if top[1].button("Close", key=f"detail_close_{detail_key}", width="content"):
            st.session_state["open_result_detail"] = None
            st.rerun()

        if source == "new":
            data = _new_reaction_details(int(row["id"]), _new_db_mtime())
            reaction = data.get("reaction") or row
            st.caption(f"New · {reaction.get('squib') or row['id']} · {reaction.get('year') or ''}")
            st.markdown(
                _formula_to_html_display(
                    reaction.get("reaction_latex")
                    or reaction.get("reaction_canonical")
                    or reaction.get("reaction_text")
                    or ""
                ),
                unsafe_allow_html=True,
            )
            _render_new_reaction_details(reaction, data.get("measurements") or [])
            return

        data = _reaction_details(int(row["id"]), _db_mtime())
        reaction = data.get("reaction") or row
        st.caption(
            f"Table {reaction.get('table_no')} · "
            f"Reaction {reaction.get('buxton_reaction_number') or row['id']}"
        )
        _render_formula(reaction)
        if reaction.get("reaction_name"):
            st.markdown(f"**Name:** {_clean_text_latex(reaction['reaction_name'])}")
        _render_reaction_details(reaction, data.get("measurements") or [])


def _result_table_row(row: dict[str, Any]) -> str:
    source = str(row.get("_source") or "buxton")
    if source == "new":
        values = _new_result_summary(row)
    else:
        values = _buxton_result_summary(row)
    return (
        "<tr>"
        f"<td>{values['reference']}</td>"
        f"<td>{values['reaction']}</td>"
        f"<td>{values['source']}</td>"
        f"<td>{values['solvent']}</td>"
        f"<td>{values['rate']}</td>"
        f"<td><a href=\"{values['detail_href']}\">Detail</a></td>"
        "</tr>"
    )


def _buxton_result_summary(row: dict[str, Any]) -> dict[str, str]:
    data = _reaction_details(int(row["id"]), _db_mtime())
    reaction = data.get("reaction") or row
    measurements = data.get("measurements") or []
    first_measurement = _normalize_measurement_for_display(measurements[0]) if measurements else {}
    reference = (
        f"Table {reaction.get('table_no')}, "
        f"No. {reaction.get('buxton_reaction_number') or reaction.get('id')}"
    )
    return {
        "reference": escape(reference),
        "reaction": _formula_to_inline_html(
            reaction.get("formula_latex")
            or reaction.get("formula_canonical")
            or ""
        ),
        "source": "Buxton",
        "solvent": "H<sub>2</sub>O",
        "rate": _rate_to_inline_html(first_measurement.get("rate_value")),
        "detail_href": _detail_href("buxton", int(reaction["id"])),
    }


def _new_result_summary(row: dict[str, Any]) -> dict[str, str]:
    data = _new_reaction_details(int(row["id"]), _new_db_mtime())
    reaction = data.get("reaction") or row
    measurements = data.get("measurements") or []
    first_measurement = measurements[0] if measurements else {}
    reference = str(reaction.get("squib") or reaction.get("year") or f"New:{reaction['id']}")
    return {
        "reference": escape(reference),
        "reaction": _formula_to_inline_html(
            reaction.get("reaction_latex")
            or reaction.get("reaction_canonical")
            or reaction.get("reaction_text")
            or ""
        ),
        "source": "New",
        "solvent": _new_solvents_inline(reaction),
        "rate": _rate_to_inline_html(first_measurement.get("rate_value")),
        "detail_href": _detail_href("new", int(reaction["id"])),
    }


def _detail_href(source: str, reaction_id: int) -> str:
    return f"/reaction_detail_page?source={quote(source)}&id={int(reaction_id)}"


def _rate_to_inline_html(value: Any) -> str:
    clean = str(value or "").strip()
    if not clean or clean == "-":
        return "—"
    return _inline_latex_text_to_html(_prepare_new_rate_value(clean))


def _new_solvents_inline(reaction: dict[str, Any]) -> str:
    raw = reaction.get("solvents_json") or reaction.get("solvent_details_json")
    try:
        items = json.loads(str(raw or "[]"))
    except json.JSONDecodeError:
        items = []
    values = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        value = item.get("name_latex") or item.get("formula") or item.get("name")
        if value:
            values.append(_inline_latex_text_to_html(value))
    return ", ".join(values) if values else "—"


def _render_new_reaction_card(row: dict[str, Any]) -> None:
    data = _new_reaction_details(int(row["id"]), _new_db_mtime())
    reaction = data.get("reaction") or row
    measurements = data.get("measurements") or []

    with st.container(border=True):
        st.caption(
            f"New · {reaction.get('squib') or 'unknown reference'} · "
            f"{reaction.get('year') or 'unknown year'}"
        )
        st.markdown(
            _formula_to_html_display(
                reaction.get("reaction_latex")
                or reaction.get("reaction_canonical")
                or reaction.get("reaction_text")
                or ""
            ),
            unsafe_allow_html=True,
        )
        if reaction.get("title"):
            st.markdown(f"**Reference:** {_clean_text_latex(reaction['title'])}")
        with st.expander("New Details", expanded=False):
            _render_new_reaction_details(reaction, measurements)


def _render_reaction_details(reaction: dict[str, Any], measurements: list[dict[str, Any]]) -> None:
    st.link_button(
        "Report this reaction",
        f"/report_reaction_page?reaction_id={int(reaction['id'])}",
        width="content",
    )

    st.code(
        f"Canonical: {reaction.get('formula_canonical') or '-'}\n"
        f"Reactants: {reaction.get('reactants') or '-'}\n"
        f"Products: {reaction.get('products') or '-'}"
    )
    if reaction.get("notes"):
        st.markdown(
            f"**Notes:** {_inline_latex_text_to_html(reaction['notes'])}",
            unsafe_allow_html=True,
        )

    entry_image_path = _reaction_entry_image_path(reaction)
    if entry_image_path:
        st.image(str(entry_image_path), width="stretch", caption="Rendered table entry")
    else:
        st.info("Rendered table entry unavailable.")

    image_path = _reaction_image_path(reaction)
    show_png = st.toggle(
        "Show original Buxton PNG",
        value=False,
        key=f"show_source_png_{int(reaction['id'])}",
    )
    if show_png:
        if image_path:
            st.image(str(image_path), width="stretch", caption=image_path.name)
        else:
            st.info("PNG unavailable.")

    st.markdown("**Measurements**")
    if not measurements:
        st.caption("No measurements recorded.")
        return

    for raw_item in measurements:
        item = _normalize_measurement_for_display(raw_item)
        ref = item.get("citation_text") or item.get("buxton_code") or item.get("references_raw") or ""
        links = []
        if item.get("doi"):
            links.append(f"[DOI](https://doi.org/{item['doi']})")
        if item.get("source_url"):
            links.append(f"[source]({item['source_url']})")
        suffix = f" · {', '.join(links)}" if links else ""
        cols = st.columns([1.2, 1, 1])
        with cols[0]:
            st.caption("rate")
            rate = _prepare_math_value(item.get("rate_value") or "-")
            if rate == "-":
                st.write("—")
            else:
                st.latex(rate)
        with cols[1]:
            st.caption("pH")
            st.write(_plain_or_dash(item.get("pH")))
        with cols[2]:
            st.caption("method")
            st.write(_plain_or_dash(item.get("method")))
        if item.get("conditions"):
            st.markdown(
                f"**Notes:** {_inline_latex_text_to_html(item['conditions'])}",
                unsafe_allow_html=True,
            )
        if ref or suffix:
            st.caption(f"{ref}{suffix}")


def _render_new_reaction_details(reaction: dict[str, Any], measurements: list[dict[str, Any]]) -> None:
    st.code(
        f"New ID: {reaction.get('id')}\n"
        f"Canonical: {reaction.get('reaction_canonical') or '-'}\n"
        f"Reactants: {reaction.get('reactants_text') or '-'}\n"
        f"Products: {reaction.get('products_text') or '-'}\n"
        f"Detail URL: {reaction.get('detail_url') or '-'}"
    )

    _render_new_species("Reactants", reaction.get("reactant_details_json"))
    _render_new_species("Products", reaction.get("product_details_json"))
    _render_new_species("Solvent", reaction.get("solvent_details_json") or reaction.get("solvents_json"))

    cols = st.columns(3)
    cols[0].caption("data type")
    cols[0].write(_plain_or_dash(reaction.get("data_type")))
    cols[1].caption("method")
    cols[1].write(_plain_or_dash(reaction.get("experimental_method")))
    cols[2].caption("technique")
    cols[2].write(_plain_or_dash(reaction.get("analytical_technique")))

    if reaction.get("comment"):
        st.markdown(
            f"**Comment:** {_inline_latex_text_to_html(reaction['comment'])}",
            unsafe_allow_html=True,
        )

    st.markdown("**Reference**")
    reference_parts = [
        reaction.get("authors"),
        reaction.get("journal"),
        reaction.get("year"),
    ]
    st.write("; ".join(str(part) for part in reference_parts if part))
    if reaction.get("citation_text"):
        st.caption(str(reaction["citation_text"]))
    link_cols = st.columns(3)
    if reaction.get("doi"):
        link_cols[0].link_button("DOI", f"https://doi.org/{reaction['doi']}", width="content")
    if reaction.get("source_url"):
        link_cols[1].link_button("New reference", reaction["source_url"], width="content")
    if reaction.get("detail_url"):
        link_cols[2].link_button("New detail", reaction["detail_url"], width="content")

    st.markdown("**Measurements**")
    if not measurements:
        st.caption("No measurements recorded.")
        return

    for item in measurements:
        cols = st.columns([1.1, 0.7, 0.7, 0.8, 1.2])
        cols[0].caption("rate")
        rate = _prepare_new_rate_value(item.get("rate_value"))
        if rate == "-":
            cols[0].write("—")
        else:
            cols[0].latex(rate)
        cols[1].caption("pH")
        cols[1].write(_plain_or_dash(item.get("ph")))
        cols[2].caption("T, K")
        cols[2].write(_plain_or_dash(item.get("temperature_k")))
        cols[3].caption("order")
        cols[3].write(_plain_or_dash(item.get("reaction_order")))
        cols[4].caption("method")
        cols[4].write(_plain_or_dash(item.get("method")))
        if item.get("comment"):
            st.markdown(
                f"**Notes:** {_inline_latex_text_to_html(item['comment'])}",
                unsafe_allow_html=True,
            )


def _render_new_species(label: str, raw: Any) -> None:
    try:
        items = json.loads(str(raw or "[]"))
    except json.JSONDecodeError:
        items = []
    if not isinstance(items, list) or not items:
        return
    parts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        formula = str(item.get("formula") or "").strip()
        cas = str(item.get("cas_number") or "").strip()
        core = formula if formula and formula != "%" else name
        if name and formula and name != formula and formula != "%":
            core = f"{name} ({formula})"
        if cas:
            core = f"{core}, CAS {cas}"
        if core:
            parts.append(core)
    if parts:
        st.markdown(f"**{label}:** " + "; ".join(escape(part) for part in parts))


def _prepare_new_rate_value(value: Any) -> str:
    clean = str(value or "").strip()
    if not clean:
        return "-"
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)E([+-]?\d+)", clean, flags=re.I)
    if match:
        return rf"{match.group(1)} \times 10^{{{int(match.group(2))}}}"
    return _prepare_math_value(clean)


def _table_filter(label: str = "Table") -> int | None:
    choice = st.selectbox(
        label,
        options=["All", *PUBLIC_TABLES],
        format_func=lambda value: "All tables" if value == "All" else TABLE_LABELS[int(value)],
    )
    return None if choice == "All" else int(choice)


def _hero() -> None:
    _inject_seo_metadata()
    st.title("Radical Reactions Platform")
    st.subheader("Searchable Buxton radical reaction database")
    st.markdown(
        """
        Search radiation chemistry rate constants curated from the Buxton Critical Review:
        reactions of hydrated electrons, hydrogen atoms, hydroxyl radicals, oxide radical ions,
        radical-radical systems, and aqueous solution chemistry.
        """
    )
    st.markdown(
        "[Buxton Critical Review DOI: 10.1063/1.555805]"
        "(https://doi.org/10.1063/1.555805)"
    )
    st.markdown(
        """
        Developed by **Dr. Sergey Denisov** at **Institut de Chimie Physique (ICP)**,
        **UMR 8000 CNRS**, Universite Paris-Saclay.
        """
    )
    st.caption("Contact")
    st.image(_email_image_bytes(CONTACT_EMAIL), width=390)
    st.info(
        "If you find a problem in a reaction record, please use the "
        "**Report a Reaction** page. Reports are reviewed weekly and corrected data "
        "will be included in database updates. If you know articles with missing "
        "or new rate constants, use the **Suggest Articles** page."
    )
    st.markdown("[Report a Reaction](/report_reaction_page)")
    st.markdown("[Suggest Articles](/suggest_articles_page)")


def _statistics() -> None:
    stats = _stats(_db_mtime())

    cols = st.columns(3)
    cols[0].metric("Reactions", stats["reactions"])
    cols[1].metric("References", stats["references"])
    cols[2].metric("Tables", "5-9")
    st.caption(f"{stats['available_tables']} available. {stats['missing_tables']}")


def _new_access_enabled() -> bool:
    return bool(check_authentication())


def _render_login_controls() -> None:
    with st.sidebar:
        st.caption("Database Access")
        current_user = check_authentication()
        if current_user:
            st.success(f"Logged in: {current_user}")
            if st.button("Log out", width="stretch"):
                logout_user()
                st.rerun()
            return

        with st.form("public_login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", type="primary", width="stretch")
        if submitted:
            success, message = auth_db.authenticate_user(username.strip(), password)
            if success:
                login_user(username.strip())
                st.rerun()
            st.error(message)



def database_page() -> None:
    _hero()
    st.divider()
    st.subheader("Project Statistics")
    _statistics()
    has_new_access = _new_access_enabled()
    if has_new_access:
        new_stats = _new_stats(_new_db_mtime())
        with st.expander("New DB status", expanded=False):
            if _new_available():
                cols = st.columns(3)
                cols[0].metric("New reactions", new_stats["reactions"])
                cols[1].metric("New measurements", new_stats["measurements"])
                cols[2].metric("New references", new_stats["references"])
                st.caption(str(NEW_DB_PATH))
            else:
                st.warning("New DB not found locally.")

    st.divider()
    st.subheader("Search Reactions")
    default_query = str(st.query_params.get("q", "")).strip()
    default_scope = str(st.query_params.get("scope", "reactants")).strip()
    available_scope_options = dict(SEARCH_SCOPE_OPTIONS)
    if not has_new_access:
        available_scope_options.pop("solvents", None)
    if default_scope not in available_scope_options:
        default_scope = "reactants"
    scope_values = list(available_scope_options)
    scope_labels = [available_scope_options[value] for value in scope_values]
    with st.form("reaction_search_form"):
        query = st.text_input(
            "Reaction query",
            value=default_query,
            placeholder="hydroxyl radical, hydrated electron, e_aq, Ag+, O2, Table 8, reaction 12",
        )
        cols = st.columns([1, 1, 1])
        with cols[0]:
            if has_new_access:
                default_database = str(st.query_params.get("db", "both")).strip()
                if default_database not in DATABASE_OPTIONS:
                    default_database = "both"
                database_label = st.selectbox(
                    "Database",
                    list(DATABASE_OPTIONS.values()),
                    index=list(DATABASE_OPTIONS).index(default_database),
                )
                database = {
                    label: key for key, label in DATABASE_OPTIONS.items()
                }[database_label]
            else:
                database = "buxton"
                st.selectbox("Database", ["Buxton"], disabled=True)
        with cols[1]:
            scope_label = st.selectbox(
                "Search in",
                scope_labels,
                index=scope_values.index(default_scope),
            )
            search_scope = scope_values[scope_labels.index(scope_label)]
        with cols[2]:
            table_no = _table_filter() if database in {"buxton", "both"} else None
        submitted = st.form_submit_button("Search Database", type="primary")

    active_query = query.strip()
    if submitted and active_query:
        st.query_params["q"] = active_query
        st.query_params["scope"] = search_scope
        st.query_params["db"] = database
    if active_query:
        display_limit = _search_display_limit(active_query)
        if database in {"new", "both"} and not _new_available():
            st.error("New DB is not available locally.")
            return
        result = _combined_search(
            query.strip(),
            database,
            table_no,
            search_scope,
            display_limit,
            _db_mtime(),
            _new_db_mtime(),
        )
        rows = result["rows"]
        total = int(result["total"])
        if total > len(rows):
            st.caption(f"{total} matches. Showing first {len(rows)}. Refine by table or reagent.")
        else:
            st.caption(f"{total} matches")
        totals = result.get("totals") or {}
        if len(totals) > 1:
            st.caption(
                " · ".join(
                    f"{DATABASE_OPTIONS[source]}: {count}"
                    for source, count in totals.items()
                )
            )
        radical_advice = _broad_radical_advice(
            active_query,
            table_no,
            total,
            include_table_hint=database in {"buxton", "both"},
        )
        if radical_advice:
            st.warning(radical_advice)
        if database in {"buxton", "both"} and table_no is None and total > 100:
            counts = result["table_counts"]
            parts = [
                f"Table {table}: {counts[table]}"
                for table in PUBLIC_TABLES
                if counts.get(table, 0)
            ]
            st.info(
                "Many records match this query. "
                + "; ".join(parts)
                + ". Refine by table, reagent name, or chemical formula."
            )
        _render_results_table(rows)
    elif submitted:
        st.warning("Enter search query.")
    else:
        st.info("Try: `hydroxyl radical`, `hydrated electron`, `Ag+`, `O2`, `Table 8`.")


def reaction_detail_page() -> None:
    source = str(st.query_params.get("source", "buxton")).strip().lower()
    raw_id = str(st.query_params.get("id", "")).strip()
    try:
        reaction_id = int(raw_id)
    except ValueError:
        st.error("Invalid reaction id.")
        return

    st.link_button("Back to search", "/", width="content")

    if source == "new":
        if not _new_access_enabled():
            st.error("Login required for New details.")
            return
        if not _new_available():
            st.error("New DB is not available locally.")
            return
        data = _new_reaction_details(reaction_id, _new_db_mtime())
        reaction = data.get("reaction")
        if not reaction:
            st.error("New reaction not found.")
            return
        st.title("New Reaction Detail")
        st.caption(f"New · {reaction.get('squib') or reaction_id} · {reaction.get('year') or ''}")
        st.markdown(
            _formula_to_html_display(
                reaction.get("reaction_latex")
                or reaction.get("reaction_canonical")
                or reaction.get("reaction_text")
                or ""
            ),
            unsafe_allow_html=True,
        )
        _render_new_reaction_details(reaction, data.get("measurements") or [])
        return

    data = _reaction_details(reaction_id, _db_mtime())
    reaction = data.get("reaction")
    if not reaction:
        st.error("Buxton reaction not found.")
        return
    st.title("Buxton Reaction Detail")
    st.caption(
        f"Table {reaction.get('table_no')} · "
        f"Reaction {reaction.get('buxton_reaction_number') or reaction_id}"
    )
    _render_formula(reaction)
    if reaction.get("reaction_name"):
        st.markdown(f"**Name:** {_clean_text_latex(reaction['reaction_name'])}")
    _render_reaction_details(reaction, data.get("measurements") or [])


def downloads_page() -> None:
    st.title("PDF Downloads")
    st.markdown("Download compiled public PDF exports.")
    st.info(
        "The CSV-like structured database is still undergoing validation and is not "
        "published yet. If you need it for research, contact Dr. Sergey Denisov using "
        "the email image on the Home page. It will be added here after validation."
    )

    if not st.session_state.get("downloads_captcha_unlocked", False):
        with st.form("downloads_captcha_form"):
            captcha_answer = _captcha_input("downloads_captcha_form")
            submitted = st.form_submit_button("Unlock Downloads", type="primary")
        if not submitted:
            st.caption("Complete CAPTCHA to download PDFs and BibTeX.")
            return
        if not _captcha_passed("downloads_captcha_form", captcha_answer):
            _refresh_captcha("downloads_captcha_form")
            st.error("CAPTCHA failed.")
            return
        st.session_state["downloads_captcha_unlocked"] = True
        _refresh_captcha("downloads_captcha_form")
        st.rerun()

    cols = st.columns(2)
    for col, item in zip(cols, PDF_DOWNLOADS, strict=False):
        with col:
            st.subheader(item["title"])
            st.write(item["description"])
            path = _pdf_path(item)
            if not path:
                st.warning(f"PDF not found. Set `{item['env']}` or place export in default path.")
                with st.expander("Default paths", expanded=False):
                    for candidate in item["candidates"]:
                        st.code(str(candidate))
                continue

            st.caption(f"{path.name} · {_format_size(path)}")
            st.download_button(
                "Download PDF",
                data=_read_file(str(path)),
                file_name=path.name,
                mime="application/pdf",
                width="stretch",
                key=f"download_{item['key']}",
            )

    st.divider()
    st.subheader("References")
    st.markdown("Download BibTeX entries for references with DOI.")
    if BIBTEX_DOWNLOAD_PATH.exists():
        bibtex_data, bibtex_count = _bibtex_file_export(
            str(BIBTEX_DOWNLOAD_PATH),
            BIBTEX_DOWNLOAD_PATH.stat().st_mtime,
        )
    else:
        bibtex_data, bibtex_count = _bibtex_export(_db_mtime())
    st.caption(f"{bibtex_count} DOI references")
    st.download_button(
        "Download BibTeX",
        data=bibtex_data,
        file_name="radreactions_references_with_doi.bib",
        mime="application/x-bibtex",
        width="stretch",
    )


def report_reaction_page() -> None:
    st.title("Report a Reaction")
    st.markdown("Select table, Buxton reaction number, and describe the issue.")

    requested_reaction_id: int | None = None
    try:
        requested_reaction_id = int(str(st.query_params.get("reaction_id", "")).strip())
    except ValueError:
        requested_reaction_id = None
    requested_table_no = (
        _reaction_table_for_report(requested_reaction_id, _db_mtime())
        if requested_reaction_id
        else None
    )

    table_index = PUBLIC_TABLES.index(requested_table_no) if requested_table_no in PUBLIC_TABLES else 0
    table_no = st.selectbox(
        "Table",
        options=PUBLIC_TABLES,
        index=table_index,
        format_func=lambda value: TABLE_LABELS[int(value)],
    )
    choices = _reaction_choices_for_report(int(table_no), _db_mtime())

    if not choices:
        st.warning("No reactions available for this table.")
        return

    reaction_index = 0
    if requested_reaction_id:
        for index, choice in enumerate(choices):
            if int(choice["id"]) == requested_reaction_id:
                reaction_index = index
                break

    with st.form("reaction_problem_report_form", clear_on_submit=True):
        reaction = st.selectbox(
            "Buxton reaction number",
            options=choices,
            index=reaction_index,
            format_func=lambda item: item["reaction_label"],
        )
        comment = st.text_area("Comment", height=180)
        captcha_answer = _captcha_input("reaction_problem_report_form")
        submitted = st.form_submit_button("Submit Report", type="primary")

    if not submitted:
        st.caption("Reports are saved for weekly review.")
        return

    if not _captcha_passed("reaction_problem_report_form", captcha_answer):
        _refresh_captcha("reaction_problem_report_form")
        st.error("CAPTCHA failed.")
        return

    if len(comment.strip()) < 10:
        st.error("Write at least 10 characters.")
        return

    report_id = _save_problem_report(int(table_no), reaction, comment)
    _refresh_captcha("reaction_problem_report_form")
    st.success(f"Report #{report_id} saved.")


def suggest_articles_page() -> None:
    st.title("Suggest Articles")
    st.markdown(
        "Add DOI values for papers that may contain missing reactions, new rate constants, "
        "or data that should be checked."
    )

    doi_text = st.text_area(
        "DOI list",
        placeholder="10.1063/1.555805; 10.xxxx/example, https://doi.org/10.xxxx/example",
        height=110,
    )
    dois = _split_doi_list(doi_text)

    if not dois:
        st.caption("Separate DOI values with commas, semicolons, or new lines.")
        return

    if len(dois) > 20:
        st.warning("Showing first 20 DOI values. Submit large batches in smaller groups.")
        dois = dois[:20]

    with st.spinner("Checking DOI metadata..."):
        suggestions = [_lookup_doi_crossref(doi) for doi in dois]

    st.subheader("DOI Metadata")
    st.dataframe(
        [
            {
                "DOI": item["doi"],
                "Title": item["title"],
                "Year": item["year"],
                "Journal info": item["journal_info"],
                "Status": item["status"],
            }
            for item in suggestions
        ],
        hide_index=True,
        width="stretch",
    )

    st.subheader("Comments")
    with st.form("article_suggestions_form", clear_on_submit=False):
        contact_email = st.text_input("Your email (optional)")
        comments: dict[str, str] = {}
        for index, item in enumerate(suggestions, 1):
            label = item["title"] or item["doi"]
            comments[item["doi"]] = st.text_area(
                f"{index}. {label}",
                placeholder="Where to find the rate constants? What reaction/radical/reagent should be checked?",
                height=120,
                key=f"article_suggestion_comment_{index}_{item['doi']}",
            )
        captcha_answer = _captcha_input("article_suggestions_form")
        submitted = st.form_submit_button("Submit Suggestions", type="primary")

    if not submitted:
        st.caption("Suggestions are saved for weekly review.")
        return

    if not _captcha_passed("article_suggestions_form", captcha_answer):
        _refresh_captcha("article_suggestions_form")
        st.error("CAPTCHA failed.")
        return

    filled_comments = {doi: comment for doi, comment in comments.items() if comment.strip()}
    if not filled_comments:
        st.error("Add a comment for at least one DOI.")
        return
    if any(len(comment.strip()) < 10 for comment in filled_comments.values()):
        st.error("Each submitted comment must contain at least 10 characters.")
        return

    saved = _save_article_suggestions(suggestions, comments, contact_email)
    _refresh_captcha("article_suggestions_form")
    st.success(f"Saved {saved} article suggestion{'s' if saved != 1 else ''}.")


def developer_exports_page() -> None:
    st.title("Developer Exports")

    query_access_key = str(st.query_params.get("access_key", "")).strip()
    if not _admin_password_configured():
        st.error("Admin export password is not configured.")
        return

    with st.form("developer_exports_access_form"):
        access_key = st.text_input(
            "Access key",
            value=query_access_key,
            type="password",
        )
        unlocked = st.form_submit_button("Unlock", type="primary")

    has_access = _admin_password_matches(query_access_key) or (
        unlocked and _admin_password_matches(access_key)
    )
    if not has_access:
        st.caption("Access required.")
        return

    payload = _reports_export_payload()
    reaction_reports = payload["reaction_problem_reports"]
    article_suggestions = payload["article_suggestions"]

    st.subheader("Summary")
    st.json(payload["summary"])

    export_type = str(st.query_params.get("export", "all_json")).strip()
    export_options = {
        "all_json": "All reports JSON",
        "reaction_reports_json": "Reaction reports JSON",
        "article_suggestions_json": "Article suggestions JSON",
        "reaction_reports_csv": "Reaction reports CSV",
        "article_suggestions_csv": "Article suggestions CSV",
    }
    if export_type not in export_options:
        export_type = "all_json"

    selected_label = st.selectbox(
        "Export",
        options=list(export_options.values()),
        index=list(export_options).index(export_type),
    )
    selected_export = {
        label: key for key, label in export_options.items()
    }[selected_label]

    exports = {
        "all_json": (
            "radreactions_public_reports.json",
            "application/json",
            _json_download_bytes(payload),
        ),
        "reaction_reports_json": (
            "reaction_problem_reports.json",
            "application/json",
            _json_download_bytes(reaction_reports),
        ),
        "article_suggestions_json": (
            "article_suggestions.json",
            "application/json",
            _json_download_bytes(article_suggestions),
        ),
        "reaction_reports_csv": (
            "reaction_problem_reports.csv",
            "text/csv",
            _csv_download_bytes(reaction_reports),
        ),
        "article_suggestions_csv": (
            "article_suggestions.csv",
            "text/csv",
            _csv_download_bytes(article_suggestions),
        ),
    }
    file_name, mime, data = exports[selected_export]
    st.download_button(
        "Download Selected Export",
        data=data,
        file_name=file_name,
        mime=mime,
        type="primary",
        width="stretch",
    )

    st.divider()
    st.subheader("Direct Links")
    st.code("/developer_exports_page?access_key=...&export=all_json")
    st.code("/developer_exports_page?access_key=...&export=article_suggestions_json")
    st.code("/developer_exports_page?access_key=...&export=reaction_reports_csv")

    if selected_export.endswith("_csv"):
        preview_rows = article_suggestions if selected_export.startswith("article") else reaction_reports
        st.dataframe(preview_rows[:100], hide_index=True, width="stretch")
    else:
        st.json(json.loads(data.decode("utf-8")))


def main() -> None:
    current_path = urlparse(str(st.context.url)).path.rstrip("/")
    if current_path.endswith("/developer_exports_page"):
        developer_exports_page()
        return

    _render_login_controls()
    if current_path.endswith("/reaction_detail_page"):
        reaction_detail_page()
        return

    pages = [
        st.Page(database_page, title="Home"),
        st.Page(downloads_page, title="PDF Downloads"),
        st.Page(report_reaction_page, title="Report a Reaction"),
        st.Page(suggest_articles_page, title="Suggest Articles"),
    ]
    st.navigation(pages).run()


if __name__ == "__main__":
    main()
