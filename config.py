import os
from pathlib import Path

AVAILABLE_TABLES = ["table5", "table6", "table7", "table8", "table9"]

# Determine BASE_DIR robustly across environments (Railway Docker, local Windows)
# Priority:
# 1) DATA_DIR env var if provided
# 2) BASE_DIR env var if provided (back-compat)
# 3) Railway/Docker: /data (mounted volume)
# 4) Legacy Docker path: /app/data
# 5) Local Windows development: E:\ICP_notebooks\Buxton\data
# 6) Fallback: ./data relative to project
_env_data = os.getenv("DATA_DIR")
_env_base = os.getenv("BASE_DIR")

# Debug output
print(f"[CONFIG DEBUG] DATA_DIR env var: {_env_data}")
print(f"[CONFIG DEBUG] BASE_DIR env var: {_env_base}")
print(f"[CONFIG DEBUG] /app exists: {Path('/app').exists()}")
print(f"[CONFIG DEBUG] /data exists: {Path('/data').exists()}")
print(f"[CONFIG DEBUG] / exists: {Path('/').exists()}")

if _env_data:
    BASE_DIR = Path(_env_data)
    print(f"[CONFIG DEBUG] Using DATA_DIR env var: {BASE_DIR}")
elif _env_base:
    BASE_DIR = Path(_env_base)
    print(f"[CONFIG DEBUG] Using BASE_DIR env var: {BASE_DIR}")
else:
    # Check environment-specific paths in order of preference
    # Force /data for Railway/Docker environments
    if Path("/app").exists() and Path("/").exists():  # Container environment (Railway/Docker)
        BASE_DIR = Path("/data")  # Always use /data in containers
        print(f"[CONFIG DEBUG] Container detected, using /data: {BASE_DIR}")
    elif Path(r"E:\\ICP_notebooks\\Buxton").exists():  # Local Windows
        BASE_DIR = Path(r"E:\\ICP_notebooks\\Buxton\\data")
        print(f"[CONFIG DEBUG] Windows dev env: {BASE_DIR}")
    else:
        # Local development fallback
        BASE_DIR = Path(__file__).parent.parent / "data"
        print(f"[CONFIG DEBUG] Local dev fallback: {BASE_DIR}")

# Ensure BASE_DIR exists on import (for uploaded data)
BASE_DIR.mkdir(parents=True, exist_ok=True)


def get_table_paths(table_choice):
    image_dir = BASE_DIR / table_choice / "sub_tables_images"
    pdf_dir = image_dir / "csv" / "latex"
    tsv_dir = image_dir / "csv"
    db_path = image_dir / "validation_db.json"
    return image_dir, pdf_dir, tsv_dir, db_path


def get_data_dir() -> Path:
    """Return the resolved data directory path used by the app."""
    return BASE_DIR
