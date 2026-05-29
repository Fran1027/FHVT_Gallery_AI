from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QProgressBar, 
                             QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QSizePolicy, QSlider, QPushButton)
from PyQt6.QtGui import QPixmap, QFont, QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import Qt, QSize, QRect, QRectF, QPoint, QPointF, pyqtSignal

class ModernMediaSlider(QSlider):
    """Un slider con estética de reproductor multimedia profesional."""
    def __init__(self, tooltip, callback, v_min=-100, v_max=100, is_ia=False):
        super().__init__(Qt.Orientation.Vertical)
        self.setRange(v_min, v_max)
        self.setValue(0)
        self.setToolTip(tooltip)
        self.valueChanged.connect(callback)
        self.setFixedWidth(40)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Colores dinámicos
        self.accent_color = QColor("#00FF41") if not is_ia else QColor("#BD00FF") # IA usa Púrpura Neón
        self.bg_color = QColor(20, 20, 20, 230)
        self.handle_color = QColor(240, 240, 240)
        self.is_hovered = False

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin = 10
        draw_height = self.height() - (margin * 2)

        groove_rect = QRect(14, margin, 12, draw_height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.bg_color)
        painter.drawRoundedRect(groove_rect, 6, 6)

        val_range = self.maximum() - self.minimum()
        if val_range == 0: val_range = 1
        val_perc = (self.value() - self.minimum()) / val_range
        handle_y = int(groove_rect.bottom() - (val_perc * draw_height))

        progress_rect = QRect(14, handle_y, 12, groove_rect.bottom() - handle_y)
        painter.setBrush(self.accent_color)
        painter.drawRoundedRect(progress_rect, 6, 6)

        if self.is_hovered:
            painter.setBrush(QColor(255, 255, 255, 40))
            painter.drawEllipse(QPoint(20, handle_y), 14, 14)

        painter.setBrush(self.handle_color)
        painter.setPen(QPen(QColor(0,0,0,50), 1))
        painter.drawEllipse(QPoint(20, handle_y), 9, 9)

        if self.accent_color == QColor("#BD00FF"):
            painter.setBrush(Qt.GlobalColor.white)
            painter.drawEllipse(QPoint(20, handle_y), 3, 3)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Calcular la posición proporcional del clic dentro del área útil del slider
            margin = 10
            draw_height = self.height() - (margin * 2)
            if draw_height > 0:
                # Invertimos el eje Y porque los sliders verticales de Qt van de abajo hacia arriba
                click_y = event.pos().y() - margin
                val_perc = (draw_height - click_y) / draw_height
                val_perc = max(0.0, min(1.0, val_perc))
                
                new_value = int(self.minimum() + (val_perc * (self.maximum() - self.minimum())))
                self.setValue(new_value)
                event.accept()
        super().mousePressEvent(event)

class CroppedPixmapItem(QGraphicsPixmapItem):
    """Renderiza solo una porción del pixmap (para sliders de comparación)."""
    def __init__(self, pixmap=None):
        super().__init__(pixmap)
        self.crop_percent = 0.5
        
        # Pluma para la sombra/borde de la línea (Negro semitransparente, más grueso)
        self.bg_pen = QPen(QColor(0, 0, 0, 180), 5)
        self.bg_pen.setCosmetic(True)
        
        # Pluma principal (Blanco puro, centro)
        self.split_line_pen = QPen(QColor(255, 255, 255, 255), 2)
        self.split_line_pen.setCosmetic(True)
    
    def setCropPercent(self, percent):
        self.crop_percent = percent
        self.update()

    def paint(self, painter, option, widget=None):
        if not self.pixmap() or self.pixmap().isNull():
            return
        w = self.pixmap().width()
        h = self.pixmap().height()
        crop_w = w * self.crop_percent
        
        if crop_w > 0:
            source_rect = QRectF(0, 0, crop_w, h)
            painter.drawPixmap(source_rect, self.pixmap(), source_rect)
        
        # Primero dibujamos una línea gruesa oscura como borde/sombra
        painter.setPen(self.bg_pen)
        painter.drawLine(int(crop_w), 0, int(crop_w), int(h))
        
        # Luego dibujamos la línea blanca en el centro
        painter.setPen(self.split_line_pen)
        painter.drawLine(int(crop_w), 0, int(crop_w), int(h))

