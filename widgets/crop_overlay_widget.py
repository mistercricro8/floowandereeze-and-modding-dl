"""Interactive crop overlay widget with a resizable yellow crop rectangle."""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class CropOverlayWidget(QWidget):
    """
    Displays a user image with an interactive yellow crop overlay.

    The user drags the four corner handles to resize the crop area (optionally
    locked to a target aspect ratio) and drags the interior to move it.
    Emits ``crop_changed`` whenever the crop rectangle is updated.
    """

    crop_changed = Signal()

    _HANDLE = 10
    _MIN_DIM = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._target_ratio: float | None = None
        self._image_rect: QRectF | None = None
        self._crop_rect: QRectF | None = None

        self._drag_mode: str | None = None
        self._drag_start: QPointF | None = None
        self._drag_start_rect: QRectF | None = None

        self.setMouseTracking(True)
        self.setMinimumSize(QSize(100, 100))

    def set_image(self, path: str, target_ratio: float | None = None) -> None:
        """Load *path* and initialise the crop rectangle."""
        self._target_ratio = target_ratio
        self._pixmap = QPixmap(path)
        self._recalculate()
        self.update()

    def set_target_ratio(
        self, ratio: float | None, preserve_crop: bool = False
    ) -> None:
        """Change the constraint, optionally keeping the shared crop area."""
        if ratio == self._target_ratio:
            return
        self._target_ratio = ratio
        if self._pixmap and not preserve_crop:
            self._init_crop_rect()
            self.update()

    def get_crop_rect_normalized(self) -> tuple[float, float, float, float] | None:
        """
        Return the crop rect as ``(left, top, right, bottom)`` normalised to
        0..1 relative to the original image.  Returns *None* when no image or
        crop rect is set.
        """
        if not self._crop_rect or not self._image_rect:
            return None
        ir = self._image_rect
        cr = self._crop_rect.intersected(ir)
        if ir.width() == 0 or ir.height() == 0:
            return None
        return (
            (cr.left() - ir.left()) / ir.width(),
            (cr.top() - ir.top()) / ir.height(),
            (cr.right() - ir.left()) / ir.width(),
            (cr.bottom() - ir.top()) / ir.height(),
        )

    def _recalculate(self) -> None:
        self._update_image_rect()
        self._init_crop_rect()

    def _update_image_rect(self) -> None:
        if not self._pixmap:
            self._image_rect = None
            return
        pw, ph = self._pixmap.width(), self._pixmap.height()
        ww, wh = self.width(), self.height()
        if pw <= 0 or ph <= 0 or ww <= 0 or wh <= 0:
            return
        scale = min(ww / pw, wh / ph)
        sw, sh = pw * scale, ph * scale
        self._image_rect = QRectF((ww - sw) / 2, (wh - sh) / 2, sw, sh)

    def _init_crop_rect(self) -> None:
        if not self._image_rect:
            return
        ir = self._image_rect
        iw, ih = ir.width(), ir.height()

        if self._target_ratio and iw > 0 and ih > 0:
            if iw / ih > self._target_ratio:
                ch = ih
                cw = ch * self._target_ratio
            else:
                cw = iw
                ch = cw / self._target_ratio
        else:
            cw, ch = iw, ih

        cx = ir.left() + (iw - cw) / 2
        cy = ir.top() + (ih - ch) / 2
        self._crop_rect = QRectF(cx, cy, cw, ch)

    def _drag_mode_at(self, pos: QPointF) -> str | None:
        if not self._crop_rect:
            return None
        cr = self._crop_rect
        h = float(self._HANDLE)
        corners = {
            "tl": QPointF(cr.left(), cr.top()),
            "tr": QPointF(cr.right(), cr.top()),
            "bl": QPointF(cr.left(), cr.bottom()),
            "br": QPointF(cr.right(), cr.bottom()),
        }
        for name, c in corners.items():
            if abs(pos.x() - c.x()) <= h and abs(pos.y() - c.y()) <= h:
                return name
        if cr.contains(pos):
            return "move"
        return None

    def _cursor_for_mode(self, mode: str | None) -> Qt.CursorShape:
        return {
            "tl": Qt.CursorShape.SizeFDiagCursor,
            "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor,
            "bl": Qt.CursorShape.SizeBDiagCursor,
            "move": Qt.CursorShape.SizeAllCursor,
        }.get(mode, Qt.CursorShape.ArrowCursor)

    def _apply_drag(self, dx: float, dy: float) -> None:
        if not self._image_rect or not self._drag_start_rect:
            return
        ir = self._image_rect
        sr = self._drag_start_rect
        ratio = self._target_ratio
        min_d = float(self._MIN_DIM)

        if self._drag_mode == "move":
            nx = max(ir.left(), min(sr.x() + dx, ir.right() - sr.width()))
            ny = max(ir.top(), min(sr.y() + dy, ir.bottom() - sr.height()))
            self._crop_rect = QRectF(nx, ny, sr.width(), sr.height())
            return

        new_w = sr.width() - dx if self._drag_mode in ("tl", "bl") else sr.width() + dx

        if self._drag_mode in ("tl", "tr"):
            new_h = sr.height() - dy
        else:
            new_h = sr.height() + dy

        if ratio:
            if abs(dx) >= abs(dy):
                new_h = new_w / ratio
            else:
                new_w = new_h * ratio

            anchor_x = sr.right() if self._drag_mode in ("tl", "bl") else sr.left()
            anchor_y = sr.bottom() if self._drag_mode in ("tl", "tr") else sr.top()
            max_w = (
                anchor_x - ir.left()
                if self._drag_mode in ("tl", "bl")
                else ir.right() - anchor_x
            )
            max_h = (
                anchor_y - ir.top()
                if self._drag_mode in ("tl", "tr")
                else ir.bottom() - anchor_y
            )
            max_w = min(max_w, max_h * ratio)
            min_w = min(max_w, max(min_d, min_d * ratio))
            new_w = max(min_w, min(new_w, max_w))
            new_h = new_w / ratio
            nx = anchor_x - new_w if self._drag_mode in ("tl", "bl") else anchor_x
            ny = anchor_y - new_h if self._drag_mode in ("tl", "tr") else anchor_y
            self._crop_rect = QRectF(nx, ny, new_w, new_h)
            return

        new_w = max(min_d, new_w)
        new_h = max(min_d, new_h)

        if self._drag_mode == "tl":
            nx, ny = sr.right() - new_w, sr.bottom() - new_h
        elif self._drag_mode == "tr":
            nx, ny = sr.left(), sr.bottom() - new_h
        elif self._drag_mode == "bl":
            nx, ny = sr.right() - new_w, sr.top()
        else:
            nx, ny = sr.left(), sr.top()

        nx = max(ir.left(), min(nx, ir.right() - min_d))
        ny = max(ir.top(), min(ny, ir.bottom() - min_d))
        new_w = min(new_w, ir.right() - nx)
        new_h = min(new_h, ir.bottom() - ny)
        new_w = max(min_d, new_w)
        new_h = max(min_d, new_h)

        self._crop_rect = QRectF(nx, ny, new_w, new_h)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._crop_rect:
            pos = event.position()
            mode = self._drag_mode_at(pos)
            if mode:
                self._drag_mode = mode
                self._drag_start = pos
                self._drag_start_rect = QRectF(self._crop_rect)

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._drag_mode and self._drag_start and self._drag_start_rect:
            self._apply_drag(
                pos.x() - self._drag_start.x(),
                pos.y() - self._drag_start.y(),
            )
            self.crop_changed.emit()
            self.update()
        else:
            self.setCursor(QCursor(self._cursor_for_mode(self._drag_mode_at(pos))))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_mode = None
            self._drag_start = None
            self._drag_start_rect = None

    def resizeEvent(self, event):
        crop = self.get_crop_rect_normalized()
        self._update_image_rect()
        if crop and self._image_rect:
            left, top, right, bottom = crop
            image = self._image_rect
            self._crop_rect = QRectF(
                image.left() + left * image.width(),
                image.top() + top * image.height(),
                (right - left) * image.width(),
                (bottom - top) * image.height(),
            )
        else:
            self._init_crop_rect()
        self.update()

    def paintEvent(self, event):
        if not self._pixmap or not self._image_rect:
            return

        qp = QPainter(self)
        ir = self._image_rect

        scaled = self._pixmap.scaled(
            ir.size().toSize(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        qp.drawPixmap(ir.topLeft().toPoint(), scaled)

        if self._crop_rect:
            cr = self._crop_rect
            overlay = QColor(0, 0, 0, 110)
            top_h = max(0.0, cr.top() - ir.top())
            bot_h = max(0.0, ir.bottom() - cr.bottom())
            left_w = max(0.0, cr.left() - ir.left())
            right_w = max(0.0, ir.right() - cr.right())
            qp.fillRect(QRectF(ir.left(), ir.top(), ir.width(), top_h), overlay)
            qp.fillRect(QRectF(ir.left(), cr.bottom(), ir.width(), bot_h), overlay)
            qp.fillRect(QRectF(ir.left(), cr.top(), left_w, cr.height()), overlay)
            qp.fillRect(QRectF(cr.right(), cr.top(), right_w, cr.height()), overlay)

            qp.setRenderHint(QPainter.RenderHint.Antialiasing)
            qp.setPen(QPen(QColor(255, 220, 0), 2, Qt.PenStyle.DashLine))
            qp.setBrush(Qt.BrushStyle.NoBrush)
            qp.drawRect(cr)

            h = float(self._HANDLE)
            qp.setPen(QPen(QColor(255, 220, 0), 2))
            qp.setBrush(QColor(255, 255, 255, 210))
            for cx, cy in (
                (cr.left(), cr.top()),
                (cr.right(), cr.top()),
                (cr.left(), cr.bottom()),
                (cr.right(), cr.bottom()),
            ):
                qp.drawRect(QRectF(cx - h / 2, cy - h / 2, h, h))

        qp.end()
