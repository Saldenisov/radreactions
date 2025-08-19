# Validation data source of truth

As of this change, the SQLite database (reactions.db) is the single source of truth for validation status and metadata (validated_by, validated_at). Legacy JSON files data-full/table{5..9}/sub_tables_images/validation_db.json are no longer written to during validation. You can export JSON snapshots from the app sidebar when needed.

To avoid accidental overwrites in deployments (e.g., Railway), validation JSON files are ignored by Git via .gitignore entries:

**/validation_db.json
**/*_validation_db.json

Validation toggles in the UI now directly update the DB, and the Browse/Validated tabs read validator name and timestamp from the DB.

