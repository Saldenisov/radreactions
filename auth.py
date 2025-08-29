import json
from datetime import datetime
from pathlib import Path

import bcrypt
import streamlit as st


class UserManager:
    def __init__(self, users_file: str = "users.json"):
        self.users_file = Path(users_file)
        self.users_data = self._load_users()

    def _load_users(self) -> dict:
        """Load users from JSON file"""
        if self.users_file.exists():
            try:
                with open(self.users_file, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return self._create_default_users()
        else:
            return self._create_default_users()

    def _create_default_users(self) -> dict:
        """Create default users with initial passwords"""
        default_users = {
            "saldenisov": {
                "password": self._hash_password("default_pass"),
                "email": "",
                "contact_info": {"phone": "", "department": "", "institution": ""},
                "created_at": datetime.now().isoformat(),
                "last_login": None,
                "password_changed": False,
            },
            "zhiwenjiang": {
                "password": self._hash_password("default_pass"),
                "email": "",
                "contact_info": {"phone": "", "department": "", "institution": ""},
                "created_at": datetime.now().isoformat(),
                "last_login": None,
                "password_changed": False,
            },
            "jplarbre": {
                "password": self._hash_password("default_pass"),
                "email": "",
                "contact_info": {"phone": "", "department": "", "institution": ""},
                "created_at": datetime.now().isoformat(),
                "last_login": None,
                "password_changed": False,
            },
        }
        self._save_users(default_users)
        return default_users

    def _save_users(self, users_data: dict):
        """Save users to JSON file"""
        with open(self.users_file, "w", encoding="utf-8") as f:
            json.dump(users_data, f, indent=2, ensure_ascii=False)
        self.users_data = users_data

    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def _verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    def authenticate_user(self, username: str, password: str) -> tuple[bool, str]:
        """Authenticate user login"""
        if username not in self.users_data:
            return False, "Username not found"

        user = self.users_data[username]
        if self._verify_password(password, user["password"]):
            # Update last login
            user["last_login"] = datetime.now().isoformat()
            self._save_users(self.users_data)
            return True, "Login successful"
        else:
            return False, "Invalid password"

    def change_password(
        self, username: str, old_password: str, new_password: str
    ) -> tuple[bool, str]:
        """Change user password"""
        if username not in self.users_data:
            return False, "User not found"

        user = self.users_data[username]
        if not self._verify_password(old_password, user["password"]):
            return False, "Current password is incorrect"

        if len(new_password) < 8:
            return False, "New password must be at least 8 characters long"

        # Update password
        user["password"] = self._hash_password(new_password)
        user["password_changed"] = True
        user["password_change_date"] = datetime.now().isoformat()
        self._save_users(self.users_data)
        return True, "Password changed successfully"

    def update_contact_info(self, username: str, contact_info: dict) -> tuple[bool, str]:
        """Update user contact information"""
        if username not in self.users_data:
            return False, "User not found"

        user = self.users_data[username]
        user["contact_info"].update(contact_info)
        if "email" in contact_info:
            user["email"] = contact_info["email"]

        self._save_users(self.users_data)
        return True, "Contact information updated successfully"

    def get_user_info(self, username: str) -> dict | None:
        """Get user information"""
        if username in self.users_data:
            user_data = self.users_data[username].copy()
            # Remove sensitive information
            user_data.pop("password", None)
            return user_data
        return None

    def get_all_users(self) -> dict:
        """Get all users (without passwords)"""
        users = {}
        for username, user_data in self.users_data.items():
            user_copy = user_data.copy()
            user_copy.pop("password", None)
            users[username] = user_copy
        return users

    def send_registration_request(
        self, requested_username: str, email: str, justification: str
    ) -> tuple[bool, str]:
        """Send registration request email"""
        try:
            # In a real implementation, you would configure SMTP settings
            # For now, we'll just log the request
            request_data = {
                "requested_username": requested_username,
                "email": email,
                "justification": justification,
                "request_date": datetime.now().isoformat(),
            }

            # Save request to file for admin review
            requests_file = Path("registration_requests.json")
            if requests_file.exists():
                with open(requests_file, encoding="utf-8") as f:
                    requests = json.load(f)
            else:
                requests = []

            requests.append(request_data)
            with open(requests_file, "w", encoding="utf-8") as f:
                json.dump(requests, f, indent=2, ensure_ascii=False)

            return (
                True,
                "Registration request sent. Please contact sergey.denisov@universite-paris-saclay.fr for approval.",
            )
        except Exception as e:
            return False, f"Failed to send registration request: {str(e)}"


# Initialize user manager
user_manager = UserManager()


def check_authentication() -> str | None:
    """Check if user is authenticated"""
    # Console debug statements
    print("[AUTH DEBUG] check_authentication() called")
    print(f"[AUTH DEBUG] Session state keys: {list(st.session_state.keys())}")
    print(
        f"[AUTH DEBUG] authenticated_user: {st.session_state.get('authenticated_user', 'NOT_SET')}"
    )
    print(
        f"[AUTH DEBUG] authentication_status: {st.session_state.get('authentication_status', 'NOT_SET')}"
    )

    result = st.session_state.get("authenticated_user", None)
    print(f"[AUTH DEBUG] check_authentication() returning: {result}")
    return result


def login_user(username: str):
    """Log in user and set session state"""
    st.session_state.authenticated_user = username
    st.session_state.authentication_status = True


def logout_user():
    """Log out user and clear session state"""
    if "authenticated_user" in st.session_state:
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
                success, message = user_manager.authenticate_user(username, password)
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
                    success, message = user_manager.send_registration_request(
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

    user_info = user_manager.get_user_info(current_user)
    if not user_info:
        st.error("User information not found")
        return

    # User information display
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Account Information")
        st.write(f"**Username:** {current_user}")
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
                success, message = user_manager.change_password(
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

    contact_info = user_info.get("contact_info", {})

    with st.form("contact_info_form"):
        email = st.text_input("Email", value=user_info.get("email", ""))
        phone = st.text_input("Phone", value=contact_info.get("phone", ""))
        department = st.text_input("Department", value=contact_info.get("department", ""))
        institution = st.text_input("Institution", value=contact_info.get("institution", ""))

        update_contact_btn = st.form_submit_button("Update Contact Information")

        if update_contact_btn:
            new_contact_info = {
                "email": email,
                "phone": phone,
                "department": department,
                "institution": institution,
            }
            success, message = user_manager.update_contact_info(current_user, new_contact_info)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

    # Logout button
    st.markdown("---")
    if st.button("🚪 Logout"):
        logout_user()
        st.rerun()
