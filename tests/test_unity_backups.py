"""Shared texture backup regressions, without reading or modifying game bundles."""

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from PIL import Image

from dialogs.character_edit_dialog import CharacterEditDialog
from pages.field import Field
from services.card_service import CardService
from services.character_service import CharacterService
from services.field_service import FieldService
from services.sleeve_service import SleeveService
from unity.unity_utils import bundle_exists, card_art_bundle, get_configured_packer
from util.enums import CardArtCoordinates


class UnityBackupTests(unittest.TestCase):
    def setUp(self):
        previous = Path.cwd()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.addCleanup(os.chdir, previous)
        os.environ["FLOOWANDEREEZE_DATA_DIR"] = folder.name
        os.environ["FLOOWANDEREEZE_CONFIG_DIR"] = folder.name
        self.addCleanup(lambda: os.environ.pop("FLOOWANDEREEZE_DATA_DIR", None))
        self.addCleanup(lambda: os.environ.pop("FLOOWANDEREEZE_CONFIG_DIR", None))
        os.chdir(folder.name)
        self.root = Path(folder.name)
        prepare = patch(
            "services.unity_service.prepare_environment",
            side_effect=lambda miss, bundle: str(
                self.root / ("streaming" if miss else "local") / bundle
            ),
        )
        prepare.start()
        self.addCleanup(prepare.stop)
        self.image = Image.new("RGBA", (3, 2), (10, 20, 30, 255))
        texture = SimpleNamespace(
            type=SimpleNamespace(name="Texture2D"),
            read=lambda: SimpleNamespace(image=self.image),
        )
        self.environment = SimpleNamespace(objects=[texture])

    def services(self):
        for service_type in (
            CardService,
            SleeveService,
            FieldService,
            CharacterService,
        ):
            service = service_type()
            service.bundle = "abcdef01"
            yield service

    def assert_backup(self, service):
        path = self.root / "backups" / service.subfolder / "abcdef01.png"
        with Image.open(path) as saved:
            self.assertEqual(saved.size, self.image.size)
            self.assertEqual(saved.tobytes(), self.image.tobytes())
        self.assertFalse((self.root / "images").exists())

    def test_backup_saves_original_texture_for_every_service(self):
        with patch("services.unity_service.unity_load", return_value=self.environment):
            for service in self.services():
                with self.subTest(asset=service.subfolder):
                    service.create_backup(service.bundle)
                    self.assert_backup(service)

    def test_backup_fallback_preserves_destination(self):
        for initial in (SimpleNamespace(objects=[]), FileNotFoundError("missing")):
            for service in self.services():
                with (
                    self.subTest(initial=initial, asset=service.subfolder),
                    patch(
                        "services.unity_service.unity_load",
                        side_effect=[initial, self.environment],
                    ) as load,
                    patch(
                        "services.unity_service.prepare_environment",
                        side_effect=["local-bundle", "streaming-bundle"],
                    ) as prepare,
                ):
                    service.create_backup(service.bundle)
                    self.assert_backup(service)
                    self.assertEqual(load.call_count, 2)
                    self.assertEqual(
                        prepare.call_args_list,
                        [call(False, service.bundle), call(True, service.bundle)],
                    )

    def test_explicit_streaming_backup_uses_requested_source(self):
        service = CardService()
        service.bundle = "abcdef01"
        with (
            patch("services.unity_service.unity_load", return_value=self.environment),
            patch("services.unity_service.prepare_environment") as prepare,
        ):
            service.create_backup(service.bundle, miss=True)
            prepare.assert_called_once_with(True, service.bundle)
            self.assert_backup(service)

    def test_missing_texture_stops_after_both_sources(self):
        service = CardService()
        service.bundle = "abcdef01"
        with patch(
            "services.unity_service.unity_load",
            return_value=SimpleNamespace(objects=[]),
        ) as load:
            with self.assertRaisesRegex(ValueError, "No Texture2D"):
                service.create_backup(service.bundle)
            self.assertEqual(load.call_count, 2)
        self.assertFalse((self.root / "backups").exists())

    def test_missing_files_stop_after_both_sources(self):
        service = CardService()
        service.bundle = "abcdef01"
        with patch(
            "services.unity_service.unity_load",
            side_effect=FileNotFoundError("missing"),
        ) as load:
            with self.assertRaises(FileNotFoundError):
                service.create_backup(service.bundle)
            self.assertEqual(load.call_count, 2)
        self.assertFalse((self.root / "backups").exists())

    def test_regular_extraction_still_uses_images_folder(self):
        service = CardService()
        service.bundle = "abcdef01"
        with patch("services.unity_service.unity_load", return_value=self.environment):
            service.extract_texture(service.bundle)
        self.assertTrue((self.root / "images/cards/abcdef01.png").is_file())
        self.assertFalse((self.root / "backups").exists())

    def field_page(self):
        service = FieldService()
        service.bundle = "medium01"
        service.image_path = "replacement.png"
        return SimpleNamespace(
            service=service,
            selected=SimpleNamespace(
                id=1, small_bundle="small001", medium_bundle="medium01", has_backup=True
            ),
            model=MagicMock(),
            current=MagicMock(),
        )

    def character_dialog(self, has_backup=False):
        service = CharacterService()
        service.image_path = "replacement.png"
        dialog = SimpleNamespace(
            service=service,
            character=SimpleNamespace(has_backup=has_backup),
            selected_asset_bundle=None,
            current_preview=MagicMock(),
            asset_list=MagicMock(),
            asset_error_label=MagicMock(),
            image_error_label=MagicMock(),
        )
        dialog._selected_bundles = lambda: [dialog.selected_asset_bundle]
        dialog._run_asset_action = lambda title, action: (
            CharacterEditDialog._run_asset_action(dialog, title, action)
        )
        return dialog

    def test_character_replacement_backs_up_each_asset_and_preserves_originals(self):
        dialog = self.character_dialog()
        originals = {}

        def replace():
            path = self.root / "backups/characters" / f"{dialog.service.bundle}.png"
            self.assertTrue(path.is_file())
            if path in originals:
                self.assertEqual(path.read_bytes(), originals[path])
            originals[path] = path.read_bytes()

        with (
            patch(
                "dialogs.character_edit_dialog.APP_CONFIG",
                SimpleNamespace(create_backup=True),
            ),
            patch("dialogs.character_edit_dialog.session"),
            patch("dialogs.character_edit_dialog.fetch_bundle_thumb"),
            patch("dialogs.character_edit_dialog.notify") as notified,
            patch(
                "services.unity_service.unity_load", return_value=self.environment
            ) as load,
            patch.object(
                dialog.service, "replace_bundle", side_effect=replace
            ) as write,
        ):
            for bundle in ("abcdef01", "abcdef02", "abcdef01", "abcdef02"):
                dialog.selected_asset_bundle = dialog.service.bundle = bundle
                CharacterEditDialog._replace_asset(dialog)
                self.image = Image.new("RGBA", (3, 2), (50, 60, 70, 255))
            self.assertEqual(len(originals), 2)
            self.assertEqual(load.call_count, 2)
            self.assertEqual(write.call_count, 4)
            self.assertTrue(dialog.character.has_backup)
            notified.assert_called()

            (self.root / "backups/characters/abcdef02.png").unlink()
            write.side_effect = None
            CharacterEditDialog._replace_asset(dialog)
            self.assertEqual(load.call_count, 3)
            self.assertTrue((self.root / "backups/characters/abcdef02.png").is_file())
            notified.assert_called()

    def test_character_replacement_respects_disabled_backups(self):
        dialog = self.character_dialog()
        dialog.selected_asset_bundle = dialog.service.bundle = "abcdef01"
        with (
            patch(
                "dialogs.character_edit_dialog.APP_CONFIG",
                SimpleNamespace(create_backup=False),
            ),
            patch("dialogs.character_edit_dialog.session") as session,
            patch("dialogs.character_edit_dialog.notify"),
            patch("dialogs.character_edit_dialog.fetch_bundle_thumb"),
            patch.object(dialog.service, "create_backup") as backup,
            patch.object(dialog.service, "replace_bundle") as write,
        ):
            CharacterEditDialog._replace_asset(dialog)
            backup.assert_not_called()
            write.assert_called_once()
            session.commit.assert_not_called()
            self.assertFalse(dialog.character.has_backup)

    def test_character_backup_failure_prevents_replacement(self):
        dialog = self.character_dialog(has_backup=True)
        dialog.selected_asset_bundle = dialog.service.bundle = "abcdef02"
        with (
            patch(
                "dialogs.character_edit_dialog.APP_CONFIG",
                SimpleNamespace(create_backup=True),
            ),
            patch("dialogs.character_edit_dialog.session") as session,
            patch("dialogs.character_edit_dialog.notify") as notified,
            patch(
                "services.unity_service.unity_load",
                side_effect=OSError("backup failed"),
            ),
            patch.object(dialog.service, "replace_bundle") as write,
        ):
            CharacterEditDialog._replace_asset(dialog)
            write.assert_not_called()
            session.commit.assert_not_called()
            notified.assert_called_once()
        self.assertFalse((self.root / "backups").exists())

    def test_field_replacement_backs_up_both_before_writing_and_keeps_originals(self):
        page = self.field_page()
        originals = {}

        def replace():
            for bundle in ("small001", "medium01"):
                path = self.root / "backups/fields" / f"{bundle}.png"
                self.assertTrue(path.is_file())
                if bundle in originals:
                    self.assertEqual(path.read_bytes(), originals[bundle])
                originals[bundle] = path.read_bytes()

        with (
            patch("pages.field.APP_CONFIG", SimpleNamespace(create_backup=True)),
            patch("pages.field.session") as session,
            patch("pages.field.notify"),
            patch("pages.field.fetch_field_thumb"),
            patch(
                "services.unity_service.unity_load", return_value=self.environment
            ) as load,
            patch.object(page.service, "replace_bundle", side_effect=replace) as write,
        ):
            Field._replace(page)
            self.assertEqual(write.call_count, 2)
            self.assertEqual(load.call_count, 2)
            page.model.set_backup_state.assert_called_once_with(1, True)
            session.commit.assert_called_once()
            Field._replace(page)
            self.assertEqual(write.call_count, 4)
            self.assertEqual(load.call_count, 2)

    def test_field_replacement_respects_disabled_backups(self):
        page = self.field_page()
        with (
            patch("pages.field.APP_CONFIG", SimpleNamespace(create_backup=False)),
            patch("pages.field.notify"),
            patch("pages.field.fetch_field_thumb"),
            patch.object(page.service, "create_backup") as backup,
            patch.object(page.service, "replace_bundle") as write,
        ):
            Field._replace(page)
            backup.assert_not_called()
            page.model.set_backup_state.assert_not_called()
            self.assertEqual(write.call_count, 2)

    def test_field_backup_failure_prevents_any_replacement_and_retry_keeps_backup(self):
        page = self.field_page()
        with (
            patch("pages.field.APP_CONFIG", SimpleNamespace(create_backup=True)),
            patch("pages.field.session") as session,
            patch("pages.field.notify") as notified,
            patch("pages.field.fetch_field_thumb"),
            patch(
                "services.unity_service.unity_load",
                side_effect=[self.environment, OSError("backup failed")],
            ),
            patch.object(page.service, "replace_bundle") as write,
        ):
            Field._replace(page)
            notified.assert_called_once()
            write.assert_not_called()
            page.model.set_backup_state.assert_not_called()
            session.commit.assert_not_called()
            original = (self.root / "backups/fields/small001.png").read_bytes()
            with patch(
                "services.unity_service.unity_load", return_value=self.environment
            ) as load:
                Field._replace(page)
                load.assert_called_once()
            self.assertEqual(
                (self.root / "backups/fields/small001.png").read_bytes(), original
            )
            self.assertEqual(write.call_count, 2)

    def test_bundle_exists_checks_disk_without_loading(self):
        target = self.root / "ab" / "abcdef01"
        target.parent.mkdir(parents=True, exist_ok=True)
        with patch("unity.unity_utils.prepare_environment", return_value=str(target)):
            self.assertFalse(bundle_exists("abcdef01"))
            target.touch()
            self.assertTrue(bundle_exists("abcdef01"))

    def test_card_art_bundle_prefers_large_when_present(self):
        card = SimpleNamespace(
            large_bundle="large001", medium_bundle="medium01", unity_file=False
        )
        with patch("unity.unity_utils.bundle_exists", return_value=True):
            bundle, coords = card_art_bundle(card)
            self.assertEqual(bundle, "large001")
            self.assertIs(coords, CardArtCoordinates.LARGE)

    def test_card_art_bundle_falls_back_to_medium_when_hq_missing(self):
        card = SimpleNamespace(
            large_bundle="large001", medium_bundle="medium01", unity_file=False
        )
        with patch("unity.unity_utils.bundle_exists", return_value=False):
            bundle, coords = card_art_bundle(card)
            self.assertEqual(bundle, "medium01")
            self.assertIs(coords, CardArtCoordinates.MEDIUM)

    def test_card_replace_skips_missing_hq_bundle(self):
        replacement = self.root / "replacement.png"
        self.image.save(replacement)
        service = CardService()
        service.bundle = "medium01"
        service.image_path = str(replacement)
        card = SimpleNamespace(
            small_bundle="small001",
            medium_bundle="medium01",
            large_bundle="large001",
            unity_file=False,
        )
        written = []

        def fake_load(path):
            written.append(Path(path).name)
            data = MagicMock()
            data.image = self.image.copy()
            texture = SimpleNamespace(
                type=SimpleNamespace(name="Texture2D"),
                read=lambda: data,
            )
            env = MagicMock()
            env.objects = [texture]
            env.file.save.return_value = b"bundle"
            return env

        real_open = open

        def fake_open(path, mode="r", *args, **kwargs):
            if "w" in mode and isinstance(path, str):
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            return real_open(path, mode, *args, **kwargs)

        query = MagicMock()
        query.filter.return_value.first.side_effect = [None, card]
        with (
            patch("services.card_service.session") as session,
            patch(
                "services.card_service.bundle_exists",
                side_effect=lambda bundle, miss=False: bundle != "large001",
            ),
            patch(
                "services.card_service.prepare_environment",
                side_effect=lambda miss, bundle: str(self.root / bundle),
            ),
            patch("services.card_service.unity_load", side_effect=fake_load),
            patch("services.card_service.APP_CONFIG") as config,
            patch("builtins.open", side_effect=fake_open),
        ):
            session.query.return_value = query
            config.mipmap_count = 1
            config.packer = "none"
            service.replace_bundle()
        self.assertEqual(sorted(written), ["medium01", "small001"])

    def test_get_configured_packer_normalizes_to_lowercase(self):
        self.assertEqual(get_configured_packer(SimpleNamespace(packer="LZ4")), "lz4")
        self.assertEqual(get_configured_packer(SimpleNamespace(packer="Lz4Hc")), "lz4hc")
        self.assertEqual(get_configured_packer(SimpleNamespace(packer="LZMA")), "lzma")
        self.assertEqual(get_configured_packer(SimpleNamespace(packer="NONE")), "none")
        self.assertEqual(get_configured_packer(SimpleNamespace(packer=None)), "lz4")
        self.assertEqual(get_configured_packer(None), "lz4")

    def test_migrations_normalize_uppercase_packer(self):
        import sqlite3
        from database.migrations import run_migrations

        db_file = self.root / "test_migration.db"
        conn = sqlite3.connect(str(db_file))
        c = conn.cursor()
        c.execute("CREATE TABLE app_config (id INTEGER PRIMARY KEY, packer VARCHAR(5))")
        c.execute("INSERT INTO app_config (id, packer) VALUES (1, 'LZ4')")
        conn.commit()
        conn.close()

        run_migrations(str(db_file))

        conn = sqlite3.connect(str(db_file))
        c = conn.cursor()
        c.execute("SELECT packer FROM app_config WHERE id = 1")
        row = c.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "lz4")

    def test_card_crop_coordinates_for_extracted_texture(self):
        service = CardService()
        med_img = Image.new("RGBA", (256, 256), (10, 20, 30, 255))
        cropped_med = service._process_extracted_image(med_img)
        self.assertEqual(cropped_med.size, (193, 132))

        large_img = Image.new("RGBA", (512, 512), (10, 20, 30, 255))
        cropped_large = service._process_extracted_image(large_img)
        self.assertEqual(cropped_large.size, (385, 265))

        small_img = Image.new("RGBA", (128, 128), (10, 20, 30, 255))
        cropped_small = service._process_extracted_image(small_img)
        self.assertEqual(cropped_small.size, (96, 66))

        other_img = Image.new("RGBA", (100, 100), (10, 20, 30, 255))
        preserved = service._process_extracted_image(other_img)
        self.assertEqual(preserved.size, (100, 100))

    def test_card_restore_migrates_legacy_full_texture_backup(self):
        service = CardService()
        service.bundle = "card001"
        backup_dir = self.root / "backups/cards"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / "card001.png"

        legacy_full = Image.new("RGBA", (256, 256), (1, 2, 3, 255))
        legacy_full.save(backup_file)

        observed_path = []

        def fake_replace():
            observed_path.append(service.image_path)

        with patch.object(service, "replace_bundle", side_effect=fake_replace) as mock_replace:
            restored = service.restore_asset()
            self.assertTrue(restored)
            mock_replace.assert_called_once()
            self.assertEqual(observed_path, [str(backup_file)])
            self.assertIsNone(service.image_path)

        with Image.open(backup_file) as migrated:
            self.assertEqual(migrated.size, (193, 132))


if __name__ == "__main__":
    unittest.main()
