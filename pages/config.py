import logging
import os
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)

from database.objects import session
from dialogs.game_path_select_dialog import GamePathSelectDialog
from pages.models.asset_list_model import AssetListModel
from pages.ui.config import Ui_Config
from services.unity_service import UnityService
from services.update_service import (
    get_github_raw_file,
    metadata_tables_empty,
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
from widgets.inline_alert import attach_inline_alert, notify

logger = logging.getLogger(__name__)


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
        attach_inline_alert(self, self.verticalLayout)

        self.gamePathErrorLabel = QLabel(self.configPanel)
        self.gamePathErrorLabel.setObjectName("gamePathErrorLabel")
        self.gamePathErrorLabel.setStyleSheet("color: #e06c75; font-size: 11px;")
        self.gamePathErrorLabel.setWordWrap(True)
        self.gamePathErrorLabel.setVisible(False)
        self.gamePathStatusLabel = self.gamePathErrorLabel

        field_layout = QVBoxLayout()
        field_layout.setSpacing(2)
        field_layout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout.removeWidget(self.gameLine)
        field_layout.addWidget(self.gameLine)
        field_layout.addWidget(self.gamePathErrorLabel)
        self.horizontalLayout.insertLayout(0, field_layout)
        row_height = max(
            self.gameLine.sizeHint().height(),
            self.gameButton.sizeHint().height(),
            self.autoDetectGameButton.sizeHint().height(),
        )
        for control in (self.gameLine, self.gameButton, self.autoDetectGameButton):
            control.setFixedHeight(row_height)
        self.horizontalLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        for control in (self.gameButton, self.autoDetectGameButton):
            self.horizontalLayout.setAlignment(control, Qt.AlignmentFlag.AlignTop)
        self.horizontalLayout.setAlignment(
            field_layout,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )

        self.gameLine.setReadOnly(False)
        self.autoDetectGameButton.clicked.connect(self._auto_detect_game_path)
        self._connect_callbacks()
        self._set_variables()
        self._refresh_metadata_state()
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
                logger.info("Background image updated via drop: %s", file_path)
                notify(
                    self,
                    "success",
                    "Background",
                    "Background image set successfully.",
                )
                break

    def restore_all_asset_changes(self) -> None:
        count = 0
        try:
            for service, model in self._get_services_and_models():
                backups_path = os.path.join("backups", service.subfolder)

                if os.path.exists(backups_path):
                    for filename in os.listdir(backups_path):
                        file_path = os.path.join(backups_path, filename)

                        if os.path.isfile(file_path):
                            service.bundle = filename.replace(".png", "")
                            count += 1 if service.restore_asset() else 0

                model.refresh()

            logger.info("Restored %d assets to original state.", count)
            notify(
                self,
                "success",
                "Backups",
                f"{count} game files restored successfully.",
            )
        except Exception as error:
            logger.error("Failed to restore asset changes: %s", error, exc_info=True)
            notify(
                self,
                "error",
                "Restore Failed",
                f"Could not restore assets: {error}",
            )

    def delete_backups(self) -> None:
        count = 0
        try:
            for service, model in self._get_services_and_models():
                backups_path = os.path.join("backups", service.subfolder)

                if os.path.exists(backups_path):
                    for filename in os.listdir(backups_path):
                        os.remove(os.path.join(backups_path, filename))
                        count += 1

                model.reset_backups()

            logger.info("Deleted %d backups successfully.", count)
            notify(
                self,
                "success",
                "Backups",
                f"{count} backups have been deleted successfully.",
            )
        except Exception as error:
            logger.error("Failed to delete backups: %s", error, exc_info=True)
            notify(
                self,
                "error",
                "Delete Failed",
                f"Could not delete backups: {error}",
            )

    def _get_services_and_models(self):
        services: list[UnityService] = get_instances_of_subclasses(UnityService)
        models: list[AssetListModel] = get_instances_of_subclasses(AssetListModel)

        return zip(services, models, strict=True)

    def _connect_callbacks(self):
        self.gameButton.clicked.connect(self._get_game_path)
        self.gameLine.returnPressed.connect(self._manual_game_path_entered)
        self.gameLine.editingFinished.connect(self._manual_game_path_entered)
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
                logger.info("File compression set to %s", packer.upper())
                notify(
                    self,
                    "info",
                    "Compression",
                    f"File compression set to {packer.upper()}.",
                )

    def _set_background_mode(self, radio):
        if radio.isChecked():
            mode = radio.objectName().replace("Button", "")
            if mode != APP_CONFIG.background_mode:
                APP_CONFIG.background_mode = mode
                session.commit()
                if APP_CONFIG.background_path:
                    self._apply_background_style(APP_CONFIG.background_path)
                logger.info("Background mode set to %s", mode.capitalize())
                notify(
                    self,
                    "info",
                    "Background Mode",
                    f"Background mode set to {mode.capitalize()}.",
                )

    def _set_mip_count(self):
        val = self.mipBox.value()
        if val != APP_CONFIG.mipmap_count:
            APP_CONFIG.mipmap_count = val
            session.commit()
            logger.info("Image quality levels set to %d", val)
            notify(
                self,
                "info",
                "Image Quality",
                f"Image quality set to {val}.",
            )

    def _apply_background_style(self, file_path):
        """Apply background image with the selected mode (stretched or cropped)."""
        window = self.window()
        if hasattr(window, "_load_bg"):
            window._load_bg()

    def _delete_backups(self):
        answer = QMessageBox.question(
            self,
            "Delete All Backups",
            "Are you sure you want to delete all saved backups? This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.delete_backups()

    def _restore(self):
        answer = QMessageBox.question(
            self,
            "Restore All Game Files",
            "Are you sure you want to restore all game files to their original state? This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.restore_all_asset_changes()

    def _set_use_backups(self):
        create_backup = self.backupBox.checkState() == Qt.CheckState.Checked
        APP_CONFIG.create_backup = create_backup
        session.commit()
        state_str = "enabled" if create_backup else "disabled"
        logger.info("Automatic backups %s", state_str)
        notify(
            self,
            "success",
            "Backups",
            f"Backups {state_str}.",
        )

    def _get_game_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Duel Links Game Folder")
        if folder:
            self._set_game_path(folder)

    def _auto_detect_game_path(self):
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            paths = find_steam_duel_links_paths()
        finally:
            QGuiApplication.restoreOverrideCursor()

        if not paths:
            msg = (
                "No downloaded Duel Links accounts found in Steam libraries. "
                "Please select the game folder manually."
            )
            logger.warning("Auto-detect failed: %s", msg)
            self.gamePathErrorLabel.setText(msg)
            self.gamePathErrorLabel.setVisible(True)
            notify(self, "info", "Game Folder", msg)
            return

        dialog = GamePathSelectDialog(paths, self)
        if dialog.exec() and dialog.selected_game_path():
            self._set_game_path(dialog.selected_game_path())

    def _manual_game_path_entered(self):
        text = self.gameLine.text().strip().strip("'\"")
        self._set_game_path(text)

    def _update_game_dependent_controls(self, is_valid: bool) -> None:
        """
        Enable or disable controls that require a verified game installation.

        Game-dependent controls:
        - updateButton: Fetching card/asset names requires verifying game files.
        - restoreButton: Restoring original artwork directly modifies game files.
        - clearButton: Purging backup files is gated to prevent unintended state changes
          when no valid game directory is active.

        App-level preferences (background wallpaper, compression packer, image quality)
        remain enabled regardless of game installation state.
        """
        self.updateButton.setEnabled(is_valid)
        self.restoreButton.setEnabled(is_valid)
        self.clearButton.setEnabled(is_valid)

        if is_valid:
            if metadata_tables_empty():
                self.updateButton.setText("Download Card Data")
                self.updateButton.setToolTip(
                    "Downloads the card, sleeve, field, and character list "
                    "so the asset tabs can show content."
                )
            else:
                self.updateButton.setText("Check for Updates")
                self.updateButton.setToolTip(
                    "Check for Updates: Download latest card, sleeve, and field names."
                )
            self.restoreButton.setToolTip(
                "Revert all modded assets that have backups to their original in-game artwork."
            )
            self.clearButton.setToolTip(
                "Permanently delete all saved backup files to reclaim disk space."
            )
        else:
            if metadata_tables_empty():
                self.updateButton.setText("Download Card Data")
                self.updateButton.setToolTip(
                    "Set your game folder first, then download card data "
                    "to fill the asset tabs."
                )
            else:
                self.updateButton.setText("Check for Updates")
                self.updateButton.setToolTip(
                    "Set your game folder in Configuration to check for updates."
                )
            self.restoreButton.setToolTip(
                "Set your game folder in Configuration to restore original game files."
            )
            self.clearButton.setToolTip(
                "Set your game folder in Configuration to delete backups."
            )

    def _set_game_path(self, folder):
        cleaned = str(folder).strip().strip("'\"") if folder else ""
        if not cleaned:
            err_msg = "Game folder not set. Please select your game data folder."
            self.gameLine.setText("")
            self.gamePathErrorLabel.setText(err_msg)
            self.gamePathErrorLabel.setVisible(True)
            self._update_game_dependent_controls(False)
            if APP_CONFIG.game_path is not None:
                APP_CONFIG.game_path = None
                session.commit()
                self.gamePathChanged.emit()
            logger.warning("Game path cleared or left empty.")
            return

        selected = Path(cleaned)
        local_data = (
            selected if selected.name.lower() == "localdata" else selected / "LocalData"
        )
        if local_data.is_dir():
            try:
                account_candidates = [
                    normalize_game_path(str(account))
                    for account in sorted(local_data.iterdir())
                ]
                paths = [p for p in account_candidates if p]
                if len(paths) > 1:
                    dialog = GamePathSelectDialog(paths, self)
                    if not dialog.exec():
                        return
                    selected_account = dialog.selected_game_path()
                    if not selected_account:
                        return
                    cleaned = selected_account
            except OSError:
                pass

        normalized = normalize_game_path(cleaned)
        valid = False
        error_msg = None
        if normalized:
            valid, error_msg = is_valid_game_path(normalized)
        else:
            valid, error_msg = is_valid_game_path(cleaned)

        if not valid or not normalized:
            plain_err = (
                error_msg
                or "Select a Duel Links installation or game data folder containing dlpc_Data/data.unity3d."
            ).replace("LocalData", "game data folder")
            self.gameLine.setText(cleaned)
            self.gamePathErrorLabel.setText(plain_err)
            self.gamePathErrorLabel.setVisible(True)
            self._update_game_dependent_controls(False)
            if APP_CONFIG.game_path != cleaned:
                APP_CONFIG.game_path = cleaned
                session.commit()
                self.gamePathChanged.emit()
            logger.warning("Invalid game folder '%s': %s", cleaned, plain_err)
            return

        APP_CONFIG.game_path = normalized
        session.commit()
        self.gameLine.setText(normalized)
        self.gamePathErrorLabel.setText("")
        self.gamePathErrorLabel.setVisible(False)
        self._update_game_dependent_controls(True)
        self.gamePathChanged.emit()
        logger.info("Game folder successfully verified and set to: %s", normalized)
        notify(
            self,
            "success",
            "Game Folder",
            "Game folder set. Asset tabs are ready.",
        )
        if not APP_CONFIG.version or metadata_tables_empty():
            reason = "missing version" if not APP_CONFIG.version else "empty tables"
            logger.info(
                "Triggering metadata download after game path set (%s).", reason
            )
            self._check_update()

    def _set_variables(self):
        self.metadataRepositoryLine.setText(
            APP_CONFIG.metadata_repository or DEFAULT_METADATA_REPOSITORY
        )
        self.metadataBranchLine.setText(
            APP_CONFIG.metadata_branch or DEFAULT_METADATA_BRANCH
        )
        self.bgLine.setText(APP_CONFIG.background_path or "")
        self.updateLine.setText(APP_CONFIG.version or "")
        self.backupBox.setChecked(
            True if APP_CONFIG.create_backup is None else bool(APP_CONFIG.create_backup)
        )
        self.mipBox.setValue(APP_CONFIG.mipmap_count or 10)

        if hasattr(self, "label"):
            self.label.setText("Game Folder:")
        if hasattr(self, "label_6"):
            self.label_6.setText("Image Quality:")

        self.gameButton.setText("Browse...")
        self.gameButton.setToolTip("Manually select your Duel Links game folder.")
        self.gameLine.setToolTip("Folder path for Duel Links game data.")
        self.autoDetectGameButton.setToolTip(
            "Scans your Steam library folders across all installed drives to locate Duel Links automatically."
        )
        self.bgButton.setText("Browse...")
        self.bgButton.setToolTip(
            "Choose an image (PNG or JPG) to set as the background wallpaper for this application."
        )
        self.bgResetButton.setToolTip(
            "Removes the custom background image and returns to the default dark theme."
        )
        self.stretchedButton.setToolTip(
            "Stretches the background image to fill the entire application window."
        )
        self.croppedButton.setToolTip(
            "Centers the background image while keeping its original proportions."
        )
        self.backupBox.setToolTip(
            "Automatically saves original game artwork to backups/ when modding, protecting your original files."
        )
        self.mipBox.setToolTip(
            "Image quality levels for 3D rendering (10 is recommended for smooth in-game animations)."
        )
        if hasattr(self, "browseMetadataSourceButton"):
            self.browseMetadataSourceButton.setToolTip(
                "Browse for a local folder containing community metadata files."
            )
        if hasattr(self, "saveMetadataSourceButton"):
            self.saveMetadataSourceButton.setToolTip(
                "Saves this repository or local folder as your active metadata source."
            )
        if hasattr(self, "resetMetadataSourceButton"):
            self.resetMetadataSourceButton.setToolTip(
                "Resets the metadata repository and branch back to the official community default."
            )

        raw_path = APP_CONFIG.game_path
        cleaned = str(raw_path).strip().strip("'\"") if raw_path else ""
        normalized = normalize_game_path(cleaned) if cleaned else None
        valid = False
        if normalized:
            valid_flag, _ = is_valid_game_path(normalized)
            valid = bool(valid_flag)
            if valid and APP_CONFIG.game_path != normalized:
                APP_CONFIG.game_path = normalized
                session.commit()

        if valid:
            self.gameLine.setText(normalized)
            self.gamePathErrorLabel.setText("")
            self.gamePathErrorLabel.setVisible(False)
            self._update_game_dependent_controls(True)
        else:
            self.gameLine.setText(cleaned)
            if cleaned:
                _, err = is_valid_game_path(cleaned)
                err_text = (err or "Invalid game folder.").replace(
                    "LocalData", "game data folder"
                )
                self.gamePathErrorLabel.setText(err_text)
                self.gamePathErrorLabel.setVisible(True)
            else:
                self.gamePathErrorLabel.setText(
                    "Game folder not set. Please select your game data folder."
                )
                self.gamePathErrorLabel.setVisible(True)
            self._update_game_dependent_controls(False)

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

    def _save_metadata_source(self, notify_user: bool = True):
        """Persist a validated source; do not invalidate edits or downloaded data."""
        try:
            repository, branch = normalize_metadata_source(
                self.metadataRepositoryLine.text(), self.metadataBranchLine.text()
            )
        except ValueError as error:
            logger.warning("Invalid metadata source provided: %s", error)
            notify(self, "warning", "Metadata Source", str(error))
            return False
        APP_CONFIG.metadata_repository = repository
        APP_CONFIG.metadata_branch = branch
        session.commit()
        self.metadataRepositoryLine.setText(repository)
        self.metadataBranchLine.setText(branch)
        if notify_user:
            logger.info("Saved metadata source: %s @ %s", repository, branch)
            notify(
                self,
                "success",
                "Metadata Source",
                "Source saved. Choose Check for Updates to refresh metadata.",
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
        self._save_metadata_source(True)

    def _check_update(self):
        if not self._save_metadata_source(notify_user=False):
            return
        raw_path = APP_CONFIG.game_path
        cleaned = str(raw_path).strip().strip("'\"") if raw_path else ""
        normalized = normalize_game_path(cleaned) if cleaned else None
        valid = False
        msg = None
        if normalized:
            valid, msg = is_valid_game_path(normalized)
        elif cleaned:
            valid, msg = is_valid_game_path(cleaned)
        else:
            msg = "Game folder must be set to check for updates."

        if valid:
            try:
                self._get_data()
            except Exception as error:
                logger.error("Data update failed: %s", error, exc_info=True)
                notify(
                    self,
                    "error",
                    "Update Failed",
                    f"Data update failed: {error}",
                )
        else:
            plain_msg = (
                msg or "Game folder must be set to check for updates."
            ).replace("LocalData", "game data folder")
            logger.warning("Update check prevented: %s", plain_msg)
            self.gamePathErrorLabel.setText(plain_msg)
            self.gamePathErrorLabel.setVisible(True)
            notify(
                self,
                "warning",
                "Update Unavailable",
                plain_msg,
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
            or metadata_tables_empty()
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
            self._refresh_metadata_state()

            logger.info("Metadata successfully updated to version %s", remote)
            notify(self, "success", "Update", "Data updated successfully.")
        else:
            logger.info("Metadata already up to date at version %s", local)
            self._refresh_metadata_state()
            notify(self, "info", "Update", "Data already up to date.")

    def _refresh_metadata_state(self) -> None:
        """Surface a persistent first-run prompt until card data is present."""
        missing = metadata_tables_empty()
        self.updateButton.setText(
            "Download Card Data" if missing else "Check for Updates"
        )
        if missing:
            self.updateButton.setToolTip(
                "Downloads the card, sleeve, field, and character list "
                "so the asset tabs can show content."
            )
            self.updateLine.setText("Not downloaded yet")
            notify(
                self,
                "warning",
                "Card Data Missing",
                "No card data yet. Set your game folder, then click "
                "Download Card Data to fill the asset tabs.",
            )
            logger.warning("Asset metadata tables are empty; prompting download.")
        elif self.updateLine.text() == "Not downloaded yet":
            self.updateLine.setText(APP_CONFIG.version or "")

    def _get_background(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            path = file.toLocalFile()
            APP_CONFIG.background_path = path
            session.commit()
            self.bgLine.setText(APP_CONFIG.background_path)
            self._apply_background_style(path)
            logger.info("Background image updated to %s", Path(path).name)
            notify(
                self,
                "success",
                "Background",
                f"Background image updated to {Path(path).name}.",
            )

    def _reset_background(self):
        APP_CONFIG.background_path = None
        session.commit()
        self.bgLine.setText("")
        self._apply_background_style(None)
        logger.info("Background reset to default theme.")
        notify(
            self,
            "info",
            "Background",
            "App background has been reset to default.",
        )
