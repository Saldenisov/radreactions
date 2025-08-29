#!/usr/bin/env python3
"""
Volume persistence debugging script for Railway deployment.

Run this script to diagnose volume mounting and data persistence issues.
"""

import os
import platform
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path


def run_cmd(cmd: list[str]) -> str:
    """Run a command and return its output."""
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=10)
        return (
            result.stdout.strip() if result.returncode == 0 else f"ERROR: {result.stderr.strip()}"
        )
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out"
    except Exception as e:
        return f"ERROR: {e}"


def check_file_persistence():
    """Create test files to check persistence."""
    test_dir = Path("/data")
    test_file = test_dir / "persistence_test.txt"

    timestamp = datetime.now().isoformat()

    # Create test file with timestamp
    try:
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file.write_text(
            f"Created at: {timestamp}\nPID: {os.getpid()}\nHost: {platform.node()}\n"
        )
        return f"✅ Created test file at {test_file}"
    except Exception as e:
        return f"❌ Failed to create test file: {e}"


def main():
    print("🔍 Railway Volume Persistence Diagnostic")
    print("=" * 50)

    # Basic system info
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Platform: {platform.platform()}")
    print(f"Python: {platform.python_version()}")
    print(f"PID: {os.getpid()}")
    print(f"CWD: {os.getcwd()}")
    print(f"User: {os.environ.get('USER', 'unknown')}")
    print()

    # Environment variables
    print("🌍 Environment Variables:")
    for key in sorted(os.environ.keys()):
        if any(term in key.lower() for term in ["data", "base", "port", "railway", "volume"]):
            print(f"  {key} = {os.environ[key]}")
    print()

    # File system checks
    print("📁 File System Analysis:")

    # Check key directories
    key_dirs = ["/", "/data", "/app", "/tmp", "/app/data"]
    for dir_path in key_dirs:
        path = Path(dir_path)
        if path.exists():
            try:
                stat = path.stat()
                size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                files = len(list(path.rglob("*")))
                print(f"  {dir_path}: EXISTS, {files} items, {size / 1024 / 1024:.1f}MB")
            except Exception as e:
                print(f"  {dir_path}: EXISTS but error reading: {e}")
        else:
            print(f"  {dir_path}: MISSING")
    print()

    # Mount information
    print("💾 Mount Information:")
    mount_info = run_cmd(["mount"])
    if "/data" in mount_info:
        for line in mount_info.split("\n"):
            if "/data" in line:
                print(f"  {line}")
    else:
        print("  No /data mount found in mount output")

    # Check df for /data
    df_output = run_cmd(["df", "-h", "/data"])
    if "ERROR" not in df_output:
        print(f"  df -h /data: {df_output}")
    print()

    # Railway-specific checks
    print("🚂 Railway Environment:")
    railway_vars = {k: v for k, v in os.environ.items() if "railway" in k.lower()}
    if railway_vars:
        for k, v in railway_vars.items():
            print(f"  {k} = {v}")
    else:
        print("  No Railway environment variables found")
    print()

    # Check existing data
    print("📊 Data Directory Contents:")
    data_path = Path("/data")
    if data_path.exists():
        try:
            contents = list(data_path.iterdir())
            print(f"  /data contains {len(contents)} items:")
            for item in sorted(contents)[:10]:  # Show first 10 items
                if item.is_file():
                    size = item.stat().st_size
                    mod_time = datetime.fromtimestamp(item.stat().st_mtime)
                    print(f"    📄 {item.name} ({size} bytes, modified {mod_time})")
                elif item.is_dir():
                    sub_items = len(list(item.iterdir()))
                    print(f"    📁 {item.name}/ ({sub_items} items)")

            if len(contents) > 10:
                print(f"    ... and {len(contents) - 10} more items")

        except Exception as e:
            print(f"  Error reading /data: {e}")
    else:
        print("  /data does not exist")
    print()

    # Database checks
    print("🗄️ Database Status:")

    # Try to import app config
    try:
        import sys

        sys.path.insert(0, "/app")  # Ensure app is in path
        from config import BASE_DIR
        from reactions_db import DB_PATH

        print(f"  BASE_DIR resolved to: {BASE_DIR}")
        print(f"  DB_PATH resolved to: {DB_PATH}")

        if DB_PATH.exists():
            stat = DB_PATH.stat()
            mod_time = datetime.fromtimestamp(stat.st_mtime)
            print(f"  Database exists: {stat.st_size} bytes, modified {mod_time}")

            # Try to open database and get basic info
            try:
                con = sqlite3.connect(str(DB_PATH))
                cursor = con.execute("SELECT COUNT(*) FROM reactions")
                reaction_count = cursor.fetchone()[0]
                cursor = con.execute("SELECT COUNT(*) FROM measurements")
                measurement_count = cursor.fetchone()[0]
                con.close()
                print(
                    f"  Database contains: {reaction_count} reactions, {measurement_count} measurements"
                )
            except Exception as e:
                print(f"  Database exists but error reading: {e}")
        else:
            print(f"  Database does not exist at {DB_PATH}")

    except Exception as e:
        print(f"  Error importing app modules: {e}")
    print()

    # Persistence test
    print("🔄 Persistence Test:")
    result = check_file_persistence()
    print(f"  {result}")

    # Check if previous test file exists
    test_file = Path("/data/persistence_test.txt")
    if test_file.exists():
        content = test_file.read_text()
        print("  Previous test file found:")
        for line in content.strip().split("\n"):
            print(f"    {line}")
    print()

    print("✅ Diagnostic complete!")
    print("\n" + "=" * 50)
    print("💡 To check persistence across redeploys:")
    print("1. Run this script before redeploy")
    print("2. Redeploy your app")
    print("3. Run this script again after redeploy")
    print("4. Compare the 'persistence_test.txt' timestamps")


if __name__ == "__main__":
    main()
