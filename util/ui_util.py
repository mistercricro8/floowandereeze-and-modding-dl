"""
UI utility functions for the application.
This module provides functions for UI-related tasks like showing toasts
and managing the application's color palette.
"""

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


def log_action(
    logger_name: str,
    level: int | str,
    message: str,
    exc: Exception | None = None,
) -> None:
    """
    Log an application action or event without displaying popup dialogs.

    Args:
        logger_name: Target logger name (e.g. __name__ or module path).
        level: Severity level (e.g. logging.INFO, logging.ERROR, or 'info', 'error').
        message: Informational or diagnostic message to log.
        exc: Optional exception to log with traceback.
    """
    log = logging.getLogger(logger_name)
    if isinstance(level, str):
        level_name = level.upper().strip()
        numeric_level = (
            logging.getLevelNamesMapping().get(level_name)
            if hasattr(logging, "getLevelNamesMapping")
            else getattr(logging, level_name, None)
        )
        if numeric_level is None or not isinstance(numeric_level, int):
            raise ValueError(f"Invalid logging level name: '{level}'")
    elif isinstance(level, int):
        numeric_level = level
    else:
        raise TypeError(f"Expected level to be int or str, got {type(level).__name__}")

    log.log(numeric_level, message, exc_info=exc)


def show_toast(parent: Any, title: str, text: str, preset: Any = None) -> None:
    """
    Display feedback using the standardized inline alert banner.

    Args:
        parent: The widget host for the inline alert banner.
        title: Alert title.
        text: Main message text.
        preset: Optional legacy toast preset for severity mapping.
    """
    from widgets.inline_alert import notify

    preset_name = getattr(preset, "name", "")
    if not isinstance(preset_name, str):
        preset_name = str(preset) if preset is not None else ""
    preset_upper = preset_name.upper()

    if "SUCCESS" in preset_upper:
        kind = "success"
    elif "WARNING" in preset_upper:
        kind = "warning"
    elif "ERROR" in preset_upper:
        kind = "error"
    else:
        kind = "info"

    if parent is not None:
        notify(parent, kind, title, text)
    else:
        logger.info("[%s] %s: %s", kind.upper(), title, text)


def open_in_file_manager(path: str | Path) -> bool:
    """Open the directory containing the given path in the OS file manager."""
    target = Path(path).resolve()
    folder = target if target.is_dir() else target.parent
    if folder.exists():
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
    return False


def format_actionable_error(error: Exception, action_context: str) -> tuple[str, str]:
    """
    Format an exception into a human-readable summary and actionable remediation hint.

    Returns:
        tuple[str, str]: (summary_message, actionable_remediation_hint)
    """
    if isinstance(error, PermissionError):
        summary = f"File access locked during {action_context}."
        hint = (
            "Game files are locked by another process.\n"
            "Please completely exit Yu-Gi-Oh! Duel Links and any other tools, "
            "then try again."
        )
    elif isinstance(error, FileNotFoundError):
        summary = f"Required game bundle not found during {action_context}."
        err_text = str(error).strip()
        detail_line = f"\n{err_text}\n" if err_text else "\n"
        hint = (
            f"The asset bundle or game files could not be located.{detail_line}"
            "Verify your Game Path in Configuration, or launch Duel Links "
            "to ensure in-game data has finished downloading."
        )
    elif isinstance(error, ValueError):
        summary = f"Invalid data during {action_context}."
        hint = f"{error}\nPlease verify your inputs and selected file."
    else:
        summary = f"Failed to complete {action_context}."
        hint = (
            f"An unexpected error occurred ({type(error).__name__}): {error}\n"
            "Check that your storage drive has sufficient space and your game "
            "path is valid."
        )
    return summary, hint


def show_actionable_error_dialog(
    parent: QWidget | None,
    title: str,
    summary: str,
    resolution_hint: str,
    technical_details: str | None = None,
) -> None:
    """
    Display structured error feedback using the standardized inline alert banner.

    Args:
        parent: Optional parent widget hosting an inline alert banner.
        title: Error title.
        summary: Error summary.
        resolution_hint: Actionable advice for resolving the error.
        technical_details: Optional technical details.
    """
    from widgets.inline_alert import notify

    body = f"{summary}\n{resolution_hint}"
    if technical_details:
        body = f"{body}\n{technical_details}"

    if parent is not None:
        notify(parent, "error", title, body)
    else:
        logger.error("%s: %s", title, body)


def get_dark_mode_palette(app=None):
    """
    Create and return a dark mode color palette for the application.

    Args:
        app: The QApplication instance to get the base palette from.
             If None, a new QPalette will be created.

    Returns:
        QPalette: A dark mode color palette configured with appropriate colors
                 for various UI elements.
    """
    dark_palette = app.palette()
    dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.WindowText, Qt.white)
    dark_palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))
    dark_palette.setColor(QPalette.Base, QColor(42, 42, 42))
    dark_palette.setColor(QPalette.AlternateBase, QColor(66, 66, 66))
    dark_palette.setColor(QPalette.ToolTipBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ToolTipText, Qt.white)
    dark_palette.setColor(QPalette.Text, Qt.white)
    dark_palette.setColor(QPalette.PlaceholderText, QColor(160, 160, 160))
    dark_palette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
    dark_palette.setColor(QPalette.Dark, QColor(35, 35, 35))
    dark_palette.setColor(QPalette.Shadow, QColor(20, 20, 20))
    dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ButtonText, Qt.white)
    dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor(80, 80, 80))
    dark_palette.setColor(QPalette.HighlightedText, Qt.white)
    dark_palette.setColor(
        QPalette.Disabled,
        QPalette.HighlightedText,
        QColor(127, 127, 127),
    )

    return dark_palette
