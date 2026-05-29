import os
from types import SimpleNamespace
from enum import Enum, auto

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                             QPushButton, QLineEdit, QFileDialog, QDialog, 
                             QLabel, QMessageBox, QColorDialog, QScrollArea, QGridLayout, QSpinBox, QComboBox)
from PyQt6.QtGui import QPixmap, QFont, QImage, QPainter, QColor, QUndoStack
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal

from qfluentwidgets import Flyout

from core.threads import AIWorker, PaletteWorker
from core.generative import GenerativeAIWorker

from studio_logger import log_action, logger

from editor.commands import EditorCommand
from core.hardware import check_cuda_support
from core.processing import apply_image_transformations
from core.utils import excede_limite_megapixeles
from ui.panels.canvas_panel import CanvasToolsPanel
from ui.panels.palette_panel import PaletteToolsPanel

class SwatchFrame(QFrame):
    clicked = pyqtSignal()
    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event) # Permite que el QLineEdit hijo reciba clics

class BatchResultDialog(QDialog):
    def __init__(self, qimages, parent=None):
        super().__init__(parent)
        self.qimages = qimages
        self.current_index = 0
        self.setWindowTitle("Resultados del Lote (Carrusel)")
        self.setFixedSize(850, 700)
        self.setStyleSheet("""
            QDialog { background-color: #050505; color: white; }
            QLabel { font-family: 'Segoe UI'; font-size: 14px;}
            QPushButton { background-color: #1a1a1a; color: white; border: 1px solid #333; border-radius: 6px; padding: 8px 16px; font-weight: bold; }
            QPushButton:hover:enabled { background-color: #333; }
            QPushButton:disabled { color: #555; border-color: #222; }
            QPushButton#SaveBtn { background-color: #28a745; color: white; border: none; }
            QPushButton#SaveBtn:hover:enabled { background-color: #2fc353; }
            QPushButton#ExecuteBtn { background-color: #007acc; color: white; border: none; }
            QPushButton#ExecuteBtn:hover:enabled { background-color: #0098ff; }
            QPushButton#CancelBtn { background-color: transparent; color: #aaa; border: 1px solid #444; }
            QPushButton#CancelBtn:hover { background-color: #222; color: white; }
            QPushButton#NavBtn { background-color: #222; border-radius: 25px; font-size: 20px; }
            QPushButton#NavBtn:hover:enabled { background-color: #444; }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Image Display Area
        image_layout = QHBoxLayout()
        
        self.btn_prev = QPushButton("◄")
        self.btn_prev.setObjectName("NavBtn")
        self.btn_prev.setFixedSize(50, 50)
        self.btn_prev.clicked.connect(self._prev_image)
        
        self.viewer = ZoomableViewer()
        self.viewer.setMinimumSize(500, 500)
        
        self.btn_next = QPushButton("►")
        self.btn_next.setObjectName("NavBtn")
        self.btn_next.setFixedSize(50, 50)
        self.btn_next.clicked.connect(self._next_image)
        
        image_layout.addWidget(self.btn_prev)
        image_layout.addWidget(self.viewer, stretch=1)
        image_layout.addWidget(self.btn_next)
        
        main_layout.addLayout(image_layout, stretch=1)
        
        # Bottom Controls
        bottom_layout = QHBoxLayout()
        
        self.lbl_counter = QLabel()
        self.lbl_counter.setStyleSheet("color: #aaa; font-weight: bold;")
        bottom_layout.addWidget(self.lbl_counter)
        
        bottom_layout.addStretch()
        
        btn_cancel = QPushButton("Cerrar")
        btn_cancel.setObjectName("CancelBtn")
        btn_cancel.clicked.connect(self.reject)
        
        self.btn_save = QPushButton("💾 Guardar a Disco")
        self.btn_save.setObjectName("SaveBtn")
        self.btn_save.clicked.connect(self._save_current)
        
        self.btn_exec = QPushButton("✅ Aplicar al Editor")
        self.btn_exec.setObjectName("ExecuteBtn")
        self.btn_exec.clicked.connect(self.accept)
        
        bottom_layout.addWidget(btn_cancel)
        bottom_layout.addWidget(self.btn_save)
        bottom_layout.addWidget(self.btn_exec)
        
        main_layout.addLayout(bottom_layout)
        self._update_ui()
        
    def _prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._update_ui()
            
    def _next_image(self):
        if self.current_index < len(self.qimages) - 1:
            self.current_index += 1
            self._update_ui()

    def _update_ui(self):
        if not hasattr(self, 'lbl_counter') or not self.qimages:
            return
        self.btn_prev.setEnabled(self.current_index > 0)
        self.btn_next.setEnabled(self.current_index < len(self.qimages) - 1)
        self.lbl_counter.setText(f"Variación {self.current_index + 1} de {len(self.qimages)}")
        
        qimg = self.qimages[self.current_index]
        pix = QPixmap.fromImage(qimg)
        self.viewer.setPixmap(pix)
        
    def _save_current(self):
        parent_tab = self.parent()
        default_path = "variacion.png"
        if parent_tab and hasattr(parent_tab, 'file_path'):
            base, ext = os.path.splitext(parent_tab.file_path)
            default_path = f"{base}_var{self.current_index + 1}.png"
            
        file_path, _ = QFileDialog.getSaveFileName(self, "Guardar Variación", default_path, "PNG (*.png);;JPEG (*.jpg);;WEBP (*.webp)")
        if file_path:
            if self.qimages[self.current_index].save(file_path):
                QMessageBox.information(self, "Guardado", f"Imagen guardada con éxito en:\n{file_path}")
            else:
                QMessageBox.critical(self, "Error", "No se pudo guardar la imagen.")

from ui.widgets import ZoomableViewer, ModernMediaSlider, FullScreenViewer
from editor.canvas_items import ColorMarker
from tools.factory import make_btn, make_icon_btn
from tools.mirror_tool import MirrorTool
from tools.ai_tool import AIAdvancedDialog
from tools.generative_tool import GenerativeDialog

# ==============================================================================
# --- ENUMERACIONES Y ESTADOS ---
# ==============================================================================
class EditorState(Enum):
    MAIN = auto()
    EDIT_ROOT = auto()
    EDIT_MIRROR = auto()
    EDIT_ROTATE = auto()
    EDIT_CROP = auto()
    EDIT_CANVAS = auto()
    EDIT_CANVAS_ACTIVE = auto()
    EDIT_PALETTE = auto()
    EDIT_ADJUST = auto()
    EDIT_SAVE = auto()
    EDIT_AI = auto()

# ==============================================================================
# --- CLASE PRINCIPAL: IMAGE TAB ---
# ==============================================================================
class ImageTab(QWidget):
    imageUpdated = pyqtSignal()
    
    STYLE_DEFAULT = "QPushButton { background: transparent; border: 1px solid #fff; border-radius: 6px; color: #ccc; } QPushButton:disabled { color: #444; border-color: #2a2a2a; } QPushButton:hover:enabled { background: rgba(255,255,255,0.1); }"
    STYLE_ACTIVE = "QPushButton { background: #007acc; border: 1px solid #007acc; border-radius: 6px; color: white; } QPushButton:disabled { background: #1a1a1a; color: #444; border-color: #2a2a2a; }"

    # --- INICIALIZACIÓN ---
    def __init__(self, file_path):
        super().__init__()
        self.setMinimumSize(900, 600)
        self.file_path = file_path
        self.active_flyout = None
        self.angle = 0
        self.flip_h = False
        self.flip_v = False
        self.canvas_bg_color = Qt.GlobalColor.white
        self.original_pixmap = QPixmap(file_path)
        self.brightness = 1.0
        self.contrast = 1.0
        self.canvas_L = 0
        self.canvas_T = 0
        self.canvas_R = 0
        self.canvas_B = 0
        
        # --- INICIALIZAR QUndoStack ---
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(20)
        self.undo_stack.canUndoChanged.connect(self.update_menu_state)
        self.undo_stack.canRedoChanged.connect(self.update_menu_state)
        # ------------------------------
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar
        self.toolbar_container = QWidget()
        self.toolbar_container.setObjectName("toolbar_container")
        self.toolbar_container.setStyleSheet("""
            QWidget#toolbar_container {
                background-color: rgba(20, 20, 20, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 10px;
                margin: 5px 10px;
            }
        """)
        self.toolbar_layout = QHBoxLayout(self.toolbar_container)
        self.toolbar_layout.setContentsMargins(10, 5, 10, 5)
        self.toolbar_layout.setSpacing(6)
        
        icon_font = QFont("Segoe MDL2 Assets", 14)
        self.btn_fullscreen = make_btn("\uE740", "Pantalla Completa", icon_font, self.open_fullscreen)
        self.btn_edit       = make_icon_btn("edit-image.png", "Editar Imagen", callback=self.toggle_edit_mode)
        self.btn_mirror     = make_icon_btn("flip.png", "Opciones de Espejo", callback=self.toggle_mirror)
        self.btn_rotate     = make_btn("\uE7AD", "Opciones de Giro", icon_font, self.toggle_rotate)
        self.btn_crop       = make_btn("\uE7A8", "Recortar Imagen", icon_font, self.toggle_crop)
        self.btn_canvas     = make_icon_btn("expand.png", "Ampliar Lienzo", callback=self.toggle_canvas)
        self.btn_adjust     = make_btn("\uE706", "Brillo y Contraste", icon_font, self.toggle_adjust)
        self.btn_palette    = make_btn("\uE790", "Extraer Paleta", icon_font, self.toggle_palette)
        self.btn_ai         = make_icon_btn("artificial-intelligence.png", "Herramientas de IA", callback=self.toggle_ai)
        self.btn_generative = make_btn("\uE7B5", "Estilo IA", icon_font, self.toggle_generative)
        self.btn_undo       = make_btn("\uE81C", "Deshacer Paso (Undo)", icon_font, self.undo_stack.undo)
        self.btn_redo       = make_btn("\uE81D", "Rehacer Paso (Redo)", icon_font, self.undo_stack.redo)
        self.btn_cancel     = make_btn("\uE711", "Cancelar Todo", icon_font, self.cancel_edits_prompt)
        self.btn_save       = make_btn("\uE74E", "Guardar Imagen", icon_font, self.save_overwrite)
        self.btn_save.setVisible(False)
        
        # Definir grupos lógicos una sola vez
        self.toolbar_btns = [self.btn_fullscreen, self.btn_edit, self.btn_mirror, self.btn_rotate, self.btn_crop, self.btn_canvas, self.btn_adjust, self.btn_palette, self.btn_ai, self.btn_generative, self.btn_undo, self.btn_redo, self.btn_cancel, self.btn_save]
        self.edit_mode_btns = [self.btn_mirror, self.btn_rotate, self.btn_crop, self.btn_canvas, self.btn_adjust, self.btn_palette, self.btn_ai, self.btn_generative, self.btn_save, self.btn_redo]
        
        for b in self.toolbar_btns: self.toolbar_layout.addWidget(b)
        self.toolbar_layout.addStretch()
        layout.addWidget(self.toolbar_container)
        
        # Adjust Panel
        self.adjust_panel = QFrame()
        self.adjust_panel.setFixedWidth(85)
        self.adjust_panel.setStyleSheet("background-color: #1e1e1e; border: none;")
        self.adjust_panel.setVisible(False)
        self.adjust_content_layout = QVBoxLayout(self.adjust_panel)
        self.adjust_content_layout.setContentsMargins(10, 20, 35, 20)
        configs = [
            ("\uE706", "\uE708", "Ajustar Brillo", self._on_adjust_changed, 0, 200),
            ("\uE793", "\uE990", "Ajustar Contraste", self._on_adjust_changed, 0, 200),
            ("\uE7AD", "\uE7A7", "Giro Libre", self.on_free_rotate_changed, -180, 180)
        ]
        (self.br_container, self.slider_brightness), (self.ct_container, self.slider_contrast), (self.rt_container, self.slider_rotate) = [self.create_slider_capsule(*c) for c in configs]
        for c in (self.br_container, self.ct_container, self.rt_container): self.adjust_content_layout.addWidget(c, 1)
        
        # --- ESTRUCTURA CENTRAL CON BOTONES FLOTANTES ---
        self.central_container = QWidget()
        self.central_layout = QHBoxLayout(self.central_container) # VOLVEMOS A HORIZONTAL
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.setSpacing(0)

        # Contenedor para el Visor y los elementos superpuestos (STACK)
        self.viewer_stack = QWidget()
        self.stack_layout = QGridLayout(self.viewer_stack) 
        self.stack_layout.setContentsMargins(0, 0, 0, 0)

        # 1. El Visor (al fondo)
        self.viewer = ZoomableViewer()
        self.viewer.cancelClicked.connect(self._cancel_ai_worker)
        self.viewer.cropRequested.connect(self._on_crop_requested)
        self.ai_worker = None
        self.stack_layout.addWidget(self.viewer, 0, 0)

        # 2. El Panel de Botones Flotante (arriba a la izquierda)
        self.side_palette_panel = PaletteToolsPanel(self)

        # --- NUEVO: 3. Panel Flotante para el Lienzo ---
        self.side_canvas_panel = CanvasToolsPanel(self)

        # Layout superpuesto: Añadimos ambos paneles.
        self.overlay_layout = QHBoxLayout()
        self.overlay_layout.setContentsMargins(15, 15, 0, 0)
        self.overlay_layout.addWidget(self.side_palette_panel, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.overlay_layout.addWidget(self.side_canvas_panel, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.overlay_layout.addStretch()

        self.stack_layout.addLayout(self.overlay_layout, 0, 0)
        
        # --- NUEVO: 4. Panel Confirmación IA ---
        self.ai_confirm_panel = QFrame(self.viewer_stack)
        self.ai_confirm_panel.setObjectName("FloatingAIConfirm")
        self.ai_confirm_panel.setStyleSheet("""
            QFrame#FloatingAIConfirm {
                background-color: rgba(20, 20, 20, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 20px;
            }
        """)
        self.ai_confirm_panel.setVisible(False)
        self.ai_confirm_layout = QHBoxLayout(self.ai_confirm_panel)
        self.ai_confirm_layout.setContentsMargins(15, 10, 15, 10)
        self.ai_confirm_layout.setSpacing(15)
        
        self.btn_ai_save = QPushButton("💾  Guardar Resultado")
        self.btn_ai_save.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.btn_ai_save.setStyleSheet("background-color: #007acc; color: white; border-radius: 5px; padding: 8px 15px;")
        
        self.btn_ai_discard = QPushButton("❌  Descartar")
        self.btn_ai_discard.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.btn_ai_discard.setStyleSheet("background-color: #d83b01; color: white; border-radius: 5px; padding: 8px 15px;")
        
        self.ai_confirm_layout.addWidget(self.btn_ai_save)
        self.ai_confirm_layout.addWidget(self.btn_ai_discard)
        
        self.btn_ai_save.clicked.connect(self._save_ai_result)
        self.btn_ai_discard.clicked.connect(self._discard_ai_result)

        self.stack_layout.addWidget(self.ai_confirm_panel, 0, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)

        # --- NUEVO: 5. Panel Confirmación Crop ---
        self.crop_confirm_panel = QFrame(self.viewer_stack)
        self.crop_confirm_panel.setObjectName("FloatingCropConfirm")
        self.crop_confirm_panel.setStyleSheet("""
            QFrame#FloatingCropConfirm {
                background-color: rgba(20, 20, 20, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 20px;
            }
        """)
        self.crop_confirm_panel.setVisible(False)
        self.crop_confirm_layout = QHBoxLayout(self.crop_confirm_panel)
        self.crop_confirm_layout.setContentsMargins(15, 10, 15, 10)
        self.crop_confirm_layout.setSpacing(15)
        
        self.btn_crop_apply = QPushButton("✅  Aplicar Recorte")
        self.btn_crop_apply.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.btn_crop_apply.setStyleSheet("background-color: #007acc; color: white; border-radius: 5px; padding: 8px 15px;")
        
        self.btn_crop_cancel = QPushButton("❌  Cancelar")
        self.btn_crop_cancel.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.btn_crop_cancel.setStyleSheet("background-color: #d83b01; color: white; border-radius: 5px; padding: 8px 15px;")
        
        self.crop_confirm_layout.addWidget(self.btn_crop_apply)
        self.crop_confirm_layout.addWidget(self.btn_crop_cancel)
        
        self.btn_crop_apply.clicked.connect(self.viewer.apply_crop)
        self.btn_crop_cancel.clicked.connect(self.toggle_crop)

        self.stack_layout.addWidget(self.crop_confirm_panel, 0, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)

        
        # Ensamblaje final
        self.central_layout.addWidget(self.viewer_stack, 1)
        self.central_layout.addWidget(self.adjust_panel)
        
        # --- VIEWER V CONTAINER (Visor + Paleta Inferior) ---
        self.viewer_v_container = QWidget()
        self.viewer_v_layout = QVBoxLayout(self.viewer_v_container)
        self.viewer_v_layout.setContentsMargins(0, 0, 0, 0)
        self.viewer_v_layout.setSpacing(0)
        self.viewer_v_layout.addWidget(self.central_container, 1)
        
        self.palette_bar = QFrame()
        self.palette_bar.setFixedHeight(80)
        self.palette_bar.setStyleSheet("background-color: #0d0d0d; border-top: 1px solid #222;")
        self.palette_bar.setVisible(False)
        palette_main_layout = QHBoxLayout(self.palette_bar)
        # Contenedor de Paleta con SCROLL (Para no aplastar el botón de exportar)
        self.palette_scroll = QScrollArea()
        self.palette_scroll.setWidgetResizable(True)
        self.palette_scroll.setFixedHeight(65)
        self.palette_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.palette_scroll.setStyleSheet("background: transparent;")
        
        self.palette_scroll_content = QWidget()
        self.palette_layout = QHBoxLayout(self.palette_scroll_content)
        self.palette_layout.setContentsMargins(5, 5, 5, 5)
        self.palette_layout.setSpacing(10)
        self.palette_scroll.setWidget(self.palette_scroll_content)
        
        palette_main_layout.addWidget(self.palette_scroll, 1)
        self.btn_export_palette = make_btn("\uE72D", "Exportar Paleta", icon_font, self.export_palette_image)
        self.btn_export_palette.setFixedWidth(160)
        palette_main_layout.addWidget(self.btn_export_palette)
        self.viewer_v_layout.addWidget(self.palette_bar)
        layout.addWidget(self.viewer_v_container, 1)
        
        self.palette_markers = []
        self.palette_mode = "color"
        self.set_state(EditorState.MAIN)
        self._sync_ui_to_state()
        self.update_image()

    # --- FACTORÍAS DE UI ---
    def create_slider_capsule(self, icon_top, icon_bottom, tooltip, callback, v_min, v_max):
        container = QWidget(); container.setFixedWidth(50)
        container.setMinimumHeight(150)
        main_layout = QVBoxLayout(container); main_layout.setContentsMargins(0, 0, 0, 0)
        field = QFrame(); field.setStyleSheet("QFrame { background-color: #0a0a0a; border: 1px solid #FFFFFF; border-radius: 20px; }")
        field_layout = QVBoxLayout(field); field_layout.setContentsMargins(0, 15, 0, 15)
        
        lbl_top = QLabel(icon_top); lbl_top.setFont(QFont("Segoe MDL2 Assets", 12)); lbl_top.setAlignment(Qt.AlignmentFlag.AlignCenter); lbl_top.setStyleSheet("color: #888;")
        slider = ModernMediaSlider(tooltip, callback, v_min, v_max, is_ia=("IA" in tooltip.upper()))
        lbl_bottom = QLabel(icon_bottom); lbl_bottom.setFont(QFont("Segoe MDL2 Assets", 12)); lbl_bottom.setAlignment(Qt.AlignmentFlag.AlignCenter); lbl_bottom.setStyleSheet("color: #888;")
        
        field_layout.addWidget(lbl_top, 0)
        field_layout.addWidget(slider, 1, Qt.AlignmentFlag.AlignHCenter)
        field_layout.addWidget(lbl_bottom, 0)
        
        btn_close = QPushButton("\u00D7"); btn_close.setFixedSize(30, 30)
        btn_close.setStyleSheet("QPushButton { background: #222; color: white; border-radius: 15px; border: 1px solid #444; }")
        

        # --- TRABAJO CON UNDO STACK ---
        slider.sliderPressed.connect(lambda t=tooltip: self._begin_edit(t))
        slider.sliderReleased.connect(self._end_edit)
        
        neutral = (v_max + v_min) // 2
        btn_close.clicked.connect(lambda: (self._begin_edit(f"Resetear {tooltip}"), slider.setValue(neutral), self._end_edit()))
        
        main_layout.addWidget(field, 1); main_layout.addWidget(btn_close, 0, Qt.AlignmentFlag.AlignCenter)
        return container, slider

    # --- GESTIÓN DE ESTADOS Y FLUJO ---
    @log_action("Actualizando Estado de la UI")
    def set_state(self, state):
        if self.active_flyout: self.active_flyout.close(); self.active_flyout = None
        self.current_state = state
        
        self.adjust_panel.setVisible(state in [EditorState.EDIT_ADJUST, EditorState.EDIT_ROTATE])
        self.palette_bar.setVisible(state == EditorState.EDIT_PALETTE)
        self.side_palette_panel.setVisible(state == EditorState.EDIT_PALETTE)
        self.side_canvas_panel.setVisible(state in [EditorState.EDIT_CANVAS, EditorState.EDIT_CANVAS_ACTIVE])
        
        if state != EditorState.EDIT_PALETTE: self._clear_palette_markers()
        for b in self.edit_mode_btns:
            b.setStyleSheet(self.STYLE_DEFAULT); b.setVisible(state != EditorState.MAIN)
            
        is_crop = (state == EditorState.EDIT_CROP)
        self.viewer.set_crop_mode(is_crop); self.viewer.setToolTip("✂ Arrastra los tiradores o el área para seleccionar. Doble clic para aplicar." if is_crop else "")
        if hasattr(self, 'crop_confirm_panel'):
            self.crop_confirm_panel.setVisible(is_crop)
        
        if state == EditorState.MAIN:
            self.btn_edit.setStyleSheet(self.STYLE_DEFAULT)
            for b in [self.btn_undo, self.btn_redo, self.btn_cancel, self.btn_save]: b.setVisible(False)
        else:
            self.btn_edit.setStyleSheet(self.STYLE_ACTIVE)
            for b in [self.btn_undo, self.btn_redo, self.btn_cancel, self.btn_save]: b.setVisible(True)
            if state in [EditorState.EDIT_ADJUST, EditorState.EDIT_ROTATE]: self._create_proxy_pixmap()

        active_map = {
            EditorState.EDIT_ADJUST: (self.btn_adjust, [self.br_container, self.ct_container]),
            EditorState.EDIT_ROTATE: (self.btn_rotate, [self.rt_container]),
            EditorState.EDIT_CROP: (self.btn_crop, []), EditorState.EDIT_PALETTE: (self.btn_palette, []),
            EditorState.EDIT_MIRROR: (self.btn_mirror, []), EditorState.EDIT_CANVAS: (self.btn_canvas, []),
            EditorState.EDIT_AI: (self.btn_ai, []), EditorState.EDIT_SAVE: (self.btn_save, [])
        }
        if state in active_map:
            btn, show_containers = active_map[state]
            btn.setStyleSheet(self.STYLE_ACTIVE)
            if state in [EditorState.EDIT_ADJUST, EditorState.EDIT_ROTATE]:
                for c in (self.br_container, self.ct_container, self.rt_container): c.setVisible(c in show_containers)
            if state == EditorState.EDIT_PALETTE: self.extract_palette(self.palette_mode)
        self.update_menu_state()

    def _toggle_flyout_tool(self, state, tool_class, btn_widget, **tool_kwargs):
        if self.current_state == state: self.set_state(EditorState.EDIT_ROOT)
        else:
            self.set_state(state); view = tool_class(**tool_kwargs)
            if state == EditorState.EDIT_CANVAS and hasattr(view, 'update_color_icon'):
                view.update_color_icon(self.canvas_bg_color)
            f = Flyout.make(view, btn_widget, self)
            self.active_flyout = f
            style = "Flyout, FlyoutViewBase, .FlyoutView { background-color: #1a1a1a !important; border: 1px solid #333333; border-radius: 8px; } QWidget { background-color: transparent; }"
            f.setStyleSheet(style); view.setStyleSheet(style)
            f.closed.connect(lambda: self._on_flyout_closed(state))

    def _on_flyout_closed(self, state):
        if self.active_flyout: self.active_flyout = None
        # Excepción: Si cerramos el Flyout de la paleta, NO regresamos a EDIT_ROOT
        # para que la barra inferior se mantenga visible y el mouse se libere.
        if self.current_state == state and state != EditorState.EDIT_PALETTE:
            self.set_state(EditorState.EDIT_ROOT)

    def _toggle_simple_state(self, state, on_exit=None):
        if self.current_state == state:
            if on_exit: on_exit()
            self.set_state(EditorState.EDIT_ROOT)
        else: self.set_state(state)

    # --- ACCIONES DE LA BARRA DE HERRAMIENTAS ---
    def toggle_edit_mode(self): self.set_state(EditorState.EDIT_ROOT if self.current_state == EditorState.MAIN else EditorState.MAIN)
    def toggle_mirror(self): self._toggle_flyout_tool(EditorState.EDIT_MIRROR, MirrorTool, self.btn_mirror, on_flip_h=self.toggle_flip_h, on_flip_v=self.toggle_flip_v)
    def toggle_rotate(self): self._toggle_simple_state(EditorState.EDIT_ROTATE)
    def toggle_crop(self): self._toggle_simple_state(EditorState.EDIT_CROP)
    def toggle_adjust(self):
        self._toggle_simple_state(EditorState.EDIT_ADJUST)
        
    def toggle_canvas(self):
        if self.current_state in [EditorState.EDIT_CANVAS, EditorState.EDIT_CANVAS_ACTIVE]:
            self.set_state(EditorState.EDIT_ROOT)
        else:
            self.side_canvas_panel.update_btn_styles(mode="trans" if self.canvas_bg_color == Qt.GlobalColor.transparent else "color")
            self.set_state(EditorState.EDIT_CANVAS)
            
    def toggle_palette(self):
        # Ya no abrimos un Flyout, solo cambiamos el estado para mostrar los paneles laterales
        if self.current_state == EditorState.EDIT_PALETTE:
            self.set_state(EditorState.EDIT_ROOT)
        else:
            self.side_palette_panel.update_btn_styles(self.palette_mode)
            self.set_state(EditorState.EDIT_PALETTE)
    def toggle_ai(self):
        self.set_state(EditorState.EDIT_AI)
        main_win = self.window()
        if not getattr(main_win, '_cuda_prompted', False):
            if check_cuda_support():
                setattr(main_win, '_cuda_prompted', True)
                msg = (
                    "Hemos detectado que posees una tarjeta gráfica NVIDIA.\n\n"
                    "La inteligencia artificial funcionará correctamente mediante el motor universal (DirectML). "
                    "Sin embargo, si deseas obtener el MÁXIMO rendimiento exclusivo, "
                    "te recomendamos instalar el 'CUDA Toolkit' oficial de NVIDIA.\n\n"
                    "¿Deseas abrir la página oficial para descargarlo?"
                )
                from PyQt6.QtWidgets import QMessageBox
                res = QMessageBox.information(self, "Acelerador NVIDIA Detectado", msg,
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if res == QMessageBox.StandardButton.Yes:
                    import webbrowser
                    webbrowser.open("https://developer.nvidia.com/cuda-downloads")
        actions = SimpleNamespace(
            on_run_rmbg=self.run_ai_rmbg,
            on_run_upscale=self.run_ai_upscale,
            on_run_depth=self.run_ai_depth
        )
        dialog = AIAdvancedDialog(actions, self)
        dialog.exec()
        self.set_state(EditorState.EDIT_ROOT)

    def toggle_generative(self):
        self.set_state(EditorState.EDIT_AI)
        
        # Extraer a numpy array para BLIP y Generative
        safe_qimage = self.original_pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)
        import numpy as np
        ptr = safe_qimage.constBits()
        ptr.setsize(safe_qimage.sizeInBytes())
        arr = np.array(ptr).reshape(safe_qimage.height(), safe_qimage.bytesPerLine())
        img_np = arr[:, :safe_qimage.width() * 3].reshape(safe_qimage.height(), safe_qimage.width(), 3)

        dialog = GenerativeDialog(self._start_generative_worker, img_np, self)
        dialog.exec()
        self.set_state(EditorState.EDIT_ROOT)

    def confirm_canvas(self):
        if self.canvas_L == 0 and self.canvas_T == 0 and self.canvas_R == 0 and self.canvas_B == 0:
            self.set_state(EditorState.EDIT_ROOT)
            return

        # Anulamos el comando paramétrico pendiente de los spinboxes
        self._current_cmd = None 
        
        # --- FIX UNDO: Capturar estado SIN lienzo antes de hornearlo ---
        l, t, r, b = self.canvas_L, self.canvas_T, self.canvas_R, self.canvas_B
        self.canvas_L = self.canvas_T = self.canvas_R = self.canvas_B = 0
        self._begin_edit("Confirmar Lienzo", is_destructive=True)
        self.canvas_L, self.canvas_T, self.canvas_R, self.canvas_B = l, t, r, b
        # ----------------------------------------------------------------
        
        # Hornear usando la pipeline a máxima resolución
        old_state = self.current_state
        self.current_state = EditorState.MAIN 
        self.update_image()
        
        self.original_pixmap = QPixmap(self.current_pixmap)
        self.current_state = old_state
        self._reset_transformation_params()
        
        # Finalizar (Qt hace el push y refresca)
        self._end_edit()
        self.set_state(EditorState.EDIT_ROOT)
    def cancel_canvas_action(self):
        """Cancela la edición actual del lienzo y resetea los parámetros."""
        self.canvas_L = self.canvas_T = self.canvas_R = self.canvas_B = 0
        self._sync_ui_to_state()
        self.update_image()
        # Abortar comando de historial
        self._current_cmd = None
        self.set_state(EditorState.EDIT_ROOT)

    def _on_canvas_unit_changed(self):
        for sb in self.side_canvas_panel.spinboxes.values():
            sb.blockSignals(True); sb.setValue(0); sb.blockSignals(False)
        self.canvas_L = self.canvas_T = self.canvas_R = self.canvas_B = 0
        self.update_canvas_params(0, 0, 0, 0)

    def _on_canvas_spinbox_changed(self):
        if not hasattr(self, '_current_cmd') or not self._current_cmd:
             self._begin_edit("Ajuste de Lienzo")
        
        is_percent = hasattr(self, 'side_canvas_panel') and self.side_canvas_panel.canvas_unit_combo.currentIndex() == 1
        w, h = self.original_pixmap.width(), self.original_pixmap.height()
        
        def calc(val, base): return int(base * (val / 100.0)) if is_percent else val
        
        l, r = calc(self.side_canvas_panel.spinboxes["L"].value(), w), calc(self.side_canvas_panel.spinboxes["R"].value(), w)
        t, b = calc(self.side_canvas_panel.spinboxes["T"].value(), h), calc(self.side_canvas_panel.spinboxes["B"].value(), h)
        self.update_canvas_params(l, t, r, b)

    def _sync_canvas_spinboxes(self):
        if not hasattr(self, 'side_canvas_panel'): return
        is_percent = hasattr(self, 'side_canvas_panel') and self.side_canvas_panel.canvas_unit_combo.currentIndex() == 1
        bases = {"L": self.original_pixmap.width(), "R": self.original_pixmap.width(),
                 "T": self.original_pixmap.height(), "B": self.original_pixmap.height()} if is_percent else {}

        for d, sb in self.side_canvas_panel.spinboxes.items():
            sb.blockSignals(True)
            val = getattr(self, f"canvas_{d}")
            if is_percent and bases.get(d, 0) > 0: val = int(round((val / bases[d]) * 100))
            sb.setValue(val); sb.blockSignals(False)

    def _on_crop_requested(self, scene_rect):
        from PyQt6.QtCore import QRectF
        # Mapeamos el rect de la escena (donde dibujó el usuario) al rect del pixmap transformado
        intersect_f = self.viewer.pixmap_item.mapFromScene(QRectF(scene_rect)).boundingRect()
        
        # Intersectar con el contenido real para no intentar recortar fuera de los límites
        intersect = intersect_f.intersected(QRectF(self.current_pixmap.rect()))
        
        # Ignorar clics accidentales (rectángulos diminutos)
        if intersect.width() < 10 or intersect.height() < 10:
            self.set_state(EditorState.EDIT_ROOT)
            return
            
        self._begin_edit("Recortar Imagen", is_destructive=True)
        
        # Recortar de la imagen horneada
        cropped = self.current_pixmap.copy(intersect.toRect())
        self.original_pixmap = cropped
        
        # Resetear todos los parámetros y renderizar la nueva imagen recortada como base
        self._reset_transformation_params()
        self.update_image()
        
        self._end_edit()
        self.set_state(EditorState.EDIT_ROOT)

    def _handle_side_palette_click(self, mode):
        self.palette_mode = mode
        self.side_palette_panel.update_btn_styles(mode)
        self.extract_palette(mode)

    # --- HERRAMIENTAS: INTELIGENCIA ARTIFICIAL (IA) ---
    def run_ai_rmbg(self, model_rel_path): self._start_ai_worker("rmbg", "Quitando Fondo...", model_rel_path)
    def run_ai_upscale(self, model_rel_path): self._start_ai_worker("upscale", "Mejorando Calidad...", model_rel_path)
    def run_ai_depth(self, model_rel_path): self._start_ai_worker("depth", "Calculando Profundidad...", model_rel_path)

    @log_action("Ejecutando Proceso de IA")
    def _start_ai_worker(self, mode, text, model_rel_path):
        if self.original_pixmap.isNull(): return
        
        if excede_limite_megapixeles(self.original_pixmap, max_mp=4.0):
            msg = "Esta imagen es muy grande y procesarla consumirá mucha memoria.\n¿Deseas continuar?"
            res = QMessageBox.warning(self, "Aviso de Rendimiento", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if res == QMessageBox.StandardButton.No: return

        self.current_ai_mode = mode
        self.viewer.show_ai_processing(True, text)
        self._set_toolbar_enabled(False)
        
        self.ai_thread = QThread()
        
        # Convertir a QImage en el hilo principal de forma segura antes de pasar al worker
        safe_qimage = self.original_pixmap.toImage()
        self.ai_worker = AIWorker(safe_qimage, mode, model_rel_path)
        self.ai_worker.moveToThread(self.ai_thread)
        
        self.ai_worker.progress.connect(self.viewer.setProgress)
        self.ai_thread.started.connect(self.ai_worker.run)
        
        # Limpieza asíncrona impecable
        self.ai_worker.finished.connect(self.on_ai_finished)
        self.ai_worker.finished.connect(self.ai_thread.quit)
        self.ai_worker.finished.connect(self.ai_worker.deleteLater)
        self.ai_thread.finished.connect(self.ai_thread.deleteLater)
        
        self.ai_worker.error.connect(self.on_ai_error)
        self.ai_worker.error.connect(self.ai_thread.quit)
        self.ai_worker.error.connect(self.ai_worker.deleteLater)
        
        self.ai_thread.start()

    @log_action("Ejecutando IA Generativa")
    def _start_generative_worker(self, gen_mode, base_model_path, lora_path, denoising_strength, prompt, num_images=1, steps=30):
        if self.original_pixmap.isNull(): return
        
        self.current_ai_mode = "generative"
        self.viewer.show_ai_processing(True, "Inicializando motor Pytorch...")
        self._set_toolbar_enabled(False)
        
        # Extraemos la imagen actual tal cual está en el visor (RGB)
        safe_qimage = self.original_pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)
        
        import numpy as np
        ptr = safe_qimage.constBits()
        ptr.setsize(safe_qimage.sizeInBytes())
        # QImage usa padding de 4 bytes por línea, así que usamos bytesPerLine
        arr = np.array(ptr).reshape(safe_qimage.height(), safe_qimage.bytesPerLine())
        # Recortamos el padding y le damos forma (H, W, 3)
        img_np = arr[:, :safe_qimage.width() * 3].reshape(safe_qimage.height(), safe_qimage.width(), 3)
        
        self.gen_worker = GenerativeAIWorker(
            mode=gen_mode,
            base_image=img_np,
            prompt=prompt,
            base_model_path=base_model_path,
            lora_path=lora_path,
            denoising_strength=denoising_strength,
            num_images=num_images,
            num_inference_steps=steps
        )
        
        self.gen_worker.progress.connect(self.viewer.setProgress)
        self.gen_worker.status.connect(self.viewer.status_label.setText)
        
        def finish_adapter(results_np_list):
            qimages = []
            for result_np in results_np_list:
                h, w, ch = result_np.shape
                bytes_per_line = ch * w
                qimg = QImage(result_np.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
                qimages.append(qimg)
            self.on_generative_batch_finished(qimages)
            
        self.gen_worker.finished.connect(finish_adapter)
        self.gen_worker.finished.connect(self.gen_worker.deleteLater)
        
        self.gen_worker.error.connect(self.on_ai_error)
        self.gen_worker.error.connect(self.gen_worker.deleteLater)
        
        self.gen_worker.start()

    def _cancel_ai_worker(self):
        if hasattr(self, 'ai_thread') and self.ai_thread:
            try:
                if self.ai_thread.isRunning():
                    self.ai_thread.terminate(); self.ai_thread.wait()
            except RuntimeError:
                pass
            log_action("IA: Proceso cancelado por el usuario")()
            
        if hasattr(self, 'gen_worker') and self.gen_worker:
            try:
                if self.gen_worker.isRunning():
                    self.gen_worker.cancel()
                    self.gen_worker.terminate()
                    self.gen_worker.wait()
            except RuntimeError:
                pass
            log_action("IA Generativa: Proceso cancelado por el usuario")()
            
        self._cleanup_ai()

    def on_generative_batch_finished(self, qimages):
        self._cleanup_ai()
        if not qimages: return
        
        is_txt2img = getattr(self, 'current_ai_mode', "") == "txt2img"
        
        if len(qimages) == 1 and not is_txt2img:
            self.on_ai_finished(qimages[0])
            return
            
        dialog = BatchResultDialog(qimages, self)
        if is_txt2img:
            dialog.btn_exec.setText("Abrir en Nueva Pestaña")
            
        if dialog.exec():
            selected_idx = dialog.current_index
            if 0 <= selected_idx < len(qimages):
                if is_txt2img:
                    self._save_and_open_new_tab(qimages[selected_idx])
                else:
                    self.on_ai_finished(qimages[selected_idx])

    def _save_and_open_new_tab(self, qimage):
        base, ext = os.path.splitext(self.file_path)
        default_path = f"{base}_txt2img.png"
        file_path, _ = QFileDialog.getSaveFileName(self, "Guardar Imagen Generada", default_path, "PNG (*.png);;JPEG (*.jpg);;WEBP (*.webp)")
        if file_path:
            if qimage.save(file_path):
                main_win = self.window()
                if hasattr(main_win, 'open_image_tab'):
                    main_win.open_image_tab(file_path)
            else:
                QMessageBox.critical(self, "Error", "No se pudo guardar la imagen.")

    def on_ai_finished(self, qimage):
        self.viewer.setProgress(100, 100)
        self._cleanup_ai()
        
        self.ai_result_qimage = qimage
        if getattr(self, 'current_ai_mode', "") == "txt2img":
            # No hay imagen base original para comparar, solo mostrar el resultado
            self.viewer.setPixmap(QPixmap.fromImage(qimage))
        else:
            # Activar modo de comparación
            orig_scaled = self.original_pixmap.scaled(qimage.width(), qimage.height(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.viewer.setComparisonMode(orig_scaled, QPixmap.fromImage(qimage))
            
        self.ai_confirm_panel.setVisible(True)
        self._set_toolbar_enabled(False) # Mantener bloqueado hasta confirmar o descartar

    def _save_ai_result(self):
        if not hasattr(self, 'ai_result_qimage'): return
        
        base, ext = os.path.splitext(self.file_path)
        mode_suffix = getattr(self, 'current_ai_mode', "ai")
        default_path = f"{base}_{mode_suffix}.png"
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Guardar Resultado de IA", default_path, "PNG (*.png);;JPEG (*.jpg);;WEBP (*.webp)")
        if not file_path: return # Canceló el diálogo
        
        if self.ai_result_qimage.save(file_path):
            logger.info(f"IA: Variante guardada con éxito -> {os.path.basename(file_path)}")
            
            # Cargar como imagen principal y restaurar UI
            self._begin_edit("Aplicar Resultado IA", is_destructive=True)
            self.original_pixmap = QPixmap.fromImage(self.ai_result_qimage)
            self.file_path = file_path
            self._reset_transformation_params()
            self._end_edit()
            
            self._discard_ai_result() # Restaura la UI
            self.update_image()
            self.imageUpdated.emit()
            
            # Actualizar título de la pestaña
            main_win = self.window()
            if hasattr(main_win, 'tabs'):
                idx = main_win.tabs.indexOf(self)
                if idx != -1: main_win.tabs.setTabText(idx, os.path.basename(file_path))
        else:
            QMessageBox.critical(self, "Error al guardar", "No se pudo guardar la variante de IA en el disco.")

    def _discard_ai_result(self):
        self.ai_confirm_panel.setVisible(False)
        self.viewer.setPixmap(self.original_pixmap)
        self.update_image()
        self._set_toolbar_enabled(True)
        if hasattr(self, 'ai_result_qimage'):
            del self.ai_result_qimage

    def on_ai_error(self, message):
        """Maneja errores de IA y muestra mensajes claros al usuario."""
        # Detectar si es limitación de hardware o error técnico
        is_hardware_issue = "LIMITACIÓN DE HARDWARE" in message or "VRAM" in message
        
        if is_hardware_issue:
            # Diálogo de advertencia (hardware insuficiente)
            QMessageBox.warning(
                self, 
                "⚠️ Hardware Insuficiente", 
                message,
                QMessageBox.StandardButton.Ok
            )
        else:
            # Diálogo de error (problema técnico)
            QMessageBox.critical(
                self, 
                "❌ Error en Procesamiento de IA", 
                message,
                QMessageBox.StandardButton.Ok
            )
        
        self._cleanup_ai()

    def _cleanup_ai(self):
        self.viewer.show_ai_processing(False); self._set_toolbar_enabled(True)
        # Mantenemos las referencias vivas en Python. 
        # C++ las destruirá de forma segura en el bucle de eventos (deleteLater).
        # Se sobrescribirán solas la próxima vez que se ejecute la IA.

    def _set_toolbar_enabled(self, enabled):
        """Bloquea o desbloquea toda la barra de herramientas superior."""
        tools = [self.btn_fullscreen, self.btn_edit, self.btn_mirror, self.btn_rotate, 
                 self.btn_canvas, self.btn_adjust, self.btn_palette, self.btn_ai, self.btn_generative]
        for b in tools: b.setEnabled(enabled)
        
        if enabled:
            self.update_menu_state()
        else:
            for b in [self.btn_undo, self.btn_redo, self.btn_cancel, self.btn_save]: 
                b.setEnabled(False)

    def _clear_palette_markers(self):
        for m in self.palette_markers: 
            if m.scene(): self.viewer.scene.removeItem(m)
        self.palette_markers = []
        while self.palette_layout.count():
            child = self.palette_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

    @log_action("Extrayendo Paleta de Colores")
    def extract_palette(self, mode):
        self.palette_mode = mode; self._clear_palette_markers()
        if self.current_pixmap.isNull(): return
        self.palette_thread = QThread(); self.palette_worker = PaletteWorker(self.current_pixmap, mode); self.palette_worker.moveToThread(self.palette_thread)
        self.palette_thread.started.connect(self.palette_worker.run); self.palette_worker.finished.connect(self.on_palette_finished); self.palette_worker.finished.connect(self.palette_thread.quit)
        self.palette_thread.start()

    def on_palette_finished(self, final_data):
        if not final_data: return
        w, h = self.current_pixmap.width(), self.current_pixmap.height()
        # El círculo medirá aproximadamente el 2.5% del lado más corto
        marker_size = max(20, min(w, h) // 40)
        
        for item in final_data:
            c = item['color']
            # Colocar el marcador en la coordenada real de muestreo
            marker = ColorMarker(c, item['x'], item['y'], size=marker_size)
            self.viewer.scene.addItem(marker); self.palette_markers.append(marker)
            
            # --- NUEVO: Usamos SwatchFrame para permitir clics y selección de texto ---
            swatch = SwatchFrame()
            swatch.setCursor(Qt.CursorShape.PointingHandCursor)
            swatch.setStyleSheet(f"QFrame {{ background-color: {c.name()}; border: 1px solid #333333; border-radius: 4px; }} QFrame:hover {{ border: 2px solid white; }}")
            swatch.clicked.connect(marker.highlight)
            
            s_layout = QVBoxLayout(swatch); s_layout.setContentsMargins(5, 5, 5, 5); swatch.setFixedHeight(45); swatch.setFixedWidth(100)
            edit_hex = QLineEdit(c.name().upper()); edit_hex.setReadOnly(True); edit_hex.setAlignment(Qt.AlignmentFlag.AlignCenter); edit_hex.setStyleSheet("background: rgba(0,0,0,150); color: white; border: none; font-size: 9px; font-weight: bold;")
            s_layout.addWidget(edit_hex); self.palette_layout.addWidget(swatch)

    def export_palette_image(self):
        main_win = self.window()
        if hasattr(main_win, 'ignore_watcher'): main_win.ignore_watcher = True
        try:
            file_path, _ = QFileDialog.getSaveFileName(self, "Exportar Paleta", "paleta.jpg", "JPEG (*.jpg);;PNG (*.png)")
            if not file_path: return
            w, h = 1200, 400; export_img = QImage(w, h, QImage.Format.Format_ARGB32); export_img.fill(QColor("#1a1a1a"))
            p = QPainter(export_img); swatch_w = w // 5; font_hex = QFont("Segoe UI", 14, QFont.Weight.Bold)
            for i, marker in enumerate(self.palette_markers):
                color = marker.brush().color(); x = i * swatch_w; p.fillRect(x, 0, swatch_w, h - 100, color)
                p.setPen(Qt.GlobalColor.white); p.setFont(font_hex); p.drawText(QRect(x, h - 85, swatch_w, 30), Qt.AlignmentFlag.AlignCenter, color.name().upper())
            p.end(); export_img.save(file_path)
        finally:
            if hasattr(main_win, 'ignore_watcher'): QTimer.singleShot(1000, lambda: setattr(main_win, 'ignore_watcher', False))

    def on_free_rotate_changed(self, value): self.angle = value; self.update_image(); self.update_menu_state()
    def open_fullscreen(self, *args): self.fs_viewer = FullScreenViewer(self.file_path)
    # --- PUENTES DEL HISTORIAL (UNDO/REDO) ---
    def _begin_edit(self, description, is_destructive=False):
        """Paso 1: Captura el estado original antes de realizar la acción."""
        self._current_cmd = EditorCommand(self, description, is_destructive=is_destructive)

    def _end_edit(self):
        """Paso 2: Captura el estado final y guarda en el stack. Qt ejecutará redo()."""
        if hasattr(self, '_current_cmd') and self._current_cmd:
            self._current_cmd.capture_new_state()
            if self._current_cmd.is_destructive or self._current_cmd.old_params != self._current_cmd.new_params:
                self.undo_stack.push(self._current_cmd)
            self._current_cmd = None

    def update_menu_state(self):
        has_canvas = any([self.canvas_L, self.canvas_T, self.canvas_R, self.canvas_B])
        is_dirty = any([self.angle, self.flip_h, self.flip_v, self.brightness != 1.0, self.contrast != 1.0, has_canvas])
        has_history = self.undo_stack.count() > 0 or is_dirty
        
        if self.current_state != EditorState.MAIN:
            self.btn_undo.setEnabled(self.undo_stack.canUndo())
            self.btn_redo.setEnabled(self.undo_stack.canRedo())
            self.btn_cancel.setEnabled(has_history)
            self.btn_save.setEnabled(has_history)

    # --- MOTOR DE RENDERIZADO (OPEN CV + NUMPY) ---
    def _sync_ui_to_state(self):
        """Sincroniza todos los sliders y spinboxes con las variables internas."""
        # 1. Sliders (Brillo, Contraste, Rotación)
        for s, v in [(self.slider_brightness, int(self.brightness * 100)), 
                     (self.slider_contrast, int(self.contrast * 100)), 
                     (self.slider_rotate, self.angle)]:
            s.blockSignals(True)
            s.setValue(v)
            s.blockSignals(False)
            
        # 2. Spinboxes de Lienzo
        self._sync_canvas_spinboxes()
        
        # 3. Color de fondo del lienzo
        if hasattr(self, 'canvas_color_indicator'):
            # Convertimos a QColor para asegurar que .name() sea el método de Qt y no la propiedad del Enum
            c = QColor(self.canvas_bg_color)
            self.canvas_color_indicator.setStyleSheet(f"background-color: {c.name()}; border: 1px solid #aaa; border-radius: 2px;")
    
    @log_action("Deshaciendo última acción")
    def cancel_edits_prompt(self, *args):
        if QMessageBox.question(self, "Cancelar Edición", "¿Borrar todos los cambios?") == QMessageBox.StandardButton.Yes: self.cancel_edits()
    def cancel_edits(self):
        self._reset_transformation_params()
        self.original_pixmap = QPixmap(self.file_path); self.undo_stack.clear()
        self.update_image(); self.update_menu_state(); self.set_state(EditorState.MAIN)
    def _toggle_state_bool(self, attr_name, description):
        self._begin_edit(description)
        setattr(self, attr_name, not getattr(self, attr_name))
        self._end_edit()

    @log_action("Espejo Horizontal")
    def toggle_flip_h(self, *args): 
        self._toggle_state_bool("flip_h", "Espejo Horizontal")

    @log_action("Espejo Vertical")
    def toggle_flip_v(self, *args): 
        self._toggle_state_bool("flip_v", "Espejo Vertical")
    def activate_current_canvas_color(self):
        """Activa el modo color con el color actual sin abrir el diálogo."""
        if self.canvas_bg_color == Qt.GlobalColor.transparent:
            self.canvas_bg_color = Qt.GlobalColor.white
        self.side_canvas_panel.update_btn_styles(mode="color")
        self.update_image()

    def choose_custom_color(self):
        # Usamos un timer para evitar el crash de animaciones al cerrar el Flyout
        QTimer.singleShot(10, self._open_color_dialog)

    def _open_color_dialog(self):
        color = QColorDialog.getColor(self.canvas_bg_color, self, "Color de Lienzo")
        if color.isValid(): 
            self.canvas_bg_color = color
            if hasattr(self, 'canvas_color_indicator'):
                self.canvas_color_indicator.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #aaa; border-radius: 2px;")
            self.side_canvas_panel.update_btn_styles(mode="color")
            self.set_state(EditorState.EDIT_CANVAS_ACTIVE)
            
    def activate_canvas_trans(self): 
        self.canvas_bg_color = Qt.GlobalColor.transparent
        self.side_canvas_panel.update_btn_styles(mode="trans")
        self.set_state(EditorState.EDIT_CANVAS_ACTIVE)
    @log_action("Renderizando Transformaciones finales")
    def _apply_transform_to_file(self):
        # Renderiza el contenido a máxima resolución usando la nueva función pura
        old_state = self.current_state
        self.current_state = EditorState.MAIN
        
        # Invocas a tu core de procesamiento pasándole la imagen original a tope de resolución
        final_pix, _ = apply_image_transformations(
            self.original_pixmap, self.brightness, self.contrast, self.angle, 
            self.flip_h, self.flip_v, self.canvas_L, self.canvas_T, 
            self.canvas_R, self.canvas_B, self.canvas_bg_color
        )
        
        self.current_state = old_state
        return final_pix.toImage()

    def _post_save_cleanup(self, final_img):
        self.original_pixmap = QPixmap.fromImage(final_img)
        self._reset_transformation_params()
        self.undo_stack.clear()
        self.update_image()
        self.set_state(EditorState.EDIT_ROOT)

    @log_action("Renderizando Transformaciones finales")
    @log_action("Sobrescribiendo Archivo")
    def save_overwrite(self, *args):
        final_img = self._apply_transform_to_file()
        if final_img.save(self.file_path): 
            self._post_save_cleanup(final_img)

    @log_action("Guardando Copia Nueva")
    def save_as_copy(self, *args):
        final_img = self._apply_transform_to_file()
        path, _ = QFileDialog.getSaveFileName(self, "Guardar Copia", self.file_path, "Images (*.png *.jpg)")
        if path and final_img.save(path): 
            self._post_save_cleanup(final_img)

    def update_image(self):
        if self.original_pixmap.isNull(): return
        
        use_proxy = (self.current_state in [EditorState.EDIT_ADJUST, EditorState.EDIT_ROTATE])
        base_pix = self.proxy_pixmap if (use_proxy and hasattr(self, 'proxy_pixmap')) else self.original_pixmap
        
        content_pix, content_rect = apply_image_transformations(
            base_pix, self.brightness, self.contrast, self.angle, 
            self.flip_h, self.flip_v, self.canvas_L, self.canvas_T, 
            self.canvas_R, self.canvas_B, self.canvas_bg_color
        )
        
        self.content_rect = content_rect
        self.current_pixmap = content_pix
        self.viewer.setPixmap(content_pix)
        
        self.viewer.pixmap_item.setPos(-self.canvas_L, -self.canvas_T)
        self.viewer.checkerboard_item.setPos(-self.canvas_L, -self.canvas_T)
        self.viewer.scene.setSceneRect(self.viewer.pixmap_item.mapToScene(self.viewer.pixmap_item.boundingRect()).boundingRect())

    def _reset_transformation_params(self):
        """Reinicia los parámetros matemáticos y delega la actualización visual."""
        self.brightness, self.contrast, self.angle = 1.0, 1.0, 0
        self.flip_h = self.flip_v = False
        self.canvas_L = self.canvas_T = self.canvas_R = self.canvas_B = 0
        self._sync_ui_to_state()
    def update_canvas_params(self, l, t, r, b):
        self.canvas_L, self.canvas_T, self.canvas_R, self.canvas_B = l, t, r, b
        self.update_image()
        self.update_menu_state()
    def _on_adjust_changed(self):
        # Convertimos 0..200 a factor 0.0..2.0
        self.brightness = self.slider_brightness.value() / 100.0
        self.contrast = self.slider_contrast.value() / 100.0
        self.angle = self.slider_rotate.value()
        self.update_image()
        self.update_menu_state()

    def _create_proxy_pixmap(self):
        """Crea una versión ligera de la imagen para edición fluida (máx 1600px)."""
        w, h = self.original_pixmap.width(), self.original_pixmap.height()
        if w > 1600 or h > 1600:
            self.proxy_pixmap = self.original_pixmap.scaled(1600, 1600, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        else:
            self.proxy_pixmap = self.original_pixmap.copy()
