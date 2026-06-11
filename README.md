# RadReactions Public

Minimal public Streamlit website for RadReactions.

Runtime data is not stored in Git. Railway mounts persistent data at `/data`.

Required volume files:

- `/data/reactions.db`
- `/data/users.db`
- `/data/new_reactions.sqlite`

Run locally:

```bash
RAD_PUBLIC_DATA_DIR=/path/to/data streamlit run public_app.py
```
