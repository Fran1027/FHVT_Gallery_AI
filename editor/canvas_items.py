from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsObject
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath, QPainter
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QSizeF


class ColorMarker(QGraphicsEllipseItem):
    """Círculo vectorial con tamaño dinámico proporcional a la resolución."""

    def __init__(self, color, x, y, size=30):
        super().__init__(-size // 2, -size // 2, size, size)
        self.marker_size = size
        self.setPos(x, y)
        self.setZValue(100)
        self.normal_pen = QPen(Qt.GlobalColor.white, max(2, size // 10))
        self.setPen(self.normal_pen)
        self.setBrush(QBrush(color))
        self.outer_ring = QGraphicsEllipseItem(
            -size // 2 - 1, -size // 2 - 1, size + 2, size + 2, self
        )
        self.outer_ring.setPen(QPen(Qt.GlobalColor.black, 1))
        self.outer_ring.setZValue(-1)

    def highlight(self):
        s = self.marker_size
        self.setRect(-s, -s, s * 2, s * 2)
        self.outer_ring.setRect(-s - 1, -s - 1, s * 2 + 2, s * 2 + 2)
        self.setPen(QPen(QColor("#007acc"), max(4, s // 5)))
        self.setZValue(1000)
        QTimer.singleShot(1000, self.reset_highlight)

    def reset_highlight(self):
        try:
            s = self.marker_size
            self.setRect(-s // 2, -s // 2, s, s)
            self.outer_ring.setRect(-s // 2 - 1, -s // 2 - 1, s + 2, s + 2)
            self.setPen(self.normal_pen)
            self.setZValue(100)
        except RuntimeError:
            pass  # El marcador fue eliminado del lienzo por el usuario, ignoramos el timer de forma segura


class CropOverlayItem(QGraphicsObject):
    """Herramienta de recorte profesional (Single-Item Overlay)."""

    def __init__(self, scene_rect):
        super().__init__()
        self.scene_rect = scene_rect
        cx, cy = scene_rect.center().x(), scene_rect.center().y()
        w, h = scene_rect.width() * 0.8, scene_rect.height() * 0.8
        self.crop_rect = QRectF(cx - w / 2, cy - h / 2, w, h)

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setZValue(1000)

        self.drag_mode = None
        self.drag_offset = None
        self.drag_origin = None
        self.handle_size = 14
        self.margin = 10
        self.min_size = 20

    def boundingRect(self):
        return self.scene_rect

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Aplicar fondo oscuro
        path = QPainterPath()
        path.addRect(self.scene_rect)
        crop_path = QPainterPath()
        crop_path.addRect(self.crop_rect)
        path = path.subtracted(crop_path)
        painter.fillPath(path, QColor(0, 0, 0, 150))

        # Borde
        painter.setPen(QPen(Qt.GlobalColor.white, 2, Qt.PenStyle.DashLine))
        painter.drawRect(self.crop_rect)

        # Dibujar tiradores
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.setBrush(QBrush(Qt.GlobalColor.white))
        s = self.handle_size
        r = self.crop_rect
        points = [
            (r.left(), r.top()),
            (r.right(), r.top()),
            (r.left(), r.bottom()),
            (r.right(), r.bottom()),  # Dibujar esquinas
            (r.center().x(), r.top()),
            (r.center().x(), r.bottom()),
            (r.left(), r.center().y()),
            (r.right(), r.center().y()),  # Bordes
        ]
        for x, y in points:
            painter.drawRect(QRectF(x - s / 2, y - s / 2, s, s))

    def _get_hotzone(self, pos):
        r = self.crop_rect
        m = self.margin
        # Dibujar esquinas
        if QRectF(r.left() - m, r.top() - m, m * 2, m * 2).contains(pos):
            return "LT"
        if QRectF(r.right() - m, r.top() - m, m * 2, m * 2).contains(pos):
            return "RT"
        if QRectF(r.left() - m, r.bottom() - m, m * 2, m * 2).contains(pos):
            return "LB"
        if QRectF(r.right() - m, r.bottom() - m, m * 2, m * 2).contains(pos):
            return "RB"
        # Bordes
        if QRectF(r.left() + m, r.top() - m, r.width() - m * 2, m * 2).contains(pos):
            return "T"
        if QRectF(r.left() + m, r.bottom() - m, r.width() - m * 2, m * 2).contains(pos):
            return "B"
        if QRectF(r.left() - m, r.top() + m, m * 2, r.height() - m * 2).contains(pos):
            return "L"
        if QRectF(r.right() - m, r.top() + m, m * 2, r.height() - m * 2).contains(pos):
            return "R"
        # Dibujar centro
        if r.adjusted(m, m, -m, -m).contains(pos):
            return "CENTER"
        return None

    def hoverMoveEvent(self, event):
        zone = self._get_hotzone(event.pos())
        if zone in ("LT", "RB"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif zone in ("RT", "LB"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif zone in ("L", "R"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif zone in ("T", "B"):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif zone == "CENTER":
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, event):
        zone = self._get_hotzone(event.pos())
        if zone:
            self.drag_mode = zone
            self.drag_offset = (
                event.pos() - self.crop_rect.topLeft() if zone == "CENTER" else None
            )
            event.accept()
        else:
            self.drag_mode = "NEW"
            self.drag_origin = event.pos()
            self.crop_rect = QRectF(self.drag_origin, QSizeF(0, 0))
            self.update()
            event.accept()

    def mouseMoveEvent(self, event):
        if not self.drag_mode:
            return
        pos = event.pos()
        r = self.crop_rect

        if self.drag_mode == "CENTER" and self.drag_offset:
            # Mover
            new_tl = pos - self.drag_offset
            new_rect = QRectF(new_tl, r.size())
            if new_rect.left() < self.scene_rect.left():
                new_rect.moveLeft(self.scene_rect.left())
            if new_rect.right() > self.scene_rect.right():
                new_rect.moveRight(self.scene_rect.right())
            if new_rect.top() < self.scene_rect.top():
                new_rect.moveTop(self.scene_rect.top())
            if new_rect.bottom() > self.scene_rect.bottom():
                new_rect.moveBottom(self.scene_rect.bottom())
            self.crop_rect = new_rect
        elif self.drag_mode == "NEW":
            self.crop_rect = (
                QRectF(self.drag_origin, pos).normalized().intersected(self.scene_rect)
            )
        else:
            # Ejecutar redimensionamiento
            left_val, t, right, b = r.left(), r.top(), r.right(), r.bottom()
            if "L" in self.drag_mode:
                left_val = min(pos.x(), right - self.min_size)
            if "R" in self.drag_mode:
                right = max(pos.x(), left_val + self.min_size)
            if "T" in self.drag_mode:
                t = min(pos.y(), b - self.min_size)
            if "B" in self.drag_mode:
                b = max(pos.y(), t + self.min_size)
            self.crop_rect = QRectF(QPointF(left_val, t), QPointF(right, b)).intersected(
                self.scene_rect
            )

        self.update()

    def mouseReleaseEvent(self, event):
        self.drag_mode = None
