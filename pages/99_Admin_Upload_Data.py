"""Admin page for uploading data ZIP files.

This page allows authenticated admin users to upload ZIP files containing
table data that will be extracted to the data directory.
"""

import io
import os
import shutil
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
    st.title("🔧 Admin: Upload & Export Data")

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
