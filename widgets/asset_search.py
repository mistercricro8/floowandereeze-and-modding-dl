"""Card art style search controls for named accessory editors."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QCompleter, QLabel, QLineEdit, QPushButton

logger = logging.getLogger(__name__)


def add_asset_search(page, header, results_layout, asset_type):
    """Add explicit search, completion, and inline helper guidance."""
    page.searchEdit = QLineEdit(page)
    page.searchEdit.setObjectName("searchEdit")
    page.searchEdit.setPlaceholderText(f"Search {asset_type} by name...")
    page.searchEdit.setMinimumHeight(32)
    page.searchEdit.setStyleSheet("color: #ffffff;")
    palette = page.searchEdit.palette()
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#858585"))
    page.searchEdit.setPalette(palette)
    page.searchEdit.setClearButtonEnabled(True)

    page.searchButton = QPushButton(page)
    page.searchButton.setObjectName("searchButton")
    page.searchButton.setIcon(QIcon.fromTheme("edit-find"))
    page.searchButton.setToolTip("Search")
    page.searchButton.setAccessibleName("Search")
    page.searchButton.setCursor(Qt.CursorShape.PointingHandCursor)
    page.searchButton.setMinimumHeight(32)
    if page.searchButton.icon().isNull():
        page.searchButton.setText("Search")
        page.searchButton.setMaximumWidth(70)
    else:
        page.searchButton.setMaximumWidth(42)

    header.insertWidget(1, page.searchEdit, 1)
    header.insertWidget(2, page.searchButton)

    page.searchHelperLabel = QLabel("", page)
    page.searchHelperLabel.setObjectName("searchHelperLabel")
    page.searchHelperLabel.setStyleSheet("color: #d6d6d6; font-size: 11px;")
    page.searchHelperLabel.hide()
    results_layout.addWidget(page.searchHelperLabel)

    completer = QCompleter(page.model.get_names(), page)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    page.searchEdit.setCompleter(completer)
    page.searchCompleter = completer

    def search(activated_text=None, *_):
        if isinstance(activated_text, str) and activated_text:
            page.searchEdit.setText(activated_text)
        query = page.searchEdit.text().strip()
        if not query:
            page.searchHelperLabel.clear()
            page.searchHelperLabel.hide()
            page.model.filter = ""
            try:
                page.model.refresh()
            except Exception:
                logger.exception("Failed to refresh model with empty filter")
            return

        old_filter = page.model.filter
        page.model.filter = query
        if getattr(page.model, "show_favorites", False):
            page.model.show_favorites = False
            if hasattr(page, "favorites") and hasattr(page.favorites, "setChecked"):
                page.favorites.blockSignals(True)
                page.favorites.setChecked(False)
                page.favorites.blockSignals(False)

        try:
            page.model.refresh()
        except Exception as exc:
            logger.exception("Search failed for query '%s'", query)
            page.model.filter = old_filter
            page.searchHelperLabel.setText(f"Error: {exc}")
            page.searchHelperLabel.show()
            return

        count = page.model.rowCount()
        logger.debug("Search query '%s' returned %d results", query, count)
        if count == 0:
            page.searchHelperLabel.setText(f"No matches for '{query}'")
        else:
            page.searchHelperLabel.setText(f"{count} matches")
        page.searchHelperLabel.show()

    page.searchButton.clicked.connect(search)
    page.searchEdit.returnPressed.connect(search)
    completer.activated.connect(search)

    def text_changed(text: str):
        page.searchHelperLabel.clear()
        page.searchHelperLabel.hide()
        if not text:
            page.model.filter = ""
            try:
                page.model.refresh()
            except Exception:
                logger.exception("Failed to refresh model when search text cleared")

    page.searchEdit.textChanged.connect(text_changed)
