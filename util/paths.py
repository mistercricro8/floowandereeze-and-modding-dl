"""Cross-platform directory management for Floowandereeze."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import platformdirs

logger = logging.getLogger(__name__)

APP_NAME = "Floowandereeze"
_migration_messages: list[str] = []


def get_config_dir() -> Path:
    """Return the standard cross-platform configuration directory."""
    override = os.environ.get("FLOOWANDEREEZE_CONFIG_DIR")
    if override:
        path = Path(override).resolve()
    else:
        path = Path(platformdirs.user_config_dir(APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_dir() -> Path:
    """Return the standard cross-platform user data directory."""
    override = os.environ.get("FLOOWANDEREEZE_DATA_DIR")
    if override:
        path = Path(override).resolve()
    else:
        path = Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_database_path() -> Path:
    """Return the SQLite database path, migrating legacy database.db if present."""
    data_dir = get_data_dir()
    db_file = data_dir / "database.db"
    if not db_file.exists():
        legacy_db = Path("database.db").resolve()
        if legacy_db.is_file() and legacy_db != db_file:
            try:
                shutil.copy2(legacy_db, db_file)
                logger.info(
                    "Migrated existing database from %s to %s", legacy_db, db_file
                )
                _migration_messages.append(
                    f"Migrated existing database to standard data folder: {data_dir}"
                )
            except OSError as error:
                logger.warning("Failed to copy legacy database: %s", error)
    return db_file


def get_backups_dir() -> Path:
    """Return the safety backups directory, migrating legacy backups folder if present."""
    backups_dir = get_data_dir() / "backups"
    if not backups_dir.exists():
        legacy_backups = Path("backups").resolve()
        if legacy_backups.is_dir() and legacy_backups != backups_dir:
            try:
                shutil.copytree(legacy_backups, backups_dir, dirs_exist_ok=True)
                logger.info(
                    "Migrated existing backups from %s to %s",
                    legacy_backups,
                    backups_dir,
                )
                _migration_messages.append(
                    f"Migrated existing backups to standard data folder: {backups_dir}"
                )
            except OSError as error:
                logger.warning("Failed to copy legacy backups: %s", error)
    return backups_dir


def get_bundles_dir() -> Path:
    """Return the directory used for exported game bundles."""
    return get_data_dir() / "bundles"


def get_images_dir() -> Path:
    """Return the directory used for extracted texture images."""
    return get_data_dir() / "images"


def pop_migration_message() -> str | None:
    """Return and clear any pending user migration notification message."""
    global _migration_messages
    if not _migration_messages:
        return None
    message = "\n".join(_migration_messages)
    _migration_messages = []
    return message


def check_and_migrate_legacy_data() -> str | None:
    """Ensure database and backups paths are evaluated and return any migration notice."""
    get_database_path()
    get_backups_dir()
    return pop_migration_message()
