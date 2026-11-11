"""Capture real Duel Links GUI pages. See docs/development/screenshots.md.

Application imports must follow the switch to the disposable working directory.
"""

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAGES = ("config", "sleeve", "card", "field", "character", "backups")


def arguments():
    """Resolve capture options without importing the application."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "database.db")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/assets/ui")
    parser.add_argument("--pages", nargs="+", choices=PAGES, default=PAGES)
    parser.add_argument("--card-search", default="Blue-Eyes")
    parser.add_argument("--character-search", default="")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--offscreen", action="store_true")
    args = parser.parse_args()
    if args.width < 1280 or args.height < 900:
        parser.error("Use at least 1280 x 900 to keep editor controls visible.")
    if "card" in args.pages and len(args.card_search) < 3:
        parser.error("--card-search needs at least three characters.")
    args.database = args.database.resolve(strict=True)
    args.output = args.output.resolve()
    args.manifest = (
        ROOT / "build/docs-captures/manifest.json"
        if args.output == ROOT / "docs/assets/ui"
        else args.output / "manifest.json"
    )
    return args


def capture(args, sandbox):
    """Render application widgets using a consistent copy of the local database."""
    if args.offscreen:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = "1"
    os.environ["TEMP"] = os.environ["TMP"] = str(sandbox)
    with (
        closing(
            sqlite3.connect(args.database.as_uri() + "?mode=ro", uri=True)
        ) as source,
        closing(sqlite3.connect(sandbox / "database.db")) as destination,
    ):
        source.backup(destination)
    os.chdir(sandbox)
    sys.path.insert(0, str(ROOT))

    from PySide6 import QtCore, QtGui, QtWidgets

    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
    for scope in (QtCore.QSettings.Scope.UserScope, QtCore.QSettings.Scope.SystemScope):
        QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat, scope, str(sandbox))
    app = QtWidgets.QApplication([])
    app.setFont(QtGui.QFont("Segoe UI", 10))

    from database.objects import engine, session
    from dialogs.character_edit_dialog import CharacterEditDialog
    from pages.main_window import MainWindow
    from util.constants import APP_CONFIG
    from util.game_discovery import normalize_game_path
    from util.metadata_source import is_local_metadata_source
    from util.ui_util import get_dark_mode_palette

    window = None
    dialog = None
    errors = []
    manifest = {
        "qt": QtCore.qVersion(),
        "platform": app.platformName(),
        "window_mode": "windowed" if args.windowed or args.offscreen else "maximized",
        "captures": [],
    }

    def dismiss_errors():
        modal = app.activeModalWidget()
        if isinstance(modal, QtWidgets.QMessageBox):
            errors.append(modal.windowTitle())
            modal.reject()

    guard = QtCore.QTimer()
    guard.timeout.connect(dismiss_errors)
    guard.start(100)

    def settle():
        for _ in range(25):
            app.processEvents()
            time.sleep(0.02)
        if errors:
            raise RuntimeError(f"Unexpected application dialog: {errors[0]}")

    def save(widget, filename, selected=None):
        settle()
        pixmap = widget.grab()
        if pixmap.isNull() or not pixmap.save(str(args.output / filename)):
            raise RuntimeError(f"Could not save {filename}")
        manifest["captures"].append(
            {
                "file": filename,
                "selected": selected,
                "pixels": [pixmap.width(), pixmap.height()],
                "logical_size": [widget.width(), widget.height()],
            }
        )
        print(f"Saved {args.output / filename}", flush=True)

    def source_image(pixmap, name):
        if pixmap is None or pixmap.isNull():
            raise RuntimeError(f"No installed texture loaded for {name}")
        path = Path("examples") / f"{name}.png"
        path.parent.mkdir(exist_ok=True)
        if not pixmap.save(str(path)):
            raise RuntimeError(f"Could not prepare {name} preview")
        return str(path)

    try:
        needs_game = any(name not in ("config", "backups") for name in args.pages)
        if needs_game and not normalize_game_path(APP_CONFIG.game_path or ""):
            raise RuntimeError(
                "Configure a downloaded Duel Links account in the app first."
            )
        APP_CONFIG.background_path = None
        app.setPalette(get_dark_mode_palette(app))
        splash = QtWidgets.QSplashScreen()
        window = MainWindow(splash)
        window.setWindowTitle("Floowandereeze & Modding - Duel Links")
        if args.windowed or args.offscreen:
            window.showNormal()
            window.resize(args.width, args.height)
        else:
            window.showMaximized()
        settle()
        for name in args.pages:
            print(f"Preparing {name}...", flush=True)
            index = PAGES.index(name)
            window._navigation_buttons[index].trigger()
            settle()
            if (
                index not in window._loaded_pages
                or window.mainStack.currentIndex() != index
            ):
                raise RuntimeError(f"Could not open {name}")
            page = window.mainStack.currentWidget()
            selected = None
            if name == "config":
                redactions = [
                    (page.gameLine, "C:/Games/Duel Links/LocalData/00000000"),
                    (page.bgLine, ""),
                ]
                if is_local_metadata_source(page.metadataRepositoryLine.text()):
                    redactions.append(
                        (page.metadataRepositoryLine, "C:/Projects/duel-links-etl")
                    )
                for control, text in redactions:
                    blocker = QtCore.QSignalBlocker(control)
                    control.setText(text)
                    del blocker
            elif name == "backups":
                page.service.root = ROOT / "backups"
                page.refresh()
            else:
                if name == "card":
                    page.searchEdit.setText(args.card_search)
                    page.searchButton.click()
                elif name == "character" and args.character_search:
                    page.searchEdit.setText(args.character_search)
                    page._search_characters()
                settle()
                if not page.model.assets:
                    raise RuntimeError(f"No metadata results for {name}")
                view_name, handler = {
                    "sleeve": ("sleevesView", "_on_sleeve_clicked"),
                    "card": ("cardsView", "_on_card_clicked"),
                    "field": ("fieldsView", "_on_field_clicked"),
                    "character": ("charactersView", "_on_character_selected"),
                }[name]
                view = getattr(page, view_name)
                model_index = page.model.index(0, 0)
                view.setCurrentIndex(model_index)
                view.scrollTo(model_index)
                getattr(page, handler)(model_index)
                asset = page.model.assets[0]
                selected = asset.name or str(asset.id)
                if name != "character":
                    pixmap = page.current.pixmap
                    if callable(pixmap):
                        pixmap = pixmap()
                    page._load_image(source_image(pixmap, name))
            page.setFocus()
            save(window, name + ".png", selected)
            if name == "character":
                dialog = CharacterEditDialog(asset, window)
                dialog.show()
                settle()
                for row in range(dialog.asset_list.count()):
                    dialog.asset_list.setCurrentRow(row)
                    settle()
                    pixmap = dialog.current_preview.pixmap()
                    if pixmap is not None and not pixmap.isNull():
                        dialog._load_image(source_image(pixmap, "character"))
                        break
                else:
                    raise RuntimeError("No installed character texture available")
                save(dialog, "character_edit.png", selected)
                dialog.reject()
                dialog = None
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Saved manifest: {args.manifest}", flush=True)
    finally:
        guard.stop()
        if dialog is not None:
            dialog.reject()
        if window is not None:
            window.close()
            window.deleteLater()
            app.processEvents()
        session.rollback()
        session.close()
        engine.dispose()


def main():
    """Keep all app writes and settings in a disposable directory under build/."""
    args = arguments()
    args.output.mkdir(parents=True, exist_ok=True)
    (ROOT / "build").mkdir(exist_ok=True)
    previous = Path.cwd()
    try:
        with tempfile.TemporaryDirectory(
            prefix="docs-capture-", dir=ROOT / "build"
        ) as directory:
            try:
                capture(args, Path(directory))
            finally:
                os.chdir(previous)
    finally:
        os.chdir(previous)


if __name__ == "__main__":
    main()
