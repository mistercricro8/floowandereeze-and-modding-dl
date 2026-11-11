from pathlib import Path

from pyqttoast import ToastPreset
from PySide6 import QtWidgets
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
from util.ui_util import show_toast
from widgets.crop_overlay_widget import CropOverlayWidget
from widgets.image_viewer import ImageViewer
from widgets.responsive_editor import ResponsiveEditor

_FIELD_CROP_RATIO = 2.0
_BTN_STYLE = FIT_MODE_BUTTON_STYLE


class Field(QtWidgets.QWidget, Ui_Field):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.service = FieldService()
        self.model = FieldListModel()
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
                self._crop_widget.set_image(self.service.image_path, _FIELD_CROP_RATIO)
                self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()
            self._mode_stack.setCurrentIndex(1)
        else:
            self.service.crop_rect = None
            self._mode_stack.setCurrentIndex(0)

    def _on_crop_changed(self) -> None:
        if self._crop_mode:
            self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()

    def _load_image(self, path: str) -> None:
        self.assetEdit.setText(path)
        self.service.image_path = path
        self.preview.setPixmap(QPixmap(path))
        if self._crop_mode:
            self._crop_widget.set_image(path, _FIELD_CROP_RATIO)
            self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()
            self._mode_stack.setCurrentIndex(1)
        else:
            self.service.crop_rect = None
            self._mode_stack.setCurrentIndex(0)

    def _connect_callbacks(self):
        self.fieldsView.clicked.connect(self._on_field_clicked)
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace)
        self.extractButton.clicked.connect(self._extract_texture)
        self.copyButton.clicked.connect(self._copy)

    def _on_field_clicked(self, index):
        self.selected = self.model.fields[index.row()]

        self.current.setPixmap(
            fetch_bundle_thumb(self.selected.medium_bundle, (1024, 512)).pixmap(
                1024, 512
            )
        )
        self.service.bundle = self.selected.medium_bundle
        self.bundle.setText(f"Editing {asset_name(self.selected)}")
        self.label.setText(f"Fields - {asset_name(self.selected)}")

        self.replaceButton.setEnabled(True)
        self.extractButton.setEnabled(True)
        self.copyButton.setEnabled(True)

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            self._load_image(file.toLocalFile())

    def _extract_texture(self):
        self.service.extract_texture(self.service.bundle)
        show_toast(
            self,
            "Field Extraction",
            'Field extracted to the "fields" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _copy(self):
        self.service.copy_bundle()
        show_toast(
            self,
            "Field Copying",
            'Field copied to the "fields" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _replace(self):
        if not self.selected or not self.service.image_path:
            return

        bundles = [self.selected.small_bundle, self.selected.medium_bundle]
        if APP_CONFIG.create_backup:
            for bundle in bundles:
                backup = (
                    Path("backups") / self.service.subfolder / f"{slugify(bundle)}.png"
                )
                if not backup.is_file():
                    self.service.bundle = bundle
                    self.service.create_backup(bundle)
            self.model.set_backup_state(self.selected.id, True)
            session.commit()

        for bundle in bundles:
            self.service.bundle = bundle
            self.service.replace_bundle()

        self.model.refresh()
        self.current.setPixmap(fetch_field_thumb(self.selected).pixmap(768, 267))

        show_toast(
            self, "Field", "Field replacement successful", ToastPreset.SUCCESS_DARK
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
