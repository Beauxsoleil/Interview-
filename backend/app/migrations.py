"""Small, versioned SQLite migrations for existing local installations."""
from __future__ import annotations

from sqlalchemy import Engine, inspect, text


MIGRATIONS = (
    (1, "interviews", "audio_duration_seconds", "ALTER TABLE interviews ADD COLUMN audio_duration_seconds FLOAT"),
    (2, "transcripts", "revision", "ALTER TABLE transcripts ADD COLUMN revision INTEGER NOT NULL DEFAULT 1"),
    (3, "transcripts", "reviewed_at", "ALTER TABLE transcripts ADD COLUMN reviewed_at DATETIME"),
    (4, "transcripts", "edited_at", "ALTER TABLE transcripts ADD COLUMN edited_at DATETIME"),
    (5, "profiles", "source_transcript_revision", "ALTER TABLE profiles ADD COLUMN source_transcript_revision INTEGER"),
    (6, "sync_drafts", "source_transcript_revision", "ALTER TABLE sync_drafts ADD COLUMN source_transcript_revision INTEGER"),
    (7, "sync_logs", "request_id", "ALTER TABLE sync_logs ADD COLUMN request_id VARCHAR(64)"),
    (8, "interviews", "delete_requested", "ALTER TABLE interviews ADD COLUMN delete_requested BOOLEAN NOT NULL DEFAULT 0"),
    (9, "interviews", "is_combined", "ALTER TABLE interviews ADD COLUMN is_combined BOOLEAN NOT NULL DEFAULT 0"),
    (10, "interviews", "combined_parent_id", "ALTER TABLE interviews ADD COLUMN combined_parent_id INTEGER REFERENCES interviews(id) ON DELETE SET NULL"),
    (11, "interviews", "part_number", "ALTER TABLE interviews ADD COLUMN part_number INTEGER"),
    (12, "interviews", "combined_needs_rebuild", "ALTER TABLE interviews ADD COLUMN combined_needs_rebuild BOOLEAN NOT NULL DEFAULT 0"),
)


def apply_migrations(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
        ))
        applied = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}
        inspector = inspect(connection)
        for version, table, column, statement in MIGRATIONS:
            if version not in applied:
                columns = {item["name"] for item in inspector.get_columns(table)}
                if column not in columns:
                    connection.execute(text(statement))
                connection.execute(
                    text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                    {"version": version},
                )
