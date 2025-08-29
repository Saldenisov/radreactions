"""
TSV Editor Component for Streamlit with Excel-like functionality.

Provides an editable data table interface for TSV files stored as CSV with tab separators.
"""

import io
from pathlib import Path

import pandas as pd
import streamlit as st


def load_tsv_as_dataframe(tsv_path: Path) -> pd.DataFrame:
    """Load a TSV file (stored as .csv with tab delimiter) into a pandas DataFrame."""
    if not tsv_path.exists():
        # Return empty DataFrame with default columns for chemical reactions
        return pd.DataFrame(
            columns=["pH", "Rate", "Units", "Method", "Conditions", "Reference", "Notes"]
        )

    try:
        # Read as TSV (tab-delimited)
        df = pd.read_csv(tsv_path, sep="\t", dtype=str, keep_default_na=False)

        # Ensure we have at least 7 columns (standard for reaction data)
        while len(df.columns) < 7:
            df[f"Column_{len(df.columns)}"] = ""

        # Set standard column names if they're not already set
        if df.columns.tolist() == [f"Column_{i}" for i in range(len(df.columns))]:
            standard_cols = ["pH", "Rate", "Units", "Method", "Conditions", "Reference", "Notes"]
            df.columns = standard_cols[: len(df.columns)]

        return df
    except Exception as e:
        st.error(f"Error loading TSV file: {e}")
        return pd.DataFrame(
            columns=["pH", "Rate", "Units", "Method", "Conditions", "Reference", "Notes"]
        )


def save_dataframe_as_tsv(df: pd.DataFrame, tsv_path: Path) -> bool:
    """Save a pandas DataFrame as a TSV file (stored as .csv with tab delimiter)."""
    try:
        # Ensure parent directory exists
        tsv_path.parent.mkdir(parents=True, exist_ok=True)

        # Save as TSV
        df.to_csv(tsv_path, sep="\t", index=False, na_rep="", lineterminator="\n")
        return True
    except Exception as e:
        st.error(f"Error saving TSV file: {e}")
        return False


def show_tsv_editor(tsv_path: Path, current_image: str) -> tuple[bool, pd.DataFrame | None]:
    """
    Display an Excel-like editable data table for TSV content.

    Returns:
        (changed, dataframe): changed is True if data was modified, dataframe is the current data
    """
    st.header("Edit TSV Data")

    # Load current data
    df = load_tsv_as_dataframe(tsv_path)

    # Show file info
    if tsv_path.exists():
        st.info(f"📁 Editing: `{tsv_path.name}` ({len(df)} rows)")
    else:
        st.info(f"📁 Creating new file: `{tsv_path.name}`")

    # Data editor configuration
    column_config = {
        "pH": st.column_config.TextColumn("pH", help="pH value", width="small"),
        "Rate": st.column_config.TextColumn("Rate", help="Rate constant value", width="medium"),
        "Units": st.column_config.TextColumn("Units", help="Rate units", width="medium"),
        "Method": st.column_config.TextColumn("Method", help="Experimental method", width="medium"),
        "Conditions": st.column_config.TextColumn(
            "Conditions", help="Experimental conditions", width="large"
        ),
        "Reference": st.column_config.TextColumn(
            "Reference", help="Literature reference", width="large"
        ),
        "Notes": st.column_config.TextColumn("Notes", help="Additional notes", width="large"),
    }

    # Only show column config for columns that exist
    active_config = {col: config for col, config in column_config.items() if col in df.columns}

    # Add buttons above the editor
    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])

    with col1:
        add_row = st.button("➕ Add Row", help="Add a new empty row")

    with col2:
        if len(df) > 0:
            remove_last = st.button("➖ Remove Last", help="Remove the last row")
        else:
            remove_last = False

    with col3:
        clear_all = st.button("🗑️ Clear All", help="Clear all data", type="secondary")

    # Handle button actions
    if add_row:
        new_row = pd.DataFrame([[""] * len(df.columns)], columns=df.columns)
        df = pd.concat([df, new_row], ignore_index=True)

    if remove_last and len(df) > 0:
        df = df.iloc[:-1]

    if clear_all:
        df = pd.DataFrame(columns=df.columns)

    # Show the editable data table
    edited_df = st.data_editor(
        df,
        key=f"tsv_editor_{current_image}",
        use_container_width=True,
        num_rows="dynamic",  # Allow adding/removing rows in the editor
        column_config=active_config,
        hide_index=True,
    )

    # Check if data changed
    data_changed = not df.equals(edited_df)

    # Save button
    col_save, col_preview, col_export = st.columns([1, 1, 1])

    with col_save:
        if st.button(
            "💾 Save TSV", type="primary", disabled=not data_changed and tsv_path.exists()
        ):
            if save_dataframe_as_tsv(edited_df, tsv_path):
                st.success(f"✅ Saved {len(edited_df)} rows to {tsv_path.name}")
                return True, edited_df
            else:
                return False, edited_df

    with col_preview:
        if st.button("👁️ Preview Raw TSV"):
            # Show raw TSV content in expandable section
            tsv_content = edited_df.to_csv(sep="\t", index=False, na_rep="")
            with st.expander("Raw TSV Content", expanded=True):
                st.code(tsv_content, language="text")

    with col_export:
        if not edited_df.empty:
            # Download button for TSV
            tsv_content = edited_df.to_csv(sep="\t", index=False, na_rep="")
            st.download_button(
                label="⬇️ Download TSV",
                data=tsv_content,
                file_name=f"{Path(current_image).stem}.tsv",
                mime="text/tab-separated-values",
            )

    # Show data summary
    if not edited_df.empty:
        st.caption(f"📊 {len(edited_df)} rows × {len(edited_df.columns)} columns")

        # Show validation warnings
        empty_cells = edited_df.isnull().sum().sum() + (edited_df == "").sum().sum()
        if empty_cells > 0:
            st.caption(f"⚠️ {empty_cells} empty cells")
    else:
        st.caption("📊 No data")

    return data_changed, edited_df


def convert_text_to_dataframe(text_content: str) -> pd.DataFrame:
    """Convert raw TSV text (with arrows as tabs) to DataFrame."""
    # Replace arrows back to tabs
    tsv_content = text_content.replace("→", "\t")

    # Parse as TSV
    try:
        df = pd.read_csv(io.StringIO(tsv_content), sep="\t", dtype=str, keep_default_na=False)
        return df
    except Exception:
        # If parsing fails, create empty DataFrame
        return pd.DataFrame(
            columns=["pH", "Rate", "Units", "Method", "Conditions", "Reference", "Notes"]
        )


def show_migration_helper(current_image: str, text_content: str) -> pd.DataFrame | None:
    """Help users migrate from text editor to table editor."""
    if not text_content.strip():
        return None

    st.info("🔄 **Migration Helper**: Convert your text-based TSV to table format")

    if st.button("📊 Convert to Table Format"):
        df = convert_text_to_dataframe(text_content)
        if not df.empty:
            st.success(f"✅ Converted {len(df)} rows to table format")
            return df
        else:
            st.warning("⚠️ Could not parse TSV content")

    return None
