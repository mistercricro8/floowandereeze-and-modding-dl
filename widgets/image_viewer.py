from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class ImageViewer(QWidget):
    """
    Credit: musicamante at https://stackoverflow.com/a/67952671
    """

    pixmap = None
    _sizeHint = QSize()
    ratio = Qt.KeepAspectRatio
    transformation = Qt.SmoothTransformation

    def __init__(self, pixmap=None):
        super().__init__()
        self.setPixmap(pixmap)

    def setPixmap(self, pixmap):
        if self.pixmap != pixmap:
            self.pixmap = pixmap
            if isinstance(pixmap, QPixmap):
                self._sizeHint = pixmap.size()
            else:
                self._sizeHint = QSize()
            self.updateGeometry()
            self.updateScaled()

    def setAspectRatio(self, ratio):
        if self.ratio != ratio:
            self.ratio = ratio
            self.updateScaled()

    def setTransformation(self, transformation):
        if self.transformation != transformation:
            self.transformation = transformation
            self.updateScaled()

    def updateScaled(self):
        if self.pixmap:
            self.scaled = self.pixmap.scaled(
                self.size(), self.ratio, self.transformation
            )
        self.update()

    MAX_HINT_SIZE: int = 374

    def sizeHint(self) -> QSize:
        if self._sizeHint.isValid() and not self._sizeHint.isEmpty():
            pw, ph = self._sizeHint.width(), self._sizeHint.height()
            if pw <= 0 or ph <= 0:
                return QSize(self.MAX_HINT_SIZE, self.MAX_HINT_SIZE)
            scale = min(self.MAX_HINT_SIZE / pw, self.MAX_HINT_SIZE / ph)
            if scale < 1.0:
                return QSize(max(1, int(pw * scale)), max(1, int(ph * scale)))
            return self._sizeHint
        return QSize(self.MAX_HINT_SIZE, self.MAX_HINT_SIZE)

    def minimumSizeHint(self) -> QSize:
        return QSize(64, 64)

    def resizeEvent(self, event):
        self.updateScaled()

    def paintEvent(self, event):
        if not self.pixmap:
            return
        qp = QPainter(self)
        r = self.scaled.rect()
        r.moveCenter(self.rect().center())
        qp.drawPixmap(r, self.scaled)
