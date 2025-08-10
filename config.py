import os
from pathlib import Path

AVAILABLE_TABLES = ['table5', 'table6', 'table7', 'table8', 'table9']

# Use environment variable for deployment, fallback to local path for development
BASE_DIR = Path(os.getenv('BASE_DIR', r"E:\ICP_notebooks\Buxton"))

def get_table_paths(table_choice):
    image_dir = BASE_DIR / table_choice / "sub_tables_images"
    pdf_dir = image_dir / "csv" / "latex"
    tsv_dir = image_dir / "csv"
    db_path = image_dir / "validation_db.json"
    return image_dir, pdf_dir, tsv_dir, db_path
