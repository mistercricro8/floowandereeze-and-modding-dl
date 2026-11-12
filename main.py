"""
Main entry point for the Floowandereeze & Modding application.
This module initializes the Qt application, sets up the UI theme,
and handles the main application window and splash screen.
"""

import os
import sys

if getattr(sys, "frozen", False):
    os.environ.pop("_PYTHON_SYSCONFIGDATA_NAME", None)

from PySide6 import QtWidgets
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QSplashScreen

from database.objects import session
from pages.main_window import MainWindow
from util.ui_util import get_dark_mode_palette


def main() -> None:
    """Launch the Floowandereeze & Modding application."""
    app = QtWidgets.QApplication(sys.argv)
    app.setPalette(get_dark_mode_palette(app))

    try:
        splash_pixmap = QPixmap(":/ui/images/bg.jpg")
        splash = QSplashScreen(splash_pixmap)
        splash.setFont(QFont("Segoe UI", 14))
        splash.showMessage("Starting...", 4, "#FFFFFF")
        splash.show()

        splash.showMessage("Updating database...", 4, "#FFFFFF")

        splash.showMessage("Loading interface...", 4, "#FFFFFF")
        window = MainWindow(splash)
        window.setWindowTitle("Floowandereeze & Modding - Duel Links")
        window.show()

        splash.finish(window)
        app.exec()

        session.commit()
    except Exception as error:
        session.rollback()
        raise error
    finally:
        session.close()


if __name__ == "__main__":
    main()
