#!/usr/bin/env python3
"""
Automated backup scheduler for RadReactions databases.

Runs periodic backups and cleanup of old backup files.
Can be used as a standalone script or imported into the main application.
"""

import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from backup_db import backup_all_databases, cleanup_old_backups
from config import BASE_DIR


class BackupScheduler:
    """Automated backup scheduler with configurable intervals."""

    def __init__(
        self,
        backup_interval_hours: int = 6,
        cleanup_interval_days: int = 1,
        keep_backups_days: int = 7,
        backup_dir: Path = None,
    ):
        self.backup_interval = backup_interval_hours * 3600  # Convert to seconds
        self.cleanup_interval = cleanup_interval_days * 24 * 3600  # Convert to seconds
        self.keep_days = keep_backups_days
        self.backup_dir = backup_dir or (BASE_DIR / "backups")

        self._scheduler_thread = None
        self._stop_event = threading.Event()
        self._last_backup = 0
        self._last_cleanup = 0

        print("[BACKUP SCHEDULER] Configured:")
        print(f"  - Backup every {backup_interval_hours} hours")
        print(f"  - Cleanup every {cleanup_interval_days} days")
        print(f"  - Keep backups for {keep_backups_days} days")
        print(f"  - Backup directory: {self.backup_dir}")

    def start(self):
        """Start the backup scheduler in a background thread."""
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            print("[BACKUP SCHEDULER] Already running")
            return

        self._stop_event.clear()
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        print("[BACKUP SCHEDULER] ✅ Started")

    def stop(self):
        """Stop the backup scheduler."""
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            print("[BACKUP SCHEDULER] Stopping...")
            self._stop_event.set()
            self._scheduler_thread.join(timeout=5)
            print("[BACKUP SCHEDULER] ✅ Stopped")

    def _scheduler_loop(self):
        """Main scheduler loop."""
        while not self._stop_event.is_set():
            try:
                current_time = time.time()

                # Check if it's time for a backup
                if current_time - self._last_backup >= self.backup_interval:
                    self._perform_backup()
                    self._last_backup = current_time

                # Check if it's time for cleanup
                if current_time - self._last_cleanup >= self.cleanup_interval:
                    self._perform_cleanup()
                    self._last_cleanup = current_time

                # Sleep for 5 minutes before checking again
                self._stop_event.wait(300)  # 5 minutes

            except Exception as e:
                print(f"[BACKUP SCHEDULER] ❌ Error in scheduler loop: {e}")
                # Sleep before retrying
                self._stop_event.wait(60)  # 1 minute

    def _perform_backup(self):
        """Perform automated backup."""
        try:
            print(f"[BACKUP SCHEDULER] Starting scheduled backup at {datetime.now()}")
            backups = backup_all_databases(self.backup_dir)

            if backups:
                print(f"[BACKUP SCHEDULER] ✅ Backup completed: {len(backups)} files")
                for backup in backups:
                    size = backup.stat().st_size / 1024  # KB
                    print(f"[BACKUP SCHEDULER]   - {backup.name} ({size:.1f} KB)")
            else:
                print("[BACKUP SCHEDULER] ⚠️ No backups were created")

        except Exception as e:
            print(f"[BACKUP SCHEDULER] ❌ Backup failed: {e}")

    def _perform_cleanup(self):
        """Perform automated cleanup of old backups."""
        try:
            print(f"[BACKUP SCHEDULER] Starting cleanup at {datetime.now()}")
            cleanup_old_backups(self.backup_dir, self.keep_days)
            print("[BACKUP SCHEDULER] ✅ Cleanup completed")

        except Exception as e:
            print(f"[BACKUP SCHEDULER] ❌ Cleanup failed: {e}")

    def force_backup(self):
        """Force an immediate backup."""
        print("[BACKUP SCHEDULER] Forcing immediate backup...")
        self._perform_backup()
        self._last_backup = time.time()

    def force_cleanup(self):
        """Force an immediate cleanup."""
        print("[BACKUP SCHEDULER] Forcing immediate cleanup...")
        self._perform_cleanup()
        self._last_cleanup = time.time()

    def status(self) -> dict:
        """Get scheduler status."""
        is_running = self._scheduler_thread and self._scheduler_thread.is_alive()
        current_time = time.time()

        next_backup = None
        next_cleanup = None

        if is_running:
            next_backup_seconds = self.backup_interval - (current_time - self._last_backup)
            next_cleanup_seconds = self.cleanup_interval - (current_time - self._last_cleanup)

            if next_backup_seconds > 0:
                next_backup = datetime.now() + timedelta(seconds=next_backup_seconds)

            if next_cleanup_seconds > 0:
                next_cleanup = datetime.now() + timedelta(seconds=next_cleanup_seconds)

        return {
            "running": is_running,
            "last_backup": datetime.fromtimestamp(self._last_backup) if self._last_backup else None,
            "last_cleanup": datetime.fromtimestamp(self._last_cleanup)
            if self._last_cleanup
            else None,
            "next_backup": next_backup,
            "next_cleanup": next_cleanup,
            "backup_dir": str(self.backup_dir),
            "backup_interval_hours": self.backup_interval / 3600,
            "cleanup_interval_days": self.cleanup_interval / (24 * 3600),
            "keep_days": self.keep_days,
        }


