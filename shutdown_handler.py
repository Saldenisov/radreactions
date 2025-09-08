#!/usr/bin/env python3
"""
Graceful shutdown handler for RadReactions application.

Handles SIGTERM and SIGINT signals to cleanly close database connections
and perform cleanup before container shutdown.
"""

import atexit
import signal
import sys
import threading
import time

# Global shutdown flag
_shutdown_requested = threading.Event()
_cleanup_functions = []


def register_cleanup(func, *args, **kwargs):
    """Register a cleanup function to be called on shutdown."""
    _cleanup_functions.append((func, args, kwargs))


def cleanup_databases():
    """Close all database connections gracefully."""
    print("[SHUTDOWN] Closing database connections...")

    try:
        # Close reactions database connections
        from reactions_db import DB_PATH, connect

        # Force close any open connections by connecting and immediately closing
        if DB_PATH.exists():
            conn = connect(DB_PATH)
            try:
                # Perform checkpoint to ensure WAL is written to main DB
                conn.execute("PRAGMA wal_checkpoint(FULL)")
                conn.commit()
                print("[SHUTDOWN] ✅ Reactions database checkpoint completed")
            except Exception as e:
                print(f"[SHUTDOWN] ⚠️ Database checkpoint failed: {e}")
            finally:
                conn.close()

    except Exception as e:
        print(f"[SHUTDOWN] ⚠️ Error closing reactions database: {e}")

    try:
        # Close auth database connections
        from auth_db import auth_db

        # Cleanup expired tokens before shutdown
        auth_db.cleanup_expired_tokens()
        print("[SHUTDOWN] ✅ Auth database cleanup completed")

    except Exception as e:
        print(f"[SHUTDOWN] ⚠️ Error closing auth database: {e}")


def create_emergency_backup():
    """Create emergency backup on shutdown."""
    try:
        print("[SHUTDOWN] Creating emergency backup...")
        from backup_db import backup_all_databases
        from config import BASE_DIR

        emergency_dir = BASE_DIR / "emergency_backups"
        backups = backup_all_databases(emergency_dir)

        if backups:
            print(f"[SHUTDOWN] ✅ Emergency backup created: {len(backups)} files")
            for backup in backups:
                print(f"[SHUTDOWN]   - {backup}")
        else:
            print("[SHUTDOWN] ⚠️ No emergency backups created")

    except Exception as e:
        print(f"[SHUTDOWN] ⚠️ Emergency backup failed: {e}")


def graceful_shutdown(signum=None, frame=None):
    """Handle graceful shutdown."""
    signal_name = signal.Signals(signum).name if signum else "MANUAL"
    print(f"[SHUTDOWN] Received {signal_name}, initiating graceful shutdown...")

    if _shutdown_requested.is_set():
        print("[SHUTDOWN] Shutdown already in progress, ignoring...")
        return

    _shutdown_requested.set()

    try:
        # Run emergency backup
        create_emergency_backup()

        # Close databases
        cleanup_databases()

        # Run registered cleanup functions
        for func, args, kwargs in _cleanup_functions:
            try:
                print(f"[SHUTDOWN] Running cleanup: {func.__name__}")
                func(*args, **kwargs)
            except Exception as e:
                print(f"[SHUTDOWN] ⚠️ Cleanup function {func.__name__} failed: {e}")

        print("[SHUTDOWN] ✅ Graceful shutdown completed")

        # Small delay to ensure logs are written
        time.sleep(0.5)

    except Exception as e:
        print(f"[SHUTDOWN] ❌ Error during shutdown: {e}")

    finally:
        if signum:
            sys.exit(0)


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""
    # Handle SIGTERM (Docker stop)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    # Handle SIGINT (Ctrl+C)
    signal.signal(signal.SIGINT, graceful_shutdown)

    # Register atexit handler as fallback
    atexit.register(graceful_shutdown)

    print("[SHUTDOWN] ✅ Signal handlers registered")


def is_shutdown_requested():
    """Check if shutdown has been requested."""
    return _shutdown_requested.is_set()


# Auto-setup on import
if __name__ != "__main__":
    setup_signal_handlers()


if __name__ == "__main__":
    # Test the shutdown handler
    print("Testing shutdown handler... Press Ctrl+C to test")
    setup_signal_handlers()

    try:
        while not is_shutdown_requested():
            time.sleep(1)
            print("Application running... (Ctrl+C to test shutdown)")
    except KeyboardInterrupt:
        pass

    print("Shutdown test completed")
