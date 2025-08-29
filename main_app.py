import math
import sys
import time
from pathlib import Path
from typing import Any

import streamlit as st

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from auth_db import (
    auth_db,
    check_authentication,
    logout_user,
    show_user_profile_page,
)
from reactions_db import (
    ensure_db,
    get_reaction_with_measurements,
    get_validation_meta_by_source,
    get_validation_statistics,
    list_reactions,
    search_reactions,
)
from validate_embedded import show_validation_interface

st.set_page_config(page_title="Radical Reactions Platform (Buxton)", layout="wide")


# --- Simple activity logger ---
def _init_activity_log():
    if "activity_log" not in st.session_state:
        st.session_state.activity_log = []


def log_event(msg: str):
    try:
        print(f"[UI] {msg}")
    except Exception:
        pass
    _init_activity_log()
    st.session_state.activity_log.append(msg)
    # keep last 100
    if len(st.session_state.activity_log) > 100:
        st.session_state.activity_log = st.session_state.activity_log[-100:]


# Check authentication status
print("[MAIN PAGE] Starting main page load")
print(f"[MAIN PAGE] Session state page_mode: {st.session_state.get('page_mode', 'main')}")

# Volume persistence diagnostics
import os

from config import BASE_DIR
from reactions_db import DB_PATH

print(f"[VOLUME DEBUG] BASE_DIR resolved to: {BASE_DIR}")
print(f"[VOLUME DEBUG] DB_PATH resolved to: {DB_PATH}")
try:
    from auth_db import auth_db as _adb

    print(f"[VOLUME DEBUG] USERS_DB resolved to: {_adb.db_path}")
except Exception as _e:
    print(f"[VOLUME DEBUG] USERS_DB path unavailable: {_e}")
print(f"[VOLUME DEBUG] /data exists: {os.path.exists('/data')}")
print(f"[VOLUME DEBUG] BASE_DIR exists: {BASE_DIR.exists()}")
print(f"[VOLUME DEBUG] DB file exists: {DB_PATH.exists()}")
if DB_PATH.exists():
    print(f"[VOLUME DEBUG] DB file size: {DB_PATH.stat().st_size} bytes")
    print(f"[VOLUME DEBUG] DB file modified: {DB_PATH.stat().st_mtime}")
print(
    f"[VOLUME DEBUG] /data contents: {list(Path('/data').glob('*')) if Path('/data').exists() else 'N/A'}"
)

current_user = check_authentication()
print(f"[MAIN PAGE] Current user from check_authentication(): {current_user}")

# === CHECK IF WE'RE IN VALIDATION MODE ===
if st.session_state.get("page_mode") == "validate":
    print("[MAIN PAGE] Entering validation mode")

    # Check authentication for validation page
    if not current_user:
        st.error("❌ **Authentication Required for Validation**")
        st.info("Your session may have expired. Please log in again.")
        st.session_state.page_mode = "main"  # Return to main page
        st.rerun()

    # Show validation interface
    show_validation_interface(current_user)
    st.stop()  # Don't show main page content

# === CHECK IF WE'RE IN PROFILE/ADMIN MODE ===
if st.session_state.get("page_mode") == "profile":
    print("[MAIN PAGE] Entering profile/admin mode")
    if not current_user:
        st.error("❌ **Authentication Required**")
        st.info("Your session may have expired. Please log in again.")
        st.session_state.page_mode = "main"
        st.rerun()
    show_user_profile_page()
    st.stop()

# === HEADER WITH LOGIN/LOGOUT ===
header_col1, header_col2 = st.columns([3, 1])

with header_col1:
    st.title("Radical Reactions Platform")
    st.subheader(
        "Digitizing and validating radiation radical reactions from Buxton Critical Review"
    )

with header_col2:
    if current_user:
        st.success(f"👤 Logged in as: **{current_user}**")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("👤 Profile/Admin", type="secondary"):
                log_event("Profile/Admin button clicked")
                st.session_state.page_mode = "profile"
                st.rerun()
        with c2:
            if st.button("🚪 Logout", type="secondary"):
                log_event("Logout button clicked")
                logout_user()
                st.rerun()
    else:
        if st.button("🔐 Login", type="primary"):
            log_event("Open Login form button clicked")
            st.session_state.show_login = True
            st.rerun()

st.markdown("---")

