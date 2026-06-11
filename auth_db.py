import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

import bcrypt
import streamlit as st

try:
    # Prefer central data dir (mounted volume) for persistence alongside reactions.db
    from config import BASE_DIR as _DATA_DIR
except Exception:
    # Fallback to ./data under project root
    _DATA_DIR = Path(__file__).resolve().parent.parent / "data"
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


class UserAuthDB:
    """SQLite-based user authentication system with bcrypt password hashing

    The database path defaults to the persistent data directory, next to reactions.db:
      - If USERS_DB_PATH env var is set, it is used.
      - Else defaults to <DATA_DIR>/users.db where DATA_DIR is config.BASE_DIR.
    """

    def __init__(self, db_path: str | os.PathLike | None = None):
        # Resolve target path with persistence in mind
        env_path = os.getenv("USERS_DB_PATH")
        if db_path is not None:
            target = Path(db_path)
        elif env_path:
            target = Path(env_path)
        else:
            target = Path(_DATA_DIR) / "users.db"

        # One-time migration: if target doesn't exist but a legacy users.db exists in CWD/app, move it
        legacy_candidates = [
            Path.cwd() / "users.db",
            Path(__file__).resolve().parent / "users.db",
        ]
        if not target.exists():
            for cand in legacy_candidates:
                try:
                    if cand.exists() and cand.is_file():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        cand.replace(target)
                        break
                except Exception:
                    # Ignore migration errors; we'll initialize a fresh DB
                    pass

        # Ensure parent directory exists
        target.parent.mkdir(parents=True, exist_ok=True)

        self.db_path = target
        self.lock = threading.Lock()
        self._init_database()
        self._create_default_users()

    def _init_database(self):
        """Initialize the SQLite database with users table"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    email TEXT DEFAULT '',
                    phone TEXT DEFAULT '',
                    department TEXT DEFAULT '',
                    institution TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    last_login TEXT,
                    password_changed BOOLEAN DEFAULT FALSE,
                    password_change_date TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    role TEXT DEFAULT 'user'
                )
            """)

            # Create registration requests table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS registration_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    requested_username TEXT NOT NULL,
                    email TEXT NOT NULL,
                    justification TEXT NOT NULL,
                    request_date TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    processed_by TEXT,
                    processed_date TEXT
                )
            """)

            # Create session tokens table for persistent login
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

            conn.commit()

    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt with salt"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def _verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against bcrypt hash"""
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    def _create_default_users(self):
        """Create default users if they don't exist"""
        default_users = [
            {"username": "saldenisov", "password": "default_pass", "role": "admin"},
            {"username": "zhiwenjiang", "password": "default_pass", "role": "user"},
            {"username": "jplarbre", "password": "default_pass", "role": "user"},
        ]

        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                for user_data in default_users:
                    # Check if user already exists
                    cursor.execute(
                        "SELECT id FROM users WHERE username = ?", (user_data["username"],)
                    )
                    if cursor.fetchone() is None:
                        # Create user
                        password_hash = self._hash_password(user_data["password"])
                        cursor.execute(
                            """
                            INSERT INTO users (username, password_hash, created_at, role)
                            VALUES (?, ?, ?, ?)
                        """,
                            (
                                user_data["username"],
                                password_hash,
                                datetime.now().isoformat(),
                                user_data["role"],
                            ),
                        )
                        print(f"[AUTH DB] Created default user: {user_data['username']}")

                conn.commit()

    def authenticate_user(self, username: str, password: str) -> tuple[bool, str]:
        """Authenticate user login"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT password_hash, is_active FROM users
                    WHERE username = ?
                """,
                    (username,),
                )

                result = cursor.fetchone()
                if not result:
                    return False, "Username not found"

                password_hash, is_active = result

                if not is_active:
                    return False, "Account is disabled"

                if self._verify_password(password, password_hash):
                    # Update last login
                    cursor.execute(
                        """
                        UPDATE users SET last_login = ? WHERE username = ?
                    """,
                        (datetime.now().isoformat(), username),
                    )
                    conn.commit()
                    return True, "Login successful"
                else:
                    return False, "Invalid password"

    def change_password(
        self, username: str, old_password: str, new_password: str
    ) -> tuple[bool, str]:
        """Change user password"""
        if len(new_password) < 8:
            return False, "New password must be at least 8 characters long"

        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))

                result = cursor.fetchone()
                if not result:
                    return False, "User not found"

                if not self._verify_password(old_password, result[0]):
                    return False, "Current password is incorrect"

                # Update password
                new_password_hash = self._hash_password(new_password)
                cursor.execute(
                    """
                    UPDATE users SET
                        password_hash = ?,
                        password_changed = TRUE,
                        password_change_date = ?
                    WHERE username = ?
                """,
                    (new_password_hash, datetime.now().isoformat(), username),
                )

                conn.commit()
                return True, "Password changed successfully"

    def update_contact_info(self, username: str, contact_info: dict) -> tuple[bool, str]:
        """Update user contact information"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Build update query dynamically based on provided fields
                update_fields = []
                values = []

                for field in ["email", "phone", "department", "institution"]:
                    if field in contact_info:
                        update_fields.append(f"{field} = ?")
                        values.append(contact_info[field])

                if not update_fields:
                    return False, "No contact information provided"

                values.append(username)
                query = f"UPDATE users SET {', '.join(update_fields)} WHERE username = ?"

                cursor.execute(query, values)
                if cursor.rowcount == 0:
                    return False, "User not found"

                conn.commit()
                return True, "Contact information updated successfully"

    def get_user_info(self, username: str) -> dict | None:
        """Get user information (without password hash)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, username, email, phone, department, institution,
                       created_at, last_login, password_changed, password_change_date,
                       is_active, role
                FROM users WHERE username = ?
            """,
                (username,),
            )

            result = cursor.fetchone()
            if result:
                return dict(result)
            return None

    def get_all_users(self) -> list[dict]:
        """Get all users (without password hashes) - Admin function"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, username, email, phone, department, institution,
                       created_at, last_login, password_changed, password_change_date,
                       is_active, role
                FROM users ORDER BY created_at
            """)

            return [dict(row) for row in cursor.fetchall()]

    def create_user(
        self, username: str, password: str, email: str = "", role: str = "user"
    ) -> tuple[bool, str]:
        """Create new user - Admin function"""
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"

        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                try:
                    password_hash = self._hash_password(password)
                    cursor.execute(
                        """
                        INSERT INTO users (username, password_hash, email, created_at, role)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (username, password_hash, email, datetime.now().isoformat(), role),
                    )

                    conn.commit()
                    return True, f"User '{username}' created successfully"

                except sqlite3.IntegrityError:
                    return False, "Username already exists"

    def deactivate_user(self, username: str) -> tuple[bool, str]:
        """Deactivate user - Admin function"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET is_active = FALSE WHERE username = ?", (username,))

                if cursor.rowcount == 0:
                    return False, "User not found"

                conn.commit()
                return True, f"User '{username}' deactivated"

    def activate_user(self, username: str) -> tuple[bool, str]:
        """Activate user - Admin function"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET is_active = TRUE WHERE username = ?", (username,))

                if cursor.rowcount == 0:
                    return False, "User not found"

                conn.commit()
                return True, f"User '{username}' activated"

    def submit_registration_request(
        self, requested_username: str, email: str, justification: str
    ) -> tuple[bool, str]:
        """Submit registration request"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Check if username is already taken
                cursor.execute("SELECT id FROM users WHERE username = ?", (requested_username,))
                if cursor.fetchone():
                    return False, "Username already exists"

                # Check if there's already a pending request for this username
                cursor.execute(
                    """
                    SELECT id FROM registration_requests
                    WHERE requested_username = ? AND status = 'pending'
                """,
                    (requested_username,),
                )
                if cursor.fetchone():
                    return False, "Registration request for this username already pending"

                # Submit request
                cursor.execute(
                    """
                    INSERT INTO registration_requests (requested_username, email, justification, request_date)
                    VALUES (?, ?, ?, ?)
                """,
                    (requested_username, email, justification, datetime.now().isoformat()),
                )

                conn.commit()
                return True, "Registration request submitted successfully"

    def get_registration_requests(self, status: str = "pending") -> list[dict]:
        """Get registration requests - Admin function"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM registration_requests
                WHERE status = ? ORDER BY request_date
            """,
                (status,),
            )

            return [dict(row) for row in cursor.fetchall()]

    def process_registration_request(
        self, request_id: int, approve: bool, processed_by: str, password: str | None = None
    ) -> tuple[bool, str]:
        """Process registration request - Admin function"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Get request details
                cursor.execute("SELECT * FROM registration_requests WHERE id = ?", (request_id,))
                request = cursor.fetchone()
                if not request:
                    return False, "Registration request not found"

                if approve:
                    if not password or len(password) < 8:
                        return False, "Password must be at least 8 characters long"

                    # Create user
                    success, message = self.create_user(
                        request[1], password, request[2]
                    )  # username, password, email
                    if not success:
                        return False, f"Failed to create user: {message}"

                    status = "approved"
                else:
                    status = "rejected"

                # Update request status
                cursor.execute(
                    """
                    UPDATE registration_requests
                    SET status = ?, processed_by = ?, processed_date = ?
                    WHERE id = ?
                """,
                    (status, processed_by, datetime.now().isoformat(), request_id),
                )

                conn.commit()
                return True, f"Registration request {status}"

    def is_admin(self, username: str) -> bool:
        """Check if user has admin privileges"""
        user_info = self.get_user_info(username)
        return bool(user_info and user_info.get("role") == "admin")

    def is_super_admin(self, username: str) -> bool:
        """Check if user has super admin privileges (saldenisov only)"""
        return username == "saldenisov" and self.is_admin(username)

    def promote_to_admin(self, username: str) -> tuple[bool, str]:
        """Promote user to admin role - Super Admin function"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET role = 'admin' WHERE username = ?", (username,))

                if cursor.rowcount == 0:
                    return False, "User not found"

                conn.commit()
                return True, f"User '{username}' promoted to admin"

    def demote_from_admin(self, username: str) -> tuple[bool, str]:
        """Demote admin to user role - Super Admin function"""
        if username == "saldenisov":
            return False, "Cannot demote super admin"

        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET role = 'user' WHERE username = ?", (username,))

                if cursor.rowcount == 0:
                    return False, "User not found"

                conn.commit()
                return True, f"User '{username}' demoted to user"

    def reset_user_password(self, username: str, new_password: str) -> tuple[bool, str]:
        """Reset user password - Super Admin function"""
        if len(new_password) < 8:
            return False, "Password must be at least 8 characters long"

        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                new_password_hash = self._hash_password(new_password)
                cursor.execute(
                    """
                    UPDATE users SET
                        password_hash = ?,
                        password_changed = FALSE,
                        password_change_date = ?
                    WHERE username = ?
                """,
                    (new_password_hash, datetime.now().isoformat(), username),
                )

                if cursor.rowcount == 0:
                    return False, "User not found"

                conn.commit()
                return True, f"Password reset for user '{username}'"

    def get_database_stats(self) -> dict:
        """Get database statistics - Super Admin function"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # User statistics
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
            active_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            admin_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE last_login IS NOT NULL")
            users_with_login = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE password_changed = 1")
            users_changed_password = cursor.fetchone()[0]

            # Registration requests
            cursor.execute("SELECT COUNT(*) FROM registration_requests WHERE status = 'pending'")
            pending_requests = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM registration_requests")
            total_requests = cursor.fetchone()[0]

            return {
                "total_users": total_users,
                "active_users": active_users,
                "inactive_users": total_users - active_users,
                "admin_users": admin_users,
                "regular_users": total_users - admin_users,
                "users_with_login": users_with_login,
                "users_never_logged_in": total_users - users_with_login,
                "users_changed_password": users_changed_password,
                "users_default_password": total_users - users_changed_password,
                "pending_registration_requests": pending_requests,
                "total_registration_requests": total_requests,
            }

    def execute_raw_query(self, query: str, params: tuple = ()) -> tuple[bool, str, list]:
        """Execute raw SQL query - Super Admin function (USE WITH CAUTION)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, params)

                if query.strip().upper().startswith("SELECT"):
                    results = [dict(row) for row in cursor.fetchall()]
                    return True, "Query executed successfully", results
                else:
                    conn.commit()
                    return (
                        True,
                        f"Query executed successfully. Rows affected: {cursor.rowcount}",
                        [],
                    )
        except Exception as e:
            return False, f"Query failed: {str(e)}", []

    def create_session_token(self, username: str) -> str:
        """Create a session token for persistent login"""
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now() + timedelta(days=30)).isoformat()

        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Clean up expired tokens for this user
                cursor.execute(
                    "DELETE FROM session_tokens WHERE username = ? OR expires_at < datetime('now')",
                    (username,),
                )
                # Create new token
                cursor.execute(
                    "INSERT INTO session_tokens (username, token, expires_at) VALUES (?, ?, ?)",
                    (username, token, expires_at),
                )
                conn.commit()
        return token

    def validate_session_token(self, token: str) -> str | None:
        """Validate a session token and return username if valid"""
        if not token:
            return None

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT username FROM session_tokens WHERE token = ? AND expires_at > datetime('now')",
                (token,),
            )
            result = cursor.fetchone()
            return result[0] if result else None

    def invalidate_session_token(self, token: str):
        """Invalidate a session token (logout)"""
        if not token:
            return

        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM session_tokens WHERE token = ?", (token,))
                conn.commit()

    def cleanup_expired_tokens(self):
        """Clean up expired tokens"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM session_tokens WHERE expires_at < datetime('now')")
                conn.commit()


