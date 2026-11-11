from PySide6.QtWidgets import QColorDialog, QMessageBox


def show_color_dialog():
    color = QColorDialog.getColor()

    if color.isValid():
        return color

    return None


def show_confirmation_dialog(message: str, warning=False) -> bool:
    message_box = QMessageBox()
    message_box.setIcon(QMessageBox.Warning if warning else QMessageBox.Question)
    message_box.setWindowTitle("Confirmation")
    message_box.setText(message)
    message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    message_box.setDefaultButton(QMessageBox.No)

    return message_box.exec() == QMessageBox.Yes


def show_info_dialog(title: str, message: str, parent=None) -> None:
    message_box = QMessageBox(parent)
    message_box.setIcon(QMessageBox.Icon.Information)
    message_box.setWindowTitle(title)
    message_box.setText(message)
    message_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    message_box.exec()
