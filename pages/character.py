"""Character management page module."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QCompleter, QLineEdit, QPushButton, QWidget

from database.models import CharacterModel
from database.objects import session
from dialogs.character_edit_dialog import CharacterEditDialog
from pages.models.character_list_model import CharacterListModel
from pages.ui.character import Ui_Character
from services.character_service import CharacterService
from widgets.inline_alert import attach_inline_alert, notify

logger = logging.getLogger(__name__)


class Character(QWidget, Ui_Character):
    """Character management page widget."""

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.service = CharacterService()
        self.model = CharacterListModel()
        self.charactersView.setModel(self.model)
        self.selected: CharacterModel | None = None
        self.favorite.setEnabled(False)

        attach_inline_alert(self, self.verticalLayout)

        self.searchEdit = QLineEdit(self)
        self.searchEdit.setObjectName("searchEdit")
        self.searchEdit.setPlaceholderText("Search characters by name...")
        self.searchEdit.setAccessibleName("Search characters")
        self.searchEdit.setToolTip(
            "Type character name and click Search or press Enter."
        )
        self.searchEdit.setClearButtonEnabled(True)
        self.searchEdit.setMinimumHeight(32)
        self.horizontalLayout_3.insertWidget(1, self.searchEdit, 1)

        self.searchButton = QPushButton(self)
        self.searchButton.setObjectName("searchButton")
        self.searchButton.setText("Search")
        self.searchButton.setIcon(QIcon.fromTheme(QIcon.ThemeIcon.EditFind))
        self.searchButton.setToolTip("Search characters matching your query.")
        self.searchButton.setAccessibleName("Search")
        self.searchButton.setCursor(Qt.CursorShape.PointingHandCursor)
        self.searchButton.setMinimumHeight(32)
        self.horizontalLayout_3.insertWidget(2, self.searchButton)

        completer = QCompleter(self.model.get_names(), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.searchEdit.setCompleter(completer)
        completer.activated.connect(self._search_characters)

        self.clearFilterButton.setToolTip(
            "Resets your search query and series selection."
        )
        self.seriesComboBox.setToolTip("Filters characters by anime series.")
        self.charactersView.setToolTip(
            "Character roster. Double-click to edit artwork and dialogue images."
        )
        self.favorite.setText("Favorite")
        self.favorite.setToolTip("Pins this character to your favorites list.")
        self.favorites.setText("Favorites")
        self.favorites.setToolTip("Filters the list to show favorite characters only.")
        self.instructions.setText("Double-click a character to edit artwork and images")
        self.instructions.setToolTip(
            "Double-click any character in the roster to open the image editor."
        )

        self._setup_series_filter()
        self._connect_callbacks()

        self.model.filter = ""
        self.model.series_filter = ""
        self.model.show_favorites = False
        self.model.refresh()

    def _setup_series_filter(self):
        """Setup the series filter combobox."""
        series_list = self.service.get_series_list()
        self.seriesComboBox.addItem("All Series", "")
        for series in sorted(series_list):
            self.seriesComboBox.addItem(series, series)

    def _connect_callbacks(self):
        """Connect UI signals to their handlers."""
        self.charactersView.selectionModel().currentChanged.connect(
            self._on_character_selected
        )
        self.model.modelReset.connect(
            lambda: self._on_character_selected(self.charactersView.currentIndex())
        )
        self.charactersView.doubleClicked.connect(self._on_character_double_clicked)
        self.clearFilterButton.clicked.connect(self._clear_filters)
        self.favorite.stateChanged.connect(self._toggle_favorite)
        self.favorites.stateChanged.connect(self._toggle_favorites_filter)
        self.seriesComboBox.currentTextChanged.connect(self._filter_by_series)
        self.searchButton.clicked.connect(self._search_characters)
        self.searchEdit.returnPressed.connect(self._search_characters)
        self.searchEdit.textChanged.connect(self._on_search_text_changed)

    def _on_search_text_changed(self, text: str) -> None:
        """Reset search filter when search input is cleared."""
        if not text:
            self.model.filter = ""
            try:
                self.model.refresh()
            except Exception:
                logger.exception(
                    "Failed to refresh character list when search text cleared"
                )
            if hasattr(self, "inlineAlert"):
                self.inlineAlert.clear()

    def _search_characters(self, activated_text=None, *_):
        """Search character names while preserving other filters."""
        if isinstance(activated_text, str) and activated_text:
            self.searchEdit.setText(activated_text)
        query = self.searchEdit.text().strip()
        self.model.filter = query
        try:
            self.model.refresh()
            count = self.model.rowCount()
            if not query:
                if hasattr(self, "inlineAlert"):
                    self.inlineAlert.clear()
            elif count == 0:
                notify(
                    self,
                    "info",
                    "Character Search",
                    f"No characters found matching '{query}'.",
                )
            else:
                notify(
                    self,
                    "info",
                    "Character Search",
                    f"Found {count} character{'s' if count != 1 else ''} matching '{query}'.",
                )
        except Exception as exc:
            logger.exception("Character search failed for query '%s'", query)
            notify(
                self,
                "error",
                "Search Error",
                f"Failed to search characters: {exc}",
            )

    def _toggle_favorite(self, state):
        """Toggle favorite status of selected character."""
        if self.selected and self.selected.favorite != (
            state == Qt.CheckState.Checked.value
        ):
            self.selected.favorite = state == Qt.CheckState.Checked.value
            try:
                session.commit()
                if self.model.show_favorites:
                    self.model.refresh()
                name = self.selected.name or f"Character {self.selected.konami_id}"
                status_text = (
                    "added to favorites"
                    if self.selected.favorite
                    else "removed from favorites"
                )
                notify(
                    self,
                    "success",
                    "Favorite Updated",
                    f"{name} {status_text}.",
                )
            except Exception as exc:
                logger.exception(
                    "Failed to update favorite status for character %s",
                    self.selected.id,
                )
                session.rollback()
                notify(
                    self,
                    "error",
                    "Favorite Error",
                    f"Failed to update favorite: {exc}",
                )

    def _toggle_favorites_filter(self, state):
        """Toggle the favorites filter."""
        self.model.show_favorites = state == Qt.CheckState.Checked.value
        try:
            self.model.refresh()
            count = self.model.rowCount()
            if self.model.show_favorites:
                notify(
                    self,
                    "info",
                    "Favorites Filter",
                    f"Showing {count} favorite character{'s' if count != 1 else ''}.",
                )
            else:
                notify(
                    self,
                    "info",
                    "Favorites Filter",
                    f"Showing all {count} characters.",
                )
        except Exception as exc:
            logger.exception("Failed to toggle favorites filter")
            notify(
                self,
                "error",
                "Filter Error",
                f"Failed to filter by favorites: {exc}",
            )

    def _filter_by_series(self):
        """Filter characters by selected series."""
        selected_series = self.seriesComboBox.currentData()
        self.model.series_filter = selected_series or ""
        try:
            self.model.refresh()
            count = self.model.rowCount()
            series_name = self.seriesComboBox.currentText()
            if selected_series:
                notify(
                    self,
                    "info",
                    "Series Filter",
                    f"Showing {count} character{'s' if count != 1 else ''} from {series_name}.",
                )
            else:
                notify(
                    self,
                    "info",
                    "Series Filter",
                    f"Showing all {count} characters.",
                )
        except Exception as exc:
            logger.exception("Failed to filter characters by series")
            notify(
                self,
                "error",
                "Filter Error",
                f"Failed to filter by series: {exc}",
            )

    def _clear_filters(self):
        """Clear all filters and reset the view."""
        for control in (self.searchEdit, self.seriesComboBox, self.favorites):
            control.blockSignals(True)
        self.searchEdit.clear()
        self.seriesComboBox.setCurrentIndex(0)
        self.favorites.setChecked(False)
        for control in (self.searchEdit, self.seriesComboBox, self.favorites):
            control.blockSignals(False)
        self.model.filter = ""
        self.model.series_filter = ""
        self.model.show_favorites = False
        try:
            self.model.refresh()
            count = self.model.rowCount()
            notify(
                self,
                "info",
                "Filters Cleared",
                f"All filters reset. Showing {count} characters.",
            )
        except Exception as exc:
            logger.exception("Failed to clear character filters")
            notify(
                self,
                "error",
                "Filter Error",
                f"Failed to reset filters: {exc}",
            )

    def _on_character_selected(self, index, previous=None):
        """Keep the favorite control tied to the current character."""
        self.selected = (
            self.model.assets[index.row()]
            if index.isValid() and 0 <= index.row() < len(self.model.assets)
            else None
        )
        self.favorite.setEnabled(self.selected is not None)
        was_blocked = self.favorite.blockSignals(True)
        self.favorite.setChecked(bool(self.selected and self.selected.favorite))
        self.favorite.blockSignals(was_blocked)

    def _on_character_double_clicked(self, index):
        """Handle double-click on character to open edit dialog."""
        if not index.isValid() or not (0 <= index.row() < len(self.model.assets)):
            return
        character = self.model.assets[index.row()]
        try:
            dialog = CharacterEditDialog(character, self)
            dialog.exec()
            self.model.refresh()
        except Exception as exc:
            logger.exception(
                "Failed to open character edit dialog for %s", character.id
            )
            notify(
                self,
                "error",
                "Editor Error",
                f"Could not open character editor: {exc}",
            )
