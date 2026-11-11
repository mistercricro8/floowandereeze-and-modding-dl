"""Regression checks using an isolated database and offscreen Qt widgets."""

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_WORKSPACE = Path.cwd()
_TEMP = tempfile.TemporaryDirectory()
os.chdir(_TEMP.name)

from PySide6 import QtCore, QtGui, QtWidgets

_APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
QtCore.QSettings.setPath(
    QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, _TEMP.name
)

from database.migrations import run_migrations
from database.models import (
    CharacterAssetLayout,
    CharacterModel,
    FieldModel,
    SleeveModel,
)
from database.objects import engine, session
from pages.card import Card
from pages.character import Character
from pages.field import Field
from pages.main_window import MainWindow
from pages.models.character_list_model import CharacterListModel
from pages.models.field_list_model import FieldListModel
from pages.models.sleeve_list_model import SleeveListModel
from pages.sleeve import Sleeve
from services import update_service
from util import game_discovery
from util.constants import APP_CONFIG


def tearDownModule():
    session.close()
    engine.dispose()
    os.chdir(_WORKSPACE)
    _TEMP.cleanup()


class QualityOfLifeTests(unittest.TestCase):
    def setUp(self):
        session.rollback()
        session.add(APP_CONFIG)
        for model in (SleeveModel, FieldModel, CharacterModel, CharacterAssetLayout):
            session.query(model).delete()
        APP_CONFIG.game_path = ""
        APP_CONFIG.version = "2026-10-19"
        APP_CONFIG.metadata_repository = "Nauder/floowandereeze-and-modding-etl-dl"
        APP_CONFIG.metadata_branch = ""
        APP_CONFIG.metadata_last_source = None
        session.commit()
        self.thumbs = patch(
            "pages.models.named_asset_list_model.fetch_bundle_thumb",
            return_value=QtGui.QIcon(),
        )
        self.thumbs.start()
        self.addCleanup(self.thumbs.stop)

    def test_character_search_and_series_name_order(self):
        session.add_all(
            [
                CharacterModel(konami_id=1, name="Zane", series="GX"),
                CharacterModel(konami_id=2, name="zeta", series="DM"),
                CharacterModel(konami_id=3, name="alpha", series="DM", favorite=True),
                CharacterModel(konami_id=4, name="Beta", series="DM"),
                CharacterModel(konami_id=5, name=None, series="DM"),
                CharacterModel(konami_id=6, name="100% Hero", series="GX"),
            ]
        )
        session.commit()
        model = CharacterListModel()
        self.assertEqual([c.konami_id for c in model.assets], [3, 4, 5, 2, 6, 1])
        model.filter = "A"
        model.refresh()
        self.assertEqual([c.konami_id for c in model.assets], [3, 4, 5, 2, 1])
        model.series_filter = "DM"
        model.show_favorites = True
        model.refresh()
        self.assertEqual([c.konami_id for c in model.assets], [3])
        model.series_filter = ""
        model.show_favorites = False
        model.filter = "%"
        model.refresh()
        self.assertEqual([c.konami_id for c in model.assets], [6])
        model.filter = "character 5"
        model.refresh()
        self.assertEqual([c.konami_id for c in model.assets], [5])

    def test_character_search_controls_and_clear_filters(self):
        from PySide6.QtTest import QTest

        session.add_all(
            [
                CharacterModel(konami_id=1, name="Yugi", series="DM", favorite=True),
                CharacterModel(konami_id=2, name="Joey", series="DM"),
                CharacterModel(konami_id=3, name="Yuma", series="ZEXAL"),
            ]
        )
        session.commit()
        page = Character()
        self.addCleanup(page.close)
        page.searchEdit.setText("yu")
        QTest.qWait(300)
        self.assertEqual([c.konami_id for c in page.model.assets], [1, 3])
        page.seriesComboBox.setCurrentIndex(page.seriesComboBox.findData("DM"))
        page.favorites.setChecked(True)
        self.assertEqual([c.konami_id for c in page.model.assets], [1])
        page.searchEdit.setText("joey")
        page.searchEdit.returnPressed.emit()
        self.assertEqual(page.model.assets, [])
        page.clearFilterButton.click()
        self.assertEqual(page.searchEdit.text(), "")
        self.assertFalse(page.searchTimer.isActive())
        self.assertFalse(page.favorites.isChecked())
        self.assertEqual([c.konami_id for c in page.model.assets], [2, 1, 3])

    def test_character_favorite_tracks_mouse_and_keyboard_selection(self):
        from PySide6.QtTest import QTest

        session.add_all(
            [
                CharacterModel(konami_id=1, name="Joey", series="DM"),
                CharacterModel(konami_id=2, name="Yugi", series="DM", favorite=True),
            ]
        )
        session.commit()
        page = Character()
        self.addCleanup(page.close)
        page.show()
        _APP.processEvents()
        self.assertFalse(page.favorite.isEnabled())

        with patch("pages.character.show_toast") as toast:
            QTest.mouseClick(
                page.charactersView.viewport(),
                QtCore.Qt.MouseButton.LeftButton,
                pos=page.charactersView.visualRect(page.model.index(0)).center(),
            )
            self.assertEqual(page.selected.konami_id, 1)
            self.assertTrue(page.favorite.isEnabled())
            self.assertFalse(page.favorite.isChecked())
            page.favorite.click()
            session.expire_all()
            self.assertTrue(
                session.query(CharacterModel).filter_by(konami_id=1).one().favorite
            )
            toast.assert_called_once()

            page.charactersView.setFocus()
            QTest.keyClick(page.charactersView, QtCore.Qt.Key.Key_Right)
            self.assertEqual(page.selected.konami_id, 2)
            self.assertTrue(page.favorite.isChecked())
            toast.assert_called_once()

            page.favorite.click()
            session.expire_all()
            self.assertFalse(
                session.query(CharacterModel).filter_by(konami_id=2).one().favorite
            )
            self.assertTrue(
                session.query(CharacterModel).filter_by(konami_id=1).one().favorite
            )

    def test_character_unfavorite_refreshes_filter_and_clears_target(self):
        session.add(
            CharacterModel(konami_id=1, name="Yugi", series="DM", favorite=True)
        )
        session.commit()
        page = Character()
        self.addCleanup(page.close)
        page.favorites.setChecked(True)
        page.charactersView.setCurrentIndex(page.model.index(0))
        with patch("pages.character.show_toast"):
            page.favorite.click()
        self.assertEqual(page.model.assets, [])
        self.assertIsNone(page.selected)
        self.assertFalse(page.favorite.isEnabled())
        self.assertFalse(page.favorite.isChecked())

        page.favorites.setChecked(False)
        page.charactersView.setCurrentIndex(page.model.index(0))
        page.searchEdit.setText("missing")
        page.searchEdit.returnPressed.emit()
        self.assertIsNone(page.selected)
        self.assertFalse(page.favorite.isEnabled())

    def test_legacy_migration_is_repeatable(self):
        path = Path("legacy.db")
        with closing(sqlite3.connect(path)) as connection:
            connection.executescript(
                """CREATE TABLE app_config (version TEXT, background_mode TEXT);
                INSERT INTO app_config VALUES ('2026-10-19', 'stretched');
                CREATE TABLE sleeve (id INTEGER); CREATE TABLE field (id INTEGER);
                CREATE TABLE character (id INTEGER);"""
            )
        run_migrations(str(path))
        run_migrations(str(path))
        with closing(sqlite3.connect(path)) as connection:
            for table in ("sleeve", "field", "character"):
                self.assertIn(
                    "name",
                    [
                        row[1]
                        for row in connection.execute(f"PRAGMA table_info({table})")
                    ],
                )
            self.assertIsNone(
                connection.execute("SELECT version FROM app_config").fetchone()[0]
            )
            repository, branch, last_source = connection.execute(
                "SELECT metadata_repository, metadata_branch, "
                "metadata_last_source FROM app_config"
            ).fetchone()
            self.assertEqual(repository, "Nauder/floowandereeze-and-modding-etl-dl")
            self.assertEqual(branch, "")
            self.assertIsNone(last_source)
        path.unlink()

    def test_names_search_fallback_and_favorites(self):
        for cls, model_class in (
            (SleeveModel, SleeveListModel),
            (FieldModel, FieldListModel),
        ):
            session.add_all(
                [
                    cls(
                        name="Blue Eyes",
                        medium_bundle="abcdef01",
                        small_bundle="abcdef02",
                        favorite=True,
                    ),
                    cls(name=None, medium_bundle="deadbeef", small_bundle="deadbee0"),
                    cls(
                        name="100% Hero",
                        medium_bundle="12345678",
                        small_bundle="12345679",
                    ),
                ]
            )
            session.commit()
            model = model_class()
            self.assertEqual(model.rowCount(QtCore.QModelIndex()), 3)
            self.assertIn("Blue Eyes", model.get_names())
            model.filter = "eyes"
            model.refresh()
            self.assertEqual([asset.name for asset in model.assets], ["Blue Eyes"])
            model.filter = "%"
            model.refresh()
            self.assertEqual([asset.name for asset in model.assets], ["100% Hero"])
            model.filter = "dead"
            model.refresh()
            self.assertEqual(
                model.data(model.index(0), QtCore.Qt.ItemDataRole.DisplayRole),
                "deadbeef",
            )
            model.show_favorites = True
            model.refresh()
            self.assertEqual([asset.name for asset in model.assets], ["Blue Eyes"])
            self.assertIsNone(
                model.data(QtCore.QModelIndex(), QtCore.Qt.ItemDataRole.DisplayRole)
            )

    def test_metadata_names_preserve_sleeve_and_field_flags(self):
        import pandas as pd

        for cls, update in (
            (SleeveModel, update_service.update_sleeves),
            (FieldModel, update_service.update_fields),
        ):
            session.add(
                cls(
                    name=None,
                    medium_bundle="abcdef01",
                    small_bundle="abcdef02",
                    favorite=True,
                    has_backup=True,
                )
            )
            session.commit()
            data = pd.DataFrame(
                [dict(name="Named asset", medium="abcdef01", small="abcdef02")]
            )
            with patch.object(
                update_service, "get_github_parquet_file", return_value=data
            ):
                update()
            session.expire_all()
            asset = session.query(cls).one()
            self.assertEqual(asset.name, "Named asset")
            self.assertTrue(asset.favorite)
            self.assertTrue(asset.has_backup)
        self.assertIsNone(update_service.asset_label(pd.Series(dict(name=pd.NA))))
        self.assertIsNone(update_service.asset_label(pd.Series(dtype=object)))

    def test_discovery_and_path_normalization(self):
        library = Path("library")
        install = library / "steamapps" / "common" / "Yu-Gi-Oh! Duel Links"
        unity = install / "dlpc_Data" / "data.unity3d"
        unity.parent.mkdir(parents=True, exist_ok=True)
        unity.touch()
        for account in ("00000000", "12345678", "abcdef01"):
            (install / "LocalData" / account).mkdir(parents=True, exist_ok=True)
        with patch.object(
            game_discovery,
            "_get_steam_library_paths",
            return_value=[str(library), str(library)],
        ):
            paths = game_discovery.find_steam_duel_links_paths()
        self.assertEqual(len(paths), 2)
        self.assertEqual(game_discovery.normalize_game_path(str(install)), paths[0])
        self.assertIsNone(game_discovery.normalize_game_path(""))
        self.assertIsNone(
            game_discovery.normalize_game_path(str(install / "LocalData" / "00000000"))
        )

    def test_secondary_steam_libraries_are_read_from_vdf(self):
        steam = Path("steam-vdf").resolve()
        secondary = Path("secondary-steam").resolve()
        (steam / "steamapps").mkdir(parents=True, exist_ok=True)
        escaped = str(secondary).replace("\\", "\\\\")
        (steam / "steamapps/libraryfolders.vdf").write_text(
            f'"libraryfolders" {{ "0" {{ "path" "{escaped}" }} }}', encoding="utf-8"
        )
        with patch.object(
            game_discovery, "_get_steam_install_paths", return_value=[str(steam)]
        ):
            paths = game_discovery._get_steam_library_paths()
        self.assertEqual(paths, [str(steam), str(secondary)])

    def test_character_crop_tracks_selected_asset_ratio(self):
        from dialogs.character_edit_dialog import CharacterEditDialog
        from util.enums import CharaAssetType

        image = Path("character-crop.png").resolve()
        source = QtGui.QPixmap(600, 400)
        source.fill(QtCore.Qt.GlobalColor.red)
        source.save(str(image))
        self.addCleanup(image.unlink)

        with patch("dialogs.character_edit_dialog.fetch_bundle_thumb") as thumb:
            dialog = CharacterEditDialog(CharacterModel(series="DM"))
            self.addCleanup(dialog.close)
            self.assertFalse(dialog._crop_btn.isEnabled())
            dialog._load_image(str(image))

            def select_asset(width, height, bounds=None):
                asset = QtGui.QPixmap(width, height)
                asset.fill(QtCore.Qt.GlobalColor.transparent)
                painter = QtGui.QPainter(asset)
                painter.fillRect(
                    bounds or QtCore.QRect(0, 0, width, height),
                    QtCore.Qt.GlobalColor.red,
                )
                painter.end()
                thumb.return_value = QtGui.QIcon(asset)
                item = QtWidgets.QListWidgetItem()
                item.setData(
                    QtCore.Qt.ItemDataRole.UserRole, (CharaAssetType.ICON, "test")
                )
                dialog._on_asset_selected(item)

            def assert_crop_ratio(ratio):
                left, top, right, bottom = dialog.service.crop_rect
                self.assertAlmostEqual(
                    (right - left) * 600 / ((bottom - top) * 400), ratio
                )

            select_asset(100, 200)
            dialog._crop_btn.click()
            assert_crop_ratio(0.5)
            select_asset(300, 100)
            assert_crop_ratio(3)
            dialog._load_image(str(image))
            assert_crop_ratio(3)
            dialog._stretch_btn.click()
            self.assertIsNone(dialog.service.crop_rect)
            dialog._crop_btn.click()
            assert_crop_ratio(3)
            select_asset(300, 200, QtCore.QRect(30, 15, 100, 160))
            assert_crop_ratio(100 / 160)
            thumb.side_effect = ValueError("Missing asset")
            item = QtWidgets.QListWidgetItem()
            item.setData(
                QtCore.Qt.ItemDataRole.UserRole, (CharaAssetType.ICON, "missing")
            )
            dialog._on_asset_selected(item)
            self.assertFalse(dialog._crop_btn.isEnabled())
            self.assertIsNone(dialog.service.crop_rect)

    def test_character_mass_selection_preserves_crop_and_reports_partial_failure(self):
        from dialogs.character_edit_dialog import CharacterEditDialog

        image = Path("shared-character-crop.png").resolve()
        source = QtGui.QPixmap(600, 400)
        source.fill(QtCore.Qt.GlobalColor.red)
        source.save(str(image))
        self.addCleanup(image.unlink)
        character = CharacterModel(
            series="DM", icon="icon", select="select", world="world"
        )
        with patch(
            "dialogs.character_edit_dialog.fetch_bundle_thumb",
            return_value=QtGui.QIcon(source),
        ):
            dialog = CharacterEditDialog(character)
            self.addCleanup(dialog.close)
            dialog._load_image(str(image))
            dialog.asset_list.setCurrentRow(0)
            dialog._crop_btn.click()
            crop = dialog._crop_widget
            crop._crop_rect = crop._crop_rect.adjusted(30, 20, -30, -20)
            crop.crop_changed.emit()
            selected_area = dialog.service.crop_rect
            dialog.select_all_btn.click()
            self.assertEqual(len(dialog.asset_list.selectedItems()), 3)
            self.assertEqual(dialog.selection_label.text(), "3 assets selected")
            self.assertEqual(dialog.replace_btn.text(), "Replace 3 Assets")
            self.assertEqual(dialog.service.crop_rect, selected_area)
            self.assertIsNone(crop._target_ratio)
            dialog.asset_list.setCurrentItem(
                dialog.asset_list.item(2),
                QtCore.QItemSelectionModel.SelectionFlag.NoUpdate,
            )
            self.assertEqual(dialog.service.crop_rect, selected_area)
            applied = []

            def replace():
                applied.append((dialog.service.bundle, dialog.service.crop_rect))
                if dialog.service.bundle == "select":
                    raise OSError("unavailable bundle")

            with (
                patch("dialogs.character_edit_dialog.APP_CONFIG", create_backup=False),
                patch.object(dialog.service, "replace_bundle", side_effect=replace),
                patch("dialogs.character_edit_dialog.QMessageBox.warning") as warning,
            ):
                dialog.replace_btn.click()
            self.assertEqual(
                {bundle for bundle, _ in applied}, {"icon", "select", "world"}
            )
            self.assertTrue(all(rect == selected_area for _, rect in applied))
            self.assertEqual(dialog.service.bundle, dialog.selected_asset_bundle)
            warning.assert_called_once()
            self.assertIn("Completed 2 of 3", warning.call_args.args[2])
            dialog.filter_combo.setCurrentIndex(dialog.filter_combo.findData("duel"))
            self.assertFalse(dialog.replace_btn.isEnabled())
            self.assertIsNone(dialog.service.bundle)
            dialog.filter_combo.setCurrentIndex(0)
            dialog.select_all_btn.click()
            dialog.clear_selection_btn.click()
            self.assertFalse(dialog.extract_btn.isEnabled())
            self.assertFalse(dialog.restore_btn.isEnabled())
            self.assertFalse(dialog.replace_btn.isEnabled())

    def test_shared_character_crop_fits_each_content_ratio_without_stretching(self):
        from PIL import Image, ImageOps

        from services.character_service import CharacterService

        source = Image.new("RGBA", (240, 160))
        source.putdata([(x, y, 50, 255) for y in range(160) for x in range(240)])
        image = Path("shared-crop-source.png").resolve()
        source.save(image)
        self.addCleanup(image.unlink)
        output = Path("shared-crop-bundle").resolve()
        self.addCleanup(lambda: output.unlink(missing_ok=True))
        service = CharacterService()
        service.image_path = str(image)
        service.crop_rect = (0.25, 0.125, 0.75, 0.875)
        for bundle, bounds in (
            ("portrait", (10, 5, 60, 105)),
            ("landscape", (5, 20, 105, 70)),
        ):
            with self.subTest(bundle=bundle):
                original = Image.new("RGBA", (120, 120))
                original.paste((255, 255, 255, 255), bounds)
                data = MagicMock(m_Width=120, m_Height=120, image=original)
                texture = MagicMock()
                texture.type.name = "Texture2D"
                texture.read.return_value = data
                environment = MagicMock(objects=[texture])
                environment.file.save.return_value = b"bundle"
                service.bundle = bundle
                with (
                    patch(
                        "services.character_service.unity_load",
                        return_value=environment,
                    ),
                    patch(
                        "services.character_service.prepare_environment",
                        return_value=str(output),
                    ),
                ):
                    service.replace_bundle()
                result = data.set_image.call_args.kwargs["img"]
                expected = ImageOps.fit(
                    source.crop((60, 20, 180, 140)),
                    (bounds[2] - bounds[0], bounds[3] - bounds[1]),
                    method=Image.Resampling.LANCZOS,
                )
                self.assertEqual(result.getchannel("A").getbbox(), bounds)
                self.assertEqual(result.crop(bounds).tobytes(), expected.tobytes())
                self.assertEqual(service.crop_rect, (0.25, 0.125, 0.75, 0.875))

    def test_character_crop_restores_original_transparent_margins(self):
        from PIL import Image

        from services.character_service import CharacterService

        source = Image.new("RGBA", (200, 100), (10, 20, 30, 128))
        source.paste((255, 0, 0, 255), (0, 0, 50, 100))
        image = Path("padded-character-source.png").resolve()
        source.save(image)
        self.addCleanup(image.unlink)
        output = Path("character-bundle").resolve()
        self.addCleanup(lambda: output.unlink(missing_ok=True))

        for bounds in ((20, 5, 80, 85), (0, 0, 120, 100), None):
            with self.subTest(bounds=bounds):
                original = Image.new("RGBA", (120, 100), (200, 100, 50, 0))
                if bounds:
                    original.paste((0, 255, 0, 255), bounds)
                data = MagicMock(m_Width=120, m_Height=100, image=original)
                texture = MagicMock()
                texture.type.name = "Texture2D"
                texture.read.return_value = data
                environment = MagicMock(objects=[texture])
                environment.file.save.return_value = b"bundle"
                service = CharacterService()
                service.bundle = f"padding-{bounds}"
                service.image_path = str(image)
                service.crop_rect = (0.25, 0, 1, 1)
                with (
                    patch(
                        "services.character_service.unity_load",
                        return_value=environment,
                    ),
                    patch(
                        "services.character_service.prepare_environment",
                        return_value=str(output),
                    ),
                ):
                    service.replace_bundle()
                result = data.set_image.call_args.kwargs["img"]
                expected_bounds = bounds or (0, 0, 120, 100)
                self.assertEqual(result.size, original.size)
                self.assertEqual(result.getchannel("A").getbbox(), expected_bounds)
                left, top, right, bottom = expected_bounds
                for point in ((left, top), (right - 1, bottom - 1)):
                    pixel = result.getpixel(point)
                    self.assertEqual(pixel[3], 128)
                    for actual, expected in zip(pixel[:3], (10, 20, 30), strict=True):
                        self.assertLessEqual(abs(actual - expected), 1)

    def test_character_original_layout_survives_transparent_replacements(self):
        from PIL import Image
        from PIL.ImageQt import ImageQt

        from dialogs.character_edit_dialog import CharacterEditDialog
        from services.character_service import CharacterService
        from util.enums import CharaAssetType

        bounds = (20, 5, 80, 85)
        original = Image.new("RGBA", (120, 100))
        original.paste((255, 255, 255, 255), bounds)
        source = Image.new("RGBA", (60, 80))
        source.paste((255, 0, 0, 128), (15, 20, 45, 60))
        image = Path("transparent-character.png").resolve()
        source.save(image)
        self.addCleanup(image.unlink)
        output = Path("transparent-bundle").resolve()
        self.addCleanup(lambda: output.unlink(missing_ok=True))

        data = MagicMock(m_Width=120, m_Height=100, image=original)
        texture = MagicMock()
        texture.type.name = "Texture2D"
        texture.read.return_value = data
        environment = MagicMock(objects=[texture])
        environment.file.save.return_value = b"bundle"
        results = []
        with (
            patch("services.character_service.unity_load", return_value=environment),
            patch(
                "services.character_service.prepare_environment",
                return_value=str(output),
            ),
        ):
            for _ in range(3):
                service = CharacterService()
                service.bundle = "transparent"
                service.image_path = str(image)
                service.crop_rect = (0, 0, 1, 1)
                service.replace_bundle()
                data.image = data.set_image.call_args.kwargs["img"]
                results.append(data.image.tobytes())
                self.assertEqual(
                    service.original_content_bounds(service.bundle, data.image), bounds
                )
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0], results[2])
        self.assertNotEqual(data.image.getchannel("A").getbbox(), bounds)

        icon = QtGui.QIcon(QtGui.QPixmap.fromImage(ImageQt(data.image)))
        with patch(
            "dialogs.character_edit_dialog.fetch_bundle_thumb", return_value=icon
        ):
            dialog = CharacterEditDialog(CharacterModel(series="DM"))
            self.addCleanup(dialog.close)
            item = QtWidgets.QListWidgetItem()
            item.setData(
                QtCore.Qt.ItemDataRole.UserRole, (CharaAssetType.ICON, "transparent")
            )
            dialog._on_asset_selected(item)
            self.assertAlmostEqual(dialog._asset_ratio, 60 / 80)

    def test_character_padding_toggle_updates_crop_ratio(self):
        from dialogs.character_edit_dialog import CharacterEditDialog

        asset = QtGui.QPixmap(120, 100)
        asset.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(asset)
        painter.fillRect(QtCore.QRect(20, 5, 60, 80), QtCore.Qt.GlobalColor.red)
        painter.end()
        image = Path("padding-toggle.png").resolve()
        asset.save(str(image))
        self.addCleanup(image.unlink)
        with patch(
            "dialogs.character_edit_dialog.fetch_bundle_thumb",
            return_value=QtGui.QIcon(asset),
        ):
            dialog = CharacterEditDialog(CharacterModel(series="DM", icon="toggle"))
            self.addCleanup(dialog.close)
            self.assertTrue(dialog.preserve_padding_checkbox.isChecked())
            self.assertTrue(dialog.service.preserve_transparent_padding)
            dialog.asset_list.setCurrentRow(0)
            dialog._load_image(str(image))
            dialog._crop_btn.click()

            for enabled, ratio in ((False, 1.2), (True, 0.75)):
                dialog.preserve_padding_checkbox.setChecked(enabled)
                self.assertEqual(dialog.service.preserve_transparent_padding, enabled)
                self.assertAlmostEqual(dialog._asset_ratio, ratio)
                self.assertAlmostEqual(dialog._crop_widget._target_ratio, ratio)
                left, top, right, bottom = dialog.service.crop_rect
                self.assertAlmostEqual(
                    (right - left) * 120 / ((bottom - top) * 100), ratio
                )

    def test_character_padding_toggle_controls_saved_margins(self):
        from PIL import Image

        from services.character_service import CharacterService

        original = Image.new("RGBA", (120, 100))
        bounds = (20, 5, 80, 85)
        original.paste((255, 255, 255, 255), bounds)
        source = Image.new("RGBA", (120, 100), (255, 0, 0, 255))
        image = Path("padding-toggle-source.png").resolve()
        source.save(image)
        self.addCleanup(image.unlink)
        output = Path("padding-toggle-bundle").resolve()
        self.addCleanup(lambda: output.unlink(missing_ok=True))
        data = MagicMock(m_Width=120, m_Height=100, image=original)
        texture = MagicMock()
        texture.type.name = "Texture2D"
        texture.read.return_value = data
        environment = MagicMock(objects=[texture])
        environment.file.save.return_value = b"bundle"
        service = CharacterService()
        service.bundle = "toggle-save"
        service.image_path = str(image)
        service.crop_rect = (0, 0, 1, 1)
        with (
            patch("services.character_service.unity_load", return_value=environment),
            patch(
                "services.character_service.prepare_environment",
                return_value=str(output),
            ),
        ):
            for enabled, expected in ((False, (0, 0, 120, 100)), (True, bounds)):
                service.preserve_transparent_padding = enabled
                service.replace_bundle()
                data.image = data.set_image.call_args.kwargs["img"]
                self.assertEqual(data.image.size, (120, 100))
                self.assertEqual(data.image.getchannel("A").getbbox(), expected)
                self.assertEqual(
                    service.original_content_bounds(service.bundle, data.image), bounds
                )

    def test_character_original_layout_uses_existing_backup(self):
        from PIL import Image

        from services.character_service import CharacterService

        backup = Path("backups/characters/original-layout.png")
        backup.parent.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: backup.unlink(missing_ok=True))
        original = Image.new("RGBA", (120, 100))
        bounds = (10, 15, 100, 85)
        original.paste((255, 255, 255, 255), bounds)
        original.save(backup)
        replacement = Image.new("RGBA", original.size, (255, 0, 0, 255))
        service = CharacterService()
        self.assertEqual(
            service.original_content_bounds("original-layout", replacement), bounds
        )
        backup.unlink()
        self.assertEqual(
            CharacterService().original_content_bounds("original-layout", replacement),
            bounds,
        )

    def test_locked_crop_stays_in_bounds_for_all_corner_drags(self):
        from widgets.crop_overlay_widget import CropOverlayWidget

        widget = CropOverlayWidget()
        self.addCleanup(widget.close)
        for ratio in (0.05, 0.5, 1, 3, 20):
            widget._target_ratio = ratio
            widget._image_rect = QtCore.QRectF(0, 40, 256, 170)
            widget._init_crop_rect()
            start = QtCore.QRectF(widget._crop_rect)
            for corner in ("tl", "tr", "bl", "br"):
                widget._drag_mode = corner
                widget._drag_start_rect = start
                for dx, dy in ((1000, 0), (-1000, 0), (0, 1000), (0, -1000), (35, -20)):
                    widget._apply_drag(dx, dy)
                    crop = widget._crop_rect
                    self.assertAlmostEqual(crop.width() / crop.height(), ratio)
                    self.assertGreater(crop.width(), 0)
                    self.assertGreaterEqual(
                        crop.left(), widget._image_rect.left() - 1e-9
                    )
                    self.assertGreaterEqual(crop.top(), widget._image_rect.top() - 1e-9)
                    self.assertLessEqual(
                        crop.right(), widget._image_rect.right() + 1e-9
                    )
                    self.assertLessEqual(
                        crop.bottom(), widget._image_rect.bottom() + 1e-9
                    )

    def test_editor_resizes_searches_and_preserves_crop(self):
        image = Path("source.png")
        pixmap = QtGui.QPixmap(600, 400)
        pixmap.fill(QtCore.Qt.GlobalColor.red)
        pixmap.save(str(image))
        for cls in (Sleeve, Field, Card):
            page = cls()
            page.resize(1000, 700)
            page.show()
            _APP.processEvents()
            self.assertTrue(
                page.responsive_editor.scroll.widget().isAncestorOf(page.current)
            )
            self.assertTrue(
                page.responsive_editor.scroll.widget().isAncestorOf(page.selectButton)
            )
            self.assertTrue(page.current.isVisible())
            small = page.current.width()
            page._load_image(str(image.resolve()))
            page._set_fit_mode("crop")
            _APP.processEvents()
            crop = page._crop_widget
            crop._crop_rect = crop._crop_rect.adjusted(10, 10, -10, -10)
            before = crop.get_crop_rect_normalized()
            page.resize(1600, 1000)
            _APP.processEvents()
            self.assertGreater(page.current.width(), small)
            for a, b in zip(before, crop.get_crop_rect_normalized(), strict=True):
                self.assertAlmostEqual(a, b)
            if cls is not Card:
                page.searchEdit.setText("missing")
                page.searchButton.click()
                self.assertEqual(page.model.filter, "missing")
                page.searchEdit.clear()
                self.assertEqual(page.model.filter, "")
            page.close()
            page.deleteLater()
        image.unlink()

    def test_backups_available_without_game_and_after_page_reset(self):
        from pages.backups import Backups

        window = MainWindow(QtWidgets.QSplashScreen())
        self.addCleanup(window.close)
        self.assertTrue(window.actionbackups_button.isEnabled())
        self.assertFalse(window.actioncard_button.isEnabled())
        window.actionbackups_button.trigger()
        self.assertIsInstance(window.mainStack.currentWidget(), Backups)
        window._reset_asset_pages()
        window.actionbackups_button.trigger()
        self.assertIsInstance(window.mainStack.currentWidget(), Backups)

    def test_backup_flags_follow_duel_links_restore_sources(self):
        from database.models import CardModel
        from services.backup_service import BackupService, sync_backup_flags

        card = CardModel(
            name="Card",
            small_bundle="csmall",
            medium_bundle="cmedium",
            large_bundle="clarge",
        )
        sleeve = SleeveModel(small_bundle="ssmall", medium_bundle="smedium")
        field = FieldModel(small_bundle="fsmall", medium_bundle="fmedium")
        character = CharacterModel(konami_id=10, series="DM", duel_31="char31")
        session.add_all([card, sleeve, field, character])
        session.commit()
        with tempfile.TemporaryDirectory() as folder:
            service = BackupService(folder)
            names = [
                "cards/clarge.png",
                "sleeves/smedium.png",
                "fields/fmedium.png",
                "characters/char31.png",
            ]
            for name in names:
                path = service.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"original")
            sync_backup_flags(service)
            self.assertTrue(
                all(asset.has_backup for asset in (card, sleeve, field, character))
            )
            service.delete(names)
            sync_backup_flags(service)
            self.assertFalse(
                any(asset.has_backup for asset in (card, sleeve, field, character))
            )
        session.delete(card)
        session.commit()

    def test_tabs_enable_without_restart_and_load_on_demand(self):
        window = MainWindow(QtWidgets.QSplashScreen())
        self.assertFalse(window.actionsleeve_button.isEnabled())
        install = Path("tab-game")
        (install / "dlpc_Data").mkdir(exist_ok=True, parents=True)
        (install / "dlpc_Data/data.unity3d").touch()
        account = install / "LocalData/12345678"
        account.mkdir(exist_ok=True, parents=True)
        window.config_page._set_game_path(str(account))
        self.assertTrue(window.actionsleeve_button.isEnabled())
        self.assertEqual(window._loaded_pages, {0})
        window._activate_page(1)
        self.assertIsInstance(window.mainStack.currentWidget(), Sleeve)
        self.assertEqual(window._loaded_pages, {0, 1})
        window.close()

    def test_metadata_source_persists_resets_and_validates(self):
        from pages.config import Config

        page = Config()
        with patch("pages.config.show_toast"):
            page.metadataRepositoryLine.setText("Example/etl")
            page.metadataBranchLine.setText("feature/asset-names")
            page.saveMetadataSourceButton.click()
            second = Config()
            self.assertEqual(second.metadataRepositoryLine.text(), "Example/etl")
            self.assertEqual(second.metadataBranchLine.text(), "feature/asset-names")
            page.metadataRepositoryLine.setText("invalid")
            with patch.object(page, "_get_data") as download:
                page.updateButton.click()
                download.assert_not_called()
            self.assertEqual(APP_CONFIG.metadata_repository, "Example/etl")
            page.resetMetadataSourceButton.click()
            self.assertEqual(
                APP_CONFIG.metadata_repository,
                "Nauder/floowandereeze-and-modding-etl-dl",
            )
            self.assertEqual(APP_CONFIG.metadata_branch, "")
        self.assertEqual(
            page.horizontalLayout.indexOf(page.autoDetectGameButton),
            page.horizontalLayout.indexOf(page.gameButton) + 1,
        )
        page.resize(1100, 720)
        page.show()
        _APP.processEvents()
        self.assertEqual(
            page.autoDetectGameButton.geometry().center().y(),
            page.gameLine.geometry().center().y(),
        )
        page.close()
        second.close()

    def _local_metadata_repo(self):
        import pandas as pd

        temp = tempfile.TemporaryDirectory(prefix="local metadata ")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "data").mkdir()
        (root / "data/version.txt").write_text("2026-10-19\n", encoding="utf-8")
        for dataset in ("cards", "sleeves", "fields", "characters"):
            pd.DataFrame([{"name": "Unpublished " + dataset}]).to_parquet(
                root / f"data/{dataset}.parquet"
            )
        return root

    def test_local_source_browse_persists_and_reads_working_files_offline(self):
        from pages.config import Config

        root = self._local_metadata_repo()
        page = Config()
        with (
            patch("pages.config.show_toast"),
            patch(
                "pages.config.QFileDialog.getExistingDirectory", return_value=str(root)
            ),
        ):
            page.browseMetadataSourceButton.click()
            self.assertFalse(page.metadataBranchLine.isEnabled())
            page.metadataBranchLine.setText("unused-branch")
            page.saveMetadataSourceButton.click()
            self.assertEqual(APP_CONFIG.metadata_repository, str(root.resolve()))
            self.assertEqual(APP_CONFIG.metadata_branch, "")
            second = Config()
            self.assertEqual(second.metadataRepositoryLine.text(), str(root.resolve()))
            self.assertFalse(second.metadataBranchLine.isEnabled())
            with patch.object(
                update_service.requests, "get", side_effect=AssertionError("Network")
            ):
                self.assertEqual(
                    update_service.get_github_raw_file("data/version.txt"),
                    "2026-10-19\n",
                )
                for dataset in ("cards", "sleeves", "fields", "characters"):
                    frame = update_service.get_github_parquet_file(
                        f"data/{dataset}.parquet"
                    )
                    self.assertEqual(frame.iloc[0]["name"], "Unpublished " + dataset)
                (root / "data/version.txt").write_text("2026-10-20", encoding="utf-8")
                self.assertEqual(
                    update_service.get_github_raw_file("data/version.txt"), "2026-10-20"
                )
                with self.assertRaisesRegex(ValueError, "inside the local repository"):
                    update_service.get_github_raw_file("../outside.txt")
            page.resetMetadataSourceButton.click()
            self.assertTrue(page.metadataBranchLine.isEnabled())
        page.close()
        second.close()

    def test_local_source_validation_keeps_previous_source(self):
        from pages.config import Config
        from util.metadata_source import normalize_metadata_source

        root = self._local_metadata_repo()
        repository, branch = normalize_metadata_source(str(root / "data/.."), "ignored")
        self.assertEqual(repository, str(root.resolve()))
        self.assertEqual(branch, "")
        with self.assertRaisesRegex(ValueError, "does not exist"):
            normalize_metadata_source(str(root / "missing"))
        (root / "data/characters.parquet").unlink()
        page = Config()
        page.metadataRepositoryLine.setText(str(root))
        with patch("pages.config.show_toast") as toast:
            self.assertFalse(page._save_metadata_source())
            self.assertIn("characters.parquet", toast.call_args.args[2])
        self.assertEqual(
            APP_CONFIG.metadata_repository, "Nauder/floowandereeze-and-modding-etl-dl"
        )
        page.close()

    def test_local_checks_reload_same_date_and_keep_success_marker_on_failure(self):
        from contextlib import ExitStack

        from pages.config import Config
        from util.metadata_source import metadata_source_key

        root = self._local_metadata_repo()
        APP_CONFIG.metadata_repository = str(root)
        APP_CONFIG.metadata_last_source = metadata_source_key(str(root), "")
        session.commit()
        page = Config()
        with ExitStack() as stack:
            stack.enter_context(patch("pages.config.show_toast"))
            stack.enter_context(
                patch.object(
                    update_service.requests,
                    "get",
                    side_effect=AssertionError("Network"),
                )
            )
            updates = [
                stack.enter_context(patch("pages.config." + name))
                for name in (
                    "update_sleeves",
                    "update_fields",
                    "update_cards",
                    "update_characters",
                )
            ]
            page._get_data()
            page._get_data()
            self.assertTrue(all(update.call_count == 2 for update in updates))
            previous_source = APP_CONFIG.metadata_last_source
            updates[0].side_effect = OSError("local read failed")
            with self.assertRaisesRegex(OSError, "local read failed"):
                page._get_data()
            self.assertEqual(APP_CONFIG.metadata_last_source, previous_source)
            self.assertEqual(APP_CONFIG.version, "2026-10-19\n")
            self.assertTrue(page.updateButton.isEnabled())
        page.close()

    def test_version_and_datasets_use_selected_repository_and_branch(self):
        APP_CONFIG.metadata_repository = "Example/etl"
        APP_CONFIG.metadata_branch = "feature/asset-names"
        session.commit()
        response = MagicMock()
        response.json.return_value = {"download_url": "https://example.invalid/data"}
        response.text = "2026-10-19"
        with patch.object(update_service.requests, "get", return_value=response) as get:
            self.assertEqual(
                update_service.get_github_raw_file("data/version.txt"), "2026-10-19"
            )
            self.assertEqual(
                get.call_args_list[0].args[0],
                "https://api.github.com/repos/Example/etl/contents/data/version.txt",
            )
            self.assertEqual(
                get.call_args_list[0].kwargs["params"], {"ref": "feature/asset-names"}
            )
        with (
            patch.object(update_service.requests, "get", return_value=response) as get,
            patch.object(update_service, "read_parquet") as parquet,
        ):
            update_service.get_github_parquet_file("data/sleeves.parquet")
            self.assertEqual(
                get.call_args.kwargs["params"], {"ref": "feature/asset-names"}
            )
            parquet.assert_called_once_with("https://example.invalid/data")
        self.assertEqual(
            update_service._github_source(branch=""), ("Example", "etl", {})
        )
        self.assertEqual(
            update_service._github_source("Other", "repo", "test"),
            ("Other", "repo", {"ref": "test"}),
        )

    def test_branch_switch_refreshes_same_date_and_records_success_only(self):
        from contextlib import ExitStack

        from pages.config import Config
        from util.metadata_source import metadata_source_key

        page = Config()
        APP_CONFIG.metadata_last_source = metadata_source_key(
            APP_CONFIG.metadata_repository, ""
        )
        APP_CONFIG.metadata_branch = "feature/asset-names"
        session.commit()
        with ExitStack() as stack:
            stack.enter_context(patch("pages.config.show_toast"))
            stack.enter_context(
                patch("pages.config.get_github_raw_file", return_value="2026-10-19")
            )
            updates = [
                stack.enter_context(patch("pages.config." + name))
                for name in (
                    "update_sleeves",
                    "update_fields",
                    "update_cards",
                    "update_characters",
                )
            ]
            page._get_data()
            self.assertTrue(all(update.call_count == 1 for update in updates))
            successful_source = APP_CONFIG.metadata_last_source
            self.assertEqual(
                successful_source,
                metadata_source_key(
                    APP_CONFIG.metadata_repository, "feature/asset-names"
                ),
            )
            page._get_data()
            self.assertTrue(all(update.call_count == 1 for update in updates))
            APP_CONFIG.metadata_branch = "another-branch"
            session.commit()
            updates[0].side_effect = RuntimeError("download failed")
            with self.assertRaisesRegex(RuntimeError, "download failed"):
                page._get_data()
            self.assertEqual(APP_CONFIG.metadata_last_source, successful_source)
        page.close()

    def test_update_failure_does_not_advance_version(self):
        from pages.config import Config

        page = Config()
        with (
            patch("pages.config.get_github_raw_file", return_value="2026-10-20"),
            patch(
                "pages.config.update_sleeves",
                side_effect=RuntimeError("download failed"),
            ),
            patch("pages.config.update_fields"),
            patch("pages.config.update_cards"),
            patch("pages.config.update_characters"),
            self.assertRaisesRegex(RuntimeError, "download failed"),
        ):
            page._get_data()
        self.assertEqual(APP_CONFIG.version, "2026-10-19")
        self.assertTrue(page.updateButton.isEnabled())
        page.close()
