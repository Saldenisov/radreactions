"""Admin page for data management and maintenance operations.

This page provides authenticated admin users with tools for:
- Uploading and managing data ZIP files
- Database maintenance and rebuild operations
- Batch processing of TSV/CSV files to LaTeX/PDF
- Search and replace operations across tables
"""

import io
import os
import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path

import streamlit as st

# Import your existing auth functions
try:
    from auth import check_authentication
except ImportError:
    # Fallback for development
    def check_authentication() -> str | None:
        return "admin"


try:
    from config import BASE_DIR
except ImportError:
    # Fallback - prefer DATA_DIR env var, then BASE_DIR, then detect
    _data_dir_str = os.environ.get("DATA_DIR")
    _base_dir_str = os.environ.get("BASE_DIR")
    if _data_dir_str:
        BASE_DIR = Path(_data_dir_str)
    elif _base_dir_str:
        BASE_DIR = Path(_base_dir_str)
    elif Path("/data").exists():  # Docker/Railway environment (preferred mount)
        BASE_DIR = Path("/data")
    elif Path("/app").exists():  # Legacy Docker/Railway
        BASE_DIR = Path("/app/data")
    elif Path(r"E:\\ICP_notebooks\\Buxton").exists():  # Local Windows
        BASE_DIR = Path(r"E:\\ICP_notebooks\\Buxton\\data")
    else:
        BASE_DIR = Path("./data")  # Relative fallback


def is_within_base(base: str, target: str) -> bool:
    """Check if target path is within base directory to prevent zip slip attacks."""
    base = os.path.abspath(base)
    target = os.path.abspath(target)
    return os.path.commonpath([base]) == os.path.commonpath([base, target])


