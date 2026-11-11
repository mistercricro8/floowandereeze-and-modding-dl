from pyqttoast import ToastPreset
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
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
    APP_CONFIG,
    FIT_MODE_BUTTON_STYLE,
    IMAGE_EXTENSIONS,
    IMAGE_FILTER,
)
from util.ui_util import show_toast
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
        self.preview.setPixmap(QPixmap(path))
        if self._crop_mode:
            self._crop_widget.set_image(path, _SLEEVE_CROP_RATIO)
            self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()
            self._mode_stack.setCurrentIndex(1)
        else:
            self.service.crop_rect = None
            self._mode_stack.setCurrentIndex(0)

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
        if self.service.restore_asset():
            self.model.refresh()
            show_toast(
                self, "Backup", "Sleeve restored successfully", ToastPreset.SUCCESS_DARK
            )
        else:
            show_toast(
                self, "Backup", "Sleeve backup not found", ToastPreset.WARNING_DARK
            )

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
        if self.model.show_favorites:
            self.model.refresh()
            self.model.layoutChanged.emit()
        else:
            self.model.refresh()
            self.model.layoutChanged.emit()

    def _on_sleeve_clicked(self, index):
        self.selected = self.model.assets[index.row()]

        self.current.setPixmap(
            fetch_bundle_thumb(self.selected.medium_bundle, (256, 375)).pixmap(256, 375)
        )
        self.service.bundle = self.selected.medium_bundle
        self.bundle.setText(f"Editing {asset_name(self.selected)}")
        self.label.setText(f"Sleeves - {asset_name(self.selected)}")

        self.replaceButton.setEnabled(True)
        self.extractButton.setEnabled(True)
        self.restoreButton.setEnabled(True)
        self.copyButton.setEnabled(True)
        self.favoriteBox.setChecked(self.selected.favorite)

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            self._load_image(file.toLocalFile())

    def _copy(self):
        self.service.copy_bundle()
        show_toast(
            self,
            "Sleeve Copying",
            'Sleeve copied to the "sleeves" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _extract_texture(self):
        self.service.extract_texture(self.service.bundle)
        show_toast(
            self,
            "Sleeve Extraction",
            'Sleeve extracted to the "sleeves" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _replace_sleeve(self):
        if APP_CONFIG.create_backup and not self.selected.has_backup:
            self.service.create_backup(self.service.bundle)
            self.model.set_backup_state(self.selected.id, True)

        for bundle in [self.selected.small_bundle, self.selected.medium_bundle]:
            self.service.bundle = bundle
            self.service.replace_bundle()

        self.model.refresh()
        self.current.setPixmap(
            fetch_bundle_thumb(self.service.bundle, (256, 375)).pixmap(256, 375)
        )

        show_toast(
            self, "Sleeve", "Sleeve replacement successful", ToastPreset.SUCCESS_DARK
        )

    def _select_color(self):
        color = show_color_dialog()

        if color:
            self.service.border_color = color.name()
            self.borderEdit.setText(color.name())
            self._switch_border()

    def _switch_border(self):
        border_enabled = self.checkBox.isChecked()
        self.fadeCheckBox.setEnabled(border_enabled)

        if border_enabled:
            self.preview.setStyleSheet(f"""
                #preview {{
                    border: 15px solid {self.service.border_color};
                }}
            """)
        else:
            self.preview.setStyleSheet("")
            self.fadeCheckBox.setChecked(False)

        self.service.border = border_enabled
        self.service.border_fade = self.fadeCheckBox.isChecked()

    def _toggle_fade(self):
        self.service.border_fade = self.fadeCheckBox.isChecked()
        if self.fadeCheckBox.isChecked() and self.checkBox.isChecked():
            pass
