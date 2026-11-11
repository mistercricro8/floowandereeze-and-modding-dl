"""
Constants and configuration used throughout the application.
This module centralizes all application constants, configuration values,
and global state to facilitate updates and maintain consistency.
"""

from database.migrations import run_migrations
from database.models import AppConfig
from database.objects import session

FILE: dict[str, str | list[str]] = {
    "IMAGE_NAME": "image.png",
    "UNITY": "data.unity3d",
    "BACKGROUND": "ShopBGBase02",
    "CARD_SPRITE_ATLAS": "cardspriteatlas",
}

BG_TEMPLATE: str = """
    #centralwidget {
        $BG$
        margin: 0;
        padding: 0;
    }

    .QListView, .QLineEdit, .QListWidget, #preview_frame, #current_frame {
        background-color: rgba(12, 12, 12, 0.7);
    }

    .QPushButton {
        border: 1px solid #121212;
        border-radius: 5px;
        padding: 4px 10px;
        min-height: 24px;
    }

    .QToolBar::item:hover {
        background-color: rgba(12, 12, 12, 0.7);
    }

    .QPushButton:hover {
        border: 1px solid darkgreen;
    }

    .QPushButton:disabled {
        border: 1px solid #523000;
    }

    #toast-icon-widget, #toast-close-button {
        background: transparent;
        border: none;
        padding: 0px;
        min-height: 0px;
        min-width: 0px;
    }

    #toast-icon-widget:hover, #toast-close-button:hover {
        background: transparent;
        border: none;
    }
"""
"""
    CSS template to apply on background changes, the $VALUE$ placeholders
    must be replaced with nothing or valid CSS
"""


IMAGE_FILTER: str = "Image Files (*.png *.jpg *.jpeg)"
IMAGE_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".bmp", ".gif")
"""
    Types of supported images
"""

FIT_MODE_BUTTON_STYLE: str = (
    "QPushButton { border: 1px solid gray; padding: 3px 10px; border-radius: 3px; }"
    "QPushButton:checked { background-color: #3a7cc1; color: white; "
    "border-color: #2a6cb1; }"
)

run_migrations()

APP_CONFIG: AppConfig = session.query(AppConfig).first()
"""
    Database user config, created if not exists on start.
"""

if not APP_CONFIG:
    new_app = AppConfig(game_path="", create_backup=True)
    session.add(new_app)
    APP_CONFIG = new_app
