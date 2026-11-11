import logging
from pathlib import Path

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
)

from database.objects import session
from dialogs.simple_dialogs import show_color_dialog
from pages.models.named_asset_list_model import asset_name
from pages.models.sleeve_list_model import SleeveListModel
from pages.ui.sleeve import Ui_Sleeve
from services.sleeve_service import SleeveService
from unity.unity_utils import fetch_bundle_thumb
from util.constants import (
    FIT_MODE_BUTTON_STYLE,
    IMAGE_EXTENSIONS,
    IMAGE_FILTER,
)
from util.image_utils import slugify
from util.paths import get_backups_dir, get_bundles_dir, get_images_dir
from util.ui_util import (
    format_actionable_error,
    open_in_file_manager,
)
from widgets.crop_overlay_widget import CropOverlayWidget
from widgets.image_viewer import ImageViewer
from widgets.inline_alert import notify
from widgets.responsive_editor import ResponsiveEditor

logger = logging.getLogger(__name__)

_SLEEVE_CROP_RATIO = 256 / 374
_BTN_STYLE = FIT_MODE_BUTTON_STYLE


class Sleeve(QtWidgets.QWidget, Ui_Sleeve):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.service = SleeveService()
        self.model = SleeveListModel()
        self.model.filter = ""
        self.model.refresh()
        self.sleevesView.setModel(self.model)
        self.selected = None

        self._crop_mode: bool = False
        self._init_current_viewer()
        self._setup_crop_ui()
        self.responsive_editor = ResponsiveEditor(
            self,
            self.sleevesView,
            "sleeves",
            256 / 374,
            search=True,
            header=self.horizontalLayout,
        )

        self.setAcceptDrops(True)

        self._connect_callbacks()
        self._init_descriptive_controls()

    def _init_descriptive_controls(self) -> None:
        """Set clear, descriptive labels, tooltips, and initial states."""
        self.selectButton.setText("Select Image...")
        self.selectButton.setToolTip(
            "Browse your computer for an image (PNG or JPG) to use on this sleeve."
        )
        self.selectButton.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sleeveEdit.setPlaceholderText(
            "No replacement image selected (browse or drag & drop)..."
        )
        self.sleeveEdit.setToolTip(
            "Path of the selected replacement image. You can also drag and drop an image onto the preview box."
        )
        self.replaceButton.setText("Apply Mod")
        self.replaceButton.setToolTip(
            "Select or drop a replacement image first to enable applying this mod."
        )
        self.replaceButton.setEnabled(False)
        self.restoreButton.setText("Restore Original")
        self.restoreButton.setToolTip(
            "No backup saved yet. Original game art is backed up automatically when you first apply a mod."
        )
        self.restoreButton.setEnabled(False)
        self.extractButton.setText("Extract Artwork")
        self.extractButton.setToolTip(
            "Extracts the current in-game sleeve artwork to a PNG file in images/sleeves/."
        )
        self.extractButton.setEnabled(False)
        self.copyButton.setText("Export Game File")
        self.copyButton.setToolTip(
            "Exports the raw game file to bundles/sleeves/ for advanced modding or manual archiving."
        )
        self.copyButton.setEnabled(False)
        self.borderButton.setText("Pick Border Color...")
        self.borderButton.setToolTip(
            "Choose a custom color to frame the sleeve border."
        )
        self.borderEdit.setPlaceholderText("Border color hex code (e.g. #000000)...")
        self.borderEdit.setToolTip("Hex code for the selected border color.")
        self.checkBox.setText("Custom Border")
        self.checkBox.setToolTip(
            "Enables drawing a custom solid border frame around the sleeve artwork."
        )
        self.fadeCheckBox.setText("Fade Border")
        self.fadeCheckBox.setToolTip(
            "Smoothly blends the custom border into the sleeve artwork with a soft gradient fade."
        )
        self.favoriteBox.setText("Favorite")
        self.favoriteBox.setToolTip("Mark or unmark this sleeve as a favorite.")
        self.favoritesBox.setText("Favorites Only")
        self.favoritesBox.setToolTip("Filter list to display only favorite sleeves.")

        for btn in (
            self.restoreButton,
            self.extractButton,
            self.copyButton,
            self.replaceButton,
        ):
            btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            btn.setMinimumWidth(btn.fontMetrics().horizontalAdvance(btn.text()) + 20)

    def _update_action_states(self) -> None:
        """Deterministically update button states and descriptive tooltips."""
        has_sleeve = self.selected is not None
        has_image = bool(self.service.image_path)
        self.replaceButton.setEnabled(has_sleeve and has_image)
        if not has_image:
            self.replaceButton.setToolTip(
                "Select or drop a replacement image first to enable applying this mod."
            )
        elif not has_sleeve:
            self.replaceButton.setToolTip(
                "Select a sleeve from the list to enable applying this mod."
            )
        else:
            name = asset_name(self.selected)
            self.replaceButton.setToolTip(
                f"Replaces '{name}' in game files with your image. Original art is backed up first."
            )

        has_disk_backup = False
        if has_sleeve and self.selected.medium_bundle:
            backup_path = (
                get_backups_dir() / "sleeves" / f"{slugify(self.selected.medium_bundle)}.png"
            )
            has_disk_backup = backup_path.is_file()

        self.restoreButton.setEnabled(has_disk_backup)
        if has_disk_backup:
            name = asset_name(self.selected)
            self.restoreButton.setToolTip(
                f"Restores '{name}' back to the original game art from your saved backup."
            )
        else:
            self.restoreButton.setToolTip(
                "No backup saved yet. Original game art is backed up automatically when you first apply a mod."
            )

        self.extractButton.setEnabled(has_sleeve)
        if has_sleeve:
            name = asset_name(self.selected)
            self.extractButton.setToolTip(
                f"Extracts '{name}' in-game artwork to a PNG file in images/sleeves/."
            )
        else:
            self.extractButton.setToolTip(
                "Select a sleeve from the list to extract its artwork."
            )

        self.copyButton.setEnabled(has_sleeve)
        if has_sleeve:
            name = asset_name(self.selected)
            self.copyButton.setToolTip(
                f"Exports the raw game file for '{name}' to bundles/sleeves/."
            )
        else:
            self.copyButton.setToolTip(
                "Select a sleeve from the list to export its game file."
            )

    def _init_current_viewer(self) -> None:
        """Replace self.current QLabel with an ImageViewer (preserves aspect ratio)."""
        old = self.current
        max_size = old.maximumSize()
        idx = self.main_content.indexOf(old)
        self.main_content.removeWidget(old)
        old.hide()
        old.deleteLater()
        viewer = ImageViewer()
        viewer.setMaximumSize(max_size)
        viewer.setMinimumSize(1, 1)
        self.main_content.insertWidget(idx, viewer)
        self.current = viewer

    def _setup_crop_ui(self) -> None:
        """Replace the preview QLabel with a mode-stack and add fit-mode buttons."""
        old_preview = self.preview
        max_size = old_preview.maximumSize()
        idx = self.main_content.indexOf(old_preview)
        self.main_content.removeWidget(old_preview)
        old_preview.hide()
        old_preview.deleteLater()

        stretch_viewer = ImageViewer()
        stretch_viewer.setObjectName("preview")
        stretch_viewer.setMaximumSize(max_size)
        stretch_viewer.setMinimumSize(100, 100)
        self.preview = stretch_viewer

        self._mode_stack = QStackedWidget()
        self._mode_stack.setMaximumSize(max_size)
        self._mode_stack.setMinimumSize(100, 100)
        self._mode_stack.addWidget(self.preview)

        self._crop_widget = CropOverlayWidget()
        self._crop_widget.setMaximumSize(self.preview.maximumSize())
        self._crop_widget.setMinimumSize(150, 150)
        self._crop_widget.crop_changed.connect(self._on_crop_changed)
        self._mode_stack.addWidget(self._crop_widget)

        self.main_content.insertWidget(idx, self._mode_stack)

        fit_layout = QHBoxLayout()
        fit_layout.addStretch()
        fit_layout.addWidget(QLabel("Fit Mode:"))

        self._stretch_btn = QPushButton("Stretch")
        self._stretch_btn.setCheckable(True)
        self._stretch_btn.setChecked(True)
        self._stretch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stretch_btn.setStyleSheet(_BTN_STYLE)
        self._stretch_btn.setToolTip(
            "Stretches the image to fill the card sleeve without borders."
        )

        self._crop_btn = QPushButton("Crop")
        self._crop_btn.setCheckable(True)
        self._crop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._crop_btn.setStyleSheet(_BTN_STYLE)
        self._crop_btn.setToolTip(
            "Preserves image proportions and lets you select the cropped area."
        )

        fit_layout.addWidget(self._stretch_btn)
        fit_layout.addWidget(self._crop_btn)
        fit_layout.addStretch()

        self._fit_group = QButtonGroup(self)
        self._fit_group.addButton(self._stretch_btn, 0)
        self._fit_group.addButton(self._crop_btn, 1)
        self._fit_group.setExclusive(True)

        for i in range(self.verticalLayout.count()):
            item = self.verticalLayout.itemAt(i)
            if item.layout() == self.horizontalLayout_3:
                self.verticalLayout.insertLayout(i + 1, fit_layout)
                break

        self._stretch_btn.clicked.connect(lambda: self._set_fit_mode("stretch"))
        self._crop_btn.clicked.connect(lambda: self._set_fit_mode("crop"))

    def _set_fit_mode(self, mode: str) -> None:
        self._crop_mode = mode == "crop"
        if self._crop_mode:
            if self.service.image_path:
                self._crop_widget.set_image(self.service.image_path, _SLEEVE_CROP_RATIO)
                self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()
            else:
                self.service.crop_rect = None
            self._mode_stack.setCurrentIndex(1)
        else:
            self.service.crop_rect = None
            self._mode_stack.setCurrentIndex(0)
        if hasattr(self, "responsive_editor"):
            self.responsive_editor.resize_images()

    def _on_crop_changed(self) -> None:
        if self._crop_mode:
            self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()
        else:
            self.service.crop_rect = None

    def _load_image(self, path: str) -> None:
        try:
            self.sleeveEdit.setText(path)
            self.service.image_path = path
            pixmap = QPixmap(path)
            if pixmap.isNull():
                logger.error("Failed to load image from %s", path)
                notify(
                    self,
                    "error",
                    "Invalid Image",
                    f"Could not load image from '{Path(path).name}'. Please select a valid file.",
                )
                self._update_action_states()
                return
            self.preview.setPixmap(pixmap)
            if self._crop_mode:
                self._crop_widget.set_image(path, _SLEEVE_CROP_RATIO)
                self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()
                self._mode_stack.setCurrentIndex(1)
            else:
                self.service.crop_rect = None
                self._mode_stack.setCurrentIndex(0)
            self._update_action_states()
            if hasattr(self, "responsive_editor"):
                self.responsive_editor.resize_images()
            notify(
                self,
                "info",
                "Image Loaded",
                f"Loaded {Path(path).name} ({pixmap.width()}×{pixmap.height()}).",
            )
        except Exception as error:
            logger.exception("Error loading replacement image: %s", error)
            notify(self, "error", "Image Error", f"Failed to load image: {error}")
            self._update_action_states()

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
                self._load_image(file_path)
                break

    def _restore(self):
        if not self.selected:
            notify(
                self,
                "warning",
                "Restore Unavailable",
                "Please select a sleeve from the list first.",
            )
            return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.restoreButton.setEnabled(False)
        try:
            restored = False
            for bundle in [self.selected.small_bundle, self.selected.medium_bundle]:
                if not bundle:
                    continue
                self.service.bundle = bundle
                if self.service.restore_asset():
                    restored = True
            if restored:
                self.model.refresh()
                try:
                    thumb = fetch_bundle_thumb(self.selected.medium_bundle, (256, 375))
                    if thumb is not None and hasattr(thumb, "pixmap"):
                        self.current.setPixmap(thumb.pixmap(256, 375))
                except Exception as thumb_err:
                    logger.exception(
                        "Failed to refresh sleeve thumbnail: %s", thumb_err
                    )
                notify(
                    self,
                    "success",
                    "Sleeve Restored",
                    f"Restored '{asset_name(self.selected)}' to original artwork.",
                )
                self._update_sleeve_status()
            else:
                notify(
                    self,
                    "warning",
                    "Restore Unavailable",
                    f"No backup found for '{asset_name(self.selected)}'.",
                )
        except Exception as error:
            logger.exception("Failed to restore sleeve backup: %s", error)
            summary, hint = format_actionable_error(error, "restoring sleeve backup")
            notify(self, "error", summary, hint)
        finally:
            QGuiApplication.restoreOverrideCursor()
            self._update_action_states()

    def _connect_callbacks(self):
        self.sleevesView.clicked.connect(self._on_sleeve_clicked)
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace_sleeve)
        self.copyButton.clicked.connect(self._copy)
        self.extractButton.clicked.connect(self._extract_texture)
        self.borderButton.clicked.connect(self._select_color)
        self.restoreButton.clicked.connect(self._restore)
        self.checkBox.clicked.connect(self._switch_border)
        self.fadeCheckBox.clicked.connect(self._toggle_fade)
        self.favoriteBox.stateChanged.connect(self._toggle_favorite)
        self.favoritesBox.stateChanged.connect(self._toggle_favorites_filter)

    def _toggle_favorite(self, state):
        if self.selected and self.selected.favorite != (
            state == QtCore.Qt.CheckState.Checked.value
        ):
            self.selected.favorite = state == QtCore.Qt.CheckState.Checked.value
            try:
                session.commit()
                status = "added to" if self.selected.favorite else "removed from"
                notify(
                    self,
                    "success",
                    "Favorite Updated",
                    f"'{asset_name(self.selected)}' {status} favorites.",
                )
            except Exception as error:
                logger.exception("Failed to update favorite status: %s", error)
                session.rollback()
                notify(
                    self,
                    "error",
                    "Favorite Failed",
                    "Could not update favorite status.",
                )

    def _toggle_favorites_filter(self, state):
        self.model.show_favorites = state == QtCore.Qt.CheckState.Checked.value
        try:
            self.model.refresh()
            self.model.layoutChanged.emit()
            count = self.model.rowCount()
            if self.model.show_favorites:
                notify(
                    self,
                    "info",
                    "Favorites Filter",
                    f"Showing {count} favorite sleeve{'s' if count != 1 else ''}."
                    if count > 0
                    else "No favorite sleeves found.",
                )
        except Exception as error:
            logger.exception("Failed to update favorites filter: %s", error)
            notify(self, "error", "Filter Error", "Failed to update favorites filter.")

    def _update_sleeve_status(self) -> None:
        if not self.selected:
            return
        backup_path = (
            get_backups_dir() / "sleeves" / f"{slugify(self.selected.medium_bundle)}.png"
        )
        status_text = (
            "Backup: Saved"
            if backup_path.is_file()
            else "Backup: Will auto-create on mod"
        )
        self.bundle.setText(f"Editing {asset_name(self.selected)}\n{status_text}")

    def _on_sleeve_clicked(self, index):
        if not index.isValid() or not (0 <= index.row() < len(self.model.assets)):
            return
        self.selected = self.model.assets[index.row()]
        try:
            thumb = fetch_bundle_thumb(self.selected.medium_bundle, (256, 375))
            if thumb is not None and hasattr(thumb, "pixmap"):
                self.current.setPixmap(thumb.pixmap(256, 375))
            else:
                logger.warning(
                    "Thumbnail unavailable for sleeve %s",
                    getattr(self.selected, "medium_bundle", "unknown"),
                )
        except Exception as error:
            logger.exception("Failed to load sleeve preview: %s", error)
            notify(
                self,
                "error",
                "Preview Error",
                "Could not load preview image for selected sleeve.",
            )
        self.service.bundle = self.selected.medium_bundle
        self._update_sleeve_status()
        self.label.setText(f"Sleeves - {asset_name(self.selected)}")
        self.favoriteBox.setChecked(bool(self.selected.favorite))
        self._update_action_states()

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(
            self, "Select Replacement Image", "", IMAGE_FILTER
        )

        if file and file.url() != "":
            self._load_image(file.toLocalFile())

    def _copy(self):
        if not self.selected:
            notify(
                self,
                "warning",
                "Export Unavailable",
                "Select a sleeve from the list first.",
            )
            return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.service.copy_bundle()
            dest = get_bundles_dir() / "sleeves" / self.service.bundle
            notify(
                self,
                "success",
                "Game File Exported",
                f"Exported game file to {dest}.",
            )
            open_in_file_manager(dest)
        except Exception as error:
            logger.exception("Failed to export sleeve game file: %s", error)
            summary, hint = format_actionable_error(error, "exporting sleeve game file")
            notify(self, "error", summary, hint)
        finally:
            QGuiApplication.restoreOverrideCursor()

    def _extract_texture(self):
        if not self.selected:
            notify(
                self,
                "warning",
                "Extraction Unavailable",
                "Select a sleeve from the list first.",
            )
            return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.service.extract_texture(self.service.bundle)
            dest = get_images_dir() / "sleeves" / f"{slugify(self.service.bundle)}.png"
            notify(
                self,
                "success",
                "Artwork Extracted",
                f"Extracted artwork to {dest}.",
            )
            open_in_file_manager(dest)
        except Exception as error:
            logger.exception("Failed to extract sleeve artwork: %s", error)
            summary, hint = format_actionable_error(error, "extracting sleeve artwork")
            notify(self, "error", summary, hint)
        finally:
            QGuiApplication.restoreOverrideCursor()

    def _replace_sleeve(self):
        if not self.selected:
            notify(
                self,
                "warning",
                "Modification Unavailable",
                "Please select a sleeve from the list first.",
            )
            return
        if not self.service.image_path:
            notify(
                self,
                "warning",
                "Modification Unavailable",
                "Please select a replacement image first.",
            )
            return

        bundles = [self.selected.small_bundle, self.selected.medium_bundle]
        for bundle in bundles:
            if not bundle:
                continue
            backup_path = get_backups_dir() / "sleeves" / f"{slugify(bundle)}.png"
            if not backup_path.is_file():
                try:
                    self.service.bundle = bundle
                    self.service.create_backup(bundle)
                except Exception as error:
                    logger.exception(
                        "Failed to create safety backup for sleeve: %s", error
                    )
                    summary, hint = format_actionable_error(
                        error, "creating safety backup for sleeve"
                    )
                    notify(self, "error", summary, hint)
                    return
        try:
            self.model.set_backup_state(self.selected.id, True)
            session.commit()
        except Exception as error:
            logger.exception("Failed to save backup status to database: %s", error)
            session.rollback()

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.replaceButton.setText("Applying Mod...")
        self.replaceButton.setEnabled(False)
        try:
            for bundle in bundles:
                if not bundle:
                    continue
                self.service.bundle = bundle
                self.service.replace_bundle()

            self.model.refresh()
            try:
                thumb = fetch_bundle_thumb(self.selected.medium_bundle, (256, 375))
                if thumb is not None and hasattr(thumb, "pixmap"):
                    self.current.setPixmap(thumb.pixmap(256, 375))
            except Exception as thumb_err:
                logger.exception("Failed to refresh sleeve thumbnail: %s", thumb_err)

            notify(
                self,
                "success",
                "Sleeve Mod Applied",
                f"Updated '{asset_name(self.selected)}'. Original artwork is backed up.",
            )
            self._update_sleeve_status()
        except Exception as error:
            logger.exception("Failed to modify sleeve game file: %s", error)
            summary, hint = format_actionable_error(error, "modifying sleeve game file")
            notify(self, "error", summary, hint)
        finally:
            QGuiApplication.restoreOverrideCursor()
            self.replaceButton.setText("Apply Mod")
            self._update_action_states()

    def _select_color(self):
        try:
            color = show_color_dialog()
            if color:
                self.service.border_color = color.name()
                self.borderEdit.setText(color.name())
                self.borderButton.setText(f"Border: {color.name()}")
                self._switch_border()
                notify(
                    self,
                    "info",
                    "Border Color",
                    f"Border color set to {color.name()}.",
                )
        except Exception as error:
            logger.exception("Failed to select border color: %s", error)
            notify(
                self, "error", "Color Selection Error", "Could not set border color."
            )

    def _switch_border(self):
        border_enabled = self.checkBox.isChecked()
        self.fadeCheckBox.setEnabled(border_enabled)
        color = self.service.border_color or "#000000"

        if border_enabled:
            self.preview.setStyleSheet(f"""
                #preview {{
                    border: 15px solid {color};
                }}
            """)
        else:
            self.preview.setStyleSheet("")
            self.fadeCheckBox.setChecked(False)

        self.service.border = border_enabled
        self.service.border_fade = self.fadeCheckBox.isChecked()

    def _toggle_fade(self):
        self.service.border_fade = self.fadeCheckBox.isChecked()
        self._switch_border()