def extract_zip_safely(zip_bytes: bytes, dest_dir: str) -> None:
    """Extract ZIP file safely to destination directory, preventing zip slip attacks."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # Validate no paths escape dest_dir
        for name in zf.namelist():
            # Skip directories and hidden files starting with .
            if name.endswith("/") or os.path.basename(name).startswith("."):
                continue

            dest_path = os.path.join(dest_dir, name)
            if not is_within_base(dest_dir, dest_path):
                raise ValueError(f"Illegal path in zip: {name}")

        # Extract all files
        zf.extractall(dest_dir)


def delete_folder_in_base(folder_name: str) -> tuple[bool, str]:
    """Safely delete a single subfolder within BASE_DIR.

    Returns (ok, message).
    """
    try:
        # Normalize folder name to avoid traversal
        if not folder_name or os.path.basename(folder_name) != folder_name:
            return False, "Invalid folder name"

        target = Path(BASE_DIR) / folder_name
        target = target.resolve()

        # Safety checks
        base_resolved = Path(BASE_DIR).resolve()
        if not target.exists() or not target.is_dir():
            return False, "Folder not found"
        if os.path.commonpath([str(base_resolved)]) != os.path.commonpath(
            [str(base_resolved), str(target)]
        ):
            return False, "Not allowed"
        if target == base_resolved:
            return False, "Refusing to delete base directory"

        shutil.rmtree(target)
        return True, f"Deleted {folder_name}"
    except Exception as e:
        return False, f"Error: {e}"


def get_directory_size(path: Path | str) -> int:
    """Calculate total size of directory in bytes."""
    total_size = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
    except OSError:
        pass
    return total_size


def format_size(bytes_size: int) -> str:
    """Format size in bytes to human readable format."""
    size_float = float(bytes_size)
    for unit in ["B", "KB", "MB", "GB"]:
        if size_float < 1024.0:
            return f"{size_float:.1f} {unit}"
        size_float /= 1024.0
    return f"{size_float:.1f} TB"


def get_table_title(table_path: Path | str) -> str:
    """Get table title from info.txt file, or return empty string if not found.

    Args:
        table_path: Path to the table directory

    Returns:
        Table title from info.txt if found and has format 'TITLE: Name of Table',
        otherwise returns empty string.
    """
    info_file = Path(table_path) / "info.txt"
    if not info_file.exists():
        return ""

    try:
        content = info_file.read_text(encoding="utf-8").strip()
        # Look for line starting with "TITLE: "
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("TITLE: "):
                return line[7:].strip()  # Remove "TITLE: " prefix
        return ""
    except Exception:
        return ""


def create_zip_from_tables(
    base_dir: Path, selected_tables: list[str], csv_only: bool = True
) -> bytes:
    """Create a ZIP file containing selected table directories.

    Args:
        base_dir: Base directory containing table folders
        selected_tables: List of table folder names to include
        csv_only: If True, include only CSV files (and their parent folders). If False, include all files.

    Returns:
        ZIP file content as bytes preserving directory structure
    """
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for table_name in selected_tables:
            table_path = base_dir / table_name
            if not table_path.exists() or not table_path.is_dir():
                continue

            # Add files in the table directory recursively
            for root, dirs, files in os.walk(table_path):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith(".")]

                for file in files:
                    # Skip hidden files and common unwanted files
                    if file.startswith(".") or file.endswith(".tmp"):
                        continue

                    file_path = Path(root) / file
                    # If csv_only, include only files under a csv folder or with .csv extension
                    if csv_only:
                        # Accept if path contains '/csv/' segment or file endswith .csv
                        rel = file_path.relative_to(base_dir).as_posix().lower()
                        if "/csv/" not in rel and not rel.endswith(".csv"):
                            continue

                    # Create archive path relative to base_dir
                    archive_path = file_path.relative_to(base_dir)

                    try:
                        zf.write(file_path, archive_path)
                    except Exception as e:
                        # Skip files that can't be read (e.g., locked files)
                        try:
                            st.warning(f"Skipped file {file_path}: {e}")
                        except Exception:
                            pass
                        continue

    return zip_buffer.getvalue()


def get_table_info(table_path: Path) -> dict:
    """Get detailed information about a table directory.

    Returns:
        Dict with keys: name, title, size, file_count, subdirs
    """
    name = table_path.name
    title = get_table_title(table_path)
    size = get_directory_size(table_path)
    file_count = 0
    subdirs: list[str] = []

    try:
        # Count files and subdirectories
        for root, dirs, files in os.walk(table_path):
            file_count += len([f for f in files if not f.startswith(".")])
            if root == str(table_path):  # Only immediate subdirs
                subdirs = [d for d in dirs if not d.startswith(".")]
    except Exception:
        pass

    return {
        "name": name,
        "title": title,
        "size": size,
        "file_count": file_count,
        "subdirs": subdirs,
    }


def main():
    st.title("🔧 Admin Page")

    # Check authentication - only allow logged in users (basic admin check)
    try:
        current_user = check_authentication()
        if not current_user:
            st.error("❌ You must be logged in to access this page.")
            st.info("Please log in to continue.")
            return
    except Exception as e:
        st.error(f"❌ Authentication error: {str(e)}")
        st.info("Please ensure the authentication system is properly configured.")
        return

    st.success(f"✅ Authenticated as: {current_user}")

    # Admin Tools in left sidebar (superuser only)
    with st.sidebar:
        st.subheader("🛠 Admin Tools")
        if current_user == "saldenisov":
            st.caption("Admin utilities and maintenance operations.")

            # Pause toggle for DB access across pages
            _db_paused = bool(st.session_state.get("db_paused", False))
            new_pause = st.checkbox(
                "Pause DB access",
                value=_db_paused,
                help="Prevents UI from opening the DB during maintenance (avoids file locks)",
                key="sidebar_pause_db",
            )
            if new_pause != _db_paused:
                st.session_state.db_paused = new_pause
                st.success(f"DB pause set to {new_pause}")

            st.markdown("---")
            # Rebuild DB from validated sources (offline build + swap)
            if st.button(
                "🔄 Rebuild DB from Validated Sources",
                use_container_width=True,
                key="rebuild_db_btn",
            ):
                try:
                    st.session_state.db_paused = True
                    try:
                        # Best-effort: allow any open connections elsewhere to settle
                        time.sleep(0.2)
                    except Exception:
                        pass
                    from config import BASE_DIR as _BASE
                    from tools.rebuild_db import build_db_offline_fast, swap_live_db

                    build_path = _BASE / "reactions_build.db"
                    build_db_offline_fast(build_path)
                    swap_live_db(build_path)
                    st.success("Database rebuilt successfully with validated entries only!")
                except Exception as e:
                    # Fallback legacy approach if swap fails due to locks/corruption
                    msg = str(e)
                    st.warning(f"Primary rebuild failed, attempting fallback...\n{msg}")
                    try:
                        from tools.rebuild_db import rebuild_db_from_validations

                        rebuild_db_from_validations()
                        st.success("Database rebuilt successfully (fallback path).")
                    except Exception as e2:
                        st.error(f"Database rebuild failed after fallback: {e2}")
                finally:
                    st.session_state.db_paused = False

            st.markdown("---")
            # Batch: TSV -> LaTeX -> PDF for non-validated and/or missing PDFs
            st.caption("TSV → LaTeX → PDF batch")
            try:
                from config import AVAILABLE_TABLES as _ALL_TABLES
            except Exception:
                _ALL_TABLES = []
            _scope_options = ["All tables"] + _ALL_TABLES
            _selected_scope = st.selectbox(
                "Scope",
                options=_scope_options,
                index=0,
                help="Process all tables or limit to a single table",
                key="batch_scope",
            )
            _processing_mode = st.selectbox(
                "Processing mode",
                options=[
                    "Untreated (unvalidated) only",
                    "Treated (validated) only",
                    "Missing PDF only",
                    "Untreated + Missing PDF",
                    "All items",
                ],
                index=3,  # Default to "Untreated + Missing PDF"
                help="Choose which items to process based on validation status and PDF existence",
                key="batch_processing_mode",
            )
            _max_items = st.number_input(
                "Max items (0 = no limit)",
                min_value=0,
                value=0,
                step=1,
                key="batch_max_items",
            )
            _dry_run = st.checkbox("Dry run (list only)", value=False, key="batch_dry_run")
            _run_parallel = st.checkbox("Run in parallel", value=True, key="batch_parallel")
            if _run_parallel:
                try:
                    import os as _os_mod

                    default_workers = _os_mod.cpu_count() or 4
                except Exception:
                    default_workers = 4
                _workers = st.number_input(
                    "Workers",
                    min_value=1,
                    max_value=64,
                    value=int(default_workers),
                    step=1,
                    key="batch_workers",
                )
            else:
                _workers = 1

            if st.button("🧾 Run TSV → LaTeX → PDF", use_container_width=True, key="run_batch_pdf"):
                try:
                    from pathlib import Path as _Path

                    from config import AVAILABLE_TABLES, get_table_paths
                    from pdf_utils import compile_tex_to_pdf, tsv_to_full_latex_article
                    from reactions_db import ensure_db, get_validation_meta_by_source
                    from tsv_utils import correct_tsv_file

                    con_local = ensure_db()
                    tables_to_scan = (
                        AVAILABLE_TABLES
                        if _selected_scope == "All tables"
                        else [str(_selected_scope)]
                    )

                    to_process: list[tuple[str, str, _Path]] = []
                    missing_sources = 0
                    missing_pdfs = 0
                    for table in tables_to_scan:
                        IMG_DIR, PDF_DIR, TSV_DIR, _ = get_table_paths(table)
                        images = sorted([p.name for p in IMG_DIR.glob("*.png")])
                        for img in images:
                            stem = _Path(img).stem
                            csv_path = TSV_DIR / f"{stem}.csv"
                            tsv_path = TSV_DIR / f"{stem}.tsv"
                            source = (
                                csv_path
                                if csv_path.exists()
                                else (tsv_path if tsv_path.exists() else None)
                            )
                            if not source:
                                missing_sources += 1
                                continue
                            meta = get_validation_meta_by_source(con_local, str(source))
                            validated = bool(meta.get("validated", False))
                            pdf_path = PDF_DIR / f"{stem}.pdf"
                            pdf_missing = not pdf_path.exists()

                            # Determine if item should be processed based on selected mode
                            should_process = False
                            if _processing_mode == "Untreated (unvalidated) only":
                                should_process = not validated
                            elif _processing_mode == "Treated (validated) only":
                                should_process = validated
                            elif _processing_mode == "Missing PDF only":
                                should_process = pdf_missing
                            elif _processing_mode == "Untreated + Missing PDF":
                                should_process = (not validated) or pdf_missing
                            elif _processing_mode == "All items":
                                should_process = True

                            if should_process:
                                to_process.append((table, img, source))
                                if pdf_missing:
                                    missing_pdfs += 1

                    if _max_items and int(_max_items) > 0:
                        to_process = to_process[: int(_max_items)]

                    total = len(to_process)
                    scope_label = (
                        "all tables" if _selected_scope == "All tables" else f"{_selected_scope}"
                    )
                    if total == 0:
                        st.info("No items found for the selected scope and options.")
                    else:
                        if _dry_run:
                            st.info(
                                f"[Dry run] Scope: {scope_label}. Would process {total} items (missing TSV/CSV: {missing_sources}, missing PDFs: {missing_pdfs})."
                            )
                            with st.expander("Show items to process", expanded=False):
                                for table, img, src in to_process:
                                    st.write(f"{table}/{img}: {src}")
                        else:
                            st.write(
                                f"Scope: {scope_label}. Found {total} items to process (missing TSV/CSV: {missing_sources}, missing PDFs: {missing_pdfs})."
                            )
                            progress = st.progress(0.0)
                            ok = 0
                            failed = 0
                            logs: list[str] = []
                            pdfs: list[tuple[str, str, str]] = []

                            def _run_one_compile(src_path: _Path):
                                try:
                                    correct_tsv_file(src_path)
                                    latex_path = tsv_to_full_latex_article(src_path)
                                    rc, out = compile_tex_to_pdf(latex_path)
                                    if rc == 0:
                                        pdf_path = str(
                                            latex_path.parent / (latex_path.stem + ".pdf")
                                        )
                                        return True, "", pdf_path
                                    else:
                                        tail = out[-4000:] if isinstance(out, str) else str(out)
                                        return False, f"LaTeX failed (exit {rc}).\n{tail}", None
                                except Exception as e:
                                    return False, f"Error: {e}", None

                            if _run_parallel and _workers and int(_workers) > 1:
                                from concurrent.futures import ThreadPoolExecutor, as_completed

                                with ThreadPoolExecutor(max_workers=int(_workers)) as ex:
                                    futures = {
                                        ex.submit(_run_one_compile, src): (table, img, src)
                                        for (table, img, src) in to_process
                                    }
                                    for i, fut in enumerate(as_completed(futures), 1):
                                        table, img, src = futures[fut]
                                        success, log, pdf_path = fut.result()
                                        if success:
                                            ok += 1
                                            if pdf_path:
                                                pdfs.append((table, img, pdf_path))
                                        else:
                                            failed += 1
                                            if log:
                                                logs.append(f"{table}/{img}: {log}")
                                        progress.progress(i / total)
                            else:
                                for idx, (table, img, src) in enumerate(to_process, 1):
                                    success, log, pdf_path = _run_one_compile(src)
                                    if success:
                                        ok += 1
                                        if pdf_path:
                                            pdfs.append((table, img, pdf_path))
                                    else:
                                        failed += 1
                                        if log:
                                            logs.append(f"{table}/{img}: {log}")
                                    progress.progress(idx / total)

                            if failed == 0:
                                st.success(
                                    f"Completed: {ok}/{total} PDFs generated. Missing TSV/CSV: {missing_sources}; missing PDFs: {missing_pdfs}."
                                )
                            else:
                                st.warning(
                                    f"Completed with errors: success={ok}, failed={failed}, total={total}. Missing TSV/CSV: {missing_sources}; missing PDFs: {missing_pdfs}."
                                )
                                if logs:
                                    with st.expander("Show errors/logs", expanded=False):
                                        st.code("\n\n".join(logs), language="text")

                            if pdfs:
                                with st.expander("Generated PDFs", expanded=False):
                                    for table, img, pdf_path in pdfs:
                                        st.markdown(f"- {table}/{img}: `{pdf_path}`")
                except Exception as e:
                    st.error(f"Batch generation failed: {e}")

            st.markdown("---")
            # Sync DB validation state to JSON files (dangerous)
            st.markdown("**Overwrite JSON Files from Database**")
            st.warning("⚠️ IRREVERSIBLE: Overwrites all validation_db.json files with DB state.")
            sync_confirmed = st.checkbox(
                "I understand this will permanently overwrite all validation_db.json files",
                key="sidebar_sync_confirm",
            )
            if st.button(
                "🔄 Overwrite JSON Files from Database",
                disabled=not sync_confirmed,
                use_container_width=True,
                key="sidebar_sync_btn",
            ):
                try:
                    from tools.rebuild_db import sync_db_validation_to_json_files

                    sync_db_validation_to_json_files()
                    st.success("Synced database validation state to JSON files!")
                except Exception as e:
                    st.error(f"Sync failed: {e}")
        else:
            st.info("Admin tools are restricted to the owner account.")

    # Ensure BASE_DIR exists
    os.makedirs(BASE_DIR, exist_ok=True)

    # Show current data directory status
    st.subheader("📁 Current Data Directory Status")

    col1, col2 = st.columns(2)
    with col1:
        try:
            st.code(f"Target directory: {BASE_DIR.resolve()}")
        except Exception:
            st.code(f"Target directory: {BASE_DIR}")

    with col2:
        if os.path.exists(BASE_DIR):
            current_size = get_directory_size(BASE_DIR)
            st.metric("Current Size", format_size(current_size))

            # Show subdirectories
            subdirs = [
                d
                for d in os.listdir(BASE_DIR)
                if os.path.isdir(os.path.join(BASE_DIR, d)) and not d.startswith(".")
            ]

            if subdirs:
                st.write("📊 **Tables found:**")
                for subdir in sorted(subdirs):
                    subdir_path = os.path.join(BASE_DIR, subdir)
                    subdir_size = get_directory_size(subdir_path)
                    table_title = get_table_title(subdir_path)
                    if table_title:
                        st.write(f"  • `{subdir}` - **{table_title}** ({format_size(subdir_size)})")
                    else:
                        st.write(f"  • `{subdir}` ({format_size(subdir_size)})")

        else:
            st.warning("Directory does not exist yet")

    st.divider()

    # Batch Search & Replace (Tables)
    st.subheader("🔎 Batch Search & Replace (Tables)")

    # Discover tables
    if os.path.exists(BASE_DIR):
        available_tables = [
            d
            for d in sorted(os.listdir(BASE_DIR))
            if os.path.isdir(os.path.join(BASE_DIR, d)) and not d.startswith(".")
        ]
    else:
        available_tables = []

    if not available_tables:
        st.info("No tables available. Upload data first.")
    else:
        col_scope1, col_scope2 = st.columns([2, 1])
        with col_scope1:
            table_for_fr = st.selectbox(
                "Select table",
                options=available_tables,
                help="Choose a table folder to search & replace within",
            )
        with col_scope2:
            auto_compile = st.checkbox(
                "Compile after apply",
                value=True,
                help="After replacing, correct TSV and recompile LaTeX/PDF for affected files",
            )

        st.caption("Enter pattern and options, then run a dry scan. Review results and apply.")
        col_in1, col_in2, col_in3 = st.columns([2, 2, 2])
        with col_in1:
            fr_find = st.text_input("Find", key="admin_fr_find", placeholder="e.g. .OH")
        with col_in2:
            fr_repl = st.text_input("Replace with", key="admin_fr_repl", placeholder="e.g. ^.OH")
        with col_in3:
            only_eq = st.checkbox(
                "Only Reaction equation column",
                value=False,
                help="Limit replacements to the 3rd column (reaction equation)",
            )
        col_opt1, col_opt2 = st.columns([1, 1])
        with col_opt1:
            regex = st.checkbox("Regex", value=False)
        with col_opt2:
            case_sensitive = st.checkbox("Case sensitive", value=True)

        def _compile_pat_admin(pat: str):
            import re as _re

            if not pat:
                return None
            flags = 0 if case_sensitive else _re.IGNORECASE
            if regex:
                try:
                    return _re.compile(pat, flags)
                except _re.error as e:
                    st.warning(f"Invalid regex: {e}")
                    return None
            else:
                return _re.compile(_re.escape(pat), flags)

        res_key = f"admin_fr_results_{table_for_fr}"
        sel_key = f"admin_fr_selected_{table_for_fr}"

        col_btn1, col_btn2 = st.columns([1, 3])
        with col_btn1:
            if st.button("Dry scan", type="primary"):
                try:
                    from config import get_table_paths as _get_paths

                    IMG_DIR, PDF_DIR, TSV_DIR, _ = _get_paths(table_for_fr)
                except Exception as e:
                    st.error(f"Path error: {e}")
                    TSV_DIR = None
                results: list[dict[str, object]] = []
                pat = _compile_pat_admin(fr_find)
                if TSV_DIR and pat:
                    import re as _re

                    images = sorted([p.name for p in IMG_DIR.glob("*.png")])
                    for img in images:
                        stem = Path(img).stem
                        csv_p = TSV_DIR / f"{stem}.csv"
                        if not csv_p.exists():
                            continue
                        try:
                            text_i = csv_p.read_text(encoding="utf-8")
                        except Exception:
                            continue
                        matches = 0
                        new_text_i = text_i
                        try:
                            if only_eq:
                                new_lines: list[str] = []
                                for ln in text_i.split("\n"):
                                    if not ln:
                                        new_lines.append(ln)
                                        continue
                                    cols = ln.split("\t")
                                    if len(cols) >= 3:
                                        old = cols[2]
                                        matches += len(list(pat.finditer(old)))
                                        cols[2] = pat.sub(lambda _m: fr_repl, old)
                                        ln = "\t".join(cols)
                                    new_lines.append(ln)
                                new_text_i = "\n".join(new_lines)
                            else:
                                matches = len(list(pat.finditer(text_i)))
                                new_text_i = pat.sub(lambda _m: fr_repl, text_i)
                        except _re.error as _e:
                            st.warning(f"Regex error in {csv_p.name}: {_e}")
                            continue
                        if matches > 0 and new_text_i != text_i:
                            results.append(
                                {
                                    "path": str(csv_p),
                                    "file": csv_p.name,
                                    "matches": matches,
                                    "new": new_text_i,
                                }
                            )
                st.session_state[res_key] = results
                st.session_state[sel_key] = {r["path"] for r in results}
        with col_btn2:
            st.caption("Dry scan lists impacted files without changing anything.")

        results2 = list(st.session_state.get(res_key, []))
        if results2:
            total_found = len(results2)
            st.info(f"Found {total_found} files with matches in {table_for_fr}.")

            # Pagination (20 per page)
            PAGE_SIZE = 20
            page_key = f"admin_fr_page_{table_for_fr}"
            if page_key not in st.session_state:
                st.session_state[page_key] = 0
            total_pages = max(1, (total_found + PAGE_SIZE - 1) // PAGE_SIZE)
            # Clamp
            st.session_state[page_key] = max(0, min(st.session_state[page_key], total_pages - 1))
            cur_page = st.session_state[page_key]
            start_idx = cur_page * PAGE_SIZE
            end_idx = min(start_idx + PAGE_SIZE, total_found)
            page_results = results2[start_idx:end_idx]

            # Page controls
            pc1, pc2, pc3 = st.columns([1, 2, 1])
            with pc1:
                if st.button("◀ Prev", disabled=(cur_page == 0)):
                    st.session_state[page_key] = max(0, cur_page - 1)
                    st.rerun()
            with pc2:
                st.write(f"Page {cur_page + 1}/{total_pages}  ")
                st.caption(f"Showing {start_idx + 1}-{end_idx} of {total_found}")
            with pc3:
                if st.button("Next ▶", disabled=(cur_page >= total_pages - 1)):
                    st.session_state[page_key] = min(total_pages - 1, cur_page + 1)
                    st.rerun()

            # selection controls
            sel_all_key = f"admin_fr_select_all_{table_for_fr}"
            sel_set = set(st.session_state.get(sel_key, set()))
            chk_all, _ = st.columns([1, 3])
            with chk_all:
                if st.checkbox("Select all (all pages)", key=sel_all_key, value=True):
                    sel_set = {r["path"] for r in results2}
                else:
                    pass

            # Per-file checkboxes (current page), with CSV preview on click (expander)
            for r in page_results:
                p = str(r["path"])  # noqa: F722
                fname = str(r["file"])  # noqa: F722
                mcount = int(r["matches"])  # noqa: F722
                row_cols = st.columns([1, 3])
                with row_cols[0]:
                    ck = st.checkbox(
                        "Select",
                        key=f"admin_fr_sel_{table_for_fr}_{fname}",
                        value=(p in sel_set),
                    )
                    if ck:
                        sel_set.add(p)
                    else:
                        sel_set.discard(p)
                with row_cols[1]:
                    with st.expander(f"{fname} — {mcount} matches (click to view CSV)"):
                        try:
                            csv_text = Path(p).read_text(encoding="utf-8")
                        except Exception as e:
                            csv_text = f"<error reading file: {e}>"
                        st.code(csv_text, language="text")
            st.session_state[sel_key] = sel_set

            # Parallel options
            opt1, opt2 = st.columns([1, 1])
            with opt1:
                run_parallel = st.checkbox(
                    "Run in parallel", value=True, key=f"admin_fr_parallel_{table_for_fr}"
                )
            with opt2:
                if run_parallel:
                    try:
                        import os as _os_mod

                        default_workers = _os_mod.cpu_count() or 4
                    except Exception:
                        default_workers = 4
                    workers = st.number_input(
                        "Workers",
                        min_value=1,
                        max_value=64,
                        value=int(default_workers),
                        step=1,
                        key=f"admin_fr_workers_{table_for_fr}",
                    )
                else:
                    workers = 1

            app1, app2 = st.columns([1, 1])
            with app1:
                if st.button("Apply to selected", type="secondary"):
                    try:
                        from pdf_utils import (
                            compile_tex_to_pdf as compile_fn,
                        )
                        from pdf_utils import (
                            tsv_to_full_latex_article as to_tex_fn,
                        )
                        from tsv_utils import correct_tsv_file as correct_fn

                        have_tools = True
                    except Exception as e:
                        st.error(f"Import error: {e}")
                        have_tools = False

                    # Prepare tasks
                    tasks = [
                        (str(r["path"]), str(r["new"]))
                        for r in results2
                        if str(r["path"]) in sel_set
                    ]
                    applied = 0
                    logs = []

                    def _apply_one(_p: str, _new: str):
                        _csvp = Path(_p)
                        try:
                            _csvp.write_text(_new, encoding="utf-8")
                            if have_tools:
                                correct_fn(_csvp)
                            if have_tools and auto_compile:
                                lp = to_tex_fn(_csvp)
                                compile_fn(lp)
                            return True, ""
                        except Exception as _e:
                            return False, f"Failed {Path(_p).name}: {_e}"

                    if run_parallel and workers > 1 and tasks:
                        try:
                            from concurrent.futures import ThreadPoolExecutor, as_completed

                            with ThreadPoolExecutor(max_workers=int(workers)) as ex:
                                futs = {
                                    ex.submit(_apply_one, pth, new): (pth, new)
                                    for (pth, new) in tasks
                                }
                                for ft in as_completed(futs):
                                    ok, msg = ft.result()
                                    if ok:
                                        applied += 1
                                    elif msg:
                                        logs.append(msg)
                        except Exception as e:
                            logs.append(f"Parallel execution error: {e}")
                            # fallback sequential
                            for pth, new in tasks:
                                ok, msg = _apply_one(pth, new)
                                if ok:
                                    applied += 1
                                elif msg:
                                    logs.append(msg)
                    else:
                        for pth, new in tasks:
                            ok, msg = _apply_one(pth, new)
                            if ok:
                                applied += 1
                            elif msg:
                                logs.append(msg)

                    if logs:
                        with st.expander("Show errors/logs", expanded=False):
                            st.code("\n".join(logs), language="text")
                    st.success(f"Applied to {applied} files in {table_for_fr}.")
                    st.rerun()
            with app2:
                if st.button("Apply to all", type="secondary"):
                    try:
                        from pdf_utils import (
                            compile_tex_to_pdf as compile_fn,
                        )
                        from pdf_utils import (
                            tsv_to_full_latex_article as to_tex_fn,
                        )
                        from tsv_utils import correct_tsv_file as correct_fn

                        have_tools = True
                    except Exception as e:
                        st.error(f"Import error: {e}")
                        have_tools = False

                    tasks = [(str(r["path"]), str(r["new"])) for r in results2]
                    applied = 0
                    logs = []

                    def _apply_one(_p: str, _new: str):
                        _csvp = Path(_p)
                        try:
                            _csvp.write_text(_new, encoding="utf-8")
                            if have_tools:
                                correct_fn(_csvp)
                            if have_tools and auto_compile:
                                lp = to_tex_fn(_csvp)
                                compile_fn(lp)
                            return True, ""
                        except Exception as _e:
                            return False, f"Failed {Path(_p).name}: {_e}"

                    if run_parallel and workers > 1 and tasks:
                        try:
                            from concurrent.futures import ThreadPoolExecutor, as_completed

                            with ThreadPoolExecutor(max_workers=int(workers)) as ex:
                                futs = {
                                    ex.submit(_apply_one, pth, new): (pth, new)
                                    for (pth, new) in tasks
                                }
                                for ft in as_completed(futs):
                                    ok, msg = ft.result()
                                    if ok:
                                        applied += 1
                                    elif msg:
                                        logs.append(msg)
                        except Exception as e:
                            logs.append(f"Parallel execution error: {e}")
                            for pth, new in tasks:
                                ok, msg = _apply_one(pth, new)
                                if ok:
                                    applied += 1
                                elif msg:
                                    logs.append(msg)
                    else:
                        for pth, new in tasks:
                            ok, msg = _apply_one(pth, new)
                            if ok:
                                applied += 1
                            elif msg:
                                logs.append(msg)

                    if logs:
                        with st.expander("Show errors/logs", expanded=False):
                            st.code("\n".join(logs), language="text")
                    st.success(f"Applied to {applied} files in {table_for_fr}.")
                    st.rerun()

        st.markdown("---")
        st.markdown("**Quick Fix: Replace .OH → ^.OH in Reaction equation (entire table)**")
        qf_col1, qf_col2 = st.columns([1, 1])
        with qf_col1:
            if st.button("Dry scan quick fix"):
                try:
                    from config import get_table_paths as _get_paths

                    IMG_DIR, PDF_DIR, TSV_DIR, _ = _get_paths(table_for_fr)
                except Exception as e:
                    st.error(f"Path error: {e}")
                    TSV_DIR = None
                results_qf: list[dict[str, object]] = []
                if TSV_DIR:
                    images = sorted([p.name for p in IMG_DIR.glob("*.png")])
                    for img in images:
                        stem = Path(img).stem
                        csv_p = TSV_DIR / f"{stem}.csv"
                        if not csv_p.exists():
                            continue
                        try:
                            text_i = csv_p.read_text(encoding="utf-8")
                        except Exception:
                            continue
                        matches = 0
                        new_lines_qf: list[str] = []
                        for ln in text_i.split("\n"):
                            if not ln:
                                new_lines_qf.append(ln)
                                continue
                            cols = ln.split("\t")
                            if len(cols) >= 3:
                                old = cols[2]
                                cnt = old.count(".OH")
                                if cnt:
                                    matches += cnt
                                    cols[2] = old.replace(".OH", "^.OH")
                                    ln = "\t".join(cols)
                            new_lines_qf.append(ln)
                        if matches > 0:
                            results_qf.append(
                                {
                                    "path": str(csv_p),
                                    "file": csv_p.name,
                                    "matches": matches,
                                    "new": "\n".join(new_lines_qf),
                                }
                            )
                st.session_state[res_key] = results_qf
                st.session_state[sel_key] = {r["path"] for r in results_qf}
        with qf_col2:
            if st.button("Apply quick fix to all"):
                res_qf2 = list(st.session_state.get(res_key, []))
                if not res_qf2:
                    st.info("No scanned results. Click 'Dry scan quick fix' first.")
                else:
                    try:
                        from pdf_utils import (
                            compile_tex_to_pdf as compile_fn,
                        )
                        from pdf_utils import (
                            tsv_to_full_latex_article as to_tex_fn,
                        )
                        from tsv_utils import correct_tsv_file as correct_fn

                        have_tools = True
                    except Exception as e:
                        st.error(f"Import error: {e}")
                        have_tools = False

                    # Parallel options reuse
                    run_parallel = st.session_state.get(f"admin_fr_parallel_{table_for_fr}", True)
                    workers = int(st.session_state.get(f"admin_fr_workers_{table_for_fr}", 4))

                    tasks = [(str(r["path"]), str(r["new"])) for r in res_qf2]
                    applied = 0
                    logs = []

                    def _apply_one(_p: str, _new: str):
                        _csvp = Path(_p)
                        try:
                            _csvp.write_text(_new, encoding="utf-8")
                            if have_tools:
                                correct_fn(_csvp)
                            if have_tools and auto_compile:
                                lp = to_tex_fn(_csvp)
                                compile_fn(lp)
                            return True, ""
                        except Exception as _e:
                            return False, f"Failed {Path(_p).name}: {_e}"

                    if run_parallel and workers > 1 and tasks:
                        try:
                            from concurrent.futures import ThreadPoolExecutor, as_completed

                            with ThreadPoolExecutor(max_workers=int(workers)) as ex:
                                futs = {
                                    ex.submit(_apply_one, pth, new): (pth, new)
                                    for (pth, new) in tasks
                                }
                                for ft in as_completed(futs):
                                    ok, msg = ft.result()
                                    if ok:
                                        applied += 1
                                    elif msg:
                                        logs.append(msg)
                        except Exception as e:
                            logs.append(f"Parallel execution error: {e}")
                            for pth, new in tasks:
                                ok, msg = _apply_one(pth, new)
                                if ok:
                                    applied += 1
                                elif msg:
                                    logs.append(msg)
                    else:
                        for pth, new in tasks:
                            ok, msg = _apply_one(pth, new)
                            if ok:
                                applied += 1
                            elif msg:
                                logs.append(msg)

                    if logs:
                        with st.expander("Show errors/logs", expanded=False):
                            st.code("\n".join(logs), language="text")
                    st.success(f"Quick fix applied to {applied} files in {table_for_fr}.")

    # Export section - placed before delete for better workflow
    st.subheader("📥 Export Table Data")

    # Get available tables
    available_tables = []
    if os.path.exists(BASE_DIR):
        available_tables = [
            d
            for d in sorted(os.listdir(BASE_DIR))
            if os.path.isdir(os.path.join(BASE_DIR, d)) and not d.startswith(".")
        ]

    if not available_tables:
        st.info("No tables available to export. Upload data first.")
    else:
        # Display table information
        st.write(f"📋 **Available tables ({len(available_tables)}):**")

        table_infos = []
        for table in available_tables:
            table_path = Path(BASE_DIR) / table
            info = get_table_info(table_path)
            table_infos.append(info)

            display_name = f"{info['name']}" + (f" - {info['title']}" if info["title"] else "")
            st.write(
                f"  • **{display_name}** ({format_size(info['size'])}, {info['file_count']} files)"
            )

        # Table selection for export
        selected_export_tables = st.multiselect(
            "Select tables to export",
            options=available_tables,
            help="Select one or more tables to download as a ZIP file",
        )

        if selected_export_tables:
            # Options: CSV-only or full table content
            csv_only = st.checkbox(
                "Include only CSV files (recommended for syncing to local)",
                value=True,
                help="When enabled, exports only CSV files (and their parent folders) to keep the ZIP small. Disable to export images/latex too.",
            )

            # Show what will be exported
            st.write("**Export will include:**")
            total_size = 0
            total_files = 0
            for table in selected_export_tables:
                info = next(t for t in table_infos if t["name"] == table)
                total_size += info["size"]
                total_files += info["file_count"]
                display_name = table + (f" - {info['title']}" if info["title"] else "")
                st.write(
                    f"  • {display_name} ({format_size(info['size'])}, {info['file_count']} files)"
                )

            st.write(
                f"**Total (full table sizes shown above; CSV-only ZIP will be smaller):** {format_size(total_size)}, {total_files} files"
            )

            # Export button
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            suffix = "csv_only" if csv_only else "full"
            filename = f"table_export_{suffix}_{timestamp}.zip"

            if st.button("📦 Create Export ZIP", type="primary"):
                try:
                    with st.spinner("Creating export ZIP..."):
                        zip_data = create_zip_from_tables(
                            Path(BASE_DIR), selected_export_tables, csv_only=csv_only
                        )

                    st.success(
                        f"✅ Export ZIP created successfully! ({format_size(len(zip_data))})"
                    )

                    # Download button
                    st.download_button(
                        label="⬇️ Download Export ZIP",
                        data=zip_data,
                        file_name=filename,
                        mime="application/zip",
                        help=f"Download {len(selected_export_tables)} selected tables ({'CSV-only' if csv_only else 'full content'})",
                    )

                except Exception as e:
                    st.error(f"❌ Error creating export: {str(e)}")

    st.divider()

    # Delete specific folders section
    st.subheader("🧹 Delete Specific Folders")
    try:
        subdirs_for_delete = [
            d
            for d in os.listdir(BASE_DIR)
            if os.path.isdir(os.path.join(BASE_DIR, d)) and not d.startswith(".")
        ]
    except Exception:
        subdirs_for_delete = []

    if not subdirs_for_delete:
        st.caption("No folders available to delete.")
    else:
        selected_folders = st.multiselect(
            "Select folders to delete (permanent)",
            options=sorted(subdirs_for_delete),
            help="Deletes selected folders from the data directory permanently.",
        )

        if st.button("🗑️ Delete selected folders", type="secondary", disabled=not selected_folders):
            any_deleted = False
            messages: list[str] = []
            for folder in selected_folders:
                ok, msg = delete_folder_in_base(folder)
                messages.append(f"{folder}: {'✅' if ok else '❌'} {msg}")
                any_deleted = any_deleted or ok

            if any_deleted:
                st.success("Some folders were deleted. Refreshing...")
                for m in messages:
                    st.write(m)
                st.rerun()
            else:
                st.warning("No folders were deleted.")
                for m in messages:
                    st.write(m)

    st.divider()

    # Upload section
    st.subheader("📤 Upload Data ZIP File")

    st.info("""
    **Upload Instructions:**
    - Upload a ZIP file containing your table data directories
    - The ZIP should contain folders like `Table5/`, `Table6/`, etc.
    - Each table folder can optionally contain an `info.txt` file with format: `TITLE: Name of Table`
    - If no `info.txt` file exists, the table name will be displayed without a title
    - Maximum file size: 500 MB
    - ⚠️ **Warning**: This will replace existing data in the target directory
    """)

    uploaded_file = st.file_uploader(
        "Choose a ZIP file containing table data",
        type=["zip"],
        help="Select a ZIP file with your data contents",
    )

    if uploaded_file is not None:
        file_size_mb = len(uploaded_file.getvalue()) / (1024 * 1024)
        st.info(f"📦 **Uploaded file**: `{uploaded_file.name}` ({file_size_mb:.1f} MB)")

        # Show contents of ZIP file
        try:
            with zipfile.ZipFile(uploaded_file) as zf:
                file_list = [f for f in zf.namelist() if not f.endswith("/")]
                st.write(f"📋 **ZIP contains {len(file_list)} files**")

                # Show first few files as preview
                if file_list:
                    st.write("**Preview (first 10 files):**")
                    for filename in file_list[:10]:
                        st.write(f"  • `{filename}`")
                    if len(file_list) > 10:
                        st.write(f"  ... and {len(file_list) - 10} more files")

        except zipfile.BadZipFile:
            st.error("❌ Invalid ZIP file. Please upload a valid ZIP archive.")
            return
        except Exception as e:
            st.error(f"❌ Error reading ZIP file: {str(e)}")
            return

        # Confirmation and extraction
        st.divider()

        col1, col2 = st.columns([1, 1])

        with col1:
            if st.button("🗑️ Clear Existing Data First", type="secondary"):
                try:
                    if os.path.exists(BASE_DIR):
                        # Remove all contents but keep the directory
                        for item in os.listdir(BASE_DIR):
                            item_path = os.path.join(BASE_DIR, item)
                            if os.path.isdir(item_path):
                                shutil.rmtree(item_path)
                            else:
                                os.remove(item_path)
                        st.success("✅ Existing data cleared successfully!")
                        st.rerun()
                    else:
                        st.info("ℹ️ Directory was already empty")
                except Exception as e:
                    st.error(f"❌ Error clearing data: {str(e)}")

        with col2:
            if st.button("🚀 Extract ZIP to Data Directory", type="primary"):
                try:
                    with st.spinner("Extracting ZIP file..."):
                        # Simple: just extract directly to BASE_DIR
                        extract_zip_safely(uploaded_file.getvalue(), str(BASE_DIR))
                        st.info("📁 ZIP contents extracted directly to data directory")

                    st.success("✅ **Data uploaded and extracted successfully!**")
                    st.balloons()

                    # Show updated directory status
                    new_size = get_directory_size(BASE_DIR)
                    st.metric("New Directory Size", format_size(new_size))

                    # Suggest next steps
                    st.info(
                        "💡 **Next steps:** Navigate to other pages to verify your data is accessible."
                    )

                    # Auto-refresh the page to show new status
                    st.rerun()

                except ValueError as e:
                    st.error(f"❌ Security error: {str(e)}")
                except zipfile.BadZipFile:
                    st.error("❌ Invalid ZIP file format")
                except Exception as e:
                    st.error(f"❌ Error extracting ZIP file: {str(e)}")

    # Footer with additional info
    st.divider()
    st.caption("""
    🔒 **Security Note**: This upload/export feature is restricted to administrators only.
    All uploaded files are validated to prevent directory traversal attacks.
    Export creates complete backups of selected table directories.
    """)


if __name__ == "__main__":
    main()