# Initialize the database
auth_db = UserAuthDB()


# Cookie-based persistent authentication
def get_session_token() -> str | None:
    """Get session token from cookies"""
    try:
        # Try to get from query params first (for initial login redirect)
        query_params = st.query_params
        if "token" in query_params:
            token = query_params["token"]
            # Clear token from URL
            st.query_params.clear()
            return token

        # Fallback to session state (acts as cookie substitute)
        return st.session_state.get("session_token")
    except Exception:
        return None


def set_session_token(token: str):
    """Set session token in cookies"""
    st.session_state.session_token = token


def clear_session_token():
    """Clear session token from cookies"""
    if "session_token" in st.session_state:
        del st.session_state.session_token


# Streamlit session state management functions
def check_authentication() -> str | None:
    """Check if user is authenticated using persistent tokens"""
    # Console debug statements
    print("[AUTH DEBUG] check_authentication() called")

    # First check session state for quick access
    if "authenticated_user" in st.session_state:
        username = st.session_state.get("authenticated_user")
        print(f"[AUTH DEBUG] Found user in session state: {username}")
        return username

    # Check for persistent session token
    token = get_session_token()
    if token:
        print("[AUTH DEBUG] Found session token, validating...")
        username = auth_db.validate_session_token(token)
        if username:
            print(f"[AUTH DEBUG] Token valid for user: {username}")
            # Restore session state
            st.session_state.authenticated_user = username
            st.session_state.authentication_status = True
            return username
        else:
            print("[AUTH DEBUG] Token invalid or expired")
            clear_session_token()

    print("[AUTH DEBUG] No valid authentication found")
    return None