# === LOGIN FORM (if requested) ===
if st.session_state.get("show_login", False) and not current_user:
    st.header("🔐 Login")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_col1, login_col2 = st.columns([1, 1])

        with login_col1:
            submit_button = st.form_submit_button("Login", type="primary")
        with login_col2:
            cancel_button = st.form_submit_button("Cancel")

        if cancel_button:
            log_event("Login form canceled")
            st.session_state.show_login = False
            st.rerun()

        if submit_button:
            if username and password:
                success, message = auth_db.authenticate_user(username, password)
                if success:
                    from auth_db import login_user

                    login_user(username)
                    st.session_state.show_login = False
                    st.success(message)
                    log_event(f"User '{username}' logged in")
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.error("Please enter both username and password")

    st.markdown("---")
    st.markdown("### New User Registration")
    st.markdown(
        "To request a new account, please email **sergey.denisov@universite-paris-saclay.fr** with:"
    )
    st.markdown("- Requested username")
    st.markdown("- Your institutional email")
    st.markdown("- Justification for access")

    st.stop()  # Don't show the rest of the page during login

# === MAIN CONTENT ===
col1, col2 = st.columns([2, 1])
with col1:
    st.markdown(
        """
        This project develops an open platform for radiation radical reactions, initially curated from the Buxton Critical Review of Rate Constants for Reactions of Hydrated Electrons, Hydrogen Atoms and Hydroxyl Radicals in Aqueous Solution (DOI: 10.1063/1.555805). The workflow is:

        - Extract and correct TSV files from table images
        - Generate LaTeX/PDF for human-readable rendering
        - Validate entries collaboratively
        - Publish a searchable database of reactions
        """
    )

with col2:
    if current_user:
        st.success(
            "✅ You are logged in! You can access the validation workflow to "
            "validate OCR results and contribute to the database."
        )
        # Use session-state based navigation to preserve authentication
        st.markdown(
            """
            ### 🔍 Access Validation Workflow
            """
        )

        if st.button("🔍 Go to Validation Page", type="primary", use_container_width=True):
            print("[MAIN PAGE] User clicked validation button, setting page_mode to 'validate'")
            log_event("Navigate to Validation Page button clicked")
            st.session_state.page_mode = "validate"
            st.rerun()
    else:
        st.info(
            "👆 Login above to access the validation workflow. "
            "Public users can search the database below."
        )

st.markdown("---")

# Optional maintenance pause to prevent DB access during swaps
_db_paused = bool(st.session_state.get("db_paused", False))
if _db_paused:
    con = None
else:
    con = ensure_db()

# === VALIDATION STATISTICS (for all users) ===
st.subheader("📊 Project Statistics")

if _db_paused:
    st.info("Statistics are temporarily unavailable during maintenance.")
else:
    try:
        assert con is not None, "Database connection is None"
        stats = get_validation_statistics(con)

        # Global overview
        global_stats = stats["global"]
        db_stats = stats["database"]

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                "Total Images",
                global_stats["total_images"],
                help="Total OCR images across all tables",
            )
        with col2:
            st.metric(
                "Validated Images",
                global_stats["validated_images"],
                help="Images that have been validated by experts",
            )
        with col3:
            st.metric(
                "Database Reactions",
                db_stats["validated_reactions"],
                help="Validated reactions available in the searchable database",
            )
        with col4:
            st.metric(
                "Total Measurements",
                db_stats["total_measurements"],
                help="Individual reaction measurements in the database",
            )

        # Progress bar
        progress_text = f"Validation Progress: {global_stats['validated_images']}/{global_stats['total_images']} images ({global_stats['validation_percentage']:.1f}%)"
        st.caption(progress_text)
        st.progress(global_stats["validation_percentage"] / 100.0)

        # Per-table breakdown
        with st.expander("📋 Detailed Progress by Table", expanded=False):
            table_stats = stats["tables"]
            for table_stat in table_stats:
                table_name = table_stat["table"]
                table_no = table_stat["table_no"]

                # Table category descriptions
                table_descriptions = {
                    5: "Radical-radical reactions",
                    6: "Hydrated electrons in aqueous solution",
                    7: "Hydrogen atoms in aqueous solution",
                    8: "Hydroxyl radicals in aqueous solution",
                    9: "Oxide radical ion in aqueous solution",
                }

                description = table_descriptions.get(table_no, f"Table {table_no}")

                col_name, col_progress, col_numbers = st.columns([2, 2, 1])
                with col_name:
                    st.write(f"**{table_name.upper()}:** {description}")
                with col_progress:
                    if table_stat["total_images"] > 0:
                        progress_val = table_stat["validation_percentage"] / 100.0
                        st.progress(progress_val)
                    else:
                        st.write("No images")
                with col_numbers:
                    st.write(
                        f"{table_stat['validated_images']}/{table_stat['total_images']} ({table_stat['validation_percentage']:.1f}%)"
                    )

    except Exception as e:
        st.error(f"Could not load statistics: {e}")