# Global scheduler instance
_global_scheduler = None


def get_scheduler() -> BackupScheduler:
    """Get the global scheduler instance."""
    global _global_scheduler
    if _global_scheduler is None:
        # Configure from environment variables or defaults
        backup_hours = int(os.getenv("BACKUP_INTERVAL_HOURS", "6"))
        cleanup_days = int(os.getenv("CLEANUP_INTERVAL_DAYS", "1"))
        keep_days = int(os.getenv("KEEP_BACKUPS_DAYS", "7"))

        _global_scheduler = BackupScheduler(
            backup_interval_hours=backup_hours,
            cleanup_interval_days=cleanup_days,
            keep_backups_days=keep_days,
        )

    return _global_scheduler


def start_scheduler():
    """Start the global backup scheduler."""
    scheduler = get_scheduler()
    scheduler.start()

    # Register with shutdown handler
    try:
        import shutdown_handler

        shutdown_handler.register_cleanup(scheduler.stop)
        print("[BACKUP SCHEDULER] ✅ Registered with shutdown handler")
    except ImportError:
        print("[BACKUP SCHEDULER] ⚠️ Shutdown handler not available")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Automated backup scheduler")
    parser.add_argument("--backup-hours", type=int, default=6, help="Hours between backups")
    parser.add_argument("--cleanup-days", type=int, default=1, help="Days between cleanups")
    parser.add_argument("--keep-days", type=int, default=7, help="Days to keep backups")
    parser.add_argument("--backup-dir", type=Path, help="Backup directory")
    parser.add_argument("--run-once", action="store_true", help="Run backup once and exit")
    parser.add_argument("--status", action="store_true", help="Show scheduler status")

    args = parser.parse_args()

    if args.status:
        scheduler = get_scheduler()
        status = scheduler.status()
        print("\n=== Backup Scheduler Status ===")
        for key, value in status.items():
            print(f"{key}: {value}")
        exit(0)

    if args.run_once:
        print("Running one-time backup...")
        backup_dir = args.backup_dir or (BASE_DIR / "backups")
        backups = backup_all_databases(backup_dir)
        if backups:
            print(f"✅ Created {len(backups)} backup(s)")
        cleanup_old_backups(backup_dir, args.keep_days)
        exit(0)

    # Run scheduler continuously
    scheduler = BackupScheduler(
        backup_interval_hours=args.backup_hours,
        cleanup_interval_days=args.cleanup_days,
        keep_backups_days=args.keep_days,
        backup_dir=args.backup_dir,
    )

    scheduler.start()

    try:
        print("Backup scheduler running... Press Ctrl+C to stop")
        while True:
            time.sleep(60)
            # Optionally print status every hour
            if int(time.time()) % 3600 == 0:
                status = scheduler.status()
                print(
                    f"[STATUS] Next backup: {status['next_backup']}, Next cleanup: {status['next_cleanup']}"
                )
    except KeyboardInterrupt:
        print("\nStopping scheduler...")
        scheduler.stop()
        print("Scheduler stopped")
