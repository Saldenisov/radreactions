import csv
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture()
def data_env(tmp_path, monkeypatch):
    """Provide a temporary DATA_DIR and live modules reloaded against it.

    Returns a dict with:
      - base_dir: Path to temp data dir
      - mods: dict of reloaded modules { 'config', 'reactions_db', 'import_reactions', 'tools_rebuild_db', 'fast_populate_db', 'pdf_utils', 'tsv_utils' }
    """
    base = tmp_path / "data"
    base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(base))

    # Reload modules that depend on config.BASE_DIR
    import config as _config

    importlib.reload(_config)

    import reactions_db as _rdb

    importlib.reload(_rdb)

    import import_reactions as _imp

    importlib.reload(_imp)

    import tools.rebuild_db as _rebuild

    importlib.reload(_rebuild)

    import fast_populate_db as _fast

    importlib.reload(_fast)

    import pdf_utils as _pdf

    importlib.reload(_pdf)

    import tsv_utils as _tsv

    importlib.reload(_tsv)

    return {
        "base_dir": base,
        "mods": {
            "config": _config,
            "reactions_db": _rdb,
            "import_reactions": _imp,
            "tools_rebuild_db": _rebuild,
            "fast_populate_db": _fast,
            "pdf_utils": _pdf,
            "tsv_utils": _tsv,
        },
    }


def make_table_with_item(
    base_dir: Path,
    table: str,
    stem: str,
    *,
    buxton_no: str = "6-001",
    name: str = "Hydrated electron with oxygen",
    reaction: str = r"\\ce{e_{aq}^{-} + O_2 -> O_2^{.-}}",
    pH: str = "7",
    rate: str = "5.5 x 10^9",
    comments: str = "Test",
    ref: str = "BXT001",
    validated: bool = True,
) -> dict:
    """Create minimal table directory with one PNG and TSV/CSV and validation_db.json."""
    img_dir = base_dir / table / "sub_tables_images"
    csv_dir = img_dir / "csv"
    img_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    (img_dir / f"{stem}.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    # single-row TSV (tab-separated) written as .csv extension according to project convention
    row = [buxton_no, name, reaction, pH, rate, comments, ref]
    with open(csv_dir / f"{stem}.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(row)

    db_json = img_dir / "validation_db.json"
    db = {f"{stem}.png": validated}
    db_json.write_text(json.dumps(db, indent=2), encoding="utf-8")

    return {"image": img_dir / f"{stem}.png", "csv": csv_dir / f"{stem}.csv", "db": db_json}
