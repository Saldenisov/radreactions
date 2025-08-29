import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st
from PIL import Image, UnidentifiedImageError

from auth_db import show_user_profile_page
from config import AVAILABLE_TABLES, BASE_DIR, get_table_paths
from pdf_utils import compile_tex_to_pdf, tsv_to_full_latex_article
from tsv_utils import correct_tsv_file, tsv_to_visible, visible_to_tsv


def discover_tables(base_dir: Path) -> list[str]:
    """Discover table folders available under base_dir.

    A table folder is any subdirectory of base_dir that is not hidden and contains
    a "sub_tables_images" subdirectory (the expected structure for tables).
    """
    try:
        candidates: list[str] = []
        for p in sorted(base_dir.iterdir()):
            if not p.is_dir():
                continue
            name = p.name
            if name.startswith("."):
                continue
            if (p / "sub_tables_images").exists():
                candidates.append(name)

        def table_key(n: str):
            m = re.match(r"table(\d+)$", n, re.IGNORECASE)
            return int(m.group(1)) if m else n.lower()

        candidates.sort(key=table_key)
        return candidates
    except Exception:
        return []


# Try import fitz (PyMuPDF) - non-fatal, PDF features will be disabled if not available
try:
    import fitz

    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    fitz = None


def is_lfs_pointer(p: Path) -> bool:
    try:
        with p.open("rb") as f:
            head = f.read(200)
        return head.startswith(b"version https://git-lfs.github.com/spec/v1")
    except Exception:
        return False