def login_user(username: str):
    """Log in user and set session state with persistent token"""
    # Create persistent session token
    token = auth_db.create_session_token(username)
    set_session_token(token)

    # Set session state
    st.session_state.authenticated_user = username
    st.session_state.authentication_status = True
    print(f"[AUTH DEBUG] User {username} logged in successfully with persistent token")


def logout_user():
    """Log out user and clear session state and tokens"""
    # Invalidate persistent session token
    token = get_session_token()
    if token:
        auth_db.invalidate_session_token(token)
        clear_session_token()

    # Clear session state
    if "authenticated_user" in st.session_state:
        print(f"[AUTH DEBUG] Logging out user: {st.session_state.authenticated_user}")
        del st.session_state.authenticated_user
    if "authentication_status" in st.session_state:
        del st.session_state.authentication_status


def require_authentication():
    """Decorator/function to require authentication"""
    if not check_authentication():
        st.error("Please log in to access this application")
        show_login_page()
        st.stop()


def show_login_page():
    """Display login form"""
    st.title("🔐 Login to OCR Validator")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")

        if submit_button:
            if username and password:
                success, message = auth_db.authenticate_user(username, password)
                if success:
                    login_user(username)
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.error("Please enter both username and password")

    st.markdown("---")
    st.markdown("### New User Registration")
    st.markdown(
        "To request a new account, please email **sergey.denisov@universite-paris-saclay.fr** with:"
    )
    st.markdown("- Requested username")
    st.markdown("- Your institutional email")
    st.markdown("- Justification for access")

    with st.expander("Or submit registration request here"):
        with st.form("registration_form"):
            reg_username = st.text_input("Requested Username")
            reg_email = st.text_input("Your Email")
            reg_justification = st.text_area("Justification for Access")
            reg_submit = st.form_submit_button("Submit Registration Request")

            if reg_submit:
                if reg_username and reg_email and reg_justification:
                    success, message = auth_db.submit_registration_request(
                        reg_username, reg_email, reg_justification
                    )
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                else:
                    st.error("Please fill in all fields")


