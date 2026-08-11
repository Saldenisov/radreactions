# RadReactions Public

Public Streamlit interface for validated Buxton radiation-chemistry reactions, with
restricted access to the newer NIST-derived corpus.

## Runtime data

Data is not stored in Git. Railway mounts persistent data at `/data`; local runs use
`RAD_PUBLIC_DATA_DIR`.

Required:

- `reactions.db` — validated Buxton corpus. Opened read-only; absence is a hard error.
- `users.db` — local bcrypt user store. Created only for authentication state.

Optional:

- `new_db.sqlite` — restricted NIST-derived reactions.
- `public_problem_reports.db` — user-submitted reports and article suggestions.
- `public_usage_stats.db` — bounded aggregate telemetry.
- PDF and BibTeX exports configured through `RAD_PUBLIC_CLEAN_PDF`,
  `RAD_PUBLIC_DIRTY_PDF`, and `RAD_PUBLIC_BIBTEX`.

Override individual database paths with `USERS_DB_PATH`, `RAD_PUBLIC_NEW_DB`,
`RAD_PUBLIC_REPORTS_DB`, and `RAD_PUBLIC_USAGE_DB`.

## Security configuration

No default users or passwords are embedded in the application. To create one initial
administrator in a new `users.db`, set both variables before first start:

```bash
export RAD_PUBLIC_BOOTSTRAP_ADMIN_USERNAME=admin
export RAD_PUBLIC_BOOTSTRAP_ADMIN_PASSWORD='replace-with-at-least-12-characters'
```

Bootstrap does not replace an active user's password. Accounts retaining the retired
`default_pass` password are automatically deactivated; explicit bootstrap variables
can securely recover that inactive username. Remove bootstrap variables after account
creation or recovery.

Developer exports use `RAD_PUBLIC_ADMIN_PASSWORD`. The password is entered in the UI
and retained only in the current Streamlit session; it is never accepted through URL
query parameters.

Set a deployment-specific `RAD_USAGE_HASH_SALT` to store hashed IP/user-agent
identifiers. Without it, identifiers are discarded. `RAD_USAGE_RETENTION_DAYS`
defaults to 90 and is constrained to 1–365 days.

## Local development

```bash
python -m pip install -r requirements-dev.txt
export RAD_PUBLIC_DATA_DIR=/absolute/path/to/data
streamlit run public_app.py
```

```bash
python -m ruff check .
python -m pytest -q
python -m compileall -q *.py nist
```

## NIST ingestion

The provenance-first `nist/` package archives immutable request attempts and derives
canonical Detail state only from classified responses. It enforces the official NIST
Solution Kinetics host, a maximum five-record batch, at least 180 seconds between
requests, and at most 100 requests/day across separate CLI invocations.

Operational commands and the remaining migration boundary are documented in
[`docs/nist_ingestion.md`](docs/nist_ingestion.md). Current retrieval counts and the
1,720-row missing inventory are under
[`audit/nist_retrieval_2026-07-29/`](audit/nist_retrieval_2026-07-29/).

## Deployment

`Dockerfile`, `railway.json`, and `railway.toml` use the Streamlit health endpoint
`/_stcore/health`. Configure secrets in Railway, mount `/data`, and never bake runtime
databases or credentials into the image.
