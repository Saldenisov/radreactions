"""Minimal local authentication store for restricted public data access."""

import hashlib
import os
import secrets
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import bcrypt
import streamlit as st

from config import BASE_DIR

AUTH_FAILURE_MESSAGE = "Invalid username or password"
SESSION_LIFETIME = timedelta(days=30)
_LEGACY_DEFAULT_PASSWORD = b"default_pass"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_now() -> str:
    return _utc_now().isoformat()


class UserAuthDB:
    """SQLite user store with bcrypt password hashes and server-side session tokens."""

    def __init__(self, db_path: str | os.PathLike[str] | None = None):
        configured_path = os.getenv("USERS_DB_PATH")
        self.db_path = Path(db_path or configured_path or BASE_DIR / "users.db").expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self._init_database()
        self._disable_legacy_default_passwords()
        self._bootstrap_admin_from_environment()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _init_database(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_login TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    role TEXT NOT NULL DEFAULT 'user'
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS session_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_tokens_token ON session_tokens(token)"
            )

    @staticmethod
    def _hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def _verify_password(password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _disable_legacy_default_passwords(self) -> None:
        """Disable accounts retaining a password from the retired insecure bootstrap."""
        with self.lock, self._connect() as con:
            rows = con.execute("SELECT id, password_hash FROM users WHERE is_active = 1").fetchall()
            compromised_ids = [
                int(row["id"])
                for row in rows
                if self._verify_password(_LEGACY_DEFAULT_PASSWORD.decode("utf-8"), row["password_hash"])
            ]
            con.executemany(
                "UPDATE users SET is_active = 0 WHERE id = ?",
                [(user_id,) for user_id in compromised_ids],
            )

    def _bootstrap_admin_from_environment(self) -> None:
        """Create one admin only when both explicit bootstrap variables are configured."""
        username = (os.getenv("RAD_PUBLIC_BOOTSTRAP_ADMIN_USERNAME") or "").strip()
        password = os.getenv("RAD_PUBLIC_BOOTSTRAP_ADMIN_PASSWORD") or ""
        if not username or not password:
            return
        if len(username) > 128 or len(password) < 12:
            return
        with self.lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO users (username, password_hash, created_at, role)
                VALUES (?, ?, ?, 'admin')
                ON CONFLICT(username) DO NOTHING
                """,
                (username, self._hash_password(password), _iso_now()),
            )

    def authenticate_user(self, username: str, password: str) -> tuple[bool, str]:
        """Authenticate without revealing whether username exists or is active."""
        with self.lock, self._connect() as con:
            row = con.execute(
                "SELECT password_hash, is_active FROM users WHERE username = ?", (username,)
            ).fetchone()
            if not row or not bool(row["is_active"]):
                return False, AUTH_FAILURE_MESSAGE
            if not self._verify_password(password, str(row["password_hash"])):
                return False, AUTH_FAILURE_MESSAGE
            con.execute("UPDATE users SET last_login = ? WHERE username = ?", (_iso_now(), username))
            return True, "Login successful"

    def create_session_token(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        token_digest = self._token_digest(token)
        expires_at = (_utc_now() + SESSION_LIFETIME).isoformat()
        with self.lock, self._connect() as con:
            con.execute("DELETE FROM session_tokens WHERE username = ?", (username,))
            con.execute(
                "INSERT INTO session_tokens (username, token, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (username, token_digest, expires_at, _iso_now()),
            )
        return token

    def validate_session_token(self, token: str) -> str | None:
        if not token:
            return None
        with self._connect() as con:
            row = con.execute(
                """
                SELECT st.username, st.expires_at
                FROM session_tokens AS st
                JOIN users AS u ON u.username = st.username
                WHERE st.token = ? AND u.is_active = 1
                """,
                (self._token_digest(token),),
            ).fetchone()
            if not row:
                return None
            try:
                expires_at = datetime.fromisoformat(str(row["expires_at"]))
            except ValueError:
                return None
            if expires_at.tzinfo is None or expires_at <= _utc_now():
                return None
            return str(row["username"])

    def invalidate_session_token(self, token: str) -> None:
        if not token:
            return
        with self.lock, self._connect() as con:
            con.execute("DELETE FROM session_tokens WHERE token = ?", (self._token_digest(token),))


auth_db = UserAuthDB()


def get_session_token() -> str | None:
    """Return token only from server-side Streamlit session state."""
    return st.session_state.get("session_token")


def set_session_token(token: str) -> None:
    st.session_state.session_token = token


def clear_session_token() -> None:
    st.session_state.pop("session_token", None)


def check_authentication() -> str | None:
    token = get_session_token()
    username = auth_db.validate_session_token(token) if token else None
    if username:
        st.session_state.authenticated_user = username
        return username
    clear_session_token()
    st.session_state.pop("authenticated_user", None)
    return None


def login_user(username: str) -> None:
    set_session_token(auth_db.create_session_token(username))
    st.session_state.authenticated_user = username


def logout_user() -> None:
    token = get_session_token()
    if token:
        auth_db.invalidate_session_token(token)
    clear_session_token()
    st.session_state.pop("authenticated_user", None)
