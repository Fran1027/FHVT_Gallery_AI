import math
from PyQt6.QtWidgets import QListView, QStyledItemDelegate, QStyle, QSizePolicy
from PyQt6.QtGui import QPixmap, QColor, QFont, QPainter, QFontMetrics
from PyQt6.QtCore import Qt, QSize, QRect, QAbstractListModel, QModelIndex, pyqtSignal

class ImageModel(QAbstractListModel):
    """Modelo de alto rendimiento para miles de imágenes."""
    def __init__(self, images=None):
        super().__init__()
        self.images = images or []

    def rowCount(self, parent=QModelIndex()):
        return len(self.images)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.images):
            return None
        img_data = self.images[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return img_data['file']
        elif role == Qt.ItemDataRole.DecorationRole:
            return img_data['pixmap']
        elif role == Qt.ItemDataRole.UserRole:
            return img_data
        elif role == Qt.ItemDataRole.ToolTipRole:
            size_mb = img_data['size'] / (1024*1024)
            return f"{img_data['file']}\n{img_data['width']}x{img_data['height']} - {size_mb:.1f} MB"
        return None


    def set_images(self, images):
        """Carga masiva ultra rápida."""
        self.beginResetModel()
        self.images = list(images)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self.images = []
        self.endResetModel()

class ImageDelegate(QStyledItemDelegate):
    """Renderizador optimizado (O(1)) que evita escalados en tiempo real."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thumb_size = 140
        self.padding = 10

    def sizeHint(self, option, index):
        return QSize(self.thumb_size + self.padding * 2, self.thumb_size + 40)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect
        is_selected = option.state & QStyle.StateFlag.State_Selected
        is_hover = option.state & QStyle.StateFlag.State_MouseOver
        
        if is_selected:
            bg_color = QColor("#007acc")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 8, 8)
        elif is_hover:
            bg_color = QColor("#2a2d2e")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 8, 8)
            
        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            target_rect = QRect(rect.x() + self.padding, rect.y() + self.padding, self.thumb_size, self.thumb_size)
            
            # DIBUJADO DIRECTO: El pixmap ya viene escalado desde el Thread
            px = target_rect.x() + (target_rect.width() - pixmap.width()) // 2
            py = target_rect.y() + (target_rect.height() - pixmap.height()) // 2
            
            painter.setBrush(QColor(0, 0, 0, 100))
            painter.drawRoundedRect(px+2, py+2, pixmap.width(), pixmap.height(), 4, 4)
            painter.drawPixmap(px, py, pixmap)
            
        text = index.data(Qt.ItemDataRole.DisplayRole)
        painter.setPen(QColor("#ffffff") if is_selected else QColor("#cccccc"))
        painter.setFont(QFont("Segoe UI", 9))
        text_rect = QRect(rect.x() + self.padding, rect.y() + self.thumb_size + self.padding + 5, self.thumb_size, 20)
        elided_text = QFontMetrics(painter.font()).elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, elided_text)
        painter.restore()

class GroupListWidget(QListView):
    """Vista de lista optimizada con cálculo de altura matemático O(1)."""
    itemSelectionChanged = pyqtSignal()
    itemDoubleClicked = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_model = ImageModel()
        self.setModel(self.image_model)
        self.setItemDelegate(ImageDelegate(self))
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setSpacing(10)
        self.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
        self.setUniformItemSizes(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setFrameShape(QListView.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.selectionModel().selectionChanged.connect(lambda: self.itemSelectionChanged.emit())
        self.doubleClicked.connect(self.itemDoubleClicked.emit)


    def clear(self):
        self.image_model.clear()
        self.update_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_height()

    def update_height(self):
        """Cálculo matemático ultra-rápido de altura sin forzar layouts."""
        items_count = self.image_model.rowCount()
        if items_count == 0:
            self.setFixedHeight(0)
            return
            
        delegate = self.itemDelegate()
        item_size = delegate.sizeHint(None, None)
        item_w = item_size.width()
        item_h = item_size.height()
        
        viewport_w = self.viewport().width()
        if viewport_w <= 0: viewport_w = self.width()
            
        # Cuántas columnas caben
        columns = max(1, viewport_w // (item_w + self.spacing()))
        # Filas necesarias
        rows = math.ceil(items_count / columns)
        
        # Altura = (Filas * Alto) + Espaciados + Margen
        total_h = (rows * item_h) + (rows * self.spacing()) + 15
        self.setFixedHeight(int(total_h))
