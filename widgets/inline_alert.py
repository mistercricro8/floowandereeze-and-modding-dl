"""
Inline feedback infrastructure for in-app alert banners and notifications.

GUI-thread only: All UI operations, widgets, and helper functions in this
module must be called from the Qt main/GUI thread.

Usage Example:
    >>> # In page UI initialization:
    >>> attach_inline_alert(self, self.verticalLayout)
    >>> # To notify users inline (never pops modal windows):
    >>> notify(self, "success", "Export Complete", "Backup saved successfully.")
    >>> notify(self, "error", "Operation Failed", "Could not write to file.")
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6 import QtCore, QtWidgets

logger = logging.getLogger(__name__)

BORDER_COLORS: dict[str, str] = {
    "info": "#3a7cc1",
    "success": "#15a06f",
    "warning": "#b58900",
    "error": "#a93226",
}
AUTO_HIDE_KINDS: set[str] = {"info", "success"}
AUTO_HIDE_DURATION_MS: int = 4000


class InlineAlert(QtWidgets.QFrame):
    """
    In-app alert banner widget for displaying non-modal inline notifications.

    Never creates a top-level window, never invokes modal event loops, and
    never requests input focus.
    GUI-thread only: Must be manipulated on the Qt GUI thread.

    Usage Example:
        >>> alert = attach_inline_alert(self, self.verticalLayout)
        >>> alert.show_message("success", "Saved", "Settings updated.")
        >>> alert.show_message("error", "Failed", "Could not load image.")
        >>> alert.clear()
        >>> notify(self, "info", "Notice", "Processing finished.")
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inlineAlert")
        self.setVisible(False)
        self.setMinimumWidth(0)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        self._title_label = QtWidgets.QLabel(self)
        self._title_label.setObjectName("inlineAlertTitle")
        self._title_label.setWordWrap(True)
        self._title_label.setMinimumWidth(0)
        self._title_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self._title_label.setVisible(False)

        self._text_label = QtWidgets.QLabel(self)
        self._text_label.setObjectName("inlineAlertText")
        self._text_label.setWordWrap(True)
        self._text_label.setMinimumWidth(0)
        self._text_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self._text_label.setVisible(False)

        layout.addWidget(self._title_label)
        layout.addWidget(self._text_label)

        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.clear)

    def show_message(self, kind: str, title: str, text: str) -> None:
        """
        Display an inline alert banner with contextual severity styling.

        Success and info alerts automatically clear after ~4 seconds.
        Warning and error alerts remain visible until explicitly cleared or replaced.
        Empty text clears the alert banner.

        Args:
            kind: Alert severity ('info', 'success', 'warning', 'error').
            title: Headline or summary title (hidden if empty).
            text: Main alert message. An empty string clears the alert.

        Raises:
            ValueError: If `kind` is not one of ('info', 'success', 'warning', 'error').
        """
        clean_text = "" if text is None else str(text).strip()
        clean_title = "" if title is None else str(title).strip()

        if not clean_text:
            self.clear()
            return

        kind_key = kind.lower().strip() if isinstance(kind, str) else ""
        if kind_key not in BORDER_COLORS:
            raise ValueError(
                f"Invalid alert kind '{kind}'. Expected one of: "
                f"{', '.join(BORDER_COLORS.keys())}"
            )

        self._timer.stop()

        if clean_title:
            self._title_label.setText(clean_title)
            self._title_label.setVisible(True)
        else:
            self._title_label.setText("")
            self._title_label.setVisible(False)

        self._text_label.setText(clean_text)
        self._text_label.setVisible(True)

        border_color = BORDER_COLORS[kind_key]
        self.setStyleSheet(
            f"#inlineAlert {{"
            f" background-color: rgba(12, 12, 12, 0.85);"
            f" border: 1px solid {border_color};"
            f" border-radius: 5px;"
            f"}}"
            f"#inlineAlertTitle {{"
            f" color: #ffffff;"
            f" font-weight: bold;"
            f" background: transparent;"
            f" border: none;"
            f"}}"
            f"#inlineAlertText {{"
            f" color: #d6d6d6;"
            f" background: transparent;"
            f" border: none;"
            f"}}"
        )
        self.updateGeometry()
        self.setVisible(True)

        if kind_key in AUTO_HIDE_KINDS:
            self._timer.start(AUTO_HIDE_DURATION_MS)

    def minimumSizeHint(self) -> QtCore.QSize:
        if not self.isVisible():
            return QtCore.QSize(0, 0)
        return QtCore.QSize(0, 36)

    def sizeHint(self) -> QtCore.QSize:
        if not self.isVisible():
            return QtCore.QSize(0, 0)
        parent = self.parentWidget()
        parent_w = parent.width() if parent else self.width()
        avail_w = max(200, parent_w - 24)
        total_h = 16
        if self._title_label.isVisible() and self._title_label.text():
            tr = self._title_label.fontMetrics().boundingRect(
                QtCore.QRect(0, 0, avail_w, 10000),
                QtCore.Qt.TextFlag.TextWordWrap,
                self._title_label.text(),
            )
            total_h += tr.height() + 4
        if self._text_label.isVisible() and self._text_label.text():
            tr = self._text_label.fontMetrics().boundingRect(
                QtCore.QRect(0, 0, avail_w, 10000),
                QtCore.Qt.TextFlag.TextWordWrap,
                self._text_label.text(),
            )
            total_h += tr.height()
        return QtCore.QSize(avail_w, total_h)

    def clear(self) -> None:
        """Clear all message labels and hide the inline alert banner."""
        self._timer.stop()
        self._title_label.setText("")
        self._title_label.setVisible(False)
        self._text_label.setText("")
        self._text_label.setVisible(False)
        self.setVisible(False)
        self.updateGeometry()


