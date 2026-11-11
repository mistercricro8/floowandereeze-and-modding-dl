"""Character management page module."""

from pyqttoast import ToastPreset
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLineEdit, QWidget

from database.models import CharacterModel
from database.objects import session
from dialogs.character_edit_dialog import CharacterEditDialog
from pages.models.character_list_model import CharacterListModel
from pages.ui.character import Ui_Character
from services.character_service import CharacterService
from util.ui_util import show_toast


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

        self.searchEdit = QLineEdit(self)
        self.searchEdit.setObjectName("searchEdit")
        self.searchEdit.setPlaceholderText("Search characters")
        self.searchEdit.setAccessibleName("Search characters")
        self.searchEdit.setClearButtonEnabled(True)
        self.horizontalLayout_3.insertWidget(1, self.searchEdit, 1)
        self.searchTimer = QTimer(self)
        self.searchTimer.setSingleShot(True)
        self.searchTimer.setInterval(200)
        self.searchTimer.timeout.connect(self._search_characters)

        self.clearFilterButton.setToolTip("Reset all character search filters")
        self.seriesComboBox.setToolTip("Filter characters by anime series")
        self.charactersView.setToolTip(
            "Double-click any character to open the asset editor"
        )
        self._setup_series_filter()
        self._connect_callbacks()

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
        self.searchEdit.textChanged.connect(lambda: self.searchTimer.start())
        self.searchEdit.returnPressed.connect(self._search_characters)

    def _search_characters(self):
        """Search character names while preserving the other filters."""
        self.searchTimer.stop()
        self.model.filter = self.searchEdit.text().strip()
        self.model.refresh()
        if self.model.filter:
            show_toast(
                self,
                "Character Search",
                f"Showing characters matching '{self.model.filter}'",
                ToastPreset.INFORMATION_DARK,
            )

    def _toggle_favorite(self, state):
        """Toggle favorite status of selected character."""
        if self.selected and self.selected.favorite != (
            state == Qt.CheckState.Checked.value
        ):
            self.selected.favorite = state == Qt.CheckState.Checked.value
            session.commit()
            if self.model.show_favorites:
                self.model.refresh()
            show_toast(
                self,
                "Favorite",
                "Character favorite status updated",
                ToastPreset.SUCCESS_DARK,
            )

    def _toggle_favorites_filter(self, state):
        """Toggle the favorites filter."""
        self.model.show_favorites = state == Qt.CheckState.Checked.value
        self.model.refresh()
        show_toast(
            self,
            "Filter",
            "Showing favorites only"
            if self.model.show_favorites
            else "Showing all characters",
            ToastPreset.INFORMATION_DARK,
        )

    def _filter_by_series(self):
        """Filter characters by selected series."""
        selected_series = self.seriesComboBox.currentData()
        self.model.series_filter = selected_series or ""
        self.model.refresh()

    def _clear_filters(self):
        """Clear all filters and reset the view."""
        for control in (self.searchEdit, self.seriesComboBox, self.favorites):
            control.blockSignals(True)
        self.searchTimer.stop()
        self.searchEdit.clear()
        self.seriesComboBox.setCurrentIndex(0)
        self.favorites.setChecked(False)
        for control in (self.searchEdit, self.seriesComboBox, self.favorites):
            control.blockSignals(False)
        self.model.filter = ""
        self.model.series_filter = ""
        self.model.show_favorites = False
        self.model.refresh()
        show_toast(
            self,
            "Filters Cleared",
            "All character filters have been reset",
            ToastPreset.INFORMATION_DARK,
        )

    def _on_character_selected(self, index, previous=None):
        """Keep the favorite control tied to the current character."""
        self.selected = self.model.assets[index.row()] if index.isValid() else None
        self.favorite.setEnabled(self.selected is not None)
        was_blocked = self.favorite.blockSignals(True)
        self.favorite.setChecked(bool(self.selected and self.selected.favorite))
        self.favorite.blockSignals(was_blocked)

    def _on_character_double_clicked(self, index):
        """Handle double-click on character to open edit dialog."""
        if not index.isValid():
            return
        character = self.model.assets[index.row()]

        dialog = CharacterEditDialog(character, self)
        dialog.exec()

        self.model.refresh()