st.markdown("---")

# Activity log (visible only to superuser)
if current_user == "saldenisov":
    with st.expander("🪵 Activity Log", expanded=False):
        _init_activity_log()
        if st.session_state.activity_log:
            for entry in st.session_state.activity_log[-15:]:
                st.write(f"- {entry}")
        else:
            st.caption("No activity yet")

# === BROWSE + SEARCH TABS ===
browse_tab, search_tab = st.tabs(["📚 Browse Reactions", "🔎 Search Reactions"])

# --- Admin-only tools: Resync from JSON and Fast update ---
if current_user == "saldenisov":
    with st.expander("🛠 Admin Tools", expanded=False):
        st.caption("Admin utilities and statistics for the reactions database.")
        st.warning(
            "These actions will reset reactions.db. Ensure no other process is using the database before running."
        )
        # Pause toggle
        pause_col, _ = st.columns([1, 3])
        with pause_col:
            new_pause = st.checkbox(
                "Pause DB access",
                value=_db_paused,
                help="Prevents UI from opening the DB during maintenance (avoids Windows file locks)",
            )
            if new_pause != _db_paused:
                st.session_state.db_paused = new_pause
                log_event(f"Admin: DB pause set to {new_pause}")
                st.rerun()

        # Single rebuild button - now only imports validated entries
        if st.button(
            "🔄 Rebuild Database from Validated Sources", type="primary", use_container_width=True
        ):
            log_event("Admin: Database rebuild initiated")
            # Engage pause and close our page connection to release locks before swap
            st.session_state.db_paused = True
            try:
                if "con" in locals() and con is not None:
                    con.close()
            except Exception:
                pass
            try:
                from config import BASE_DIR
                from tools.rebuild_db import build_db_offline_fast, swap_live_db

                build_path = BASE_DIR / "reactions_build.db"
                # Build offline using fast path (validated entries only)
                build_db_offline_fast(build_path)
                # Swap into place
                swap_live_db(build_path)
                st.success("Database rebuilt successfully with validated entries only!")
                log_event("Admin: Database rebuild completed (offline swap)")
                st.session_state.db_paused = False
                con = ensure_db()
                st.rerun()
            except Exception as e:
                # If DB is corrupted and locked, attempt legacy retry after brief wait
                msg = str(e)
                if "Failed to remove corrupted DB" in msg or "Could not remove" in msg:
                    log_event(
                        "Admin: Rebuild failed due to locked/corrupted DB; retrying legacy path"
                    )
                    time.sleep(0.5)
                    try:
                        from tools.rebuild_db import rebuild_db_from_validations

                        rebuild_db_from_validations()
                        st.success("Database rebuilt successfully (after retry).")
                        log_event("Admin: Database rebuild completed after retry")
                        st.session_state.db_paused = False
                        con = ensure_db()
                        st.rerun()
                    except Exception as e2:
                        st.error(f"Database rebuild failed after retry: {e2}")
                        log_event(f"Admin: Database rebuild failed after retry: {e2}")
                        st.session_state.db_paused = False
                        try:
                            con = ensure_db()
                        except Exception:
                            pass
                else:
                    st.error(f"Database rebuild failed: {e}")
                    log_event(f"Admin: Database rebuild failed: {e}")
                    st.session_state.db_paused = False
                    # Make sure connection is open even on error
                    try:
                        con = ensure_db()
                    except Exception:
                        pass

        # Batch: TSV -> LaTeX -> PDF for NON-validated reactions
        st.markdown("---")
        st.subheader("🧾 Generate PDFs for Non-validated Reactions")
        st.caption(
            "Scans all tables for images with existing TSV/CSV that are not validated; fixes TSV, regenerates LaTeX, and compiles PDFs."
        )
        # Scope and limits
        try:
            from config import AVAILABLE_TABLES as _ALL_TABLES

            _scope_options = ["All tables"] + _ALL_TABLES
        except Exception:
            _scope_options = ["All tables"]
        _selected_scope = st.selectbox(
            "Scope",
            options=_scope_options,
            index=0,
            help="Process all tables or limit to a single table",
        )
        _max_items = st.number_input(
            "Max items to process (0 = no limit)",
            min_value=0,
            value=0,
            step=1,
            help="Use to cap processing for large runs",
        )
        # Execution options
        _dry_run = st.checkbox("Dry run (list items only, no compilation)", value=False)
        _run_parallel = st.checkbox("Run in parallel", value=True)
        _workers = None
        if _run_parallel:
            try:
                import os as _os_mod

                default_workers = _os_mod.cpu_count() or 4
            except Exception:
                default_workers = 4
            _workers = st.number_input(
                "Workers (parallel xelatex processes)",
                min_value=1,
                max_value=64,
                value=int(default_workers),
                step=1,
                help="Use up to CPU cores; reduce if IO/memory constrained",
            )

        if st.button(
            "🧾 Run TSV → LaTeX → PDF for Non-validated", type="secondary", use_container_width=True
        ):
            try:
                from config import AVAILABLE_TABLES, get_table_paths
                from pdf_utils import compile_tex_to_pdf, tsv_to_full_latex_article
                from reactions_db import ensure_db, get_validation_meta_by_source
                from tsv_utils import correct_tsv_file

                con_local = ensure_db()

                # Determine tables to scan based on scope
                tables_to_scan = (
                    AVAILABLE_TABLES if _selected_scope == "All tables" else [str(_selected_scope)]
                )

                # Discover all non-validated items with a TSV/CSV present
                to_process: list[tuple[str, str, Path]] = []
                missing_sources = 0
                for table in tables_to_scan:
                    IMG_DIR, PDF_DIR, TSV_DIR, _ = get_table_paths(table)
                    images = sorted([p.name for p in IMG_DIR.glob("*.png")])
                    for img in images:
                        stem = Path(img).stem
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
                        if not bool(meta.get("validated", False)):
                            to_process.append((table, img, source))

                # Apply max limit if requested
                if _max_items and int(_max_items) > 0:
                    to_process = to_process[: int(_max_items)]

                total = len(to_process)
                scope_label = (
                    "all tables" if _selected_scope == "All tables" else f"{_selected_scope}"
                )

                if total == 0:
                    st.info("No unvalidated reactions with TSV/CSV found for the selected scope.")
                else:
                    if _dry_run:
                        st.info(
                            f"[Dry run] Scope: {scope_label}. Would process {total} items (missing TSV/CSV encountered: {missing_sources})."
                        )
                        if to_process:
                            with st.expander("Show items to process", expanded=False):
                                for table, img, src in to_process:
                                    st.write(f"{table}/{img}: {src}")
                    else:
                        st.write(
                            f"Scope: {scope_label}. Found {total} unvalidated items to process "
                            f"(missing TSV/CSV encountered: {missing_sources})."
                        )
                        progress = st.progress(0.0)
                        ok = 0
                        failed = 0
                        logs: list[str] = []
                        pdfs: list[tuple[str, str, str]] = []  # (table, img, pdf_path)

                        def _run_one_compile(src_path: Path):
                            try:
                                # 1) Correct TSV content in-place
                                correct_tsv_file(src_path)
                                # 2) Generate LaTeX
                                latex_path = tsv_to_full_latex_article(src_path)
                                # 3) Compile to PDF
                                rc, out = compile_tex_to_pdf(latex_path)
                                if rc == 0:
                                    pdf_path = str(latex_path.parent / (latex_path.stem + ".pdf"))
                                    return True, "", pdf_path
                                else:
                                    tail = out[-4000:] if isinstance(out, str) else str(out)
                                    return False, f"LaTeX failed (exit {rc}).\n{tail}", None
                            except Exception as e:
                                return False, f"Error: {e}", None

                        if _run_parallel:
                            try:
                                from concurrent.futures import ThreadPoolExecutor, as_completed
                            except Exception:
                                ThreadPoolExecutor = None  # type: ignore
                                as_completed = None  # type: ignore
                            if ThreadPoolExecutor is None:
                                st.warning(
                                    "Parallel module unavailable; falling back to sequential execution."
                                )
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
                            else:
                                workers = int(_workers or 4)
                                with ThreadPoolExecutor(max_workers=workers) as ex:
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
                                f"Completed: {ok}/{total} PDFs generated successfully. Missing TSV/CSV encountered: {missing_sources}."
                            )
                        else:
                            st.warning(
                                f"Completed with errors: success={ok}, failed={failed}, total={total}. Missing TSV/CSV encountered: {missing_sources}."
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
        st.subheader("⚠️ Advanced Operations")

        # Sync DB to JSON files with warning
        st.markdown("**Overwrite JSON Files from Database**")
        st.warning(
            "⚠️ **IRREVERSIBLE OPERATION**: This will overwrite all validation_db.json files "
            "with current database validation state. Any manual edits to JSON files will be lost permanently."
        )

        # Two-step confirmation for sync
        sync_confirmed = st.checkbox(
            "I understand this will permanently overwrite all validation_db.json files",
            key="sync_confirmation",
        )

        if st.button(
            "🔄 Overwrite JSON Files from Database",
            type="secondary",
            disabled=not sync_confirmed,
            use_container_width=True,
        ):
            log_event("Admin: Sync DB to JSON initiated")
            try:
                from tools.rebuild_db import sync_db_validation_to_json_files

                sync_db_validation_to_json_files()
                st.success("✅ Successfully synced database validation state to JSON files!")
                log_event("Admin: Sync DB to JSON completed")
            except Exception as e:
                st.error(f"Sync failed: {e}")
                log_event(f"Admin: Sync DB to JSON failed: {e}")

        st.info(
            "ℹ️ **How validation works:**\n"
            "- Use the validation interface to mark reactions as validated\n"
            "- Validation status is stored in the database in real-time\n"
            "- Rebuild database reads from validation_db.json files on disk\n"
            "- Export JSON files from validation interface for backup\n"
            "- Use 'Overwrite JSON Files' only if you need JSON files to match current database state"
        )

with browse_tab:
    if st.session_state.get("db_paused", False):
        st.info("DB access is paused for maintenance. Resume in Admin Tools to browse.")
    else:
        left, right = st.columns([1.2, 2])
        with left:
            name_filter = st.text_input("Filter by name/formula", placeholder="type to filter...")
            assert con is not None, "Database connection is None"
            rows_all = list_reactions(
                con, name_filter=name_filter or None, limit=2000, validated_only=True
            )
            if not rows_all:
                st.info("No validated reactions yet.")
            else:
                # Pagination setup
                PAGE_SIZE = 15
                total = len(rows_all)
                total_pages = max(1, math.ceil(total / PAGE_SIZE))
                # Reset page when filter changes
                if st.session_state.get("browse_last_filter") != (name_filter or ""):
                    st.session_state.browse_page = 0
                    st.session_state.browse_last_filter = name_filter or ""
                page = int(st.session_state.get("browse_page", 0))
                page = max(0, min(page, total_pages - 1))
                start = page * PAGE_SIZE
                end = min(start + PAGE_SIZE, total)
                page_rows = rows_all[start:end]

                # Page controls
                pc1, pc2, pc3 = st.columns([1, 2, 1])
                with pc1:
                    if st.button("◀ Prev", disabled=(page == 0)):
                        log_event("Browse: Prev page")
                        st.session_state.browse_page = max(0, page - 1)
                        st.rerun()
                with pc2:
                    st.write(f"Page {page + 1} / {total_pages}  ")
                with pc3:
                    if st.button("Next ▶", disabled=(page >= total_pages - 1)):
                        log_event("Browse: Next page")
                        st.session_state.browse_page = min(total_pages - 1, page + 1)
                        st.rerun()

                # Build a simple list with per-row checkboxes (only Name and Formula)
                if "browse_selected" not in st.session_state:
                    st.session_state.browse_selected = set()
                current_selected = set(st.session_state.get("browse_selected", set()))
                new_selected = set()
                for r in page_rows:
                    rid = int(r["id"])
                    label_name = (r["reaction_name"] or "").strip()
                    label = f"{label_name} | {r['formula_canonical']}".strip(" |")
                    checked = st.checkbox(
                        label, value=(rid in current_selected), key=f"browse_chk_{rid}"
                    )
                    if checked:
                        new_selected.add(rid)
                st.session_state.browse_selected = new_selected
                st.session_state.selected_reaction_ids = sorted(list(new_selected))
        with right:
            sel_ids = st.session_state.get("selected_reaction_ids", [])
            if not sel_ids:
                st.info("Select one or more reactions from the table to view details.")
            else:
                for rid in sel_ids:
                    assert con is not None, "Database connection is None"
                    data = get_reaction_with_measurements(con, rid)
                    rec: Any = data.get("reaction")
                    ms = data.get("measurements", [])
                    if not rec:
                        continue
                    with st.expander(
                        rec["reaction_name"] or rec["formula_canonical"], expanded=False
                    ):
                        st.markdown(f"**Table:** {rec['table_no']} ({rec['table_category']})")
                        st.latex(rec["formula_latex"])
                        st.code(f"Reactants: {rec['reactants']}\nProducts: {rec['products']}")
                        if rec["notes"]:
                            st.markdown(f"**Notes:** {rec['notes']}")
                        # Validator metadata from DB
                        try:
                            src = rec["source_path"] or ""
                            if src:
                                assert con is not None, "Database connection is None"
                                meta = get_validation_meta_by_source(con, src)
                                if meta.get("validated"):
                                    who = meta.get("by") or "unknown"
                                    when = meta.get("at") or "unknown time"
                                    st.markdown(f"**Validated by:** {who}  ")
                                    st.markdown(f"**Validated at:** {when}")
                        except Exception:
                            pass
                        st.markdown("### Measurements")
                        if not ms:
                            st.info("No measurements recorded")
                        else:
                            for m in ms:
                                ref_label = (
                                    m["doi"]
                                    and f"DOI: https://doi.org/{m['doi']}"
                                    or (m["citation_text"] or m["buxton_code"] or "")
                                )
                                st.markdown(
                                    f"- pH: {m['pH'] or '-'}; rate: {m['rate_value'] or '-'}; method: {m['method'] or '-'}"
                                )
                                if ref_label:
                                    st.markdown(f"  ↳ Reference: {ref_label}")

with search_tab:
    if st.session_state.get("db_paused", False):
        st.info("DB access is paused for maintenance. Resume in Admin Tools to search.")
    else:
        if current_user:
            st.info("🔓 Authenticated Search: full access to DB and advanced filters.")
        else:
            st.info("🌐 Public Search: basic search across reactions DB.")
        query = st.text_input(
            "Search reactions (text or formula)",
            placeholder="e.g. e_aq^- OH•, hydroxyl, O2•-",
            key="search_query",
        )
        max_hits = st.number_input(
            "Max results", min_value=1, max_value=200, value=25, step=1, key="max_hits"
        )
        with st.expander("🔧 Advanced Search Options"):
            table_filter = st.selectbox(
                "Table (category)",
                options=["All", 5, 6, 7, 8, 9],
                key="table_filter",
                format_func=lambda x: {
                    "All": "All",
                    5: "Table5 (radical-radical reactions)",
                    6: "Table6 (hydrated electrons)",
                    7: "Table7 (hydrogen atoms)",
                    8: "Table8 (hydroxyl radicals)",
                    9: "Table9 (oxide radical ion)",
                }[x]
                if x != "All"
                else "All",
            )
        if query:
            table_no = None if table_filter == "All" else int(table_filter)
            try:
                assert con is not None, "Database connection is None"
                rows = search_reactions(con, query, table_no=table_no, limit=int(max_hits))
            except Exception as e:
                st.error(f"DB search error: {e}")
                rows = []
            st.write(f"Found {len(rows)} matches")
            if rows:
                for i, r in enumerate(rows, 1):
                    with st.expander(f"Result {i}: {r['formula_canonical']}"):
                        st.markdown(f"**Table:** {r['table_no']} ({r['table_category']})")
                        if r["reaction_name"]:
                            st.markdown(f"**Name:** {r['reaction_name']}")
                        st.latex(r["formula_latex"])
                        st.code(f"Reactants: {r['reactants']}\nProducts: {r['products']}")
                        if r["notes"]:
                            st.markdown(f"**Notes:** {r['notes']}")
        else:
            st.info("Enter a search term above to find reactions.")
