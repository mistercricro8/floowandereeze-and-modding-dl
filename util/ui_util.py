"""
UI utility functions for the application.
This module provides functions for UI-related tasks like showing toasts
and managing the application's color palette.
"""

import logging
from pathlib import Path

from pyqttoast import Toast, ToastPosition, ToastPreset
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import QMessageBox, QWidget

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


def show_toast(parent, title: str, text: str, preset: ToastPreset):
    """
    Show a toast notification to the user.

    .. deprecated::
        Deprecated: use `widgets.inline_alert.notify` instead of toast popups
        to provide non-intrusive feedback without stealing window focus.

    Args:
        parent: The parent widget for the toast
        title: The title text of the toast
        text: The main text content of the toast
        preset: The visual preset to apply to the toast
    """
    logger.warning("show_toast is deprecated; use widgets.inline_alert.notify instead")
    target = parent.window() if hasattr(parent, "window") else parent
    if target is not None:
        Toast.setPositionRelativeToWidget(target)
    Toast.setPosition(ToastPosition.BOTTOM_RIGHT)
    Toast.setOffset(24, 24)

    toast = Toast(target)
    toast.applyPreset(preset)
    toast.setTitle(title)
    toast.setText(text)
    toast.setDuration(3500)
    toast.setShowDurationBar(False)
    toast.setShowCloseButton(False)
    toast.setShowIconSeparator(False)
    toast.setBorderRadius(6)
    toast.setBackgroundColor(QColor(24, 24, 24, 240))
    toast.setTitleColor(QColor(255, 255, 255))
    toast.setTextColor(QColor(210, 210, 210))
    toast.setStyleSheet(
        """
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
    )
    toast.show()


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
    Display a structured dialog explaining what failed and how to resolve it.

    .. deprecated::
        Deprecated: use `widgets.inline_alert.notify` to present errors inline
        without opening modal dialog windows.
    """
    logger.warning(
        "show_actionable_error_dialog is deprecated; use widgets.inline_alert.notify instead"
    )
    valid_parent = parent if isinstance(parent, QWidget) else None
    box = QMessageBox(valid_parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(f"<b>{summary}</b>")
    formatted_hint = resolution_hint.replace("\n", "<br>")
    box.setInformativeText(f"<b>How to resolve:</b><br>{formatted_hint}")
    if technical_details:
        box.setDetailedText(technical_details)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


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
