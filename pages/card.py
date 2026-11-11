"""Card management page module."""

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCompleter,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QWidget,
)

from database.models import CardModel
from database.objects import session
from pages.models.card_list_model import CardListModel
from pages.ui.card import Ui_Card
from services.card_service import CardService
from unity.unity_utils import card_art_bundle, fetch_bundle_thumb
from util.constants import (
    FIT_MODE_BUTTON_STYLE,
    IMAGE_EXTENSIONS,
    IMAGE_FILTER,
)
from util.enums import CardArtCoordinates
from util.image_utils import slugify
from util.ui_util import (
    format_actionable_error,
    open_in_file_manager,
)
from widgets.crop_overlay_widget import CropOverlayWidget
from widgets.image_viewer import ImageViewer
from widgets.inline_alert import attach_inline_alert, notify
from widgets.responsive_editor import ResponsiveEditor

logger = logging.getLogger(__name__)

_CARD_CROP_RATIO = 1.0
_BTN_STYLE = FIT_MODE_BUTTON_STYLE


class Card(QWidget, Ui_Card):
    """Card management page widget."""

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

        attach_inline_alert(self, self.verticalLayout)
        self._connect_callbacks()
        self._init_descriptive_controls()
        self.model.filter = ""
        self.model.refresh()

    def _init_descriptive_controls(self) -> None:
        """Set clear, plain-language labels, tooltips, and initial states."""
        self.bundle.setText("Select a card from the list below to begin editing.")
        self.selectButton.setText("Select Image...")
        self.selectButton.setToolTip(
            "Browse your computer for a PNG or JPG image to replace card artwork."
        )
        self.selectButton.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cardEdit.setPlaceholderText(
            "No replacement image selected (browse or drag & drop)..."
        )
        self.cardEdit.setToolTip(
            "File path of your replacement image. Drag and drop is also supported."
        )
        self.replaceButton.setText("Apply Mod")
        self.replaceButton.setToolTip(
            "Select or drop a replacement image first to enable applying this mod."
        )
        self.replaceButton.setEnabled(False)
        self.restoreButton.setText("Restore Original")
        self.restoreButton.setToolTip(
            "No backup saved yet. Original art is backed up when you apply a mod."
        )
        self.restoreButton.setEnabled(False)
        self.extractButton.setText("Extract Artwork")
        self.extractButton.setToolTip(
            "Extracts current in-game artwork to a PNG file in images/cards/."
        )
        self.extractButton.setEnabled(False)
        self.copyButton.setText("Export Game File")
        self.copyButton.setToolTip(
            "Copies the game file to bundles/cards/ for modding or archiving."
        )
        self.copyButton.setEnabled(False)
        self.searchButton.setText("Search")
        self.searchButton.setToolTip("Finds cards matching your search query.")
        self.searchEdit.setPlaceholderText("Search cards by name...")
        self.searchEdit.setToolTip(
            "Type part of a card name and click Search or press Enter."
        )
        self.favorite.setText("Favorite")
        self.favorite.setToolTip(
            "Pins this card to your favorites for quick filtering later."
        )
        self.favorites.setText("Favorites")
        self.favorites.setToolTip(
            "Filters the card list to display only your favorite cards."
        )

        for btn in (
            self.restoreButton,
            self.extractButton,
            self.copyButton,
            self.replaceButton,
        ):
            btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            btn.setMinimumWidth(btn.fontMetrics().horizontalAdvance(btn.text()) + 20)

    def _update_action_states(self) -> None:
        """Update button states and tooltips based on current selection."""
        has_card = self.selected is not None
        has_image = bool(self.service.image_path)
        self.replaceButton.setEnabled(has_card and has_image)
        if not has_image:
            self.replaceButton.setToolTip(
                "Select or drop a replacement image first to enable applying this mod."
            )
        elif not has_card:
            self.replaceButton.setToolTip(
                "Select a card from the list to enable applying this mod."
            )
        else:
            self.replaceButton.setToolTip(
                f"Replaces artwork for '{self.selected.name}'. Original is backed up."
            )

        has_disk_backup = False
        if has_card:
            bundle, _ = card_art_bundle(self.selected)
            backup_path = Path("backups/cards") / f"{slugify(bundle)}.png"
            has_disk_backup = backup_path.is_file()

        self.restoreButton.setEnabled(has_disk_backup)
        if has_disk_backup:
            self.restoreButton.setToolTip(
                f"Restores '{self.selected.name}' to original game art from backup."
            )
        else:
            self.restoreButton.setToolTip(
                "No backup saved yet. Original art is backed up when you apply a mod."
            )

        self.extractButton.setEnabled(has_card)
        if has_card:
            self.extractButton.setToolTip(
                f"Extracts artwork for '{self.selected.name}' to images/cards/."
            )
        else:
            self.extractButton.setToolTip("Select a card to extract its artwork.")

        can_copy = has_card and not getattr(self.selected, "unity_file", False)
        self.copyButton.setEnabled(can_copy)
        if can_copy:
            self.copyButton.setToolTip(
                f"Exports game file for '{self.selected.name}' to bundles/cards/."
            )
        elif has_card:
            self.copyButton.setToolTip("This card game file cannot be exported.")
        else:
            self.copyButton.setToolTip("Select a card to export its game file.")

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
        self._stretch_btn.setToolTip(
            "Stretches the image to completely fill the card art boundary."
        )

        self._crop_btn = QPushButton("Crop")
        self._crop_btn.setCheckable(True)
        self._crop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._crop_btn.setStyleSheet(_BTN_STYLE)
        self._crop_btn.setToolTip(
            "Keeps image proportions and lets you frame the area to use."
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
        pixmap = QPixmap(path)
        self.preview.setPixmap(pixmap)
        if self._crop_mode:
            self._crop_widget.set_image(path, _CARD_CROP_RATIO)
            self.service.crop_rect = self._crop_widget.get_crop_rect_normalized()
            self._mode_stack.setCurrentIndex(1)
        else:
            self.service.crop_rect = None
            self._mode_stack.setCurrentIndex(0)
        self._update_action_states()
        if not pixmap.isNull():
            notify(
                self,
                "info",
                "Image Selected",
                f"Loaded {Path(path).name} ({pixmap.width()}×{pixmap.height()})",
            )
        else:
            logger.warning("Selected image could not be loaded: %s", path)
            notify(
                self,
                "error",
                "Image Error",
                f"Could not load image from {Path(path).name}.",
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
        self.searchEdit.textChanged.connect(self._search_text_changed)
        self.favorite.stateChanged.connect(self._toggle_favorite)
        self.favorites.stateChanged.connect(self._toggle_favorites_filter)

        completer = QCompleter(self.service.get_names(), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.searchEdit.setCompleter(completer)
        completer.activated.connect(self._search)

    def _toggle_favorite(self, state):
        if self.selected and self.selected.favorite != (
            state == Qt.CheckState.Checked.value
        ):
            self.selected.favorite = state == Qt.CheckState.Checked.value
            try:
                session.commit()
                status_text = (
                    "added to favorites"
                    if self.selected.favorite
                    else "removed from favorites"
                )
                notify(
                    self,
                    "success",
                    "Favorite Updated",
                    f"Card '{self.selected.name}' {status_text}.",
                )
            except Exception as error:
                logger.exception(
                    "Failed to update favorite status for card %s", self.selected.name
                )
                session.rollback()
                notify(
                    self,
                    "error",
                    "Database Error",
                    f"Could not update favorite status: {error}",
                )

    def _toggle_favorites_filter(self, state):
        self.model.show_favorites = state == Qt.CheckState.Checked.value
        try:
            if self.model.show_favorites:
                self.model.refresh()
                self.model.layoutChanged.emit()
                count = self.model.rowCount()
                notify(
                    self,
                    "info",
                    "Filter",
                    f"Showing {count} favorite card{'s' if count != 1 else ''}.",
                )
            else:
                self.model.filter = (
                    self.searchEdit.text().strip()
                    if len(self.searchEdit.text().strip()) >= 3
                    else ""
                )
                self.model.refresh()
                self.model.layoutChanged.emit()
                count = self.model.rowCount()
                notify(
                    self,
                    "info",
                    "Filter",
                    f"Showing all {count} cards.",
                )
        except Exception as error:
            logger.exception("Failed to toggle favorites filter")
            notify(
                self,
                "error",
                "Filter Error",
                f"Failed to update card filter: {error}",
            )

    def _restore(self):
        if not self.selected:
            notify(
                self,
                "warning",
                "Card Restore",
                "Please select a card from the list first.",
            )
            return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.restoreButton.setEnabled(False)
        try:
            if self.service.restore_asset():
                self.model.refresh()
                bundle, coords = card_art_bundle(self.selected)
                thumb = fetch_bundle_thumb(
                    bundle,
                    (374, 374),
                    self.selected.unity_file,
                    coords.value,
                )
                self.current.setPixmap(thumb.pixmap(374, 374) if thumb else QPixmap())
                notify(
                    self,
                    "success",
                    "Card Restored",
                    f"Restored '{self.selected.name}' to original game artwork.",
                )
                backup_path = Path("backups/cards") / f"{slugify(bundle)}.png"
                status_text = (
                    "Backup: Saved"
                    if backup_path.is_file()
                    else "Backup: Will auto-create on mod"
                )
                quality = (
                    "High quality"
                    if coords is CardArtCoordinates.LARGE
                    else "Standard quality"
                )
                self.bundle.setText(
                    f"Editing {self.selected.name} ({quality}, game file: {bundle})\n"
                    f"{status_text}"
                )
            else:
                notify(
                    self,
                    "warning",
                    "Card Restore",
                    f"No backup found for '{self.selected.name}'.",
                )
        except Exception as error:
            logger.exception("Failed to restore card %s", self.selected.name)
            summary, hint = format_actionable_error(error, "restoring original card")
            notify(self, "error", "Restore Error", f"{summary}\n{hint}")
        finally:
            QGuiApplication.restoreOverrideCursor()
            self._update_action_states()

    def _on_card_clicked(self, index):
        if not index.isValid() or not (0 <= index.row() < len(self.model.assets)):
            return
        self.selected = self.model.assets[index.row()]
        bundle, coords = card_art_bundle(self.selected)

        try:
            thumb = fetch_bundle_thumb(
                bundle,
                (374, 374),
                self.selected.unity_file,
                coords.value,
            )
            if thumb:
                self.current.setPixmap(thumb.pixmap(374, 374))
            else:
                self.current.setPixmap(QPixmap())
        except Exception:
            logger.exception("Failed to load thumbnail for card %s", self.selected.name)
            self.current.setPixmap(QPixmap())

        self.service.bundle = bundle
        self.service.unity_file = self.selected.unity_file

        backup_path = Path("backups/cards") / f"{slugify(bundle)}.png"
        status_text = (
            "Backup: Saved"
            if backup_path.is_file()
            else "Backup: Will auto-create on mod"
        )
        quality = (
            "High quality" if coords is CardArtCoordinates.LARGE else "Standard quality"
        )
        self.bundle.setText(
            f"Editing {self.selected.name} ({quality}, game file: {bundle})\n"
            f"{status_text}"
        )

        self.label.setText(f"Cards - {self.selected.name}")
        self.favorite.setChecked(self.selected.favorite)
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
                "Game File Export",
                "Please select a card from the list first.",
            )
            return
        if self.service.unity_file:
            notify(
                self,
                "warning",
                "Game File Export",
                "Cannot export this type of game file.",
            )
            return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.service.copy_bundle()
            dest = Path("bundles/cards") / self.service.bundle
            notify(
                self,
                "success",
                "Game File Exported",
                f"Game file copied to {dest}",
            )
            open_in_file_manager(dest)
        except Exception as error:
            logger.exception(
                "Failed to export game file for card %s", self.selected.name
            )
            summary, hint = format_actionable_error(error, "exporting game file")
            notify(self, "error", "Export Error", f"{summary}\n{hint}")
        finally:
            QGuiApplication.restoreOverrideCursor()

    def _extract_texture(self):
        if not self.selected:
            notify(
                self,
                "warning",
                "Artwork Extraction",
                "Please select a card from the list first.",
            )
            return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.service.extract_texture(self.service.bundle)
            dest = Path("images/cards") / f"{slugify(self.service.bundle)}.png"
            notify(
                self,
                "success",
                "Artwork Extracted",
                f"Artwork extracted to {dest}",
            )
            open_in_file_manager(dest)
        except Exception as error:
            logger.exception(
                "Failed to extract artwork for card %s", self.selected.name
            )
            summary, hint = format_actionable_error(error, "extracting card artwork")
            notify(self, "error", "Extraction Error", f"{summary}\n{hint}")
        finally:
            QGuiApplication.restoreOverrideCursor()

    def _replace(self):
        if not self.selected:
            notify(
                self,
                "warning",
                "Card Mod",
                "Please select a card from the list first.",
            )
            return
        if not self.service.image_path:
            notify(
                self,
                "warning",
                "Card Mod",
                "Please select a replacement image first.",
            )
            return

        bundle, coords = card_art_bundle(self.selected)
        backup_path = Path("backups/cards") / f"{slugify(bundle)}.png"
        if not backup_path.is_file():
            try:
                self.service.create_backup(self.service.bundle)
                self.model.set_backup_state(self.selected.id, True)
                session.commit()
            except Exception as error:
                logger.exception(
                    "Failed to create safety backup for card %s", self.selected.name
                )
                summary, hint = format_actionable_error(error, "creating safety backup")
                notify(self, "error", "Backup Protection Failed", f"{summary}\n{hint}")
                return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.replaceButton.setText("Applying Mod...")
        self.replaceButton.setEnabled(False)
        try:
            self.service.replace_bundle()
            self.model.refresh()
            thumb = fetch_bundle_thumb(
                self.service.bundle,
                (374, 374),
                self.service.unity_file,
                coords.value,
            )
            self.current.setPixmap(thumb.pixmap(374, 374) if thumb else QPixmap())
            notify(
                self,
                "success",
                "Card Mod Applied",
                f"Replaced artwork for '{self.selected.name}'. Original is backed up.",
            )
            backup_path = Path("backups/cards") / f"{slugify(bundle)}.png"
            status_text = (
                "Backup: Saved"
                if backup_path.is_file()
                else "Backup: Will auto-create on mod"
            )
            quality = (
                "High quality"
                if coords is CardArtCoordinates.LARGE
                else "Standard quality"
            )
            self.bundle.setText(
                f"Editing {self.selected.name} ({quality}, game file: {bundle})\n"
                f"{status_text}"
            )
        except Exception as error:
            logger.exception(
                "Failed to modify game file for card %s", self.selected.name
            )
            summary, hint = format_actionable_error(error, "modifying card game file")
            notify(self, "error", "Mod Application Error", f"{summary}\n{hint}")
        finally:
            QGuiApplication.restoreOverrideCursor()
            self.replaceButton.setText("Apply Mod")
            self._update_action_states()

    def _search_text_changed(self, text: str) -> None:
        if not text:
            self.model.filter = ""
            try:
                self.model.refresh()
                self.model.layoutChanged.emit()
            except Exception:
                logger.exception("Failed to refresh model when search text cleared")
            if hasattr(self, "inlineAlert"):
                self.inlineAlert.clear()

    def _search(self, activated_text=None, *_):
        if isinstance(activated_text, str) and activated_text:
            self.searchEdit.setText(activated_text)
        search_filter = self.searchEdit.text().strip()

        if self.model.show_favorites:
            self.model.show_favorites = False
            self.favorites.blockSignals(True)
            self.favorites.setChecked(False)
            self.favorites.blockSignals(False)

        if not search_filter:
            self.model.filter = ""
            try:
                self.model.refresh()
                self.model.layoutChanged.emit()
            except Exception:
                logger.exception("Failed to refresh card model with empty query")
            if hasattr(self, "inlineAlert"):
                self.inlineAlert.clear()
            return

        self.model.filter = search_filter
        try:
            self.model.refresh()
            self.model.layoutChanged.emit()
            count = self.model.rowCount()
            if count == 0:
                notify(
                    self,
                    "info",
                    "Search",
                    f"No cards found matching '{search_filter}'.",
                )
            else:
                notify(
                    self,
                    "info",
                    "Search",
                    f"Found {count} card{'s' if count != 1 else ''} matching '{search_filter}'.",
                )
        except Exception as error:
            logger.exception("Card search failed for query '%s'", search_filter)
            notify(
                self,
                "error",
                "Search Error",
                f"Failed to search cards: {error}",
            )
