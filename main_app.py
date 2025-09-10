import json
import math
import sys
from pathlib import Path
from typing import Any

import streamlit as st

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Initialize graceful shutdown handler
try:
    print("[MAIN] Graceful shutdown handler initialized")
except Exception as e:
    print(f"[MAIN] Warning: Could not initialize shutdown handler: {e}")

# Initialize automated backup scheduler
try:
    from backup_scheduler import start_scheduler

    start_scheduler()
    print("[MAIN] Automated backup scheduler started")
except Exception as e:
    print(f"[MAIN] Warning: Could not start backup scheduler: {e}")
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

# Optional PDF rendering support
try:
    import fitz  # PyMuPDF

    HAS_FITZ_MAIN = True
except Exception:
    fitz = None
    HAS_FITZ_MAIN = False

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

from config import BASE_DIR, get_table_paths
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

# One-time initial scan to ensure PNG previews exist for PDFs on Railway
try:
    import threading as _th

    from config import get_data_dir as _get_data_dir
    from pdf_preview import ensure_png_up_to_date

    def _start_initial_pdf_preview_scan():
        try:
            base_dir = _get_data_dir()
        except Exception:
            base_dir = Path("/data")
        if not (Path("/data").exists() and base_dir.exists()):
            print(
                f"[MAIN] Skipping initial PDF preview scan (not container or /data missing): base_dir={base_dir}"
            )
            return

        def _scan():
            try:
                count = 0
                for pdf in base_dir.rglob("latex/*.pdf"):
                    try:
                        ensure_png_up_to_date(pdf)
                        count += 1
                    except Exception as e:
                        print(f"[MAIN] Preview update failed for {pdf}: {e}")
                print(f"[MAIN] Initial PDF preview scan complete: {count} PDFs processed")
            except Exception as e:
                print(f"[MAIN] Initial PDF preview scan error: {e}")

        t = _th.Thread(target=_scan, daemon=True)
        t.start()
        print("[MAIN] Initial PDF preview scan started in background")

    # Guard to run only once per container process (Streamlit re-runs the script)
    import os as _os

    if _os.environ.get("RAD_PDF_PREVIEW_SCAN_STARTED") != "1":
        _os.environ["RAD_PDF_PREVIEW_SCAN_STARTED"] = "1"
        _start_initial_pdf_preview_scan()
    else:
        print("[MAIN] Initial PDF preview scan already started (guarded)")
