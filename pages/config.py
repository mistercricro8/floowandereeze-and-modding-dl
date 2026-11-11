import os
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path

from pyqttoast import ToastPreset
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QProgressDialog,
    QWidget,
)

from database.objects import session
from dialogs.game_path_select_dialog import GamePathSelectDialog
from dialogs.simple_dialogs import show_confirmation_dialog
from pages.models.asset_list_model import AssetListModel
from pages.ui.config import Ui_Config
from services.unity_service import UnityService
from services.update_service import (
    get_github_raw_file,
    update_cards,
    update_characters,
    update_fields,
    update_sleeves,
)
from util.constants import APP_CONFIG, IMAGE_EXTENSIONS, IMAGE_FILTER
from util.game_discovery import find_steam_duel_links_paths, normalize_game_path
from util.metadata_source import (
    DEFAULT_METADATA_BRANCH,
    DEFAULT_METADATA_REPOSITORY,
    is_local_metadata_source,
    metadata_source_key,
    normalize_metadata_source,
)
from util.python_utils import get_instances_of_subclasses, is_valid_game_path
from util.ui_util import show_toast


class Config(QWidget, Ui_Config):
    """
    Main configuration page.

    This page contains the configuration for the app, including the game path,
    background image, and backup settings.
    """

    gamePathChanged = Signal()
    dataUpdated = Signal()

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.autoDetectGameButton.clicked.connect(self._auto_detect_game_path)
        self._connect_callbacks()
        self._set_variables()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accepts drag and drop of image files."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(IMAGE_EXTENSIONS):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handles the drop event of an image file."""
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(IMAGE_EXTENSIONS):
                APP_CONFIG.background_path = file_path
                session.commit()
                self.bgLine.setText(APP_CONFIG.background_path)

                self._apply_background_style(file_path)
                show_toast(
                    self,
                    "Background",
                    "Background image set successfully",
                    ToastPreset.SUCCESS_DARK,
                )
                break

    def restore_all_asset_changes(self) -> None:
        count = 0

        for service, model in self._get_services_and_models():
            backups_path = os.path.join("backups", service.subfolder)

            if os.path.exists(backups_path):
                for filename in os.listdir(backups_path):
                    file_path = os.path.join(backups_path, filename)

                    if os.path.isfile(file_path):
                        service.bundle = filename.replace(".png", "")
                        count += 1 if service.restore_asset() else 0

            model.refresh()

        show_toast(
            self,
            "Backups",
            f"{count} assets have been restored successfully",
            ToastPreset.SUCCESS_DARK,
        )

    def delete_backups(self) -> None:
        count = 0

        for service, model in self._get_services_and_models():
            backups_path = os.path.join("backups", service.subfolder)

            if os.path.exists(backups_path):
                for filename in os.listdir(backups_path):
                    os.remove(os.path.join(backups_path, filename))
                    count += 1

            model.reset_backups()

        show_toast(
            self,
            "Backups",
            f"{count} backups have been deleted successfully",
            ToastPreset.SUCCESS_DARK,
        )

    def _get_services_and_models(self):
        services: list[UnityService] = get_instances_of_subclasses(UnityService)
        models: list[AssetListModel] = get_instances_of_subclasses(AssetListModel)

        return zip(services, models, strict=True)

    def _connect_callbacks(self):
        self.gameButton.clicked.connect(self._get_game_path)
        self.gameLine.returnPressed.connect(self._manual_game_path_entered)
        self.updateButton.clicked.connect(self._check_update)
        self.saveMetadataSourceButton.clicked.connect(
            lambda: self._save_metadata_source()
        )
        self.resetMetadataSourceButton.clicked.connect(self._reset_metadata_source)
        self.browseMetadataSourceButton.clicked.connect(self._browse_metadata_source)
        self.metadataRepositoryLine.textChanged.connect(
            self._update_metadata_source_controls
        )
        self.bgButton.clicked.connect(self._get_background)
        self.bgResetButton.clicked.connect(self._reset_background)
        self.backupBox.clicked.connect(self._set_use_backups)
        self.restoreButton.clicked.connect(self._restore)
        self.clearButton.clicked.connect(self._delete_backups)
        self.mipBox.textChanged.connect(self._set_mip_count)
        for radio in [
            self.noneButton,
            self.lzmaButton,
            self.lz4Button,
            self.lz4hcButton,
            self.lzhamButton,
        ]:
            radio.toggled.connect(lambda checked, r=radio: self._set_packer(r))

        for radio in [self.stretchedButton, self.croppedButton]:
            radio.toggled.connect(lambda checked, r=radio: self._set_background_mode(r))

    def _set_packer(self, radio):
        if radio.isChecked():
            packer = radio.objectName().replace("Button", "")
            if packer != APP_CONFIG.packer:
                APP_CONFIG.packer = packer
                session.commit()
                show_toast(
                    self,
                    "Compression",
                    f"Asset compression set to {packer.upper()}",
                    ToastPreset.INFORMATION_DARK,
                )

    def _set_background_mode(self, radio):
        if radio.isChecked():
            mode = radio.objectName().replace("Button", "")
            if mode != APP_CONFIG.background_mode:
                APP_CONFIG.background_mode = mode
                session.commit()
                if APP_CONFIG.background_path:
                    self._apply_background_style(APP_CONFIG.background_path)
                show_toast(
                    self,
                    "Background Mode",
                    f"Background mode set to {mode.capitalize()}",
                    ToastPreset.INFORMATION_DARK,
                )

    def _set_mip_count(self):
        val = self.mipBox.value()
        if val != APP_CONFIG.mipmap_count:
            APP_CONFIG.mipmap_count = val
            session.commit()
            show_toast(
                self,
                "Mipmaps",
                f"Mipmap count set to {val}",
                ToastPreset.INFORMATION_DARK,
            )

    def _apply_background_style(self, file_path):
        """Apply background image with the selected mode (stretched or cropped)."""
        window = self.window()
        if hasattr(window, "_load_bg"):
            window._load_bg()

    def _delete_backups(self):
        if show_confirmation_dialog(
            "Are you sure you want to delete all backups? "
            "This action cannot be undone.",
            True,
        ):
            self.delete_backups()

    def _restore(self):
        if show_confirmation_dialog(
            "Are you sure you want to restore all changes? "
            "This action cannot be undone.",
            True,
        ):
            self.restore_all_asset_changes()

    def _set_use_backups(self):
        create_backup = self.backupBox.checkState() == Qt.CheckState.Checked
        APP_CONFIG.create_backup = create_backup
        session.commit()

        show_toast(
            self,
            "Backups",
            f"Backups {'enabled' if create_backup else 'disabled'}.",
            ToastPreset.SUCCESS_DARK,
        )

    def _get_game_path(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Duel Links or Player Data Folder"
        )
        if folder:
            self._set_game_path(folder)

    def _auto_detect_game_path(self):
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            paths = find_steam_duel_links_paths()
        finally:
            QGuiApplication.restoreOverrideCursor()

        if not paths:
            show_toast(
                self,
                "Game Path",
                "No downloaded Duel Links accounts found in Steam or Proton prefixes. "
                "Select the folder manually.",
                ToastPreset.INFORMATION_DARK,
            )
            return
        dialog = GamePathSelectDialog(paths, self)
        if dialog.exec() and dialog.selected_game_path():
            self._set_game_path(dialog.selected_game_path())

    def _manual_game_path_entered(self):
        text = self.gameLine.text().strip()
        if text and text != APP_CONFIG.game_path:
            self._set_game_path(text)

    def _set_game_path(self, folder):
        cleaned = str(folder).strip().strip("'\"")
        path = normalize_game_path(cleaned)
        if not path:
            _, msg = is_valid_game_path(cleaned)
            show_toast(
                self,
                "Game Path",
                msg or "Invalid game folder.",
                ToastPreset.WARNING_DARK,
            )
            return
        from pathlib import Path

        selected = Path(cleaned)
        local_data = (
            selected if selected.name.lower() == "localdata" else selected / "LocalData"
        )
        if local_data.is_dir():
            paths = [
                normalize_game_path(str(account))
                for account in sorted(local_data.iterdir())
            ]
            paths = [account for account in paths if account]
            if len(paths) > 1:
                dialog = GamePathSelectDialog(paths, self)
                if not dialog.exec():
                    return
                path = dialog.selected_game_path()
                if not path:
                    return
        APP_CONFIG.game_path = path
        session.commit()
        self.gameLine.setText(path)
        self.gamePathChanged.emit()
        if not APP_CONFIG.version:
            self._check_update()
        show_toast(
            self,
            "Game Path",
            "Game path set. Asset tabs are ready.",
            ToastPreset.SUCCESS_DARK,
        )

    def _set_variables(self):
        self.metadataRepositoryLine.setText(
            APP_CONFIG.metadata_repository or DEFAULT_METADATA_REPOSITORY
        )
        self.metadataBranchLine.setText(
            APP_CONFIG.metadata_branch or DEFAULT_METADATA_BRANCH
        )
        self.gameLine.setText(APP_CONFIG.game_path)
        self.bgLine.setText(APP_CONFIG.background_path)
        self.updateLine.setText(APP_CONFIG.version)
        self.backupBox.setChecked(APP_CONFIG.create_backup or False)
        self.mipBox.setValue(APP_CONFIG.mipmap_count or 10)
        self.updateButton.setText("Check for Updates")
        self.updateButton.setToolTip(
            "Check remote repository for card/sleeve/field updates"
        )
        self.gameButton.setText("Browse...")
        self.gameButton.setToolTip("Select Duel Links game data directory")
        self.bgButton.setText("Browse...")
        self.bgButton.setToolTip("Select custom background image")
        self.bgResetButton.setToolTip("Reset app background to default")
        self.autoDetectGameButton.setToolTip(
            "Automatically search Steam libraries for Duel Links"
        )
        for radio in [
            self.noneButton,
            self.lzmaButton,
            self.lz4Button,
            self.lz4hcButton,
            self.lzhamButton,
        ]:
            if radio.objectName().startswith(APP_CONFIG.packer or "lz4"):
                radio.setChecked(True)
                break

        background_mode = APP_CONFIG.background_mode or "stretched"
        for radio in [self.stretchedButton, self.croppedButton]:
            if radio.objectName().startswith(background_mode):
                radio.setChecked(True)
                break

    def _save_metadata_source(self, notify=True):
        """Persist a validated source; do not invalidate edits or downloaded data."""
        try:
            repository, branch = normalize_metadata_source(
                self.metadataRepositoryLine.text(), self.metadataBranchLine.text()
            )
        except ValueError as error:
            show_toast(self, "Metadata Source", str(error), ToastPreset.WARNING_DARK)
            return False
        APP_CONFIG.metadata_repository = repository
        APP_CONFIG.metadata_branch = branch
        session.commit()
        self.metadataRepositoryLine.setText(repository)
        self.metadataBranchLine.setText(branch)
        if notify:
            show_toast(
                self,
                "Metadata Source",
                "Source saved. Choose Check to refresh metadata.",
                ToastPreset.SUCCESS_DARK,
            )
        return True

    def _update_metadata_source_controls(self):
        """Local sources use the current working tree; branch selection is
        for GitHub."""
        self.metadataBranchLine.setEnabled(
            not is_local_metadata_source(self.metadataRepositoryLine.text().strip())
        )

    def _browse_metadata_source(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Local Metadata Repository"
        )
        if folder:
            self.metadataRepositoryLine.setText(folder)

    def _reset_metadata_source(self):
        """Restore the original repository and its default-branch behavior."""
        self.metadataRepositoryLine.setText(DEFAULT_METADATA_REPOSITORY)
        self.metadataBranchLine.setText(DEFAULT_METADATA_BRANCH)
        self._save_metadata_source()

    def _check_update(self):
        if not self._save_metadata_source(notify=False):
            return
        valid, msg = (
            is_valid_game_path(APP_CONFIG.game_path)
            if APP_CONFIG.game_path
            else (False, "Game Path must be set to update app")
        )
        if valid:
            try:
                self._get_data()
            except Exception as error:
                show_toast(
                    self,
                    "Update",
                    f"Data update failed: {error}",
                    ToastPreset.WARNING_DARK,
                )
        else:
            show_toast(
                self,
                "Update",
                msg or "Game Path must be set to update app",
                ToastPreset.WARNING_DARK,
            )

    def _get_data(self):
        source = metadata_source_key(
            APP_CONFIG.metadata_repository or DEFAULT_METADATA_REPOSITORY,
            APP_CONFIG.metadata_branch or DEFAULT_METADATA_BRANCH,
        )
        remote = get_github_raw_file("data/version.txt")
        local = APP_CONFIG.version

        if (
            is_local_metadata_source(APP_CONFIG.metadata_repository)
            or not local
            or APP_CONFIG.metadata_last_source != source
            or datetime.strptime(local.strip(), "%Y-%m-%d").date()
            < datetime.strptime(remote.strip(), "%Y-%m-%d").date()
        ):
            progress = QProgressDialog("Updating data...", "Cancel", 0, 4, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setWindowTitle("Updating")
            progress.setCancelButton(None)
            progress.show()

            self.updateButton.setEnabled(False)
            try:
                with ThreadPoolExecutor(max_workers=4) as executor:
                    futures = [
                        executor.submit(update)
                        for update in (
                            update_sleeves,
                            update_cards,
                            update_fields,
                            update_characters,
                        )
                    ]
                    pending = set(futures)
                    while pending:
                        done, pending = wait(
                            pending, timeout=0.05, return_when=FIRST_COMPLETED
                        )
                        for future in done:
                            future.result()
                        progress.setValue(len(futures) - len(pending))
                        QApplication.processEvents()
            finally:
                progress.close()
                self.updateButton.setEnabled(True)
            session.expire_all()

            APP_CONFIG.version = remote
            APP_CONFIG.metadata_last_source = source
            session.commit()

            self.updateLine.setText(APP_CONFIG.version)
            self.dataUpdated.emit()

            show_toast(
                self, "Update", "Data updated successfully", ToastPreset.SUCCESS_DARK
            )
        else:
            show_toast(
                self, "Update", "Data already up to date", ToastPreset.SUCCESS_DARK
            )

    def _get_background(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            path = file.toLocalFile()
            APP_CONFIG.background_path = path
            session.commit()
            self.bgLine.setText(APP_CONFIG.background_path)
            self._apply_background_style(path)
            show_toast(
                self,
                "Background",
                f"Background image updated to {Path(path).name}",
                ToastPreset.SUCCESS_DARK,
            )

    def _reset_background(self):
        APP_CONFIG.background_path = None
        session.commit()
        self.bgLine.setText("")
        self._apply_background_style(None)
        show_toast(
            self,
            "Background",
            "App background has been reset to default",
            ToastPreset.INFORMATION_DARK,
        )
