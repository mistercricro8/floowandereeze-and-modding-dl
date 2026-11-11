import logging
from pathlib import Path

from PySide6 import QtWidgets
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
from pages.models.field_list_model import FieldListModel
from pages.models.named_asset_list_model import asset_name
from pages.ui.field import Ui_Field
from services.field_service import FieldService
from unity.unity_utils import fetch_bundle_thumb, fetch_field_thumb
from util.constants import (
    APP_CONFIG,
    FIT_MODE_BUTTON_STYLE,
    IMAGE_EXTENSIONS,
    IMAGE_FILTER,
)
from util.image_utils import slugify
from util.ui_util import (
    format_actionable_error,
    open_in_file_manager,
)
from widgets.crop_overlay_widget import CropOverlayWidget
from widgets.image_viewer import ImageViewer
from widgets.inline_alert import notify
from widgets.responsive_editor import ResponsiveEditor

logger = logging.getLogger(__name__)

_FIELD_CROP_RATIO = 2.0
_BTN_STYLE = FIT_MODE_BUTTON_STYLE


class Field(QtWidgets.QWidget, Ui_Field):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.service = FieldService()
        self.model = FieldListModel()
        self.model.filter = ""
        self.model.refresh()
        self.fieldsView.setModel(self.model)
        self.selected = None

        self._crop_mode: bool = False
        self._init_current_viewer()
        self._setup_crop_ui()
        self.responsive_editor = ResponsiveEditor(
            self,
            self.fieldsView,
            "fields",
            2.0,
            search=True,
            header=None,
        )

        self.setAcceptDrops(True)

        self._connect_callbacks()
        self._init_descriptive_controls()

    def _init_descriptive_controls(self) -> None:
        """Set clear, descriptive labels, tooltips, and initial states."""
        self.selectButton.setText("Select Image...")
        self.selectButton.setToolTip(
            "Browse your computer for an image (PNG or JPG) to use on this playmat."
        )
        self.selectButton.setCursor(Qt.CursorShape.PointingHandCursor)
        self.assetEdit.setPlaceholderText(
            "No replacement image selected (browse or drag & drop)..."
        )
        self.assetEdit.setToolTip(
            "Path of the selected replacement image. You can also drag and drop an image onto the preview box."
        )
        self.replaceButton.setText("Apply Mod")
        self.replaceButton.setToolTip(
            "Select or drop a replacement image first to enable applying this mod."
        )
        self.replaceButton.setEnabled(False)

        self.restoreButton = QPushButton("Restore Original", self)
        self.restoreButton.setObjectName("restoreButton")
        self.restoreButton.setEnabled(False)
        self.restoreButton.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restoreButton.setToolTip(
            "No backup saved yet. Original game art is backed up automatically when you first apply a mod."
        )
        self.restoreButton.clicked.connect(self._restore)
        idx = self.horizontalLayout_4.indexOf(self.replaceButton)
        self.horizontalLayout_4.insertWidget(idx, self.restoreButton)

        self.extractButton.setText("Extract Artwork")
        self.extractButton.setToolTip(
            "Extracts the current in-game playmat artwork to a PNG file in images/fields/."
        )
        self.extractButton.setEnabled(False)
        self.copyButton.setText("Export Game File")
        self.copyButton.setToolTip(
            "Exports the raw game file to bundles/fields/ for advanced modding or manual archiving."
        )
        self.copyButton.setEnabled(False)

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
        has_field = self.selected is not None
        has_image = bool(self.service.image_path)
        if hasattr(self, "replaceButton"):
            self.replaceButton.setEnabled(has_field and has_image)
            if not has_image:
                self.replaceButton.setToolTip(
                    "Select or drop a replacement image first to enable applying this mod."
                )
            elif not has_field:
                self.replaceButton.setToolTip(
                    "Select a playmat from the list to enable applying this mod."
                )
            else:
                name = asset_name(self.selected)
                self.replaceButton.setToolTip(
                    f"Replaces '{name}' in game files with your image. Original art is backed up first."
                )

        has_disk_backup = False
        if has_field and getattr(self.selected, "medium_bundle", None):
            backup_path = (
                Path("backups/fields") / f"{slugify(self.selected.medium_bundle)}.png"
            )
            has_disk_backup = backup_path.is_file()

        if hasattr(self, "restoreButton"):
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

        if hasattr(self, "extractButton"):
            self.extractButton.setEnabled(has_field)
            if has_field:
                name = asset_name(self.selected)
                self.extractButton.setToolTip(
                    f"Extracts '{name}' in-game artwork to a PNG file in images/fields/."
                )
            else:
                self.extractButton.setToolTip(
                    "Select a playmat from the list to extract its artwork."
                )

        if hasattr(self, "copyButton"):
            self.copyButton.setEnabled(has_field)
            if has_field:
                name = asset_name(self.selected)
                self.copyButton.setToolTip(
                    f"Exports the raw game file for '{name}' to bundles/fields/."
                )
            else:
                self.copyButton.setToolTip(
                    "Select a playmat from the list to export its game file."
                )

    def _init_current_viewer(self) -> None:
        """Replace self.current QLabel with an ImageViewer (preserves aspect ratio)."""
        old = self.current
        max_size = old.maximumSize()
        idx = self.horizontalLayout.indexOf(old)
        self.horizontalLayout.removeWidget(old)
        old.hide()
        old.deleteLater()
        viewer = ImageViewer()
        viewer.setMaximumSize(max_size)
        viewer.setMinimumSize(1, 1)
        self.horizontalLayout.insertWidget(idx, viewer)
        self.current = viewer

    def _setup_crop_ui(self) -> None:
        """Replace the preview QLabel with a mode-stack and add fit-mode buttons."""
        old_preview = self.preview
        max_size = old_preview.maximumSize()
        idx = self.horizontalLayout_2.indexOf(old_preview)
        self.horizontalLayout_2.removeWidget(old_preview)
        old_preview.hide()
        old_preview.deleteLater()

        stretch_viewer = ImageViewer()
        stretch_viewer.setObjectName("preview")
        stretch_viewer.setMaximumSize(max_size)
        stretch_viewer.setMinimumSize(100, 50)
        self.preview = stretch_viewer

        self._mode_stack = QStackedWidget()
        self._mode_stack.setMaximumSize(max_size)
        self._mode_stack.setMinimumSize(100, 50)
        self._mode_stack.addWidget(self.preview)

        self._crop_widget = CropOverlayWidget()
        self._crop_widget.setMaximumSize(self.preview.maximumSize())
        self._crop_widget.setMinimumSize(150, 75)
        self._crop_widget.crop_changed.connect(self._on_crop_changed)
        self._mode_stack.addWidget(self._crop_widget)

        self.horizontalLayout_2.insertWidget(idx, self._mode_stack)

        fit_layout = QHBoxLayout()
        fit_layout.addStretch()
        fit_layout.addWidget(QLabel("Fit Mode:"))

        self._stretch_btn = QPushButton("Stretch")
        self._stretch_btn.setCheckable(True)
        self._stretch_btn.setChecked(True)
        self._stretch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stretch_btn.setStyleSheet(_BTN_STYLE)
        self._stretch_btn.setToolTip(
            "Stretches the image across the entire playmat surface."
        )

        self._crop_btn = QPushButton("Crop")
        self._crop_btn.setCheckable(True)
        self._crop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._crop_btn.setStyleSheet(_BTN_STYLE)
        self._crop_btn.setToolTip(
            "Preserves image proportions and lets you select the visible playmat area."
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
                self._crop_widget.set_image(self.service.image_path, _FIELD_CROP_RATIO)
                self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()
            else:
                self.service.crop_rect = None
            self._mode_stack.setCurrentIndex(1)
        else:
            self.service.crop_rect = None
            self._mode_stack.setCurrentIndex(0)

    def _on_crop_changed(self) -> None:
        if self._crop_mode:
            self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()
        else:
            self.service.crop_rect = None

    def _load_image(self, path: str) -> None:
        try:
            self.assetEdit.setText(path)
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
                self._crop_widget.set_image(path, _FIELD_CROP_RATIO)
                self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()
                self._mode_stack.setCurrentIndex(1)
            else:
                self.service.crop_rect = None
                self._mode_stack.setCurrentIndex(0)
            self._update_action_states()
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

    def _connect_callbacks(self):
        self.fieldsView.clicked.connect(self._on_field_clicked)
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace)
        self.extractButton.clicked.connect(self._extract_texture)
        self.copyButton.clicked.connect(self._copy)

    def _update_field_status(self) -> None:
        if not self.selected:
            return
        backup_path = (
            Path("backups/fields") / f"{slugify(self.selected.medium_bundle)}.png"
        )
        status_text = (
            "Backup: Saved"
            if backup_path.is_file()
            else "Backup: Will auto-create on mod"
        )
        if hasattr(self, "bundle"):
            self.bundle.setText(f"Editing {asset_name(self.selected)}\n{status_text}")

    def _on_field_clicked(self, index):
        if not index.isValid() or not (0 <= index.row() < len(self.model.fields)):
            return
        self.selected = self.model.fields[index.row()]
        try:
            thumb = fetch_bundle_thumb(self.selected.medium_bundle, (1024, 512))
            if thumb is not None and hasattr(thumb, "pixmap"):
                self.current.setPixmap(thumb.pixmap(1024, 512))
            else:
                logger.warning(
                    "Thumbnail unavailable for playmat %s",
                    getattr(self.selected, "medium_bundle", "unknown"),
                )
        except Exception as error:
            logger.exception("Failed to load playmat preview: %s", error)
            notify(
                self,
                "error",
                "Preview Error",
                "Could not load preview image for selected playmat.",
            )

        self.service.bundle = self.selected.medium_bundle
        self._update_field_status()
        self.label.setText(f"Playmats - {asset_name(self.selected)}")
        self._update_action_states()

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(
            self, "Select Replacement Image", "", IMAGE_FILTER
        )

        if file and file.url() != "":
            self._load_image(file.toLocalFile())

    def _restore(self):
        if not self.selected:
            notify(
                self,
                "warning",
                "Restore Unavailable",
                "Please select a playmat from the list first.",
            )
            return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        if hasattr(self, "restoreButton"):
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
                    thumb = fetch_field_thumb(self.selected)
                    if thumb is not None and hasattr(thumb, "pixmap"):
                        self.current.setPixmap(thumb.pixmap(768, 267))
                except Exception as thumb_err:
                    logger.exception(
                        "Failed to refresh playmat thumbnail: %s", thumb_err
                    )
                notify(
                    self,
                    "success",
                    "Playmat Restored",
                    f"Restored '{asset_name(self.selected)}' to original artwork.",
                )
                self._update_field_status()
            else:
                notify(
                    self,
                    "warning",
                    "Restore Unavailable",
                    f"No backup found for '{asset_name(self.selected)}'.",
                )
        except Exception as error:
            logger.exception("Failed to restore playmat backup: %s", error)
            summary, hint = format_actionable_error(error, "restoring playmat backup")
            notify(self, "error", summary, hint)
        finally:
            QGuiApplication.restoreOverrideCursor()
            self._update_action_states()

    def _extract_texture(self):
        if not self.selected:
            notify(
                self,
                "warning",
                "Extraction Unavailable",
                "Select a playmat from the list first.",
            )
            return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.service.extract_texture(self.service.bundle)
            dest = Path("images/fields") / f"{slugify(self.service.bundle)}.png"
            notify(
                self,
                "success",
                "Artwork Extracted",
                f"Extracted artwork to {dest}.",
            )
            open_in_file_manager(dest)
        except Exception as error:
            logger.exception("Failed to extract playmat artwork: %s", error)
            summary, hint = format_actionable_error(error, "extracting playmat artwork")
            notify(self, "error", summary, hint)
        finally:
            QGuiApplication.restoreOverrideCursor()

    def _copy(self):
        if not self.selected:
            notify(
                self,
                "warning",
                "Export Unavailable",
                "Select a playmat from the list first.",
            )
            return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.service.copy_bundle()
            dest = Path("bundles/fields") / self.service.bundle
            notify(
                self,
                "success",
                "Game File Exported",
                f"Exported game file to {dest}.",
            )
            open_in_file_manager(dest)
        except Exception as error:
            logger.exception("Failed to export playmat game file: %s", error)
            summary, hint = format_actionable_error(
                error, "exporting playmat game file"
            )
            notify(self, "error", summary, hint)
        finally:
            QGuiApplication.restoreOverrideCursor()

    def _replace(self):
        if not self.selected:
            notify(
                self,
                "warning",
                "Modification Unavailable",
                "Please select a playmat from the list first.",
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
        if APP_CONFIG.create_backup:
            try:
                for bundle in bundles:
                    if not bundle:
                        continue
                    backup = (
                        Path("backups")
                        / self.service.subfolder
                        / f"{slugify(bundle)}.png"
                    )
                    if not backup.is_file():
                        self.service.bundle = bundle
                        self.service.create_backup(bundle)
                self.model.set_backup_state(self.selected.id, True)
                session.commit()
            except Exception as error:
                logger.exception(
                    "Failed to create safety backup for playmat: %s", error
                )
                summary, hint = format_actionable_error(
                    error, "creating safety backup for playmat"
                )
                notify(self, "error", summary, hint)
                return

        if hasattr(self, "replaceButton"):
            self.replaceButton.setText("Applying Mod...")
            self.replaceButton.setEnabled(False)
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for bundle in bundles:
                if not bundle:
                    continue
                self.service.bundle = bundle
                self.service.replace_bundle()

            self.model.refresh()
            try:
                thumb = fetch_field_thumb(self.selected)
                if thumb is not None and hasattr(thumb, "pixmap"):
                    self.current.setPixmap(thumb.pixmap(768, 267))
            except Exception as thumb_err:
                logger.exception("Failed to refresh playmat thumbnail: %s", thumb_err)

            notify(
                self,
                "success",
                "Playmat Mod Applied",
                f"Updated '{asset_name(self.selected)}'. Original artwork is backed up.",
            )
            if hasattr(self, "_update_field_status"):
                self._update_field_status()
        except Exception as error:
            logger.exception("Failed to modify playmat game file: %s", error)
            summary, hint = format_actionable_error(
                error, "modifying playmat game file"
            )
            notify(self, "error", summary, hint)
        finally:
            QGuiApplication.restoreOverrideCursor()
            if hasattr(self, "replaceButton"):
                self.replaceButton.setText("Apply Mod")
            if hasattr(self, "_update_action_states"):
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
