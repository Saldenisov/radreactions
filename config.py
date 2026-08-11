import os
from pathlib import Path

AVAILABLE_TABLES = ["table5", "table6", "table7", "table8", "table9"]


def _resolve_base_dir() -> Path:
    """Resolve runtime data location without creating or mutating it on import."""
    configured = os.getenv("DATA_DIR") or os.getenv("BASE_DIR")
    if configured:
        return Path(configured).expanduser()
    if Path("/app").exists():
        return Path("/data")
    return Path(__file__).resolve().parent / "data"


BASE_DIR = _resolve_base_dir()


def get_table_paths(table_choice: str) -> tuple[Path, Path, Path, Path]:
    image_dir = BASE_DIR / table_choice / "sub_tables_images"
    pdf_dir = image_dir / "csv" / "latex"
    tsv_dir = image_dir / "csv"
    db_path = image_dir / "validation_db.json"
    return image_dir, pdf_dir, tsv_dir, db_path


def get_data_dir() -> Path:
    """Return resolved runtime data directory."""
    return BASE_DIR