except Exception as e:
    print(f"[MAIN] Warning: Could not start initial PDF preview scan: {e}")

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

                        # Render compiled PDF (as PNG) if available, above validation info
                        try:
                            # sqlite3.Row does not support .get(); use key access with guards
                            try:
                                _tno_val = rec["table_no"]
                            except Exception:
                                _tno_val = None
                            try:
                                _png_val = rec["png_path"]
                            except Exception:
                                _png_val = None
                            tno = int(_tno_val) if _tno_val is not None else None
                            png_path = str(_png_val) if _png_val else ""
                            stem = Path(png_path).stem if png_path else None
                            if tno and stem:
                                IMAGE_DIR, PDF_DIR, TSV_DIR, _ = get_table_paths(f"table{tno}")
                                possible_pdf_paths = [
                                    PDF_DIR / f"{stem}.pdf",
                                    TSV_DIR / "latex" / f"{stem}.pdf",
                                ]
                                for _pdf in possible_pdf_paths:
                                    if _pdf.exists():
                                        if HAS_FITZ_MAIN:
                                            try:
                                                doc = fitz.open(_pdf)
                                                pix = doc.load_page(0).get_pixmap(
                                                    matrix=fitz.Matrix(2.5, 2.5)
                                                )
                                                st.image(
                                                    pix.tobytes(output="png"),
                                                    use_container_width=True,
                                                    caption=f"PDF: {_pdf.name}",
                                                )
                                            except Exception as _e:
                                                st.warning(
                                                    f"Could not render PDF {_pdf.name}: {_e}"
                                                )
                                        else:
                                            st.info(
                                                "PDF preview unavailable: PyMuPDF not installed on server"
                                            )
                                        break
                        except Exception as _e:
                            st.caption(f"PDF preview error: {_e}")

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

                        # Admin/non-admin actions
                        try:
                            from auth_db import auth_db as _adb

                            is_admin = bool(_adb.is_admin(current_user)) if current_user else False
                        except Exception:
                            is_admin = False

                        # Determine paths for potential TSV editing or reporting
                        try:
                            try:
                                _tno_val = rec["table_no"]
                            except Exception:
                                _tno_val = None
                            try:
                                _png_val = rec["png_path"]
                            except Exception:
                                _png_val = None
                            tno = int(_tno_val) if _tno_val is not None else None
                            png_path = str(_png_val) if _png_val else ""
                            stem = Path(png_path).stem if png_path else None
                            src_csv = None
                            if tno and stem:
                                _, _PDF_DIR, TSV_DIR, _ = get_table_paths(f"table{tno}")
                                csv_path = TSV_DIR / f"{stem}.csv"
                                tsv_path = TSV_DIR / f"{stem}.tsv"
                                src_csv = (
                                    csv_path
                                    if csv_path.exists()
                                    else (tsv_path if tsv_path.exists() else None)
                                )
                        except Exception:
                            src_csv = None

                        if is_admin:
                            from pdf_utils import compile_tex_to_pdf, tsv_to_full_latex_article
                            from tsv_utils import correct_tsv_file

                            with st.expander("🛠️ Admin: Edit TSV and Recompile", expanded=False):
                                if not src_csv:
                                    st.info("No CSV/TSV found for this reaction.")
                                else:
                                    # Load current TSV content
                                    try:
                                        cur_text = Path(src_csv).read_text(encoding="utf-8")
                                    except Exception:
                                        cur_text = ""
                                    t_key = f"admin_edit_tsv_{rid}"
                                    edited = st.text_area(
                                        f"Edit TSV for {Path(src_csv).name}",
                                        value=cur_text,
                                        height=220,
                                        key=t_key,
                                    )
                                    cols = st.columns([1, 1])
                                    with cols[0]:
                                        if st.button("💾 Save TSV", key=f"save_tsv_{rid}"):
                                            try:
                                                Path(src_csv).write_text(edited, encoding="utf-8")
                                                st.success("TSV saved.")
                                            except Exception as e:
                                                st.error(f"Save failed: {e}")
                                    with cols[1]:
                                        if st.button(
                                            "🔄 Save + Correct + Recompile",
                                            key=f"recompile_tsv_{rid}",
                                        ):
                                            try:
                                                Path(src_csv).write_text(edited, encoding="utf-8")
                                                _ = correct_tsv_file(Path(src_csv))
                                                lp = tsv_to_full_latex_article(Path(src_csv))
                                                rc, out = compile_tex_to_pdf(lp)
                                                if rc != 0:
                                                    st.error(f"Compilation failed:\n{out}")
                                                else:
                                                    st.success("Recompiled successfully.")
                                                    # Try to render freshly compiled PDF
                                                    try:
                                                        if HAS_FITZ_MAIN:
                                                            pdf_file = lp.parent / (
                                                                lp.stem + ".pdf"
                                                            )
                                                            if pdf_file.exists():
                                                                doc = fitz.open(pdf_file)
                                                                pix = doc.load_page(0).get_pixmap(
                                                                    matrix=fitz.Matrix(2, 2)
                                                                )
                                                                st.image(
                                                                    pix.tobytes(output="png"),
                                                                    use_container_width=True,
                                                                )
                                                    except Exception as e:
                                                        st.warning(f"Preview failed: {e}")
                                            except Exception as e:
                                                st.error(f"Recompile failed: {e}")
                        else:
                            # Non-admin/guest: problem report with lightweight CAPTCHA
                            with st.expander("📝 Report a problem", expanded=False):
                                import random
                                from datetime import datetime

                                from config import BASE_DIR as _BASE

                                email = st.text_input(
                                    "Your email (optional)", key=f"rep_email_{rid}"
                                )
                                comment = st.text_area(
                                    "Describe the problem", height=120, key=f"rep_comment_{rid}"
                                )
                                # Simple math captcha
                                a = random.randint(1, 9)
                                b = random.randint(1, 9)
                                st.caption("Human check: What is the sum?")
                                ans = st.text_input(f"{a} + {b} = ?", key=f"rep_captcha_{rid}")
                                if st.button("Submit report", key=f"rep_submit_{rid}"):
                                    try:
                                        if str(ans).strip() != str(a + b):
                                            st.error("Captcha failed. Please try again.")
                                        elif not comment.strip():
                                            st.error(
                                                "Please add a short description of the problem."
                                            )
                                        else:
                                            report_dir = _BASE / "reports"
                                            report_dir.mkdir(parents=True, exist_ok=True)
                                            ts = datetime.now().isoformat().replace(":", "-")
                                            # Safe extraction from sqlite3.Row
                                            try:
                                                _png = rec["png_path"]
                                            except Exception:
                                                _png = None
                                            try:
                                                _src = rec["source_path"]
                                            except Exception:
                                                _src = None
                                            payload = {
                                                "reaction_id": int(rid),
                                                "png_path": _png,
                                                "source_path": _src,
                                                "user": current_user or "guest",
                                                "email": email or None,
                                                "comment": comment.strip(),
                                                "created_at": datetime.now().isoformat(),
                                            }
                                            (report_dir / f"report_{rid}_{ts}.json").write_text(
                                                json.dumps(payload, indent=2, ensure_ascii=False),
                                                encoding="utf-8",
                                            )
                                            st.success(
                                                "Thank you! Your report has been saved and will be reviewed."
                                            )
                                    except Exception as e:
                                        st.error(f"Could not save report: {e}")

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