def show_user_profile_page():
    """Display user profile management page"""
    current_user = check_authentication()
    if not current_user:
        show_login_page()
        return

    st.title(f"👤 Profile: {current_user}")

    user_info = auth_db.get_user_info(current_user)
    if not user_info:
        st.error("User information not found")
        return

    # User information display
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Account Information")
        st.write(f"**Username:** {current_user}")
        st.write(f"**Role:** {user_info.get('role', 'user')}")
        st.write(f"**Created:** {user_info.get('created_at', 'Unknown')}")
        st.write(f"**Last Login:** {user_info.get('last_login', 'Never')}")

    with col2:
        st.subheader("Password Status")
        password_changed = user_info.get("password_changed", False)
        if password_changed:
            st.success("✅ Custom password set")
            st.write(f"**Changed:** {user_info.get('password_change_date', 'Unknown')}")
        else:
            st.warning("⚠️ Using default password - please change it")

    # Password change form
    st.markdown("---")
    st.subheader("🔑 Change Password")
    with st.form("password_change_form"):
        current_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        change_password_btn = st.form_submit_button("Change Password")

        if change_password_btn:
            if not all([current_password, new_password, confirm_password]):
                st.error("Please fill in all password fields")
            elif new_password != confirm_password:
                st.error("New passwords do not match")
            else:
                success, message = auth_db.change_password(
                    current_user, current_password, new_password
                )
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

    # Contact information form
    st.markdown("---")
    st.subheader("📞 Contact Information")

    with st.form("contact_info_form"):
        email = st.text_input("Email", value=user_info.get("email", ""))
        phone = st.text_input("Phone", value=user_info.get("phone", ""))
        department = st.text_input("Department", value=user_info.get("department", ""))
        institution = st.text_input("Institution", value=user_info.get("institution", ""))

        update_contact_btn = st.form_submit_button("Update Contact Information")

        if update_contact_btn:
            new_contact_info = {
                "email": email,
                "phone": phone,
                "department": department,
                "institution": institution,
            }
            success, message = auth_db.update_contact_info(current_user, new_contact_info)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

    # Admin panel (if user is admin)
    if auth_db.is_admin(current_user):
        st.markdown("---")
        st.subheader("🔧 Admin Panel")

        if auth_db.is_super_admin(current_user):
            admin_tab1, admin_tab2, admin_tab3, admin_tab4, admin_tab5 = st.tabs(
                ["Users", "Registration Requests", "Create User", "Super Admin", "Database"]
            )
        else:
            admin_tab1, admin_tab2, admin_tab3 = st.tabs(
                ["Users", "Registration Requests", "Create User"]
            )

        with admin_tab1:
            st.write("**All Users:**")
            users = auth_db.get_all_users()
            for user in users:
                with st.expander(f"{user['username']} ({user['role']})"):
                    st.write(f"**Email:** {user['email']}")
                    st.write(f"**Active:** {user['is_active']}")
                    st.write(f"**Last Login:** {user['last_login'] or 'Never'}")

                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button(
                            "Deactivate", key=f"deact_{user['id']}", disabled=not user["is_active"]
                        ):
                            success, msg = auth_db.deactivate_user(user["username"])
                            if success:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                    with col_b:
                        if st.button(
                            "Activate", key=f"act_{user['id']}", disabled=user["is_active"]
                        ):
                            success, msg = auth_db.activate_user(user["username"])
                            if success:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

        with admin_tab2:
            st.write("**Pending Registration Requests:**")
            requests = auth_db.get_registration_requests()
            for req in requests:
                with st.expander(f"{req['requested_username']} - {req['email']}"):
                    st.write(f"**Justification:** {req['justification']}")
                    st.write(f"**Requested:** {req['request_date']}")

                    with st.form(f"process_req_{req['id']}"):
                        temp_password = st.text_input(
                            "Temporary Password", type="password", key=f"pwd_{req['id']}"
                        )
                        col_approve, col_reject = st.columns(2)

                        with col_approve:
                            approve = st.form_submit_button("✅ Approve")
                        with col_reject:
                            reject = st.form_submit_button("❌ Reject")

                        if approve:
                            if temp_password:
                                success, msg = auth_db.process_registration_request(
                                    req["id"], True, current_user, temp_password
                                )
                                if success:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                            else:
                                st.error("Please provide a temporary password")

                        if reject:
                            success, msg = auth_db.process_registration_request(
                                req["id"], False, current_user
                            )
                            if success:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

        with admin_tab3:
            st.write("**Create New User:**")
            with st.form("create_user_form"):
                new_username = st.text_input("Username")
                new_email = st.text_input("Email")
                new_password = st.text_input("Password", type="password")
                new_role = st.selectbox("Role", ["user", "admin"])
                create_user_btn = st.form_submit_button("Create User")

                if create_user_btn:
                    if new_username and new_password:
                        success, message = auth_db.create_user(
                            new_username, new_password, new_email, new_role
                        )
                        if success:
                            st.success(message)
                        else:
                            st.error(message)
                    else:
                        st.error("Username and password are required")

        # Super Admin Panel (only for saldenisov)
        if auth_db.is_super_admin(current_user):
            with admin_tab4:
                st.write("**🔥 Super Admin Controls (saldenisov only):**")
                st.warning(
                    "⚠️ These functions can modify user roles and passwords. Use with caution."
                )

                # Role Management
                st.subheader("Role Management")
                users = auth_db.get_all_users()
                for user in users:
                    if user["username"] != "saldenisov":  # Can't modify super admin
                        with st.expander(f"Manage {user['username']} ({user['role']})"):
                            col_promote, col_demote, col_reset = st.columns(3)

                            with col_promote:
                                if st.button(
                                    "Promote to Admin",
                                    key=f"promote_{user['id']}",
                                    disabled=user["role"] == "admin",
                                ):
                                    success, msg = auth_db.promote_to_admin(user["username"])
                                    if success:
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(msg)

                            with col_demote:
                                if st.button(
                                    "Demote to User",
                                    key=f"demote_{user['id']}",
                                    disabled=user["role"] == "user",
                                ):
                                    success, msg = auth_db.demote_from_admin(user["username"])
                                    if success:
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(msg)

                            with col_reset:
                                with st.form(f"reset_password_{user['id']}"):
                                    new_pwd = st.text_input(
                                        "New Password", type="password", key=f"newpwd_{user['id']}"
                                    )
                                    if st.form_submit_button("Reset Password"):
                                        if new_pwd:
                                            success, msg = auth_db.reset_user_password(
                                                user["username"], new_pwd
                                            )
                                            if success:
                                                st.success(msg)
                                                st.rerun()
                                            else:
                                                st.error(msg)
                                        else:
                                            st.error("Please enter a new password")

            with admin_tab5:
                st.write("**📊 Database Management:**")

                # Database Statistics
                st.subheader("Database Statistics")
                stats = auth_db.get_database_stats()

                col_stats1, col_stats2 = st.columns(2)
                with col_stats1:
                    st.metric("Total Users", stats["total_users"])
                    st.metric("Active Users", stats["active_users"])
                    st.metric("Admin Users", stats["admin_users"])
                    st.metric("Users with Login", stats["users_with_login"])

                with col_stats2:
                    st.metric("Inactive Users", stats["inactive_users"])
                    st.metric("Regular Users", stats["regular_users"])
                    st.metric("Changed Passwords", stats["users_changed_password"])
                    st.metric("Pending Requests", stats["pending_registration_requests"])

                # Admin: Resync from JSON
                st.markdown("---")
                st.subheader("🔄 Admin: Resync from JSON")
                st.caption(
                    "Run a one-off sync that imports validated TSV/CSV and updates validation flags. A dry-run will only scan for issues."
                )
                # Show BASE_DIR for verification
                try:
                    from config import BASE_DIR as _BASE_DIR

                    st.code(f"BASE_DIR = {_BASE_DIR}")
                except Exception:
                    st.warning("Could not resolve BASE_DIR")
                # Per-table filter
                table_choice = st.selectbox(
                    "Table(s)",
                    options=["All", 5, 6, 7, 8, 9],
                    format_func=lambda x: {
                        "All": "All Tables",
                        5: "Table 5",
                        6: "Table 6",
                        7: "Table 7",
                        8: "Table 8",
                        9: "Table 9",
                    }.get(x, str(x)),
                )
                chosen_tables = (5, 6, 7, 8, 9) if table_choice == "All" else (int(table_choice),)
                col_sync_btn, col_dry_btn = st.columns([1, 1])
                with col_sync_btn:
                    do_sync = st.button("Admin: Resync from JSON", type="primary")
                with col_dry_btn:
                    do_dry = st.button("Dry-run scan (no writes)")
                if do_sync or do_dry:
                    try:
                        from import_reactions import sync_validations_to_db

                        st.info("⏳ Running sync... check console logs for details")
                        summary = sync_validations_to_db(
                            table_numbers=chosen_tables, dry_run=bool(do_dry)
                        )
                        if do_dry:
                            st.info("Dry-run complete. No changes were written.")
                        else:
                            st.success(
                                f"Updated {summary['updated_total']} reactions; imported {summary['imported_total']} sources"
                            )
                        issues = summary.get("issues", [])
                        if issues:
                            st.warning(
                                f"Detected {len(issues)} issue(s) during sync. Expand items below to review."
                            )
                            # Small banner list of common issues first
                            missing = [i for i in issues if i.get("issue") == "missing_source_file"]
                            no_rows = [i for i in issues if i.get("issue") == "no_rows_updated"]
                            if missing:
                                st.warning(
                                    f"{len(missing)} image(s) validated but TSV/CSV not found by stem. Check filenames and locations."
                                )
                            if no_rows:
                                st.warning(
                                    f"{len(no_rows)} source(s) updated but 0 DB rows changed. Possible path mismatch."
                                )
                            # Detailed expandable items
                            for idx, it in enumerate(issues, 1):
                                with st.expander(
                                    f"Issue {idx}: {it.get('issue', 'unknown')} | Table {it.get('table_no', '?')}"
                                ):
                                    st.json(it)
                        else:
                            st.info("No issues detected.")
                    except Exception as e:
                        st.error(f"Sync failed to execute: {e}")

                # Raw SQL Query Interface
                st.markdown("---")
                st.subheader("🔧 Raw SQL Query Interface")
                st.warning("⚠️ DANGER ZONE: Direct database access. Use only if you know SQL!")

                with st.form("sql_query_form"):
                    sql_query = st.text_area(
                        "SQL Query:", placeholder="SELECT * FROM users;", height=100
                    )

                    col_execute, col_examples = st.columns([1, 2])
                    with col_execute:
                        execute_query = st.form_submit_button("Execute Query")

                    with col_examples:
                        st.write("**Common queries:**")
                        st.code("SELECT * FROM users;")
                        st.code("SELECT username, role, is_active FROM users;")
                        st.code("SELECT * FROM registration_requests;")

                    if execute_query and sql_query.strip():
                        success, message, results = auth_db.execute_raw_query(sql_query.strip())

                        if success:
                            st.success(message)
                            if results:
                                st.dataframe(results)
                            else:
                                st.info("Query executed successfully (no results to display)")
                        else:
                            st.error(message)

                # Database File Info
                st.markdown("---")
                st.subheader("📁 Database File Information")
                db_path = auth_db.db_path
                if db_path.exists():
                    stat = db_path.stat()
                    st.write(f"**Database Path:** `{db_path}`")
                    st.write(f"**File Size:** {stat.st_size} bytes ({stat.st_size / 1024:.1f} KB)")
                    st.write(f"**Last Modified:** {datetime.fromtimestamp(stat.st_mtime)}")
                else:
                    st.error("Database file not found!")

                # Railway Console Access Instructions
                st.markdown("---")
                st.subheader("🚂 Railway Console Access")
                st.info(
                    "To access the database directly on Railway:\n\n"
                    "1. Go to your Railway dashboard\n"
                    "2. Open your service → Settings → Console\n"
                    "3. Run: `sqlite3 users.db`\n"
                    "4. Use SQL commands like `.tables`, `.schema users`, `SELECT * FROM users;`"
                )

    # Logout button
    st.markdown("---")
    if st.button("🚪 Logout"):
        logout_user()
        st.rerun()