class ZoomableViewer(QGraphicsView):
    cancelClicked = pyqtSignal()
    cropRequested = pyqtSignal(QRectF)
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setStyleSheet("background-color: #1e1e1e; border: none;")
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        
        self.zoom_factor = 1.0
        self.base_pixmap = None
        
        self.in_comparison_mode = False
        self.is_dragging_split = False
        self._is_fitting = False
        self.crop_mode = False
        
        self.checkerboard_item = QGraphicsPixmapItem()
        self.checkerboard_item.setZValue(-1)
        self.scene.addItem(self.checkerboard_item)

        self.overlay_widget = QWidget(self)
        self.overlay_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        overlay_layout = QVBoxLayout(self.overlay_widget)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.setSpacing(15)

        self.icon_label = QLabel("\uE9F5") 
        self.icon_label.setFont(QFont("Segoe MDL2 Assets", 48))
        self.icon_label.setStyleSheet("color: #4a4a4a; background: transparent;")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel("Vista Previa")
        self.title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #6e6e6e; background: transparent;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("Selecciona una imagen")
        self.status_label.setStyleSheet("font-size: 14px; color: #5c5c5c; background: transparent;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedSize(300, 6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background-color: #2d2d2d; border: none; border-radius: 3px; }
            QProgressBar::chunk { background-color: #007acc; border-radius: 3px; }
        """)
        self.progress_bar.hide()

        self.btn_cancel = QPushButton("CANCELAR PROCESO")
        self.btn_cancel.setFixedSize(200, 35)
        self.btn_cancel.setStyleSheet("""
            QPushButton { background-color: rgba(255, 59, 59, 0.1); color: #ff3b3b; border: 1px solid #ff3b3b; border-radius: 6px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background-color: #ff3b3b; color: white; }
        """)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.cancelClicked.emit)
        self.btn_cancel.hide()

        overlay_layout.addStretch()
        overlay_layout.addWidget(self.icon_label)
        overlay_layout.addWidget(self.title_label)
        overlay_layout.addWidget(self.status_label)
        overlay_layout.addWidget(self.progress_bar)
        overlay_layout.addWidget(self.btn_cancel, 0, Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addStretch()

    def setPixmap(self, pixmap):
        self.in_comparison_mode = False
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        if hasattr(self, 'ai_pixmap_item') and self.ai_pixmap_item.scene():
            self.scene.removeItem(self.ai_pixmap_item)
            del self.ai_pixmap_item
            
        self.overlay_widget.hide()
        self.base_pixmap = pixmap
        if not pixmap or pixmap.isNull():
            self.pixmap_item.setPixmap(QPixmap())
            self.checkerboard_item.setVisible(False)
            self.overlay_widget.show()
            return
            
        self.pixmap_item.setPixmap(pixmap)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self._rebuild_checkerboard(pixmap.width(), pixmap.height())
        self.checkerboard_item.setPos(self.pixmap_item.pos())
        self.fit_or_center()
        self.zoom_factor = 1.0

    def setComparisonMode(self, pixmap_original, pixmap_ai):
        """Activa el modo de slider (Before/After)"""
        self.setPixmap(pixmap_original)
        self.in_comparison_mode = True
        self.setDragMode(QGraphicsView.DragMode.NoDrag) # Desactivar pan automático para controlar el slider
        
        self.ai_pixmap_item = CroppedPixmapItem(pixmap_ai)
        self.ai_pixmap_item.setPos(self.pixmap_item.pos())
        self.scene.addItem(self.ai_pixmap_item)
        self.ai_pixmap_item.setCropPercent(0.5)

    def set_crop_mode(self, enabled):
        self.crop_mode = enabled
        if enabled:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.ArrowCursor)
            from editor.canvas_items import CropOverlayItem
            self.crop_overlay = CropOverlayItem(self.pixmap_item.sceneBoundingRect())
            self.scene.addItem(self.crop_overlay)
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if hasattr(self, 'crop_overlay') and self.crop_overlay:
                self.scene.removeItem(self.crop_overlay)
                self.crop_overlay = None

    def apply_crop(self):
        if hasattr(self, 'crop_overlay') and self.crop_overlay:
            if hasattr(self, 'cropRequested'):
                self.cropRequested.emit(self.crop_overlay.crop_rect)

    def mousePressEvent(self, event):
        if getattr(self, 'crop_mode', False):
            # CropOverlayItem maneja sus propios eventos de mouse,
            # pero propagamos para que funcionen
            super().mousePressEvent(event)
            return
            
        if self.in_comparison_mode:
            scene_pos = self.mapToScene(event.pos())
            item_pos = self.pixmap_item.mapFromScene(scene_pos)
            w = self.base_pixmap.width()
            current_split_x = w * self.ai_pixmap_item.crop_percent
            
            # Convert to view coordinates to check tolerance
            view_split_pos = self.mapFromScene(self.pixmap_item.mapToScene(QPointF(current_split_x, 0)))
            if abs(event.pos().x() - view_split_pos.x()) < 30: # Tolerancia en píxeles de pantalla
                self.is_dragging_split = True
                self.setCursor(Qt.CursorShape.SplitHCursor)
                return
            else:
                # Si hizo clic fuera, permitir pan
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, 'crop_mode', False):
            super().mouseMoveEvent(event)
            return
            
        if self.in_comparison_mode and self.is_dragging_split:
            scene_pos = self.mapToScene(event.pos())
            item_pos = self.pixmap_item.mapFromScene(scene_pos)
            w = self.base_pixmap.width()
            percent = item_pos.x() / w
            percent = max(0.0, min(1.0, percent))
            self.ai_pixmap_item.setCropPercent(percent)
            return
            
        if self.in_comparison_mode and not self.is_dragging_split:
            # Hover cursor update
            scene_pos = self.mapToScene(event.pos())
            item_pos = self.pixmap_item.mapFromScene(scene_pos)
            if self.base_pixmap:
                current_split_x = self.base_pixmap.width() * self.ai_pixmap_item.crop_percent
                view_split_pos = self.mapFromScene(self.pixmap_item.mapToScene(QPointF(current_split_x, 0)))
                if abs(event.pos().x() - view_split_pos.x()) < 30:
                    self.setCursor(Qt.CursorShape.SplitHCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
                    
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if getattr(self, 'crop_mode', False):
            super().mouseReleaseEvent(event)
            return
            
        if self.in_comparison_mode and self.is_dragging_split:
            self.is_dragging_split = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if getattr(self, 'crop_mode', False) and event.button() == Qt.MouseButton.LeftButton:
            self.apply_crop()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _rebuild_checkerboard(self, w, h):
        # 1. Crear el patrón base pequeñito (32x32)
        pattern = QPixmap(32, 32)
        pattern.fill(Qt.GlobalColor.white)
        p = QPainter(pattern)
        p.fillRect(0, 0, 16, 16, QColor("#e0e0e0"))
        p.fillRect(16, 16, 16, 16, QColor("#e0e0e0"))
        p.end()

        # 2. Rellenar todo el fondo de un solo golpe usando el Brush
        cb = QPixmap(int(w), int(h))
        p2 = QPainter(cb)
        p2.fillRect(0, 0, int(w), int(h), QBrush(pattern))
        p2.end()

        self.checkerboard_item.setPixmap(cb)
        self.checkerboard_item.setVisible(True)

    def fit_or_center(self):
        if self._is_fitting or not self.base_pixmap or self.base_pixmap.isNull():
            return
        self._is_fitting = True
        try:
            self.resetTransform()
            img_size = self.base_pixmap.size()
            view_size = self.viewport().size()
            if img_size.width() > view_size.width() or img_size.height() > view_size.height():
                self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        finally:
            self._is_fitting = False

    def setText(self, text):
        if hasattr(self, 'ai_movie') and self.ai_movie is not None:
            self.ai_movie.stop()
        self.icon_label.setMovie(None)
        
        self.pixmap_item.setPixmap(QPixmap())
        self.checkerboard_item.setVisible(False)
        self.overlay_widget.show()
        icon = "\uE114"
        title = "Vista Previa"
        if "Cargando" in text:
            icon = "\uE895"; title = "Procesando..."
        elif "Error" in text:
            icon = "\uEA39"; title = "Error"
        elif "No se encontraron" in text:
            icon = "\uE1A5"; title = "Carpeta Vacía"
        self.icon_label.setText(icon)
        self.title_label.setText(title)
        self.status_label.setText(text)

    def show_ai_processing(self, show, text="Procesando con IA..."):
        from PyQt6.QtGui import QMovie
        import os
        
        if show:
            self.overlay_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            self.overlay_widget.show()
            
            # Cargar GIF animado si existe en assets
            from core.utils import get_base_path
            gif_path = os.path.join(get_base_path(), "assets", "loader.gif")
            if os.path.exists(gif_path):
                if not hasattr(self, 'ai_movie') or self.ai_movie is None:
                    self.ai_movie = QMovie(gif_path)
                self.icon_label.setMovie(self.ai_movie)
                self.ai_movie.start()
            else:
                self.icon_label.setMovie(None)
                self.icon_label.setText("\uE99A") # Gears icon instead of Info icon
                
            self.title_label.setText("IA Procesando...")
            self.status_label.setText(text)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.show()
            self.btn_cancel.show()
        else:
            if hasattr(self, 'ai_movie') and self.ai_movie is not None:
                self.ai_movie.stop()
            self.icon_label.setMovie(None)
            self.overlay_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.overlay_widget.hide()
            self.progress_bar.hide()
            self.btn_cancel.hide()
        
    def setProgress(self, value, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(value)
        if value < total: self.progress_bar.show()
        else: self.progress_bar.hide()

    def wheelEvent(self, event):
        if not self.base_pixmap or self.base_pixmap.isNull(): return
        zoom_in_factor = 1.15
        zoom_out_factor = 1.0 / zoom_in_factor
        
        # 1. Calcular el factor tentativo
        factor = zoom_in_factor if event.angleDelta().y() > 0 else zoom_out_factor
        new_zoom = self.zoom_factor * factor
        
        # 2. Clampear de forma estricta entre 0.5 (50%) y 40.0 (4000%)
        if new_zoom < 0.5:
            new_zoom = 0.5
        elif new_zoom > 40.0:
            new_zoom = 40.0
            
        # 3. Calcular el ratio relativo real respecto al estado actual
        ratio = new_zoom / self.zoom_factor
        self.zoom_factor = new_zoom
        
        # 4. Aplicar la transformación de un solo golpe
        self.scale(ratio, ratio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.overlay_widget.resize(self.size())
        if self.base_pixmap and not self.base_pixmap.isNull():
            if self.zoom_factor == 1.0: self.fit_or_center()

class FullScreenViewer(ZoomableViewer):
    def __init__(self, file_path):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: black; border: none;")
        pix = QPixmap(file_path)
        if not pix.isNull(): self.setPixmap(pix)
        self.showFullScreen()
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self.close()
        else: super().keyPressEvent(event)