def attach_inline_alert(
    page: Any,
    layout: QtWidgets.QLayout | None,
    name: str = "inlineAlert",
) -> InlineAlert:
    """
    Create and insert an InlineAlert at the top (index 0) of the page layout.

    Idempotent: if `page.<name>` already exists and is not None, returns it.
    GUI-thread only: Must be called from the Qt main/GUI thread.

    Usage Example:
        >>> # In page UI initialization:
        >>> attach_inline_alert(self, self.verticalLayout)
        >>> # To notify users inline (never pops modal windows):
        >>> notify(self, "success", "Export Complete", "Backup saved successfully.")
        >>> notify(self, "error", "Operation Failed", "Could not write to file.")

    Args:
        page: The host page instance.
        layout: The host page layout (must not be None).
        name: Property name on the host page (defaults to 'inlineAlert').

    Returns:
        InlineAlert: The created or existing alert widget instance.

    Raises:
        ValueError: If `page` or `layout` is None.
        TypeError: If `layout` cannot accommodate child widget insertion.
    """
    if page is None:
        raise ValueError("Cannot attach InlineAlert: 'page' is None.")
    if hasattr(page, name):
        existing = getattr(page, name)
        if existing is not None:
            return existing
    if layout is None:
        raise ValueError("Cannot attach InlineAlert: 'layout' is None.")

    alert = InlineAlert(parent=page if isinstance(page, QtWidgets.QWidget) else None)
    if isinstance(layout, QtWidgets.QBoxLayout) or hasattr(layout, "insertWidget"):
        layout.insertWidget(0, alert)
    elif hasattr(layout, "addWidget"):
        layout.addWidget(alert)
    else:
        raise TypeError(
            f"Unsupported layout type for alert banner: {type(layout).__name__}"
        )

    setattr(page, name, alert)
    return alert


def notify(page: Any, kind: str, title: str, text: str) -> None:
    """
    Notify the user inline without stealing focus or opening popup windows.

    Uses `page.inlineAlert` if attached; otherwise falls back to logging and
    updates `page.status` label if present.
    GUI-thread only: Modifies Qt widgets; must be called from the main thread.

    Usage Example:
        >>> # In page UI initialization:
        >>> attach_inline_alert(self, self.verticalLayout)
        >>> # To notify users inline (never pops modal windows):
        >>> notify(self, "success", "Export Complete", "Backup saved successfully.")
        >>> notify(self, "error", "Operation Failed", "Could not write to file.")

    Args:
        page: The page instance (may contain `inlineAlert` or `status` attributes).
        kind: Message severity ('info', 'success', 'warning', 'error').
        title: Short title or header for the notification.
        text: Main explanatory message. An empty string clears the alert.

    Raises:
        ValueError: If kind is unknown when falling back to logging.
    """
    clean_text = "" if text is None else str(text).strip()
    clean_title = "" if title is None else str(title).strip()

    alert = getattr(page, "inlineAlert", None) if page is not None else None
    if alert is not None and hasattr(alert, "show_message"):
        if not clean_text:
            alert.clear()
        else:
            alert.show_message(kind=kind, title=clean_title, text=clean_text)
        return

    status_label = getattr(page, "status", None) if page is not None else None
    if not clean_text:
        if status_label is not None and hasattr(status_label, "setText"):
            status_label.setText("")
        return

    log_message = f"{clean_title}: {clean_text}" if clean_title else clean_text
    kind_lower = kind.lower().strip() if isinstance(kind, str) else ""

    if kind_lower == "error":
        logger.error(log_message)
    elif kind_lower == "warning":
        logger.warning(log_message)
    elif kind_lower in ("info", "success"):
        logger.info(log_message)
    else:
        raise ValueError(
            f"Invalid alert kind '{kind}'. Expected 'info', 'success', 'warning', or 'error'."
        )

    if status_label is not None and hasattr(status_label, "setText"):
        status_label.setText(log_message)
