#!/usr/bin/env python3
"""
Database backup utility for RadReactions SQLite databases.

Creates timestamped backups of both reactions.db and users.db with compression.
"""

import gzip
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from config import BASE_DIR
from reactions_db import DB_PATH


def backup_database(db_path: Path, backup_dir: Path, compress: bool = True) -> Path:
    """Create a backup of SQLite database with timestamp."""
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_name = db_path.stem

    # Create backup filename
    backup_name = f"{db_name}_backup_{timestamp}.db"
    backup_path = backup_dir / backup_name

    print(f"Creating backup: {db_path} -> {backup_path}")

    # Use SQLite's built-in backup for consistency
    source_conn = sqlite3.connect(str(db_path))
    backup_conn = sqlite3.connect(str(backup_path))

    try:
        source_conn.backup(backup_conn)
        print(f"✅ Database backup created: {backup_path}")
    finally:
        source_conn.close()
        backup_conn.close()

    # Compress backup if requested
    if compress:
        compressed_path = backup_path.with_suffix(".db.gz")
        print(f"Compressing backup: {compressed_path}")

        with open(backup_path, "rb") as f_in:
            with gzip.open(compressed_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        # Remove uncompressed backup
        backup_path.unlink()
        backup_path = compressed_path
        print(f"✅ Compressed backup created: {backup_path}")

    return backup_path


def backup_all_databases(backup_dir: Path = None) -> list[Path]:
    """Backup all application databases."""
    if backup_dir is None:
        backup_dir = BASE_DIR / "backups"

    backups = []

    # Backup reactions database
    try:
        reactions_backup = backup_database(DB_PATH, backup_dir)
        backups.append(reactions_backup)
    except Exception as e:
        print(f"❌ Failed to backup reactions.db: {e}")

    # Backup users database
    try:
        from auth_db import auth_db

        users_db_path = Path(auth_db.db_path)
        users_backup = backup_database(users_db_path, backup_dir)
        backups.append(users_backup)
    except Exception as e:
        print(f"❌ Failed to backup users.db: {e}")

    return backups


def restore_database(backup_path: Path, target_path: Path) -> bool:
    """Restore database from backup."""
    try:
        if backup_path.suffix == ".gz":
            # Decompress first
            temp_path = target_path.with_suffix(".tmp")
            print(f"Decompressing backup: {backup_path}")

            with gzip.open(backup_path, "rb") as f_in:
                with open(temp_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            backup_path = temp_path

        print(f"Restoring database: {backup_path} -> {target_path}")

        # Create backup of current database if it exists
        if target_path.exists():
            current_backup = target_path.with_suffix(".db.pre_restore")
            shutil.copy2(target_path, current_backup)
            print(f"Current database backed up to: {current_backup}")

        # Restore the backup
        shutil.copy2(backup_path, target_path)

        # Clean up temp file if created
        if backup_path.suffix == ".tmp":
            backup_path.unlink()

        print(f"✅ Database restored: {target_path}")
        return True

    except Exception as e:
        print(f"❌ Failed to restore database: {e}")
        return False


def cleanup_old_backups(backup_dir: Path, keep_days: int = 7):
    """Remove backups older than specified days."""
    if not backup_dir.exists():
        return

    cutoff_time = datetime.now().timestamp() - (keep_days * 24 * 60 * 60)
    removed_count = 0

    for backup_file in backup_dir.glob("*_backup_*.db*"):
        if backup_file.stat().st_mtime < cutoff_time:
            backup_file.unlink()
            removed_count += 1
            print(f"Removed old backup: {backup_file}")

    if removed_count > 0:
        print(f"✅ Cleaned up {removed_count} old backup(s)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Database backup utility")
    parser.add_argument("--backup-dir", type=Path, help="Backup directory")
    parser.add_argument("--restore", type=Path, help="Restore from backup file")
    parser.add_argument("--target", type=Path, help="Target database for restore")
    parser.add_argument("--cleanup", type=int, help="Clean up backups older than N days")

    args = parser.parse_args()

    if args.restore:
        if not args.target:
            print("❌ --target required for restore operation")
            exit(1)
        restore_database(args.restore, args.target)
    elif args.cleanup:
        backup_dir = args.backup_dir or (BASE_DIR / "backups")
        cleanup_old_backups(backup_dir, args.cleanup)
    else:
        # Default: create backups
        backup_dir = args.backup_dir or (BASE_DIR / "backups")
        backups = backup_all_databases(backup_dir)

        if backups:
            print(f"\n✅ Created {len(backups)} backup(s):")
            for backup in backups:
                print(f"  - {backup}")
        else:
            print("❌ No backups were created")
