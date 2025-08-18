import streamlit as st
from PIL import Image
from pathlib import Path
import json
from datetime import datetime
from config import AVAILABLE_TABLES, get_table_paths, BASE_DIR
from db_utils import load_db, get_stats_for_table, aggregate_stats
from tsv_utils import tsv_to_visible, visible_to_tsv, correct_tsv_file
from pdf_utils import tsv_to_full_latex_article, compile_tex_to_pdf
from auth_db import show_user_profile_page

# Try import fitz (PyMuPDF)
try:
    import fitz
except ImportError:
    st.error("PyMuPDF is required. Install with `pip install PyMuPDF`.")
    st.stop()

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
            print(f"[VALIDATE MODE] User clicked back button, returning to main page")
            st.session_state.page_mode = 'main'
            st.rerun()
    
    st.markdown("---")
    
    # === Sidebar controls and global stats ===
    st.sidebar.title('Validation Controls')
    
    # === User Information ===
    st.sidebar.markdown(f"### 👤 User: **{current_user}**")
    if st.sidebar.button("👤 My Profile"):
        st.session_state.show_profile = True
        st.rerun()

    # Check if we should show profile page
    if st.session_state.get('show_profile', False):
        st.session_state.show_profile = False
        show_user_profile_page()
        st.stop()

    st.sidebar.markdown("---")
    table_choice = st.sidebar.selectbox(
        "Select Table Folder:",
        options=AVAILABLE_TABLES,
        index=AVAILABLE_TABLES.index('table6') if 'table6' in AVAILABLE_TABLES else 0,
    )

    agg_total, agg_validated, agg_percent = aggregate_stats(AVAILABLE_TABLES, get_table_paths)
    st.sidebar.markdown("### **All Tables (Global Stats)**")
    st.sidebar.markdown(f"**Total images:** {agg_total}")
    st.sidebar.markdown(f"**Validated:** {agg_validated} ({agg_percent:.1f}%)")
    st.sidebar.markdown("---")

    # === Paths and DB for current table ===
    IMAGE_DIR, PDF_DIR, TSV_DIR, DB_PATH = get_table_paths(table_choice)
    # Debug info to help diagnose path issues in deployments
    st.sidebar.markdown(f"BASE_DIR: {BASE_DIR}")
    st.sidebar.markdown(f"IMAGE_DIR exists: {IMAGE_DIR.exists()}")
    st.sidebar.markdown(f"IMAGE_DIR: {IMAGE_DIR}")

    db = load_db(DB_PATH, IMAGE_DIR)

    table_total, table_validated, table_percent = get_stats_for_table(db)
    st.sidebar.markdown(f"### **Selected Table: {table_choice}**")
    st.sidebar.markdown(f"**Total images:** {table_total}")
    st.sidebar.markdown(f"**Validated:** {table_validated} ({table_percent:.1f}%)")

    filter_mode = st.sidebar.selectbox(
        "Show images:",
        options=["All", "Only unvalidated"],
        index=0
    )

    if filter_mode == "Only unvalidated":
        images = [img for img, valid in db.items() if not valid]
    else:
        images = list(db.keys())

    if not images:
        st.sidebar.warning("No images to display for this filter.")
        st.stop()

    # === Navigation logic ===
    if 'idx' not in st.session_state or st.session_state.get("table_choice") != table_choice:
        st.session_state.idx = 0
        st.session_state.table_choice = table_choice  # reset idx on table change

    if st.session_state.idx >= len(images):
        st.session_state.idx = 0
    prev, nxt = st.sidebar.columns(2)
    with prev:
        if st.button('Previous'):
            st.session_state.idx = max(0, st.session_state.idx-1)
    with nxt:
        if st.button('Next'):
            st.session_state.idx = min(len(images)-1, st.session_state.idx+1)
    st.sidebar.number_input('Image Index', 0, len(images)-1, st.session_state.idx, key='idx')

    current_image = images[st.session_state.idx]
    st.sidebar.markdown(f'**Current:** {current_image}')

    # === Validation toggle ===
    validated = st.sidebar.checkbox(
        'Validated',
        value=db.get(current_image, False),
        key=f'validated_{table_choice}_{current_image}'
    )
    if validated != db.get(current_image, False):
        db[current_image] = validated
        DB_PATH.write_text(json.dumps(db, indent=2, ensure_ascii=False))

    # === Download Section ===
    st.sidebar.markdown("---")
    st.sidebar.markdown("### **📥 Download Validation Data**")

    # Download current table validation DB
    if st.sidebar.button(f"Download {table_choice} DB"):
        # Prepare the validation database for download
        download_data = {
            "table_name": table_choice,
            "export_timestamp": datetime.now().isoformat(),
            "total_images": table_total,
            "validated_images": table_validated,
            "validation_percentage": table_percent,
            "validation_data": db
        }
        
        # Create JSON string
        json_str = json.dumps(download_data, indent=2, ensure_ascii=False)
        
        # Create download button
        st.sidebar.download_button(
            label=f"💾 {table_choice}_validation_db.json",
            data=json_str,
            file_name=f"{table_choice}_validation_db.json",
            mime="application/json",
            key=f"download_{table_choice}"
        )

    # Download all tables validation data
    if st.sidebar.button("Download All Tables DBs"):
        all_tables_data = {
            "export_timestamp": datetime.now().isoformat(),
            "global_stats": {
                "total_images": agg_total,
                "validated_images": agg_validated,
                "validation_percentage": agg_percent
            },
            "tables": {}
        }
        
        for table in AVAILABLE_TABLES:
            try:
                _, _, _, table_db_path = get_table_paths(table)
                if table_db_path.exists():
                    table_db = load_db(table_db_path, get_table_paths(table)[0])
                    table_stats = get_stats_for_table(table_db)
                    
                    all_tables_data["tables"][table] = {
                        "total_images": table_stats[0],
                        "validated_images": table_stats[1],
                        "validation_percentage": table_stats[2],
                        "validation_data": table_db
                    }
            except Exception as e:
                st.sidebar.error(f"Error loading {table}: {str(e)}")
        
        # Create download button for all tables
        json_str = json.dumps(all_tables_data, indent=2, ensure_ascii=False)
        st.sidebar.download_button(
            label="💾 all_tables_validation_data.json",
            data=json_str,
            file_name="all_tables_validation_data.json",
            mime="application/json",
            key="download_all_tables"
        )

    # === Main Page Tabs ===
    tab1, tab2, tab3 = st.tabs(['Image', 'TSV', 'LaTeX'])

    # === IMAGE TAB ===
    with tab1:
        st.header('Image Preview')
        img_path = IMAGE_DIR / current_image
        if img_path.exists():
            st.image(Image.open(img_path), use_container_width=True)
        else:
            st.error('Image not found')

        st.markdown('---')
        st.header('Parsed PDF (rendered)')
        pdf_path = PDF_DIR / (Path(current_image).stem + '.pdf')
        if pdf_path.exists():
            doc = fitz.open(pdf_path)
            pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(3, 3))
            st.image(pix.tobytes(output='png'), use_container_width=True)
        else:
            st.error('PDF not found')

    # === TSV TAB ===
    with tab2:
        st.header('Edit TSV')
        # Support both .tsv and legacy .csv (tab-delimited) files
        stem = Path(current_image).stem
        tsv_candidate = TSV_DIR / f"{stem}.tsv"
        csv_candidate = TSV_DIR / f"{stem}.csv"
        if tsv_candidate.exists():
            tsv_path = tsv_candidate
        elif csv_candidate.exists():
            tsv_path = csv_candidate
        else:
            # default to creating a .tsv on save if nothing exists yet
            tsv_path = tsv_candidate
        tab_symbol = "→"

        if tsv_candidate.exists() or csv_candidate.exists():
            tsv_text = tsv_path.read_text(encoding='utf-8')
        else:
            tsv_text = ''
            st.info('No TSV/CSV found yet for this image. You can create one and save.')

        # Session state: show fixed/corrected TSV after saving
        session_key = f'edited_visible_{current_image}'
        if session_key not in st.session_state:
            st.session_state[session_key] = tsv_to_visible(tsv_text, tab_symbol=tab_symbol)

        edited_visible = st.text_area(
            'TSV content',
            value=st.session_state[session_key],
            height=400,
            key=f'tsv_text_area_{current_image}'
        )

        if st.button('Save and Recompile from TSV'):
            # Write user edits as raw TSV, then apply correction and update text area
            edited_tsv = visible_to_tsv(edited_visible, tab_symbol=tab_symbol)
            tsv_path.write_text(edited_tsv, encoding='utf-8')
            corrected_tsv_text = correct_tsv_file(tsv_path)
            st.session_state[session_key] = tsv_to_visible(corrected_tsv_text, tab_symbol=tab_symbol)
            tsv_text = corrected_tsv_text

            # Recreate LaTeX from TSV and compile
            latex_path = tsv_to_full_latex_article(tsv_path)
            # Also update LaTeX editor content so it's in sync when switching tabs
            latex_session_key = f'edited_latex_{current_image}'
            try:
                st.session_state[latex_session_key] = latex_path.read_text(encoding='utf-8')
            except Exception:
                pass

            returncode, out = compile_tex_to_pdf(latex_path)
            if returncode != 0:
                st.error(f'Compilation failed:\n{out}')
            else:
                st.success('Compiled and corrections applied!')
                doc = fitz.open(latex_path.parent / (latex_path.stem + '.pdf'))
                pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(2,2))
                st.image(pix.tobytes(output='png'), use_container_width=True)

    # === LaTeX TAB ===
    with tab3:
        st.header('Edit LaTeX')
        # Determine the same TSV path candidates to infer LaTeX location
        stem = Path(current_image).stem
        tsv_candidate = TSV_DIR / f"{stem}.tsv"
        csv_candidate = TSV_DIR / f"{stem}.csv"
        if tsv_candidate.exists():
            base_tsv_path = tsv_candidate
        elif csv_candidate.exists():
            base_tsv_path = csv_candidate
        else:
            base_tsv_path = tsv_candidate  # will be created on regeneration

        # LaTeX path follows pdf_utils: TSV_DIR/<...>/latex/<stem>.tex
        latex_path = (base_tsv_path.parent / 'latex' / f'{stem}.tex')

        col_gen, col_save, col_compile = st.columns([1,1,1])
        with col_gen:
            if st.button('Recreate LaTeX from TSV'):
                try:
                    lp = tsv_to_full_latex_article(base_tsv_path)
                    # Refresh editor content immediately with regenerated LaTeX
                    latex_session_key = f'edited_latex_{current_image}'
                    try:
                        st.session_state[latex_session_key] = lp.read_text(encoding='utf-8')
                    except Exception:
                        pass
                    st.success(f'Regenerated: {lp.name}')
                except Exception as e:
                    st.error(f'Failed to regenerate LaTeX: {e}')

        # Load or create LaTeX content for editing
        if latex_path.exists():
            latex_text = latex_path.read_text(encoding='utf-8')
        else:
            latex_text = ''
            st.info('No LaTeX file yet. Click "Recreate LaTeX from TSV" to generate.')

        latex_session_key = f'edited_latex_{current_image}'
        if latex_session_key not in st.session_state:
            st.session_state[latex_session_key] = latex_text

        edited_latex = st.text_area(
            'LaTeX content (.tex)',
            value=st.session_state[latex_session_key],
            height=500,
            key=f'latex_text_area_{current_image}'
        )

        with col_save:
            if st.button('Save LaTeX'):
                # Ensure directory exists
                latex_path.parent.mkdir(parents=True, exist_ok=True)
                latex_path.write_text(edited_latex, encoding='utf-8')
                st.session_state[latex_session_key] = edited_latex
                st.success('LaTeX saved.')

        with col_compile:
            if st.button('Compile from LaTeX'):
                if not latex_path.exists():
                    st.error('No LaTeX file found. Generate or save it first.')
                else:
                    returncode, out = compile_tex_to_pdf(latex_path)
                    if returncode != 0:
                        st.error(f'Compilation failed:\n{out}')
                    else:
                        st.success('Compiled LaTeX successfully!')
                        pdf_file = latex_path.parent / (latex_path.stem + '.pdf')
                        if pdf_file.exists():
                            doc = fitz.open(pdf_file)
                            pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(2,2))
                            st.image(pix.tobytes(output='png'), use_container_width=True)