def show_validation_interface(current_user):
    """Display the validation interface within the main app"""
    print(f"[VALIDATE MODE] Starting validation interface for user: {current_user}")

    # Header with back button
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("🔍 OCR Validation Workflow")
        st.write(f"Logged in as: **{current_user}**")

    with col2:
        if st.button("⬅️ Back to Main", type="secondary"):
            print("[VALIDATE MODE] User clicked back button, returning to main page")
            st.session_state.page_mode = "main"
            st.rerun()

    st.markdown("---")

    # === Sidebar controls and global stats ===
    st.sidebar.title("Validation Controls")

    # === User Information ===
    st.sidebar.markdown(f"### 👤 User: **{current_user}**")
    if st.sidebar.button("👤 My Profile"):
        st.session_state.show_profile = True
        st.rerun()

    # Check if we should show profile page
    if st.session_state.get("show_profile", False):
        st.session_state.show_profile = False
        show_user_profile_page()
        st.stop()

    st.sidebar.markdown("---")

    # Discover available tables dynamically from BASE_DIR; fall back to static list
    discovered = discover_tables(BASE_DIR)
    TABLES = discovered if discovered else AVAILABLE_TABLES

    table_choice = st.sidebar.selectbox(
        "Select Table Folder:",
        options=TABLES,
        index=TABLES.index("table6") if "table6" in TABLES else 0,
    )
    debug_mode = st.sidebar.checkbox(
        "Enable debug logs", value=False, help="Show verbose DB operations for validation"
    )

    # Compute global stats from DB across all tables (optimized with bulk queries)
    def natural_key(s: str):
        # Natural sort: split digits and non-digits so 'img2.png' < 'img10.png'
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

    def table_images(table_name):
        img_dir, _, tsv_dir, _ = get_table_paths(table_name)
        imgs = sorted([p.name for p in img_dir.glob("*.png")], key=natural_key)
        return imgs, tsv_dir

    from reactions_db import (
        DB_PATH as REACTIONS_DB_PATH,
    )
    from reactions_db import (
        ensure_db,
        ensure_reaction_for_png,
        get_validation_meta_by_image,
        get_validation_meta_by_source,
        set_skipped_by_image,
        set_skipped_by_source,
    )

    # Tolerate older deployments missing set_validated_by_image
    _set_validated_by_image: Any | None = None
    try:
        from reactions_db import (
            set_validated_by_image as _set_validated_by_image,
        )
    except Exception:
        pass

    # Reuse single DB connection throughout the validation interface
    # Use the persistent reactions DB (resolved in reactions_db.DB_PATH)
    con = ensure_db()

    # Debug information - show DB path and existence
    try:
        st.sidebar.markdown(f"**DB file:** {REACTIONS_DB_PATH}")
        if REACTIONS_DB_PATH.exists():
            try:
                db_size = REACTIONS_DB_PATH.stat().st_size
                st.sidebar.markdown(f"**DB size:** {db_size:,} bytes")
            except Exception as size_e:
                st.sidebar.markdown(f"**DB size error:** {size_e}")
    except Exception as db_e:
        st.sidebar.error(f"**DB path error:** {db_e}")
        # Fallback: try to show at least the raw path
        try:
            st.sidebar.markdown(f"**Raw DB_PATH:** {repr(REACTIONS_DB_PATH)}")
        except Exception:
            st.sidebar.error("Cannot display DB path information")

    # Compute global stats: by PNG (each PNG is a reaction). CSV presence is optional.
    agg_total = 0
    agg_validated = 0
    for t in TABLES:
        img_dir, _, _, _ = get_table_paths(t)
        imgs = sorted([p.name for p in img_dir.glob("*.png")], key=natural_key)
        agg_total += len(imgs)
        for img in imgs:
            png_path = img_dir / img
            meta = get_validation_meta_by_image(con, str(png_path))
            if meta.get("validated"):
                agg_validated += 1
    agg_percent = (100 * agg_validated / agg_total) if agg_total else 0.0

    st.sidebar.markdown("### **All Tables (Global Stats)**")
    st.sidebar.markdown(f"**Total images:** {agg_total}")
    st.sidebar.markdown(f"**Validated:** {agg_validated} ({agg_percent:.1f}%)")
    st.sidebar.markdown("---")

    # === Paths and DB for current table ===
    IMAGE_DIR, PDF_DIR, TSV_DIR, DB_JSON_PATH = get_table_paths(table_choice)
    # Debug info to help diagnose path issues in deployments
    st.sidebar.markdown(f"BASE_DIR: {BASE_DIR}")
    st.sidebar.markdown(f"IMAGE_DIR exists: {IMAGE_DIR.exists()}")
    st.sidebar.markdown(f"IMAGE_DIR: {IMAGE_DIR}")

    # Determine images directly from directory; compute stats from cached validation data
    images_all = sorted([p.name for p in IMAGE_DIR.glob("*.png")], key=natural_key)

    # Build local cache for current table - prefer PNG-level meta, fallback to source-level meta
    # Clear any existing cache to ensure we always get fresh DB state
    current_table_cache = {}

    def _source_for_image(stem: str):
        csv_file = TSV_DIR / f"{stem}.csv"
        tsv_file = TSV_DIR / f"{stem}.tsv"
        if csv_file.exists():
            return csv_file
        if tsv_file.exists():
            return tsv_file
        return None

    # Force refresh validation cache from DB on each page load
    for img in images_all:
        png_path = IMAGE_DIR / img
        stem = Path(img).stem
        try:
            meta_png = get_validation_meta_by_image(con, str(png_path))
        except Exception:
            meta_png = {"validated": False, "by": None, "at": None}

        # Fallback: if PNG-level says not validated, try source-level meta
        meta = meta_png
        if not bool(meta_png.get("validated", False)):
            src = _source_for_image(stem)
            if src is not None:
                try:
                    meta_src = get_validation_meta_by_source(con, str(src))
                    if bool(meta_src.get("validated", False)):
                        meta = meta_src
                except Exception:
                    pass

        current_table_cache[img] = meta

    def image_meta(name: str):
        return current_table_cache.get(
            name, {"validated": False, "by": None, "at": None, "skipped": False}
        )

    table_total = len(images_all)
    table_validated = sum(
        1 for img in images_all if current_table_cache.get(img, {}).get("validated")
    )
    table_percent = (100 * table_validated / table_total) if table_total else 0.0

    st.sidebar.markdown(f"### **Selected Table: {table_choice}**")
    st.sidebar.markdown(f"**Total images:** {table_total}")
    st.sidebar.markdown(f"**Validated:** {table_validated} ({table_percent:.1f}%)")

    filter_mode = st.sidebar.selectbox(
        "Show images:", options=["All", "Only unvalidated", "Only skipped"], index=0
    )

    if filter_mode == "Only unvalidated":
        images = [
            img
            for img in images_all
            if not image_meta(img).get("validated") and not image_meta(img).get("skipped", False)
        ]
    elif filter_mode == "Only skipped":
        images = [img for img in images_all if image_meta(img).get("skipped", False)]
    else:
        images = images_all

    if not images:
        st.sidebar.warning("No images to display for this filter.")
        st.stop()

    # === Navigation logic with table pagination ===
    PAGE_SIZE = 15
    total_images = len(images)
    total_pages = max(1, (total_images + PAGE_SIZE - 1) // PAGE_SIZE)

    # Initialize page number and selected image
    if "page_num" not in st.session_state or st.session_state.get("table_choice") != table_choice:
        st.session_state.page_num = 0
        st.session_state.table_choice = table_choice

    if "selected_image" not in st.session_state:
        st.session_state.selected_image = images[0] if images else None

    # Ensure page number is valid
    if st.session_state.page_num >= total_pages:
        st.session_state.page_num = max(0, total_pages - 1)

    current_page = st.session_state.page_num
    start_idx = current_page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_images)
    page_images = images[start_idx:end_idx]

    # Page navigation controls
    st.sidebar.markdown("### 📋 Image Selection Table")
    page_col1, page_col2, page_col3 = st.sidebar.columns([1, 2, 1])

    with page_col1:
        if st.button("◀ Prev Page", disabled=(current_page == 0)):
            st.session_state.page_num = max(0, current_page - 1)
            st.rerun()

    with page_col2:
        st.write(f"Page {current_page + 1}/{total_pages}")
        st.write(f"({start_idx + 1}-{end_idx} of {total_images})")

    with page_col3:
        if st.button("Next Page ▶", disabled=(current_page >= total_pages - 1)):
            st.session_state.page_num = min(total_pages - 1, current_page + 1)
            st.rerun()

    # Create table data for current page
    table_data = []
    for img in page_images:
        meta = image_meta(img)
        is_validated = bool(meta.get("validated", False))
        is_skipped = bool(meta.get("skipped", False))

        # Create display name with color coding
        if is_validated:
            display_name = f":green[✓ {img}]"
            status = "✅ Validated"
        elif is_skipped:
            # Streamlit doesn't have :yellow, use :orange as closest
            display_name = f":orange[⏭ {img}]"
            status = "⏭️ Skipped"
        else:
            display_name = f":red[✗ {img}]"
            status = "❌ Not Validated"

        table_data.append(
            {
                "Select": "",
                "Image": display_name,
                "Status": status,
                "Validated By": meta.get("by", "-") if is_validated else "-",
                "Validated At": meta.get("at", "-")[:19]
                if is_validated and meta.get("at")
                else "-",
            }
        )

    # Display the table
    if table_data:
        st.sidebar.markdown("**Click on a row to select an image:**")

        # Build label map for current page
        label_map = {
            page_images[i]: f"{table_data[i]['Image']} | {table_data[i]['Status']}"
            for i in range(len(page_images))
        }

        current_selected = st.session_state.get("selected_image")
        radio_key = f"image_selector_{table_choice}_{filter_mode}_{current_page}"

        # Ensure the radio's state is aligned with current selection before rendering
        if radio_key not in st.session_state or st.session_state.get(radio_key) not in page_images:
            st.session_state[radio_key] = (
                current_selected if current_selected in page_images else page_images[0]
            )

        # Radio button selection with options as image names (stable values)
        selected_img = st.sidebar.radio(
            "Select image:",
            options=page_images,
            format_func=lambda img: label_map.get(img, img),
            key=radio_key,
        )

        if selected_img:
            st.session_state.selected_image = selected_img

    current_image = st.session_state.get("selected_image")
    if not current_image or current_image not in images:
        current_image = images[0] if images else None
        st.session_state.selected_image = current_image

    # === Validation/Skip controls (DB is the source of truth) ===
    # Read current status from DB for the selected image by PNG
    png_path = IMAGE_DIR / current_image

    db_meta_checked = False
    db_meta_skipped = False
    try:
        meta = get_validation_meta_by_image(con, str(png_path))
        db_meta_checked = bool(meta.get("validated", False))
        db_meta_skipped = bool(meta.get("skipped", False))

        # Debug logging for currently selected image (comment out for production)
        # print(f"[DEBUG SELECTED] {current_image} -> DB check: validated={db_meta_checked}, by={meta.get('by')}, at={meta.get('at')}")
        # print(f"[DEBUG SELECTED] Source file: {source_file}")
        # print(f"[DEBUG SELECTED] CSV exists: {csv_file.exists()}")
    except Exception:
        # print(f"[DEBUG SELECTED ERROR] {current_image} -> Exception: {e}")
        db_meta_checked = False

    # Show current status and action buttons instead of a checkbox
    if db_meta_checked:
        status_text = "✅ Validated"
    elif db_meta_skipped:
        status_text = "⏭️ Skipped"
    else:
        status_text = "❌ Not Validated"
    st.sidebar.markdown(f"**Status:** {status_text}")
    act_col1, act_col2, act_col3 = st.sidebar.columns(3)
    do_validate = False
    do_unvalidate = False
    do_skip = False
    do_unskip = False
    with act_col1:
        if st.button("Validate", key=f"btn_validate_{table_choice}_{current_image}"):
            do_validate = True
    with act_col2:
        if st.button("Unvalidate", key=f"btn_unvalidate_{table_choice}_{current_image}"):
            do_unvalidate = True
    with act_col3:
        if not db_meta_skipped:
            if st.button("Skip", key=f"btn_skip_{table_choice}_{current_image}"):
                do_skip = True
        else:
            if st.button("Unskip", key=f"btn_unskip_{table_choice}_{current_image}"):
                do_unskip = True

    desired_state = None
    if do_validate:
        desired_state = True
    elif do_unvalidate:
        desired_state = False

    if desired_state is not None and desired_state != db_meta_checked:
        # Ensure reactions for this source are present; if not, import
        try:
            from reactions_db import ensure_db

            con = ensure_db()

            # Ensure a reaction row exists for this PNG; attempt to import CSV if present
            try:
                tno = (
                    int(table_choice.replace("table", ""))
                    if table_choice.startswith("table")
                    else None
                )
                stem = Path(current_image).stem
                csv_file = TSV_DIR / f"{stem}.csv"
                rid = None
                if tno is not None:
                    if csv_file.exists():
                        try:
                            from import_reactions import import_single_csv_idempotent

                            if debug_mode:
                                st.sidebar.write(f"[DEBUG] Importing measurements from {csv_file}")
                            rcount, mcount = import_single_csv_idempotent(csv_file, tno)
                            if debug_mode:
                                st.sidebar.write(
                                    f"[DEBUG] Import result: reactions={rcount}, measurements={mcount}"
                                )
                            st.sidebar.info(
                                f"Synchronized CSV to DB: {mcount} measurements updated."
                            )
                        except Exception as e:
                            st.sidebar.warning(f"Auto-import failed: {e}")
                    else:
                        # Create a minimal reaction for this PNG
                        try:
                            if debug_mode:
                                st.sidebar.write(
                                    f"[DEBUG] Ensuring minimal reaction for PNG {png_path}"
                                )
                            rid = ensure_reaction_for_png(
                                con,
                                table_no=tno,
                                png_path=str(png_path),
                                csv_path=None,
                            )
                            if debug_mode:
                                st.sidebar.write(
                                    f"[DEBUG] ensure_reaction_for_png -> reaction_id={rid}"
                                )
                        except Exception as e:
                            if debug_mode:
                                st.sidebar.write(f"[DEBUG] ensure_reaction_for_png failed: {e}")
                            pass
            except Exception as e:
                if debug_mode:
                    st.sidebar.write(f"[DEBUG] Pre-validation ensure step failed: {e}")
                pass

            # Update DB validation state with metadata by PNG path
            timestamp = datetime.now().isoformat() if desired_state else None

            # Fallback if older reactions_db lacks set_validated_by_image
            def _fallback_set_validated_by_image(_con, _png, _validated, *, by=None, at_iso=None):
                try:
                    fn = Path(_png).name
                    if _validated:
                        cur = _con.execute(
                            "UPDATE reactions SET validated = 1, validated_by = ?, validated_at = ?, updated_at = datetime('now') WHERE png_path LIKE '%' || ?",
                            (by, at_iso, fn),
                        )
                    else:
                        cur = _con.execute(
                            "UPDATE reactions SET validated = 0, validated_by = NULL, validated_at = NULL, updated_at = datetime('now') WHERE png_path LIKE '%' || ?",
                            (fn,),
                        )
                    _con.commit()
                    return cur.rowcount
                except Exception:
                    return 0

            updated_img = (
                _set_validated_by_image(
                    con,
                    str(png_path),
                    desired_state,
                    by=current_user if desired_state else None,
                    at_iso=timestamp,
                )
                if _set_validated_by_image is not None
                else _fallback_set_validated_by_image(
                    con,
                    str(png_path),
                    desired_state,
                    by=current_user if desired_state else None,
                    at_iso=timestamp,
                )
            )

            # Also update by source if we can resolve it
            updated_src = 0
            try:
                stem2 = Path(current_image).stem
                csv2 = TSV_DIR / f"{stem2}.csv"
                tsv2 = TSV_DIR / f"{stem2}.tsv"
                src2 = csv2 if csv2.exists() else (tsv2 if tsv2.exists() else None)
                if src2 is not None:
                    from reactions_db import set_validated_by_source as _set_by_src

                    updated_src = _set_by_src(
                        con,
                        str(src2),
                        desired_state,
                        by=current_user if desired_state else None,
                        at_iso=timestamp,
                    )
            except Exception as _e:
                pass

            if debug_mode:
                st.sidebar.write(
                    f"[DEBUG] updates -> by_image={updated_img}, by_source={updated_src}"
                )

            updated_count = (updated_img or 0) + (updated_src or 0)

            if updated_count == 0:
                st.sidebar.info("No reactions were updated (already in desired state).")

            # Verify the update worked by re-querying DB and force cache refresh
            try:
                verify_meta = get_validation_meta_by_image(con, str(png_path))
                if debug_mode:
                    st.sidebar.write(f"[DEBUG] Verified meta after update: {verify_meta}")
                # Use the verified meta instead of our constructed meta
                new_meta = verify_meta
            except Exception as e:
                if debug_mode:
                    st.sidebar.write(f"[DEBUG] DB verification failed: {e}")
                # Fallback to constructed meta
                new_meta = {
                    "validated": bool(desired_state),
                    "by": current_user if desired_state else None,
                    "at": timestamp,
                    "skipped": db_meta_skipped,
                }

            # Update local caches with verified DB state
            try:
                current_table_cache[current_image] = new_meta
                if debug_mode:
                    st.sidebar.write(f"[DEBUG] Cache updated for {current_image}: {new_meta}")
            except Exception as e:
                if debug_mode:
                    st.sidebar.write(f"[DEBUG] Cache update failed: {e}")
                pass

            # If validated and in "Only unvalidated", select next
            if desired_state and filter_mode == "Only unvalidated":
                remaining_unvalidated = [
                    img
                    for img in images_all
                    if not current_table_cache.get(img, {}).get("validated", False)
                    and not current_table_cache.get(img, {}).get("skipped", False)
                ]
                if remaining_unvalidated:
                    st.session_state.selected_image = remaining_unvalidated[0]
                    if remaining_unvalidated[0] not in images[start_idx:end_idx]:
                        st.session_state.page_num = 0

            st.rerun()
        except Exception as e:
            st.sidebar.warning(f"Validation sync failed: {e}")

    # Handle Skip/Unskip actions
    if (do_skip and not db_meta_skipped) or (do_unskip and db_meta_skipped):
        try:
            from reactions_db import ensure_db

            con = ensure_db()
            # Ensure reaction exists (import CSV if present; otherwise create minimal row)
            try:
                tno = (
                    int(table_choice.replace("table", ""))
                    if table_choice.startswith("table")
                    else None
                )
                stem = Path(current_image).stem
                csv_file = TSV_DIR / f"{stem}.csv"
                if tno is not None:
                    if csv_file.exists():
                        try:
                            from import_reactions import import_single_csv_idempotent

                            if debug_mode:
                                st.sidebar.write(
                                    f"[DEBUG] Importing measurements from {csv_file} (pre-skip)"
                                )
                            rcount, mcount = import_single_csv_idempotent(csv_file, tno)
                            if debug_mode:
                                st.sidebar.write(
                                    f"[DEBUG] Import result (pre-skip): reactions={rcount}, measurements={mcount}"
                                )
                            # Optional user feedback
                            # st.sidebar.info(f"Synchronized CSV to DB: {mcount} measurements updated.")
                        except Exception as e:
                            st.sidebar.warning(f"Auto-import failed before skip: {e}")
                    else:
                        try:
                            if debug_mode:
                                st.sidebar.write(
                                    f"[DEBUG] Ensuring minimal reaction for PNG {png_path} (pre-skip)"
                                )
                            ensure_reaction_for_png(
                                con,
                                table_no=tno,
                                png_path=str(png_path),
                                csv_path=None,
                            )
                        except Exception:
                            pass
            except Exception:
                pass

            timestamp = datetime.now().isoformat() if do_skip else None
            updated_img = set_skipped_by_image(
                con,
                str(png_path),
                bool(do_skip),
                by=current_user if do_skip else None,
                at_iso=timestamp,
            )
            updated_src = 0
            try:
                stem2 = Path(current_image).stem
                csv2 = TSV_DIR / f"{stem2}.csv"
                tsv2 = TSV_DIR / f"{stem2}.tsv"
                src2 = csv2 if csv2.exists() else (tsv2 if tsv2.exists() else None)
                if src2 is not None:
                    updated_src = set_skipped_by_source(
                        con,
                        str(src2),
                        bool(do_skip),
                        by=current_user if do_skip else None,
                        at_iso=timestamp,
                    )
            except Exception:
                pass

            try:
                verify_meta = get_validation_meta_by_image(con, str(png_path))
                new_meta = verify_meta
            except Exception:
                new_meta = {
                    "validated": db_meta_checked,
                    "by": meta.get("by"),
                    "at": meta.get("at"),
                    "skipped": bool(do_skip),
                }
            current_table_cache[current_image] = new_meta

            # Adjust selection for filters
            if do_skip and filter_mode == "Only unvalidated":
                remaining_unvalidated = [
                    img
                    for img in images_all
                    if not current_table_cache.get(img, {}).get("validated", False)
                    and not current_table_cache.get(img, {}).get("skipped", False)
                ]
                if remaining_unvalidated:
                    st.session_state.selected_image = remaining_unvalidated[0]
                    if remaining_unvalidated[0] not in images[start_idx:end_idx]:
                        st.session_state.page_num = 0
            if do_unskip and filter_mode == "Only skipped":
                remaining_skipped = [
                    img
                    for img in images_all
                    if current_table_cache.get(img, {}).get("skipped", False)
                ]
                if remaining_skipped:
                    st.session_state.selected_image = remaining_skipped[0]
                    if remaining_skipped[0] not in images[start_idx:end_idx]:
                        st.session_state.page_num = 0

            st.rerun()
        except Exception as e:
            st.sidebar.warning(f"Skip sync failed: {e}")

    # === Download Section ===
    st.sidebar.markdown("---")
    st.sidebar.markdown("### **📥 Export Validation JSON (from DB)**")

    # Export current table validation map derived from DB
    if st.sidebar.button(f"Export {table_choice} validation JSON"):
        validation_map = {}
        for img in images_all:
            meta = image_meta(img)
            validation_map[img] = {
                "validated": bool(meta.get("validated")),
                "by": meta.get("by"),
                "at": meta.get("at"),
            }
        download_data = {
            "table_name": table_choice,
            "export_timestamp": datetime.now().isoformat(),
            "total_images": table_total,
            "validated_images": table_validated,
            "validation_percentage": table_percent,
            "validation_data": validation_map,
        }
        json_str = json.dumps(download_data, indent=2, ensure_ascii=False)
        st.sidebar.download_button(
            label=f"💾 {table_choice}_validation_db.json",
            data=json_str,
            file_name=f"{table_choice}_validation_db.json",
            mime="application/json",
            key=f"download_{table_choice}",
        )

    # Export all tables validation data from DB
    if st.sidebar.button("Export all tables validation JSON"):
        all_tables_data: dict[str, object] = {
            "export_timestamp": datetime.now().isoformat(),
            "global_stats": {
                "total_images": agg_total,
                "validated_images": agg_validated,
                "validation_percentage": agg_percent,
            },
        }
        tables: dict[str, object] = {}
        for table in TABLES:
            img_dir, _, tsv_dir, _ = get_table_paths(table)
            imgs = sorted([p.name for p in img_dir.glob("*.png")])
            t_total = len(imgs)
            val_map: dict[str, dict[str, object]] = {}
            t_valid = 0
            for img in imgs:
                stem = Path(img).stem
                src_csv = tsv_dir / f"{stem}.csv"
                src_tsv = tsv_dir / f"{stem}.tsv"
                source_file = (
                    str(src_csv if src_csv.exists() else src_tsv)
                    if (src_csv.exists() or src_tsv.exists())
                    else None
                )
                meta = (
                    get_validation_meta_by_source(con, source_file)
                    if source_file
                    else {"validated": False, "by": None, "at": None}
                )
                val_map[img] = {
                    "validated": bool(meta.get("validated")),
                    "by": meta.get("by"),
                    "at": meta.get("at"),
                }
                if bool(val_map[img]["validated"]):
                    t_valid += 1
            tables[table] = {
                "total_images": t_total,
                "validated_images": t_valid,
                "validation_percentage": (100 * t_valid / t_total) if t_total else 0.0,
                "validation_data": val_map,
            }
        all_tables_data["tables"] = tables
        json_str = json.dumps(all_tables_data, indent=2, ensure_ascii=False)
        st.sidebar.download_button(
            label="💾 all_tables_validation_data.json",
            data=json_str,
            file_name="all_tables_validation_data.json",
            mime="application/json",
            key="download_all_tables",
        )

    # === Main Page Tabs ===
    tab1, tab2, tab3 = st.tabs(["Image", "TSV", "LaTeX"])

    # === IMAGE TAB ===
    with tab1:
        st.header("Image Preview")
        img_path = IMAGE_DIR / current_image
        if img_path.exists():
            try:
                st.image(Image.open(img_path), use_container_width=True)
            except UnidentifiedImageError:
                if is_lfs_pointer(img_path):
                    st.error(
                        f"Image appears to be a Git LFS pointer and not the binary file: {img_path}. "
                        "Enable git-lfs in your Docker build (install git-lfs and run 'git lfs fetch' + 'git lfs checkout'), or ensure images are present."
                    )
                else:
                    st.error(f"Unidentified image format: {img_path}")
            except Exception as e:
                st.error(f"Failed to display image {img_path}: {e}")
        else:
            st.error("Image not found")

        st.markdown("---")
        st.header("Parsed PDF (rendered)")

        # Check multiple possible locations for the compiled PDF
        stem = Path(current_image).stem
        possible_pdf_paths = [
            PDF_DIR / f"{stem}.pdf",  # LaTeX compilation output directory (from config)
            TSV_DIR / "latex" / f"{stem}.pdf",  # Alternative LaTeX compilation path
        ]

        pdf_found = False
        for pdf_path in possible_pdf_paths:
            if pdf_path.exists():
                if HAS_FITZ:
                    try:
                        doc = fitz.open(pdf_path)
                        pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(3, 3))
                        st.image(pix.tobytes(output="png"), use_container_width=True)
                        st.caption(f"PDF source: {pdf_path.name}")
                        pdf_found = True
                        break
                    except Exception as e:
                        st.warning(f"Could not display PDF {pdf_path.name}: {e}")
                        continue
                else:
                    st.warning("PDF display unavailable: PyMuPDF not installed")
                    break

        if not pdf_found:
            st.info(
                "No compiled PDF found. Use 'Save and Recompile from TSV' or 'Compile from LaTeX' to generate."
            )

    # === TSV TAB ===
    with tab2:
        # Editor mode selection
        # Persist editor mode across reruns; default to Text Editor
        if "tsv_editor_mode" not in st.session_state:
            st.session_state.tsv_editor_mode = "📝 Text Editor (Classic)"
        editor_mode = st.radio(
            "Choose editor mode:",
            options=["📊 Table Editor (Excel-like)", "📝 Text Editor (Classic)"],
            index=1,  # Default to text editor
            horizontal=True,
            help="Table editor provides Excel-like editing, Text editor shows raw TSV with arrows",
            key="tsv_editor_mode",
        )

        # Use CSV files (tab-delimited)
        stem = Path(current_image).stem
        csv_file = TSV_DIR / f"{stem}.csv"
        tsv_path = csv_file  # Use CSV file for TSV operations
        tab_symbol = "→"

        if editor_mode == "📊 Table Editor (Excel-like)":
            # Use simple editor (works without pandas)
            data_changed = False
            try:
                from simple_tsv_editor import show_simple_tsv_editor

                data_changed, edited_data = show_simple_tsv_editor(tsv_path, current_image)
            except Exception as e:
                st.error(f"Table editor error: {e}")
                st.info("Table Editor encountered an error; staying on current mode.")
                data_changed = False

            # Only process changes if we're still in table editor mode
            if editor_mode == "📊 Table Editor (Excel-like)" and data_changed:
                # Apply TSV corrections to the saved file
                try:
                    corrected_tsv_text = correct_tsv_file(tsv_path)
                    st.success("TSV corrections applied!")

                    # Auto-generate LaTeX and compile
                    latex_path = tsv_to_full_latex_article(tsv_path)
                    latex_session_key = f"edited_latex_{current_image}"
                    try:
                        st.session_state[latex_session_key] = latex_path.read_text(encoding="utf-8")
                    except Exception:
                        pass

                    returncode, out = compile_tex_to_pdf(latex_path)
                    if returncode != 0:
                        st.error(f"LaTeX compilation failed:\n{out}")
                    else:
                        st.success("LaTeX compiled successfully!")
                        # Show compiled PDF preview
                        if HAS_FITZ:
                            try:
                                doc = fitz.open(latex_path.parent / (latex_path.stem + ".pdf"))
                                pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(2, 2))
                                st.image(pix.tobytes(output="png"), use_container_width=True)
                            except Exception as e:
                                st.warning(f"Could not display PDF preview: {e}")
                        else:
                            st.warning("PDF preview unavailable: PyMuPDF not installed")

                    # Auto-sync to DB
                    try:
                        from import_reactions import (
                            import_single_csv_idempotent as import_single_csv_idempotent_fn,
                        )

                        tno = (
                            int(table_choice.replace("table", ""))
                            if table_choice.startswith("table")
                            else None
                        )
                        if tno:
                            rcount, mcount = import_single_csv_idempotent_fn(Path(tsv_path), tno)
                            st.sidebar.info(f"TSV synced to DB: {mcount} measurements refreshed.")
                    except Exception as e:
                        st.sidebar.warning(f"Auto DB sync failed: {e}")

                except Exception as e:
                    st.error(f"Error applying corrections: {e}")

        if editor_mode == "📝 Text Editor (Classic)":
            # Original text editor implementation
            if csv_file.exists():
                tsv_text = tsv_path.read_text(encoding="utf-8")
            else:
                tsv_text = ""
                st.info("No CSV found yet for this image. You can create one and save.")

            # Session state: show fixed/corrected TSV after saving
            session_key = f"edited_visible_{current_image}"
            if session_key not in st.session_state:
                st.session_state[session_key] = tsv_to_visible(tsv_text, tab_symbol=tab_symbol)

            edited_visible = st.text_area(
                "TSV content (arrows represent tabs)",
                value=st.session_state[session_key],
                height=400,
                key=f"tsv_text_area_{current_image}",
                help="Use arrows (→) to represent tab separators. Click 'Table Editor' above for Excel-like editing.",
            )

            if st.button("Save and Recompile from TSV"):
                # Write user edits as raw TSV, then apply correction and update text area
                edited_tsv = visible_to_tsv(edited_visible, tab_symbol=tab_symbol)
                tsv_path.write_text(edited_tsv, encoding="utf-8")
                corrected_tsv_text = correct_tsv_file(tsv_path)
                st.session_state[session_key] = tsv_to_visible(
                    corrected_tsv_text, tab_symbol=tab_symbol
                )
                tsv_text = corrected_tsv_text

                # Recreate LaTeX from TSV and compile
                latex_path = tsv_to_full_latex_article(tsv_path)
                # Also update LaTeX editor content so it's in sync when switching tabs
                latex_session_key = f"edited_latex_{current_image}"
                try:
                    st.session_state[latex_session_key] = latex_path.read_text(encoding="utf-8")
                except Exception:
                    pass

                returncode, out = compile_tex_to_pdf(latex_path)
                if returncode != 0:
                    st.error(f"Compilation failed:\n{out}")
                else:
                    st.success("Compiled and corrections applied!")
                    if HAS_FITZ:
                        try:
                            doc = fitz.open(latex_path.parent / (latex_path.stem + ".pdf"))
                            pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(2, 2))
                            st.image(pix.tobytes(output="png"), use_container_width=True)
                        except Exception as e:
                            st.warning(f"Could not display PDF preview: {e}")
                    else:
                        st.warning("PDF preview unavailable: PyMuPDF not installed")

                # Automatically sync TSV to DB (idempotent), regardless of validation state
                try:
                    from import_reactions import (
                        import_single_csv_idempotent as import_single_csv_idempotent_fn,
                    )

                    tno = (
                        int(table_choice.replace("table", ""))
                        if table_choice.startswith("table")
                        else None
                    )
                    if tno:
                        rcount, mcount = import_single_csv_idempotent_fn(Path(tsv_path), tno)
                        st.sidebar.info(f"TSV synced to DB: {mcount} measurements refreshed.")
                except Exception as e:
                    st.sidebar.warning(f"Auto DB sync failed: {e}")

            # --- Wrap selected text with \ce{...} helper ---
            # Note: Streamlit can't read the selection from st.text_area; paste the selected text below
            st.divider()
            ce_col1, ce_col2, ce_col3 = st.columns([2, 1, 1])
            with ce_col1:
                st.text_input(
                    "Selected text to wrap",
                    key=f"wrap_ce_sel_{current_image}",
                    placeholder="Paste the selected text here",
                    help="Streamlit cannot read your selection from the editor. Paste the exact text you want to wrap.",
                )
            with ce_col2:
                wrap_all = st.checkbox(
                    "Wrap all",
                    value=False,
                    key=f"wrap_ce_all_{current_image}",
                    help="If enabled, wraps all occurrences; otherwise only the first occurrence.",
                )
            with ce_col3:
                if st.button(
                    r"$\\ce{}$",
                    key=f"wrap_ce_btn_{current_image}",
                    help=r"Wrap selection with $\\ce{...}$",
                ):
                    base_text = st.session_state.get(session_key, edited_visible)
                    target = st.session_state.get(f"wrap_ce_sel_{current_image}", "") or ""
                    if target:
                        replacement = f"$\\ce{{{target}}}$"
                        new_text = (
                            base_text.replace(target, replacement)
                            if wrap_all
                            else base_text.replace(target, replacement, 1)
                        )
                        st.session_state[session_key] = new_text
                        st.success(r"Wrapped selection with $\\ce{...}$.")
                        st.rerun()
                    else:
                        st.warning("Enter the text to wrap in the field provided.")

    # === LaTeX TAB ===
    with tab3:
        st.header("Edit LaTeX")
        # Determine CSV file path for LaTeX generation
        stem = Path(current_image).stem
        csv_file = TSV_DIR / f"{stem}.csv"
        base_tsv_path = csv_file  # Use CSV file for LaTeX operations

        # LaTeX path follows pdf_utils: TSV_DIR/<...>/latex/<stem>.tex
        latex_path = base_tsv_path.parent / "latex" / f"{stem}.tex"

        col_gen, col_save, col_compile = st.columns([1, 1, 1])
        with col_gen:
            if st.button("Recreate LaTeX from TSV"):
                try:
                    lp = tsv_to_full_latex_article(base_tsv_path)
                    # Refresh editor content immediately with regenerated LaTeX
                    latex_session_key = f"edited_latex_{current_image}"
                    try:
                        st.session_state[latex_session_key] = lp.read_text(encoding="utf-8")
                    except Exception:
                        pass
                    st.success(f"Regenerated: {lp.name}")
                except Exception as e:
                    st.error(f"Failed to regenerate LaTeX: {e}")

        # Load or create LaTeX content for editing
        if latex_path.exists():
            latex_text = latex_path.read_text(encoding="utf-8")
        else:
            latex_text = ""
            st.info('No LaTeX file yet. Click "Recreate LaTeX from TSV" to generate.')

        latex_session_key = f"edited_latex_{current_image}"
        if latex_session_key not in st.session_state:
            st.session_state[latex_session_key] = latex_text

        edited_latex = st.text_area(
            "LaTeX content (.tex)",
            value=st.session_state[latex_session_key],
            height=500,
            key=f"latex_text_area_{current_image}",
        )

        with col_save:
            if st.button("Save LaTeX"):
                # Ensure directory exists
                latex_path.parent.mkdir(parents=True, exist_ok=True)
                latex_path.write_text(edited_latex, encoding="utf-8")
                st.session_state[latex_session_key] = edited_latex
                st.success("LaTeX saved.")

        with col_compile:
            if st.button("Compile from LaTeX"):
                if not latex_path.exists():
                    st.error("No LaTeX file found. Generate or save it first.")
                else:
                    returncode, out = compile_tex_to_pdf(latex_path)
                    if returncode != 0:
                        st.error(f"Compilation failed:\n{out}")
                    else:
                        st.success("Compiled LaTeX successfully!")
                        pdf_file = latex_path.parent / (latex_path.stem + ".pdf")
                        if pdf_file.exists():
                            if HAS_FITZ:
                                try:
                                    doc = fitz.open(pdf_file)
                                    pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(2, 2))
                                    st.image(pix.tobytes(output="png"), use_container_width=True)
                                except Exception as e:
                                    st.warning(f"Could not display PDF preview: {e}")
                            else:
                                st.warning("PDF preview unavailable: PyMuPDF not installed")
