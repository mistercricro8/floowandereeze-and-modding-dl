"""Tests for cross-platform directory management and legacy data migration."""

import os
import tempfile
import unittest
from pathlib import Path

from util import paths


class PathsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)

        paths.pop_migration_message()

        self.orig_config = os.environ.get("FLOOWANDEREEZE_CONFIG_DIR")
        self.orig_data = os.environ.get("FLOOWANDEREEZE_DATA_DIR")

        def restore_env():
            if self.orig_config is not None:
                os.environ["FLOOWANDEREEZE_CONFIG_DIR"] = self.orig_config
            else:
                os.environ.pop("FLOOWANDEREEZE_CONFIG_DIR", None)
            if self.orig_data is not None:
                os.environ["FLOOWANDEREEZE_DATA_DIR"] = self.orig_data
            else:
                os.environ.pop("FLOOWANDEREEZE_DATA_DIR", None)

        self.addCleanup(restore_env)

    def test_environment_variable_overrides(self):
        custom_config = self.temp_path / "custom_config"
        custom_data = self.temp_path / "custom_data"
        os.environ["FLOOWANDEREEZE_CONFIG_DIR"] = str(custom_config)
        os.environ["FLOOWANDEREEZE_DATA_DIR"] = str(custom_data)

        self.assertEqual(paths.get_config_dir(), custom_config)
        self.assertEqual(paths.get_data_dir(), custom_data)
        self.assertTrue(custom_config.is_dir())
        self.assertTrue(custom_data.is_dir())

    def test_subdirectories_use_data_dir(self):
        custom_data = self.temp_path / "app_data"
        os.environ["FLOOWANDEREEZE_DATA_DIR"] = str(custom_data)

        self.assertEqual(paths.get_database_path(), custom_data / "database.db")
        self.assertEqual(paths.get_backups_dir(), custom_data / "backups")
        self.assertEqual(paths.get_bundles_dir(), custom_data / "bundles")
        self.assertEqual(paths.get_images_dir(), custom_data / "images")

    def test_legacy_database_migration(self):
        workspace = self.temp_path / "workspace"
        data_target = self.temp_path / "target_data"
        workspace.mkdir()
        data_target.mkdir()

        legacy_db = workspace / "database.db"
        legacy_db.write_text("sqlite-test-content", encoding="utf-8")

        cwd = os.getcwd()
        os.chdir(workspace)
        self.addCleanup(os.chdir, cwd)

        os.environ["FLOOWANDEREEZE_DATA_DIR"] = str(data_target)

        target_db = paths.get_database_path()
        self.assertEqual(target_db, data_target / "database.db")
        self.assertTrue(target_db.is_file())
        self.assertEqual(target_db.read_text(encoding="utf-8"), "sqlite-test-content")

        message = paths.pop_migration_message()
        self.assertIsNotNone(message)
        self.assertIn("Migrated existing database", message)
        # Message was cleared
        self.assertIsNone(paths.pop_migration_message())

    def test_legacy_backups_migration(self):
        workspace = self.temp_path / "workspace"
        data_target = self.temp_path / "target_data"
        workspace.mkdir()
        data_target.mkdir()

        legacy_backup_file = workspace / "backups" / "cards" / "test.png"
        legacy_backup_file.parent.mkdir(parents=True)
        legacy_backup_file.write_bytes(b"image-data")

        cwd = os.getcwd()
        os.chdir(workspace)
        self.addCleanup(os.chdir, cwd)

        os.environ["FLOOWANDEREEZE_DATA_DIR"] = str(data_target)

        target_backups = paths.get_backups_dir()
        self.assertEqual(target_backups, data_target / "backups")
        migrated_file = target_backups / "cards" / "test.png"
        self.assertTrue(migrated_file.is_file())
        self.assertEqual(migrated_file.read_bytes(), b"image-data")

        message = paths.pop_migration_message()
        self.assertIsNotNone(message)
        self.assertIn("Migrated existing backups", message)

    def test_check_and_migrate_legacy_data_returns_combined_alert(self):
        workspace = self.temp_path / "workspace"
        data_target = self.temp_path / "target_data"
        workspace.mkdir()
        data_target.mkdir()

        (workspace / "database.db").write_text("db", encoding="utf-8")
        legacy_card = workspace / "backups" / "cards" / "item.png"
        legacy_card.parent.mkdir(parents=True)
        legacy_card.write_bytes(b"data")

        cwd = os.getcwd()
        os.chdir(workspace)
        self.addCleanup(os.chdir, cwd)

        os.environ["FLOOWANDEREEZE_DATA_DIR"] = str(data_target)

        alert_message = paths.check_and_migrate_legacy_data()
        self.assertIsNotNone(alert_message)
        self.assertIn("Migrated existing database", alert_message)
        self.assertIn("Migrated existing backups", alert_message)
        self.assertIsNone(paths.check_and_migrate_legacy_data())
