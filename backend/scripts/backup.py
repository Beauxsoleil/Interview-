#!/usr/bin/env python3
"""Create a consistent, restrictive local backup of SQLite and uploaded audio."""
from __future__ import annotations

import os
import sqlite3
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Allow the documented `python scripts/backup.py` invocation from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings


def create_backup() -> Path:
    if not settings.database_url.startswith("sqlite:///"):
        raise RuntimeError("The bundled backup command supports SQLite installations only.")
    source_db = Path(settings.database_url.removeprefix("sqlite:///"))
    if not source_db.exists():
        raise RuntimeError(f"Database not found: {source_db}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = settings.backup_dir / f"interview-backup-{stamp}.tar.gz"
    with tempfile.TemporaryDirectory(prefix="interview-backup-") as temp_name:
        snapshot = Path(temp_name) / "app.db"
        with sqlite3.connect(source_db) as source, sqlite3.connect(snapshot) as target:
            source.backup(target)
        with tarfile.open(destination, "w:gz") as archive:
            archive.add(snapshot, arcname="app.db")
            if settings.audio_dir.exists():
                archive.add(settings.audio_dir, arcname="audio", recursive=True)
    os.chmod(destination, 0o600)

    backups = sorted(settings.backup_dir.glob("interview-backup-*.tar.gz"), reverse=True)
    for expired in backups[settings.backup_retention_count:]:
        expired.unlink()
    return destination


if __name__ == "__main__":
    print(create_backup())
