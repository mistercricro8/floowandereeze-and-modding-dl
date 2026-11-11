"""
Main window implementation for the Floowandereeze & Modding application.
This module provides the main application window that hosts all the different
pages and handles navigation between them.
"""

import logging

from PySide6 import QtCore, QtGui, QtWidgets

from database.objects import session
from pages.backups import Backups
from pages.card import Card
from pages.character import Character
from pages.config import Config
from pages.field import Field
from pages.sleeve import Sleeve
from pages.ui.main_window import Ui_MainWindow
from services.update_service import metadata_tables_empty
from util.constants import APP_CONFIG, BG_TEMPLATE
from util.game_discovery import normalize_game_path
from util.python_utils import is_valid_game_path

logger = logging.getLogger(__name__)


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    """
    Main window class that serves as the container for all application pages.

    This class handles:
    - Loading and managing different pages (Config, Sleeve, Card, etc.)
    - Navigation between pages through the toolbar
    - Background image management
    - Game path validation and error handling

    Attributes:
        splash: The splash screen widget used during application startup
    """

    def __init__(self, splash: QtWidgets.QSplashScreen):
        """
        Initialize the main window.

        Args:
            splash: The splash screen widget to show loading progress
        """
        super().__init__()
        self.splash = splash
        self.setupUi(self)
        self._configure_navigation()

        self._load_pages()
        self._connect_menu_callbacks()
        self._load_bg()

        self._window_settings = QtCore.QSettings("Floowandereeze", "DuelLinks")
        geometry = self._window_settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.show()

    def _load_pages(self) -> None:
        """Keep startup quick and create asset pages when first visited."""
        self._page_classes = (Config, Sleeve, Card, Field, Character, Backups)
        self.config_page = Config()
        self.mainStack.addWidget(self.config_page)
        self.config_page.gamePathChanged.connect(self._reset_asset_pages)
        self.config_page.dataUpdated.connect(self._reset_asset_pages)
        self._reset_asset_pages()

    NAV_TOOLTIPS = {
        "Configuration": "Configuration: Set Duel Links game folder, download card name updates, and configure backups.",
        "Sleeves": "Sleeves: Browse, extract, and mod card sleeve artwork and custom borders.",
        "Cards": "Cards: Browse, extract, and mod card artwork.",
        "Fields": "Fields: Browse, extract, and mod duel playmat and field surfaces.",
        "Characters": "Characters: Browse and edit character dialogue busts, duel cut-ins, and portraits.",
        "Backups": "Backups: View, export, import, or manage your saved original game files.",
    }

    def _reset_asset_pages(self):
        self.mainStack.setCurrentIndex(0)
        while self.mainStack.count() > 1:
            widget = self.mainStack.widget(1)
            self.mainStack.removeWidget(widget)
            widget.deleteLater()
        self._loaded_pages = {0}

        raw_path = APP_CONFIG.game_path
        cleaned = str(raw_path).strip().strip("'\"") if raw_path else ""
        normalized = normalize_game_path(cleaned) if cleaned else None
        if normalized and APP_CONFIG.game_path != normalized:
            APP_CONFIG.game_path = normalized
            session.commit()

        valid = False
        if normalized:
            valid_flag, _ = is_valid_game_path(normalized)
            valid = bool(valid_flag)

        missing_metadata = metadata_tables_empty() if valid else False
        unlocked = valid and not missing_metadata

        for action in (
            self.actionsleeve_button,
            self.actioncard_button,
            self.actionfield_button,
            self.actioncharacter_button,
        ):
            action.setEnabled(unlocked)
            if not valid:
                action.setToolTip(
                    f"Set your game folder in Configuration to unlock {action.text()}."
                )
            elif missing_metadata:
                action.setToolTip(
                    f"Download card data in Configuration to unlock {action.text()}."
                )
            else:
                action.setToolTip(self.NAV_TOOLTIPS.get(action.text(), action.text()))

        self.actionconfig_button.setEnabled(True)
        self.actionconfig_button.setToolTip(
            self.NAV_TOOLTIPS.get("Configuration", "Configuration")
        )
        self.actionbackups_button.setEnabled(True)
        self.actionbackups_button.setToolTip(
            self.NAV_TOOLTIPS.get("Backups", "Backups")
        )

        for _ in self._page_classes[1:]:
            self.mainStack.addWidget(QtWidgets.QWidget())

    def _activate_page(self, index):
        if index not in self._loaded_pages:
            placeholder = self.mainStack.widget(index)
            try:
                page = self._page_classes[index]()
            except Exception as error:
                logger.error(
                    "Could not load asset page at index %d: %s",
                    index,
                    error,
                    exc_info=True,
                )
                self.statusBar().showMessage(
                    f"Could not load asset page: {error}", 5000
                )
                return
            self.mainStack.removeWidget(placeholder)
            placeholder.deleteLater()
            self.mainStack.insertWidget(index, page)
            self._loaded_pages.add(index)
        self.mainStack.setCurrentIndex(index)

    def _configure_navigation(self) -> None:
        """Match the equal-sized navigation buttons used in floo-qt."""
        button_size = QtCore.QSize(92, 62)
        icon_size = QtCore.QSize(30, 30)
        style = QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon
        self.toolBar.setToolButtonStyle(style)
        self.toolBar.setIconSize(icon_size)
        self.toolBar.setStyleSheet("""
            QToolBar QToolButton {
                color: #f2f2f2;
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
            }
            QToolBar QToolButton:hover,
            QToolBar QToolButton:focus {
                background-color: #303030;
                border-color: #606060;
            }
            QToolBar QToolButton:pressed,
            QToolBar QToolButton:checked {
                background-color: #3b3b3b;
                border-color: #808080;
            }
            QToolBar QToolButton:disabled {
                color: #888888;
                background-color: transparent;
                border-color: transparent;
            }
            """)
        self._navigation_buttons = [
            self.actionconfig_button,
            self.actionsleeve_button,
            self.actioncard_button,
            self.actionfield_button,
            self.actioncharacter_button,
            self.actionbackups_button,
        ]
        labels = [
            "Configuration",
            "Sleeves",
            "Cards",
            "Fields",
            "Characters",
            "Backups",
        ]

        for action, label in zip(self._navigation_buttons, labels, strict=True):
            action.setText(label)
            action.setToolTip(self.NAV_TOOLTIPS.get(label, label))
            self._normalize_navigation_icon(action, icon_size)
            tool_button = self.toolBar.widgetForAction(action)
            if isinstance(tool_button, QtWidgets.QToolButton):
                tool_button.setFixedSize(button_size)
                tool_button.setIconSize(icon_size)
                tool_button.setToolButtonStyle(style)

    @staticmethod
    def _normalize_navigation_icon(action: QtGui.QAction, size: QtCore.QSize) -> None:
        """Center icons of different aspect ratios in equal square canvases."""
        source = action.icon().pixmap(QtCore.QSize(256, 256))
        if source.isNull():
            return

        source.setDevicePixelRatio(1)
        scaled = source.scaled(
            size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        canvas = QtGui.QPixmap(size)
        canvas.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(canvas)
        painter.drawPixmap(
            (size.width() - scaled.width()) // 2,
            (size.height() - scaled.height()) // 2,
            scaled,
        )
        painter.end()
        action.setIcon(QtGui.QIcon(canvas))

    def _connect_menu_callbacks(self) -> None:
        """Connects the menu buttons to their respective pages in the stack."""
        for index, button in enumerate(self._navigation_buttons):
            button.triggered.connect(lambda _, idx=index: self._activate_page(idx))

    def _load_bg(self) -> None:
        self.setStyleSheet(BG_TEMPLATE.replace("$BG$", ""))
        self.centralwidget.set_background(
            APP_CONFIG.background_path, APP_CONFIG.background_mode or "stretched"
        )

    def closeEvent(self, event):
        self._window_settings.setValue("window/geometry", self.saveGeometry())
        super().closeEvent(event)
