import importlib
import sys


def _load_auth(monkeypatch, data_dir, **environment):
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.delenv("BASE_DIR", raising=False)
    monkeypatch.delenv("USERS_DB_PATH", raising=False)
    for name, value in environment.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    for module_name in ("auth_db", "config"):
        sys.modules.pop(module_name, None)
    return importlib.import_module("auth_db")


def test_auth_does_not_create_hard_coded_users(monkeypatch, tmp_path):
    module = _load_auth(
        monkeypatch,
        tmp_path,
        RAD_PUBLIC_BOOTSTRAP_ADMIN_USERNAME=None,
        RAD_PUBLIC_BOOTSTRAP_ADMIN_PASSWORD=None,
    )

    with module.auth_db._connect() as con:
        assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_auth_bootstrap_is_explicit_and_auth_failure_is_generic(monkeypatch, tmp_path):
    module = _load_auth(
        monkeypatch,
        tmp_path,
        RAD_PUBLIC_BOOTSTRAP_ADMIN_USERNAME="bootstrap-admin",
        RAD_PUBLIC_BOOTSTRAP_ADMIN_PASSWORD="long-bootstrap-password",
    )

    with module.auth_db._connect() as con:
        row = con.execute("SELECT username, role FROM users").fetchone()
    assert dict(row) == {"username": "bootstrap-admin", "role": "admin"}
    assert module.auth_db.authenticate_user("missing", "nope") == (
        False,
        module.AUTH_FAILURE_MESSAGE,
    )
    assert module.auth_db.authenticate_user("bootstrap-admin", "wrong") == (
        False,
        module.AUTH_FAILURE_MESSAGE,
    )
    assert module.auth_db.authenticate_user("bootstrap-admin", "long-bootstrap-password")[0]


def test_legacy_default_password_account_is_disabled(monkeypatch, tmp_path):
    module = _load_auth(monkeypatch, tmp_path)
    path = tmp_path / "legacy-users.db"
    legacy_db = module.UserAuthDB(path)
    with legacy_db._connect() as con:
        con.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            ("legacy", legacy_db._hash_password("default_pass"), module._iso_now()),
        )

    migrated_db = module.UserAuthDB(path)
    with migrated_db._connect() as con:
        assert con.execute("SELECT is_active FROM users WHERE username = 'legacy'").fetchone()[0] == 0

    monkeypatch.setenv("RAD_PUBLIC_BOOTSTRAP_ADMIN_USERNAME", "legacy")
    monkeypatch.setenv("RAD_PUBLIC_BOOTSTRAP_ADMIN_PASSWORD", "replacement-password")
    recovered_db = module.UserAuthDB(path)
    assert recovered_db.authenticate_user("legacy", "replacement-password")[0]


def test_session_expiry_is_timezone_aware_utc(monkeypatch, tmp_path):
    module = _load_auth(
        monkeypatch,
        tmp_path,
        RAD_PUBLIC_BOOTSTRAP_ADMIN_USERNAME="bootstrap-admin",
        RAD_PUBLIC_BOOTSTRAP_ADMIN_PASSWORD="long-bootstrap-password",
    )

    token = module.auth_db.create_session_token("bootstrap-admin")
    with module.auth_db._connect() as con:
        stored_token, expires_at = con.execute(
            "SELECT token, expires_at FROM session_tokens"
        ).fetchone()
    assert stored_token != token
    assert expires_at.endswith("+00:00")
    assert module.auth_db.validate_session_token(token) == "bootstrap-admin"

    with module.auth_db._connect() as con:
        con.execute("UPDATE users SET is_active = 0 WHERE username = 'bootstrap-admin'")
    assert module.auth_db.validate_session_token(token) is None


def test_session_token_never_reads_query_parameters(monkeypatch, tmp_path):
    module = _load_auth(monkeypatch, tmp_path)
    assert "query_params" not in module.get_session_token.__code__.co_names
