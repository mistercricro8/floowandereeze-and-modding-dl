import logging

from PySide6.QtWidgets import QColorDialog, QMessageBox

logger = logging.getLogger(__name__)


def show_color_dialog():
    color = QColorDialog.getColor()

    if color.isValid():
        return color

    return None


def show_confirmation_dialog(message: str, warning=False) -> bool:
    """
    Display a confirmation prompt for destructive or irreversible actions.

    Note:
        Reserved strictly for destructive, irreversible actions (e.g. file deletion,
        overwriting backups, data reset). Non-destructive guidance and feedback must
        use inline alerts (`widgets.inline_alert.notify`) instead.

    Args:
        message: The prompt or question message to display.
        warning: Whether to display a Warning icon instead of Question icon.

    Returns:
        bool: True if the user confirmed (Yes), False if dismissed (No).
    """
    message_box = QMessageBox()
    message_box.setIcon(QMessageBox.Warning if warning else QMessageBox.Question)
    message_box.setWindowTitle("Confirmation")
    message_box.setText(message)
    message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    message_box.setDefaultButton(QMessageBox.No)

    confirmed = message_box.exec() == QMessageBox.Yes
    if confirmed:
        logger.info("Confirmation accepted: %s", message)
    else:
        logger.info("Confirmation dismissed: %s", message)

    return confirmed


def show_info_dialog(title: str, message: str, parent=None) -> None:
    """
    Display a modal informational dialog.

    .. deprecated::
        Deprecated: use `widgets.inline_alert.notify` instead to provide inline
        feedback without interrupting the user or opening modal dialog windows.

    Args:
        title: Window title for the dialog.
        message: Informational text body.
        parent: Optional parent widget.
    """
    message_box = QMessageBox(parent)
    message_box.setIcon(QMessageBox.Icon.Information)
    message_box.setWindowTitle(title)
    message_box.setText(message)
    message_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    message_box.exec()
