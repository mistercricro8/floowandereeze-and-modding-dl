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
    Display informational feedback using the standardized inline alert banner.

    Args:
        title: Title of the informational alert.
        message: Informational text body.
        parent: Optional parent widget hosting an inline alert banner.
    """
    from widgets.inline_alert import notify

    if parent is not None:
        notify(parent, "info", title, message)
    else:
        logger.info("%s: %s", title, message)
