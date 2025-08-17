import os
from pathlib import Path

AVAILABLE_TABLES = ['table5', 'table6', 'table7', 'table8', 'table9']

# Determine BASE_DIR robustly across environments (Railway Docker, local Windows)
# Priority:
# 1) Explicit BASE_DIR env var if provided
# 2) Common container paths (/app/data preferred, then /data)
# 3) Local Windows development path
_env_base = os.getenv('BASE_DIR')
if _env_base:
    # If env var provided but path doesn't exist, fall back to common candidates
    _env_path = Path(_env_base)
    if _env_path.exists():
        BASE_DIR = _env_path
    else:
        candidates = [Path('/app/data'), Path('/data'), Path(r"E:\\ICP_notebooks\\Buxton")]
        for _p in candidates:
            if _p.exists():
                BASE_DIR = _p
                break
        else:
            BASE_DIR = Path('/app/data')
else:
    candidates = [Path('/app/data'), Path('/data'), Path(r"E:\\ICP_notebooks\\Buxton")]
    for _p in candidates:
        if _p.exists():
            BASE_DIR = _p
            break
    else:
        # Default to /app/data if nothing exists; will work in container image with baked data
        BASE_DIR = Path('/app/data')

def get_table_paths(table_choice):
    image_dir = BASE_DIR / table_choice / "sub_tables_images"
    pdf_dir = image_dir / "csv" / "latex"
    tsv_dir = image_dir / "csv"
    db_path = image_dir / "validation_db.json"
    return image_dir, pdf_dir, tsv_dir, db_path
