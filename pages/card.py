from pyqttoast import ToastPreset
from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCompleter,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QWidget,
)

from database.models import CardModel
from database.objects import session
from pages.models.card_list_model import CardListModel
from pages.ui.card import Ui_Card
from services.card_service import CardService
from unity.unity_utils import fetch_bundle_thumb
from util.constants import (
    APP_CONFIG,
    FIT_MODE_BUTTON_STYLE,
    IMAGE_EXTENSIONS,
    IMAGE_FILTER,
)
from util.enums import CardArtCoordinates
from util.ui_util import show_toast
from widgets.crop_overlay_widget import CropOverlayWidget
from widgets.image_viewer import ImageViewer
from widgets.responsive_editor import ResponsiveEditor

_CARD_CROP_RATIO = 1.0
_BTN_STYLE = FIT_MODE_BUTTON_STYLE


class Card(QWidget, Ui_Card):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.service = CardService()
        self.model = CardListModel()
        self.cardsView.setModel(self.model)
        self.selected: CardModel | None = None

        self._crop_mode: bool = False
        self._init_current_viewer()
        self._setup_crop_ui()
        self.responsive_editor = ResponsiveEditor(
            self,
            self.cardsView,
            "cards",
            1.0,
            search=False,
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
                self._crop_widget.set_image(self.service.image_path, _CARD_CROP_RATIO)
                self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()
            self._mode_stack.setCurrentIndex(1)
        else:
            self.service.crop_rect = None
            self._mode_stack.setCurrentIndex(0)

    def _on_crop_changed(self) -> None:
        if self._crop_mode:
            self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()

    def _load_image(self, path: str) -> None:
        """Shared helper called when the user picks or drops an image."""
        self.cardEdit.setText(path)
        self.service.image_path = path
        self.preview.setPixmap(QPixmap(path))
        if self._crop_mode:
            self._crop_widget.set_image(path, _CARD_CROP_RATIO)
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

    def _connect_callbacks(self):
        self.cardsView.clicked.connect(self._on_card_clicked)
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace)
        self.copyButton.clicked.connect(self._copy)
        self.extractButton.clicked.connect(self._extract_texture)
        self.searchButton.clicked.connect(self._search)
        self.restoreButton.clicked.connect(self._restore)
        self.searchEdit.returnPressed.connect(self._search)
        self.searchEdit.setClearButtonEnabled(True)
        self.searchEdit.setPlaceholderText("Search cards, min 3 characters")
        self.searchEdit.textChanged.connect(self._search_text_changed)
        self.favorite.stateChanged.connect(self._toggle_favorite)
        self.favorites.stateChanged.connect(self._toggle_favorites_filter)

        self.searchEdit.setCompleter(QCompleter(self.service.get_names()))
        self.searchEdit.completer().setCaseSensitivity(
            Qt.CaseSensitivity.CaseInsensitive
        )
        self.searchEdit.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.searchEdit.completer().activated.connect(self._search)

    def _toggle_favorite(self, state):
        if self.selected and self.selected.favorite != (
            state == Qt.CheckState.Checked.value
        ):
            self.selected.favorite = state == Qt.CheckState.Checked.value
            session.commit()
            show_toast(
                self,
                "Favorite",
                "Card favorite status updated",
                ToastPreset.SUCCESS_DARK,
            )

    def _toggle_favorites_filter(self, state):
        self.model.show_favorites = state == Qt.CheckState.Checked.value
        if self.model.show_favorites:
            self.model.refresh()
            self.model.layoutChanged.emit()
        else:
            self.model.filter = (
                self.searchEdit.text() if len(self.searchEdit.text()) >= 3 else ""
            )
            self.model.refresh()
            self.model.layoutChanged.emit()

    def _restore(self):
        if self.service.restore_asset():
            self.model.refresh()
            show_toast(
                self, "Backup", "Card restored successfully", ToastPreset.SUCCESS_DARK
            )
        else:
            show_toast(
                self, "Backup", "Card backup not found", ToastPreset.WARNING_DARK
            )

    def _on_card_clicked(self, index):
        self.selected = self.model.assets[index.row()]

        self.current.setPixmap(
            fetch_bundle_thumb(
                self.selected.large_bundle,
                (374, 374),
                self.selected.unity_file,
                CardArtCoordinates.LARGE.value,
            ).pixmap(374, 374)
        )
        self.service.bundle = self.selected.large_bundle
        self.service.unity_file = self.selected.unity_file

        self.bundle.setText(
            f"Editing {self.model.assets[index.row()].name} "
            f"({self.selected.large_bundle})"
        )

        self.label.setText(f"Cards - {self.selected.name}")
        self.replaceButton.setEnabled(True)
        self.extractButton.setEnabled(True)
        self.restoreButton.setEnabled(True)
        self.copyButton.setEnabled(True)
        self.favorite.setChecked(self.selected.favorite)

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            self._load_image(file.toLocalFile())

    def _copy(self):
        if not self.service.unity_file:
            self.service.copy_bundle()
            show_toast(
                self,
                "Card Copying",
                'Card copied to the "cards" folder',
                ToastPreset.SUCCESS_DARK,
            )
        else:
            show_toast(
                self,
                "Card Copying",
                "Cannot copy Unity3D card",
                ToastPreset.WARNING_DARK,
            )

    def _extract_texture(self):
        self.service.extract_texture(self.service.bundle)
        show_toast(
            self,
            "Card Extraction",
            'Card extracted to the "cards" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _replace(self):
        if APP_CONFIG.create_backup and not self.selected.has_backup:
            self.service.create_backup(self.service.bundle)
            self.model.set_backup_state(self.selected.id, True)

        self.service.replace_bundle()
        self.model.refresh()
        self.current.setPixmap(
            fetch_bundle_thumb(
                self.service.bundle,
                (374, 374),
                self.service.unity_file,
                CardArtCoordinates.LARGE.value,
            ).pixmap(374, 374)
        )

        show_toast(
            self, "Card", "Card replacement successful", ToastPreset.SUCCESS_DARK
        )

    def _search_text_changed(self, text):
        if not text:
            self.model.filter = ""
            self.model.refresh()
            self.model.layoutChanged.emit()

    def _search(self):
        search_filter = self.searchEdit.text()

        if not self.model.show_favorites:
            if len(search_filter) >= 3:
                self.model.filter = search_filter
                self.model.refresh()
                self.model.layoutChanged.emit()
            else:
                show_toast(
                    self,
                    "Search",
                    "Please use 3 or more characters to search",
                    ToastPreset.INFORMATION_DARK,
                )
