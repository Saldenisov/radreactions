"""
Simple TSV Editor Component for Streamlit with Excel-like functionality.
Uses only built-in Python and Streamlit - no pandas dependency.
"""

import csv
import io
from pathlib import Path
from typing import Any

import streamlit as st


def load_tsv_as_dict_list(tsv_path: Path) -> list[dict[str, str]]:
    """Load a TSV file as a list of dictionaries.

    Note: CSV files in this project do NOT have headers - the first row is data.
    We'll use standard column names based on the expected structure.
    """
    if not tsv_path.exists():
        # Return empty list
        return []

    try:
        # Standard column names for reaction data (based on project structure)
        # From import_reactions.py: buxton_no, reaction_name, formula_latex, pH, rate_value, comments, references_field
        standard_columns = [
            "No.",
            "Compound name",
            "Reaction equation",
            "pH",
            "Rate constant",
            "Comments",
            "Reference",
        ]

        # Read as TSV (tab-delimited) without headers
        with open(tsv_path, encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            data = []
            for row in reader:
                # Pad row to ensure we have 7 columns
                row = row + [""] * (7 - len(row))

                # Create dictionary with standard column names
                clean_row = {}
                for i, col_name in enumerate(standard_columns):
                    clean_row[col_name] = str(row[i]) if i < len(row) else ""
                data.append(clean_row)

        # If no data, return empty list
        if not data:
            return []

        return data
    except Exception as e:
        st.error(f"Error loading TSV file: {e}")
        return []


def save_dict_list_as_tsv(data: list[dict[str, str]], tsv_path: Path) -> bool:
    """Save a list of dictionaries as a TSV file.

    Note: This project expects CSV files WITHOUT headers - first row is data.
    We need to map the dictionary columns back to the 7-column format expected by other parts.
    """
    try:
        # Ensure parent directory exists
        tsv_path.parent.mkdir(parents=True, exist_ok=True)

        if not data:
            # Create empty file
            tsv_path.write_text("", encoding="utf-8")
            return True

        # Expected column order for the project (7 columns):
        # No., Compound name, Reaction equation, pH, Rate constant, Comments, Reference
        expected_columns = [
            "No.",
            "Compound name",
            "Reaction equation",
            "pH",
            "Rate constant",
            "Comments",
            "Reference",
        ]

        # Write TSV file WITHOUT headers (as expected by the project)
        with open(tsv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter="\t", lineterminator="\n")

            for row in data:
                # Create row in the expected 7-column format
                output_row = []
                for col_name in expected_columns:
                    # Get value from dictionary, default to empty string
                    value = row.get(col_name, "")
                    output_row.append(value)

                # Ensure we have exactly 7 columns
                output_row = output_row + [""] * (7 - len(output_row))
                output_row = output_row[:7]  # Truncate if somehow longer

                writer.writerow(output_row)

        return True
    except Exception as e:
        st.error(f"Error saving TSV file: {e}")
        return False


def dict_list_to_df_format(data: list[dict[str, str]]) -> dict[str, Any]:
    """Convert list of dicts to format suitable for st.data_editor."""
    # Use the same column names as defined in load function
    standard_columns = [
        "No.",
        "Compound name",
        "Reaction equation",
        "pH",
        "Rate constant",
        "Comments",
        "Reference",
    ]

    if not data:
        # Return empty dataframe-like structure
        return {col: [] for col in standard_columns}

    # Get all columns from data
    all_columns = set()
    for row in data:
        all_columns.update(row.keys())

    # Use standard columns if data matches, otherwise use discovered columns
    if all_columns <= set(standard_columns):
        columns = [col for col in standard_columns if col in all_columns]
    else:
        columns = sorted(list(all_columns))

    # Convert to column-oriented format
    result = {}
    for col in columns:
        result[col] = [row.get(col, "") for row in data]

    return result


def df_format_to_dict_list(df_data: dict[str, Any]) -> list[dict[str, str]]:
    """Convert st.data_editor format back to list of dicts."""
    if not df_data:
        return []

    # Get number of rows (assuming all columns have same length)
    num_rows = len(list(df_data.values())[0]) if df_data else 0
    if num_rows == 0:
        return []

    # Convert back to row-oriented format
    result = []
    for i in range(num_rows):
        row = {}
        for col, values in df_data.items():
            row[col] = str(values[i]) if i < len(values) else ""
        result.append(row)

    return result


def show_simple_tsv_editor(
    tsv_path: Path, current_image: str
) -> tuple[bool, list[dict[str, str]] | None]:
    """
    Display a simple Excel-like editable data table for TSV content.

    Returns:
        (changed, data): changed is True if data was modified, data is the current data as list of dicts
    """
    st.header("Edit TSV Data")

    # Load current data
    data = load_tsv_as_dict_list(tsv_path)

    # Show file info
    if tsv_path.exists():
        st.info(f"📁 Editing: `{tsv_path.name}` ({len(data)} rows)")
    else:
        st.info(f"📁 Creating new file: `{tsv_path.name}`")

    # Convert to dataframe format for st.data_editor
    df_data = dict_list_to_df_format(data)

    # Data editor configuration using actual column names
    column_config = {
        "No.": st.column_config.TextColumn("No.", help="Buxton reaction number", width="small"),
        "Compound name": st.column_config.TextColumn(
            "Compound name", help="Name of the compound", width="medium"
        ),
        "Reaction equation": st.column_config.TextColumn(
            "Reaction equation", help="Chemical reaction equation", width="large"
        ),
        "pH": st.column_config.TextColumn("pH", help="pH value", width="small"),
        "Rate constant": st.column_config.TextColumn(
            "Rate constant", help="Rate constant value", width="medium"
        ),
        "Comments": st.column_config.TextColumn(
            "Comments", help="Experimental conditions and notes", width="large"
        ),
        "Reference": st.column_config.TextColumn(
            "Reference", help="Literature reference", width="medium"
        ),
    }

    # Only show column config for columns that exist
    active_config = {col: config for col, config in column_config.items() if col in df_data}

    # Convert to list of dicts format for st.data_editor
    if df_data:
        # Convert column-based to row-based for data_editor
        rows = []
        num_rows = len(list(df_data.values())[0]) if df_data else 0
        columns = list(df_data.keys())

        for i in range(num_rows):
            row = {}
            for col in columns:
                row[col] = df_data[col][i] if i < len(df_data[col]) else ""
            rows.append(row)

        # Show the editable data table
        edited_rows = st.data_editor(
            rows,
            key=f"simple_tsv_editor_{current_image}",
            use_container_width=True,
            num_rows="dynamic",  # Allow adding/removing rows in the editor
            column_config=active_config,
            hide_index=True,
        )
    else:
        # Empty data - create with standard columns
        standard_columns = [
            "No.",
            "Compound name",
            "Reaction equation",
            "pH",
            "Rate constant",
            "Comments",
            "Reference",
        ]
        empty_row = dict.fromkeys(standard_columns, "")
        edited_rows = st.data_editor(
            [empty_row],
            key=f"simple_tsv_editor_{current_image}",
            use_container_width=True,
            num_rows="dynamic",
            column_config=column_config,
            hide_index=True,
        )

    # Check if data changed
    data_changed = edited_rows != data

    # Save button
    col_save, col_preview, col_export = st.columns([1, 1, 1])

    with col_save:
        if st.button(
            "💾 Save TSV", type="primary", disabled=not data_changed and tsv_path.exists()
        ):
            if save_dict_list_as_tsv(edited_rows, tsv_path):
                st.success(f"✅ Saved {len(edited_rows)} rows to {tsv_path.name}")
                return True, edited_rows
            else:
                return False, edited_rows

    with col_preview:
        if st.button("👁️ Preview Raw TSV"):
            # Show raw TSV content in expandable section (as it will be saved - WITHOUT headers)
            if edited_rows:
                # Use the same format as the save function (no headers)
                expected_columns = [
                    "No.",
                    "Compound name",
                    "Reaction equation",
                    "pH",
                    "Rate constant",
                    "Comments",
                    "Reference",
                ]
                output = io.StringIO()
                writer = csv.writer(output, delimiter="\t", lineterminator="\n")

                for row in edited_rows:
                    # Create row in the expected 7-column format
                    output_row = []
                    for col_name in expected_columns:
                        # Get value from dictionary, default to empty string
                        value = row.get(col_name, "")
                        output_row.append(value)

                    # Ensure we have exactly 7 columns
                    output_row = output_row + [""] * (7 - len(output_row))
                    output_row = output_row[:7]  # Truncate if somehow longer

                    writer.writerow(output_row)

                tsv_content = output.getvalue()
            else:
                tsv_content = ""

            with st.expander("Raw TSV Content (as saved - no headers)", expanded=True):
                st.code(tsv_content, language="text")
                st.caption(
                    "Note: This shows the actual file format (7 columns, no headers) as expected by the project."
                )

    with col_export:
        if edited_rows:
            # Download button for TSV - use same format as save function (no headers)
            expected_columns = [
                "No.",
                "Compound name",
                "Reaction equation",
                "pH",
                "Rate constant",
                "Comments",
                "Reference",
            ]
            output = io.StringIO()
            writer = csv.writer(output, delimiter="\t", lineterminator="\n")

            for row in edited_rows:
                # Create row in the expected 7-column format
                output_row = []
                for col_name in expected_columns:
                    # Get value from dictionary, default to empty string
                    value = row.get(col_name, "")
                    output_row.append(value)

                # Ensure we have exactly 7 columns
                output_row = output_row + [""] * (7 - len(output_row))
                output_row = output_row[:7]  # Truncate if somehow longer

                writer.writerow(output_row)

            tsv_content = output.getvalue()

            st.download_button(
                label="⬇️ Download TSV",
                data=tsv_content,
                file_name=f"{Path(current_image).stem}.csv",  # Use .csv extension as the project does
                mime="text/tab-separated-values",
                help="Download as tab-delimited file (7 columns, no headers)",
            )

    # Show data summary
    if edited_rows:
        st.caption(
            f"📊 {len(edited_rows)} rows × {len(edited_rows[0]) if edited_rows else 0} columns"
        )

        # Show validation warnings
        empty_cells = sum(1 for row in edited_rows for val in row.values() if not val.strip())
        if empty_cells > 0:
            st.caption(f"⚠️ {empty_cells} empty cells")
    else:
        st.caption("📊 No data")

    return data_changed, edited_rows


def convert_text_to_dict_list(text_content: str) -> list[dict[str, str]]:
    """Convert raw TSV text (with arrows as tabs) to list of dictionaries."""
    # Replace arrows back to tabs
    tsv_content = text_content.replace("→", "\t")

    # Parse as TSV
    try:
        reader = csv.DictReader(io.StringIO(tsv_content), delimiter="\t")
        return list(reader)
    except Exception:
        return []


def show_simple_migration_helper(
    current_image: str, text_content: str
) -> list[dict[str, str]] | None:
    """Help users migrate from text editor to simple table editor."""
    if not text_content.strip():
        return None

    st.info("🔄 **Migration Helper**: Convert your text-based TSV to table format")

    if st.button("📊 Convert to Table Format"):
        data = convert_text_to_dict_list(text_content)
        if data:
            st.success(f"✅ Converted {len(data)} rows to table format")
            return data
        else:
            st.warning("⚠️ Could not parse TSV content")

    return None
