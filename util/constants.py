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

    QPushButton {
        background-color: rgba(22, 27, 34, 0.85);
        color: #e6edf3;
        border: 1px solid rgba(240, 246, 252, 0.25);
        border-radius: 5px;
        padding: 4px 12px;
        min-height: 24px;
    }

    .QToolBar::item:hover {
        background-color: rgba(12, 12, 12, 0.7);
    }

    QPushButton:hover {
        background-color: rgba(33, 42, 53, 0.95);
        border: 1px solid #58a6ff;
        color: #ffffff;
    }

    QPushButton:pressed {
        background-color: rgba(20, 27, 36, 1.0);
        border: 1px solid #1f6feb;
    }

    QPushButton:disabled {
        background-color: rgba(18, 18, 18, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.1);
        color: rgba(255, 255, 255, 0.35);
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
    "QPushButton { background-color: rgba(22, 27, 34, 0.85); border: 1px solid rgba(240, 246, 252, 0.25); color: #e6edf3; padding: 3px 10px; border-radius: 4px; }"
    "QPushButton:hover { background-color: rgba(33, 42, 53, 0.95); border: 1px solid #58a6ff; color: #ffffff; }"
    "QPushButton:checked { background-color: #1f6feb; color: white; border: 1px solid #58a6ff; font-weight: bold; }"
)

run_migrations()

APP_CONFIG: AppConfig = session.query(AppConfig).first()
"""
    Database user config, created if not exists on start.
"""

if not APP_CONFIG:
    new_app = AppConfig(game_path="", create_backup=True)
    session.add(new_app)
    session.commit()
    APP_CONFIG = new_app
