from pathlib import Path

from pyqttoast import ToastPreset
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
from util.ui_util import (
    format_actionable_error,
    open_in_file_manager,
    show_actionable_error_dialog,
    show_toast,
)
from widgets.crop_overlay_widget import CropOverlayWidget
from widgets.image_viewer import ImageViewer
from widgets.responsive_editor import ResponsiveEditor

_SLEEVE_CROP_RATIO = 256 / 374
_BTN_STYLE = FIT_MODE_BUTTON_STYLE


class Sleeve(QtWidgets.QWidget, Ui_Sleeve):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.service = SleeveService()
        self.model = SleeveListModel()
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
        self.selectButton.setToolTip("Select replacement art for sleeve (PNG, JPG)")
        self.selectButton.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sleeveEdit.setPlaceholderText(
            "No replacement image selected (browse or drag & drop)..."
        )
        self.replaceButton.setText("Apply Mod")
        self.replaceButton.setToolTip("Select an image to enable replacing sleeve art")
        self.replaceButton.setEnabled(False)
        self.restoreButton.setText("Restore Original")
        self.restoreButton.setToolTip("Restore sleeve art from original backup")
        self.restoreButton.setEnabled(False)
        self.extractButton.setText("Extract Texture (PNG)")
        self.extractButton.setToolTip(
            "Extract current sleeve texture to images/sleeves/"
        )
        self.extractButton.setEnabled(False)
        self.copyButton.setText("Export Game Bundle")
        self.copyButton.setToolTip("Export raw Unity bundle file to bundles/sleeves/")
        self.copyButton.setEnabled(False)
        self.borderButton.setText("Pick Border Color...")
        self.borderButton.setToolTip("Choose a custom border color")
        self.checkBox.setText("Custom Border")
        self.fadeCheckBox.setText("Fade Border")

    def _update_action_states(self) -> None:
        """Deterministically update button states and descriptive tooltips."""
        has_sleeve = self.selected is not None
        has_image = bool(self.service.image_path)
        self.replaceButton.setEnabled(has_sleeve and has_image)
        if not has_image:
            self.replaceButton.setToolTip("Select or drop a replacement image first")
        else:
            self.replaceButton.setToolTip(
                "Replace sleeve art in game files with selected image"
            )

        has_disk_backup = False
        if has_sleeve and self.selected.medium_bundle:
            backup_path = (
                Path("backups/sleeves") / f"{slugify(self.selected.medium_bundle)}.png"
            )
            has_disk_backup = backup_path.is_file()

        self.restoreButton.setEnabled(has_disk_backup)
        if has_disk_backup:
            self.restoreButton.setToolTip("Revert sleeve art to original backup")
        else:
            self.restoreButton.setToolTip(
                "No backup available yet (will be created automatically when modding)"
            )

        self.extractButton.setEnabled(has_sleeve)
        self.copyButton.setEnabled(has_sleeve)

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

        self._crop_btn = QPushButton("Crop")
        self._crop_btn.setCheckable(True)
        self._crop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._crop_btn.setStyleSheet(_BTN_STYLE)

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
            self._mode_stack.setCurrentIndex(1)
        else:
            self.service.crop_rect = None
            self._mode_stack.setCurrentIndex(0)

    def _on_crop_changed(self) -> None:
        if self._crop_mode:
            self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()

    def _load_image(self, path: str) -> None:
        self.sleeveEdit.setText(path)
        self.service.image_path = path
        pixmap = QPixmap(path)
        self.preview.setPixmap(pixmap)
        if self._crop_mode:
            self._crop_widget.set_image(path, _SLEEVE_CROP_RATIO)
            self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()
            self._mode_stack.setCurrentIndex(1)
        else:
            self.service.crop_rect = None
            self._mode_stack.setCurrentIndex(0)
        self._update_action_states()
        if not pixmap.isNull():
            show_toast(
                self,
                "Image Selected",
                f"Loaded {Path(path).name} ({pixmap.width()}×{pixmap.height()})",
                ToastPreset.INFORMATION_DARK,
            )

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
            show_toast(
                self,
                "Sleeve Restore",
                "Please select a sleeve from the list first.",
                ToastPreset.WARNING_DARK,
            )
            return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.restoreButton.setEnabled(False)
        try:
            restored = False
            for bundle in [self.selected.small_bundle, self.selected.medium_bundle]:
                self.service.bundle = bundle
                if self.service.restore_asset():
                    restored = True
            if restored:
                self.model.refresh()
                self.current.setPixmap(
                    fetch_bundle_thumb(self.selected.medium_bundle, (256, 375)).pixmap(
                        256, 375
                    )
                )
                show_toast(
                    self,
                    "Sleeve Restored",
                    f"Restored '{asset_name(self.selected)}' to original art.",
                    ToastPreset.SUCCESS_DARK,
                )
                self._update_sleeve_status()
            else:
                show_toast(
                    self,
                    "Sleeve Restore",
                    f"No backup found for '{asset_name(self.selected)}'.",
                    ToastPreset.WARNING_DARK,
                )
        except Exception as error:
            summary, hint = format_actionable_error(error, "restoring sleeve backup")
            show_actionable_error_dialog(
                self, "Restore Error", summary, hint, str(error)
            )
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
            session.commit()
            show_toast(
                self,
                "Favorite",
                "Sleeve favorite status updated",
                ToastPreset.SUCCESS_DARK,
            )

    def _toggle_favorites_filter(self, state):
        self.model.show_favorites = state == QtCore.Qt.CheckState.Checked.value
        self.model.refresh()
        self.model.layoutChanged.emit()

    def _update_sleeve_status(self) -> None:
        if not self.selected:
            return
        backup_path = (
            Path("backups/sleeves") / f"{slugify(self.selected.medium_bundle)}.png"
        )
        status_text = (
            "Backup: Secured"
            if backup_path.is_file()
            else "Backup: Will auto-create on mod"
        )
        self.bundle.setText(f"Editing {asset_name(self.selected)}\n{status_text}")

    def _on_sleeve_clicked(self, index):
        self.selected = self.model.assets[index.row()]

        self.current.setPixmap(
            fetch_bundle_thumb(self.selected.medium_bundle, (256, 375)).pixmap(256, 375)
        )
        self.service.bundle = self.selected.medium_bundle
        self._update_sleeve_status()
        self.label.setText(f"Sleeves - {asset_name(self.selected)}")
        self.favoriteBox.setChecked(self.selected.favorite)
        self._update_action_states()

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(
            self, "Select Replacement Image", "", IMAGE_FILTER
        )

        if file and file.url() != "":
            self._load_image(file.toLocalFile())

    def _copy(self):
        if not self.selected:
            show_toast(
                self, "Export", "Select a sleeve first.", ToastPreset.WARNING_DARK
            )
            return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.service.copy_bundle()
            dest = Path("bundles/sleeves") / self.service.bundle
            show_toast(
                self,
                "Bundle Exported",
                f"Raw bundle copied to {dest}",
                ToastPreset.SUCCESS_DARK,
            )
            open_in_file_manager(dest)
        except Exception as error:
            summary, hint = format_actionable_error(error, "exporting sleeve bundle")
            show_actionable_error_dialog(
                self, "Export Error", summary, hint, str(error)
            )
        finally:
            QGuiApplication.restoreOverrideCursor()

    def _extract_texture(self):
        if not self.selected:
            show_toast(
                self, "Extraction", "Select a sleeve first.", ToastPreset.WARNING_DARK
            )
            return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.service.extract_texture(self.service.bundle)
            dest = Path("images/sleeves") / f"{slugify(self.service.bundle)}.png"
            show_toast(
                self,
                "Texture Extracted",
                f"Texture extracted to {dest}",
                ToastPreset.SUCCESS_DARK,
            )
            open_in_file_manager(dest)
        except Exception as error:
            summary, hint = format_actionable_error(error, "extracting sleeve texture")
            show_actionable_error_dialog(
                self, "Extraction Error", summary, hint, str(error)
            )
        finally:
            QGuiApplication.restoreOverrideCursor()

    def _replace_sleeve(self):
        if not self.selected:
            show_toast(
                self,
                "Sleeve Mod",
                "Please select a sleeve from the list first.",
                ToastPreset.WARNING_DARK,
            )
            return
        if not self.service.image_path:
            show_toast(
                self,
                "Sleeve Mod",
                "Please select a replacement image first.",
                ToastPreset.WARNING_DARK,
            )
            return

        bundles = [self.selected.small_bundle, self.selected.medium_bundle]
        for bundle in bundles:
            backup_path = Path("backups/sleeves") / f"{slugify(bundle)}.png"
            if not backup_path.is_file():
                try:
                    self.service.bundle = bundle
                    self.service.create_backup(bundle)
                except Exception as error:
                    summary, hint = format_actionable_error(
                        error, "creating safety backup for sleeve"
                    )
                    show_actionable_error_dialog(
                        self, "Backup Protection Failed", summary, hint, str(error)
                    )
                    return
        self.model.set_backup_state(self.selected.id, True)
        session.commit()

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.replaceButton.setText("Applying Mod...")
        self.replaceButton.setEnabled(False)
        try:
            for bundle in bundles:
                self.service.bundle = bundle
                self.service.replace_bundle()

            self.model.refresh()
            self.current.setPixmap(
                fetch_bundle_thumb(self.selected.medium_bundle, (256, 375)).pixmap(
                    256, 375
                )
            )
            show_toast(
                self,
                "Sleeve Mod Applied",
                f"Modded '{asset_name(self.selected)}'. Original is backed up.",
                ToastPreset.SUCCESS_DARK,
            )
            self._update_sleeve_status()
        except Exception as error:
            summary, hint = format_actionable_error(error, "modifying sleeve bundle")
            show_actionable_error_dialog(
                self, "Mod Application Error", summary, hint, str(error)
            )
        finally:
            QGuiApplication.restoreOverrideCursor()
            self.replaceButton.setText("Apply Mod")
            self._update_action_states()

    def _select_color(self):
        color = show_color_dialog()

        if color:
            self.service.border_color = color.name()
            self.borderEdit.setText(color.name())
            self.borderButton.setText(f"Border: {color.name()}")
            self._switch_border()

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
