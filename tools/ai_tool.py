import os
import sys
import shutil
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFrame, QComboBox, QGridLayout, QProgressBar,
                             QScrollArea, QWidget, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from huggingface_hub import hf_hub_download
from studio_logger import log_action, logger
from core.utils import get_base_path

# --- CATÁLOGO DE MODELOS ONNX (GPU: DirectML / CUDA | CPU fallback) ---
MODELS_CONFIG = {
    "4x-UltraSharp": {
        "repo": "yuvraj108c/ComfyUI-Upscaler-Onnx", "file": "4x-UltraSharp.onnx",
        "path": "models/upscale/4x-UltraSharp.onnx",
        "snapshot": False, "cat": "upscale", "tier": "Mid", "sub": "real",
        "full_sub": "Fotografía Realista", "ram": "4 GB", "vram": "2 GB",
        "full_utility": "Upscaling (Aumento de nitidez y realismo)",
        "desc": "Estándar de oro para paisajes y arquitectura. Define bordes sin añadir texturas artificiales. Motor ONNX: compatible con AMD, NVIDIA e Intel."
    },
    "4x-AnimeSharp": {
        "repo": "yuvraj108c/ComfyUI-Upscaler-Onnx", "file": "4x-AnimeSharp.onnx",
        "path": "models/upscale/4x-AnimeSharp.onnx",
        "snapshot": False, "cat": "upscale", "tier": "Mid", "sub": "anime",
        "full_sub": "Ilustración / Anime", "ram": "4 GB", "vram": "2 GB",
        "full_utility": "Upscaling (Limpieza de bordes y ruido)",
        "desc": "Especializado en dibujos y arte digital. Elimina el ruido y suaviza superficies de color plano. Motor ONNX optimizado."
    },
    "4x-UltraSharpV2": {
        "repo": "yuvraj108c/ComfyUI-Upscaler-Onnx", "file": "4x-UltraSharpV2.onnx",
        "path": "models/upscale/4x-UltraSharpV2.onnx",
        "snapshot": False, "cat": "upscale", "tier": "Pro", "sub": "real",
        "full_sub": "Retratos y Alta Fidelidad", "ram": "4 GB", "vram": "2 GB",
        "full_utility": "Upscaling V2 (Arquitectura moderna)",
        "desc": "Versión mejorada del UltraSharp. Arquitectura más ligera con mejor fidelidad en retratos y escenas complejas."
    },
    "RealESRGAN-x4": {
        "repo": "yuvraj108c/ComfyUI-Upscaler-Onnx", "file": "RealESRGAN_x4.onnx",
        "path": "models/upscale/RealESRGAN_x4.onnx",
        "snapshot": False, "cat": "upscale", "tier": "Mid", "sub": "real",
        "full_sub": "Retratos y Grupos", "ram": "4 GB", "vram": "2 GB",
        "full_utility": "Upscaling (Realismo universal)",
        "desc": "Modelo clásico de referencia. Excelente para fotos familiares o retratos donde la velocidad es importante."
    },
    # --- FP16: Mitad de VRAM, calidad prácticamente idéntica ---
    "AnimeSharp-FP16": {
        "repo": "tangalbert919/upscalers-onnx", "file": "4x-AnimeSharp_fp16.onnx",
        "path": "models/upscale/4x-AnimeSharp_fp16.onnx",
        "snapshot": False, "cat": "upscale", "tier": "Lite", "sub": "anime",
        "full_sub": "Anime FP16 (Ultra ligero)", "ram": "2 GB", "vram": "1 GB",
        "full_utility": "Upscaling 4x Anime FP16",
        "desc": "AnimeSharp en FP16. Prácticamente indistinguible del FP32 para anime. La opción más ligera para ilustración."
    },
    "UltraSharpV2-Lite-FP16": {
        "repo": "tangalbert919/upscalers-onnx", "file": "4x-UltraSharpV2_Lite_fp16.onnx",
        "path": "models/upscale/4x-UltraSharpV2_Lite_fp16.onnx",
        "snapshot": False, "cat": "upscale", "tier": "Lite", "sub": "real",
        "full_sub": "Ultra Ligero FP16", "ram": "512 MB", "vram": "256 MB",
        "full_utility": "Upscaling 4x FP16 Lite (Mínimo recurso)",
        "desc": "Solo 15 MB. El modelo más ligero del catálogo. Diseñado para hardware muy limitado o procesamiento casi en tiempo real."
    },
    # --- ANIME: Modelos especializados adicionales ---
    "4x-NMKD-Siax": {
        "repo": "yuvraj108c/ComfyUI-Upscaler-Onnx", "file": "4x_NMKD-Siax_200k.onnx",
        "path": "models/upscale/4x_NMKD-Siax_200k.onnx",
        "snapshot": False, "cat": "upscale", "tier": "Mid", "sub": "anime",
        "full_sub": "Anime / Ilustración HD", "ram": "4 GB", "vram": "2 GB",
        "full_utility": "Upscaling 4x (Anime + Arte Digital)",
        "desc": "Entrenado con 200k iteraciones sobre contenido anime real. Elimina artefactos de compresión y ruido en escenas con colores planos y líneas limpias. Muy valorado por la comunidad."
    },
    # --- ULTRA: HAT-L (Hybrid Attention Transformer Large) ---
    "4xNomos8kHAT-L-OTF": {
        "repo": "nesaorg/4xNomos8kHAT-L_otf_fp32_opset17", "file": "4xNomos8kHAT-L_otf_fp32_opset17.onnx",
        "path": "models/upscale/4xNomos8kHAT-L_otf_fp32_opset17.onnx",
        "snapshot": False, "cat": "upscale", "tier": "Ultra", "sub": "real",
        "full_sub": "Ultra Calidad — HAT-L OTF", "ram": "8 GB", "vram": "6 GB",
        "full_utility": "Upscaling 4x — HAT-L (On-The-Fly degradations)",
        "desc": "HAT-L entrenado con degradaciones reales (OTF). Restaura fotos web comprimidas, ruido y desenfoque. La opción premium para fotografía dañada. Requiere 6 GB+ VRAM."
    },
    "4xNomos8kHAT-L-Bokeh": {
        "repo": "nesaorg/4xNomos8kHAT-L_bokeh_jpg_fp32_opset17", "file": "4xNomos8kHAT-L_bokeh_jpg_fp32_opset17.onnx",
        "path": "models/upscale/4xNomos8kHAT-L_bokeh_jpg_fp32_opset17.onnx",
        "snapshot": False, "cat": "upscale", "tier": "Ultra", "sub": "real",
        "full_sub": "Ultra Calidad — HAT-L Bokeh", "ram": "8 GB", "vram": "6 GB",
        "full_utility": "Upscaling 4x — HAT-L (Bokeh + JPEG)",
        "desc": "HAT-L especializado en fotos con desenfoque artístico (bokeh) y artefactos JPEG. Ideal para fotografía de retrato de alta gama. Requiere 6 GB+ VRAM."
    },
    # --- FONDO: Background Removal ---
    "RMBG-1.4": {
        "repo": "briaai/RMBG-1.4",
        "file": "onnx/model.onnx",
        "path": "models/rmbg/RMBG-1.4.onnx",
        "snapshot": False, "cat": "rmbg", "tier": "Lite", "sub": "universal",
        "full_sub": "Sujeto Universal", "ram": "2 GB", "vram": "512 MB",
        "full_utility": "Quitar fondo (Background Removal)",
        "desc": "Versión oficial de BRIA AI en formato ONNX. Ultra-rápido y extremadamente preciso con bordes complejos."
    },
    "BiRefNet": {
        "repo": "onnx-community/BiRefNet-ONNX", "file": "onnx/model.onnx",
        "path": "models/rmbg/BiRefNet.onnx",
        "snapshot": False, "cat": "rmbg", "tier": "Pro", "sub": "universal",
        "full_sub": "Estado del Arte (FP32)", "ram": "4 GB", "vram": "4 GB",
        "full_utility": "Quitar fondo — BiRefNet FP32 (Máxima precisión)",
        "desc": "Estado del arte en segmentación. Supera a RMBG en cabello, pieles, transparencias y bordes complejos. Licencia MIT. ~928 MB."
    },
    "BiRefNet-FP16": {
        "repo": "onnx-community/BiRefNet-ONNX", "file": "onnx/model_fp16.onnx",
        "path": "models/rmbg/BiRefNet_fp16.onnx",
        "snapshot": False, "cat": "rmbg", "tier": "Mid", "sub": "universal",
        "full_sub": "Estado del Arte (FP16)", "ram": "2 GB", "vram": "2 GB",
        "full_utility": "Quitar fondo — BiRefNet FP16 (Mitad de VRAM)",
        "desc": "BiRefNet en FP16. Misma calidad de segmentación clase mundial, la mitad de VRAM. Ideal para GPUs de 4 GB o menos. Licencia MIT. ~467 MB."
    }
}

class DownloadWorker(QThread):
    finished = pyqtSignal(bool, str)
    def __init__(self, config):
        super().__init__()
        self.cfg = config

    @log_action("Descargando Modelo desde HuggingFace")
    def run(self):
        try:
            base = get_base_path()
            target_path = os.path.normpath(os.path.join(base, self.cfg['path']))
            target_dir = os.path.dirname(target_path)
            os.makedirs(target_dir, exist_ok=True)

            logger.info(f"Descargando: {self.cfg['repo']} -> {self.cfg['file']}")
            downloaded_path = hf_hub_download(
                repo_id=self.cfg['repo'],
                filename=self.cfg['file'],
                local_dir=target_dir,
                local_dir_use_symlinks=False
            )
            if os.path.normpath(downloaded_path) != target_path:
                if os.path.exists(target_path): os.remove(target_path)
                os.rename(downloaded_path, target_path)

            self.finished.emit(True, target_path)
        except Exception as e:
            logger.error(f"Error en descarga: {str(e)}")
            self.finished.emit(False, str(e))

class InfoBox(QFrame):
    """Cápsula técnica con alineación de micro-datos."""
    def __init__(self, icon, title, text, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedHeight(56) # Altura optimizada para el stack derecho
        self.setFixedWidth(145) # Ancho exacto para equilibrar la tarjeta
        self.setStyleSheet("""
            QFrame { background-color: rgba(30, 30, 30, 0.3); border: 1px solid #2a2a2a; border-radius: 10px; }
            QLabel#Title { color: #555; font-size: 8px; font-weight: bold; margin-bottom: 2px; }
            QLabel#Text { color: #ccc; font-size: 11px; }
            QLabel#Icon { font-family: 'Segoe MDL2 Assets'; font-size: 12px; color: #007acc; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)
        
        h_head = QHBoxLayout()
        lbl_icon = QLabel(icon); lbl_icon.setObjectName("Icon")
        lbl_title = QLabel(title.upper()); lbl_title.setObjectName("Title")
        h_head.addWidget(lbl_icon); h_head.addWidget(lbl_title); h_head.addStretch()
        
        lbl_text = QLabel(text); lbl_text.setObjectName("Text")
        
        layout.addLayout(h_head)
        layout.addWidget(lbl_text)

class ModelCard(QFrame):
    """Tarjeta premium con layout de doble columna simétrico."""
    clicked = pyqtSignal(str)
    
    STATIC_STYLE = """
        QFrame#Card { background-color: #080808; border: 1px solid #ff3b3b; border-radius: 15px; }
        QFrame#Card[installed="true"] { border-color: #00ff88; }
        QFrame#Card[selected="true"] { background-color: #0d0d0d; border: 3px solid #007acc; }
        QFrame#Card:hover { background-color: #111; border-color: #007acc; }
    """

    def __init__(self, name, config, is_selected=False, parent=None):
        super().__init__(parent)
        self.name = name; self.config = config; self.is_selected = is_selected
        self.setFixedSize(320, 370) # Un poco más alta para el footer
        self.setObjectName("Card"); self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        base = get_base_path()
        exists = os.path.exists(os.path.join(base, config['path']))
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 15)
        main_layout.setSpacing(15)

        # CABECERA: Título y estado
        v_header = QVBoxLayout(); v_header.setSpacing(4)
        lbl_mod_tag = QLabel("MODALIDAD:"); lbl_mod_tag.setStyleSheet("color: #444; font-size: 9px; font-weight: bold;")
        lbl_name = QLabel(name); lbl_name.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        
        status_color = "#00ff88" if exists else "#ff3b3b"
        status_bar = QFrame(); status_bar.setFixedHeight(3); status_bar.setStyleSheet(f"background-color: {status_color}; border-radius: 1px;")
        
        v_header.addWidget(lbl_mod_tag); v_header.addWidget(lbl_name); v_header.addWidget(status_bar)
        main_layout.addLayout(v_header)

        # CUERPO: Grid Híbrido (Descripción + Specs)
        h_body = QHBoxLayout(); h_body.setSpacing(12)
        
        # Izquierda: Caja de texto descriptivo
        desc_box = QFrame(); desc_box.setStyleSheet("background-color: rgba(25, 25, 25, 0.5); border: 1px solid #252525; border-radius: 12px;")
        desc_layout = QVBoxLayout(desc_box); desc_layout.setContentsMargins(15, 15, 15, 15)
        
        lbl_desc_tag = QLabel("SOBRE ESTA IA:"); lbl_desc_tag.setStyleSheet("color: #555; font-size: 8px; font-weight: bold;")
        lbl_desc = QLabel(config.get('desc', "")); lbl_desc.setStyleSheet("color: #aaa; font-size: 11px; line-height: 15px;")
        lbl_desc.setWordWrap(True); lbl_desc.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        desc_layout.addWidget(lbl_desc_tag); desc_layout.addWidget(lbl_desc); desc_layout.addStretch()
        h_body.addWidget(desc_box, 1)
        
        # Derecha: Columna de InfoBoxes
        v_specs = QVBoxLayout(); v_specs.setSpacing(8)
        v_specs.addWidget(InfoBox("\uE192", "Imagen", config.get('full_sub', "Universal")))
        v_specs.addWidget(InfoBox("\uE950", "VRAM", config.get('vram', "2 GB")))
        v_specs.addWidget(InfoBox("\uE967", "RAM", config.get('ram', "6 GB")))
        v_specs.addWidget(InfoBox("\uE713", "Utilidad", config.get('cat', "").upper()))
        h_body.addLayout(v_specs)
        
        main_layout.addLayout(h_body)

        # FOOTER: Utilidad completa
        lbl_foot = QLabel(config.get('full_utility', ""))
        lbl_foot.setStyleSheet("color: #0098ff; font-size: 10px; font-weight: bold;")
        lbl_foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(lbl_foot)

        # Estilo Dinámico basado en Propiedades
        self.setProperty("installed", bool(exists))
        self.setProperty("selected", bool(is_selected))
        self.setStyleSheet(self.STATIC_STYLE)

    def mousePressEvent(self, event):
        self.clicked.emit(self.name); super().mousePressEvent(event)

class FilterCapsule(QFrame):
    """Contenedor premium para los selectores de filtro."""
    def __init__(self, icon, title, parent=None):
        super().__init__(parent)
        self.setFixedHeight(75)
        self.setStyleSheet("""
            QFrame { background-color: #111; border: 1px solid #222; border-radius: 12px; }
            QLabel#Title { color: #555; font-size: 9px; font-weight: bold; }
            QLabel#Icon { font-family: 'Segoe MDL2 Assets'; font-size: 13px; color: #888; }
            QComboBox { background-color: #1a1a1a; border: none; border-radius: 6px; padding: 2px 10px; color: white; min-height: 28px; }
            QComboBox:hover { background-color: #222; }
        """)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 10); self.layout.setSpacing(4)
        h_head = QHBoxLayout()
        lbl_icon = QLabel(icon); lbl_icon.setObjectName("Icon")
        lbl_title = QLabel(title.upper()); lbl_title.setObjectName("Title")
        h_head.addWidget(lbl_icon); h_head.addWidget(lbl_title); h_head.addStretch()
        self.layout.addLayout(h_head)
        self.combo = QComboBox(); self.layout.addWidget(self.combo)

class AIAdvancedDialog(QDialog):
    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.actions = actions; self.selected_model = None
        self.setWindowTitle("FHVT gallery"); self.setFixedSize(1150, 780)
        
        self.setStyleSheet("""
            QDialog { background-color: #050505; color: white; }
            QLabel { font-family: 'Segoe UI'; }
            #FilterPanel { background-color: #0d0d0d; border-radius: 20px; border: 1px solid #1a1a1a; }
            
            #DeleteBtn { background-color: transparent; color: #ff3b3b; border-radius: 12px; border: 1px solid #ff3b3b; padding: 10px 30px; font-weight: bold; }
            #DeleteBtn:hover:enabled { background-color: #ff3b3b; color: white; }
            #DeleteBtn:disabled { color: #222; border-color: #111; }
            
            #DownloadBtn { background-color: transparent; color: #00ff88; border-radius: 12px; border: 1px solid #00ff88; padding: 10px 30px; font-weight: bold; }
            #DownloadBtn:hover:enabled { background-color: #00ff88; color: black; }
            #DownloadBtn:disabled { color: #222; border-color: #111; }
            
            #ExecuteBtn { background-color: transparent; color: #007acc; border-radius: 12px; border: 1px solid #007acc; padding: 10px 50px; font-weight: bold; font-size: 13px; }
            #ExecuteBtn:hover:enabled { background-color: #007acc; color: white; }
            #ExecuteBtn:disabled { color: #222; border-color: #111; }
            
            #CancelBtn { background-color: transparent; color: #666; border: 1px solid #222; border-radius: 12px; padding: 10px 30px; font-weight: bold; }
            #CancelBtn:hover { color: white; border-color: #444; background: #111; }
            
            #ClearBtn { background-color: transparent; color: #ff3b3b; font-family: 'Segoe MDL2 Assets'; border: none; font-size: 14px; }
            #ClearBtn:hover { color: #ff8888; }
            
            QScrollArea { border: none; background: transparent; }
        """)

        main_layout = QVBoxLayout(self); main_layout.setContentsMargins(35, 35, 35, 35); main_layout.setSpacing(30)

        filter_panel = QFrame(); filter_panel.setObjectName("FilterPanel")
        filter_layout = QHBoxLayout(filter_panel); filter_layout.setContentsMargins(25, 25, 25, 25); filter_layout.setSpacing(15)
        
        self.cap_type = FilterCapsule("\uE192", "Tipo de Modelo"); self.cap_type.combo.addItems(["Todos", "Anime", "Realista"]); self.combo_type = self.cap_type.combo
        self.cap_util = FilterCapsule("\uE713", "Utilidad"); self.cap_util.combo.addItems(["Cualquiera", "Upscaling", "Quitar Fondo", "Profundidad"]); self.combo_util = self.cap_util.combo
        self.cap_vram = FilterCapsule("\uE950", "Requisitos VRAM"); self.cap_vram.combo.addItems(["Cualquiera", "Lite (Sub-2GB)", "Mid (2-4GB)", "Pro (4-6GB)", "Ultra (8GB+)"]); self.combo_vram = self.cap_vram.combo
        
        filter_layout.addWidget(self.cap_type); filter_layout.addWidget(self.cap_util); filter_layout.addWidget(self.cap_vram); filter_layout.addStretch()
        
        self.status_badge = QFrame(); self.status_badge.setFixedWidth(240)
        self.status_badge.setStyleSheet("QFrame { background-color: #050505; border: 1px dashed #222; border-radius: 15px; } QLabel { color: #444; font-weight: bold; font-size: 15px; }")
        self.status_layout = QVBoxLayout(self.status_badge)
        
        h_status_top = QHBoxLayout()
        h_status_top.addStretch()
        self.btn_clear = QPushButton("\uE711"); self.btn_clear.setObjectName("ClearBtn"); self.btn_clear.setToolTip("Deseleccionar"); self.btn_clear.hide()
        h_status_top.addWidget(self.btn_clear)
        
        self.lbl_current = QLabel("ESPERANDO SELECCIÓN"); self.lbl_current.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_layout.addLayout(h_status_top); self.status_layout.addWidget(self.lbl_current, 0, Qt.AlignmentFlag.AlignCenter)
        filter_layout.addWidget(self.status_badge)
        main_layout.addWidget(filter_panel)

        self.scroll = QScrollArea(); self.scroll_content = QWidget(); self.grid = QGridLayout(self.scroll_content); self.grid.setSpacing(25); self.grid.setContentsMargins(0, 0, 0, 0); self.scroll.setWidget(self.scroll_content); self.scroll.setWidgetResizable(True); main_layout.addWidget(self.scroll)

        footer = QHBoxLayout()
        self.btn_cancel = QPushButton("CANCELAR"); self.btn_cancel.setObjectName("CancelBtn")
        self.btn_delete = QPushButton("BORRAR MODELO"); self.btn_delete.setObjectName("DeleteBtn"); self.btn_delete.setEnabled(False)
        self.btn_download = QPushButton("DESCARGAR ASSETS"); self.btn_download.setObjectName("DownloadBtn"); self.btn_download.setEnabled(False)
        self.btn_execute = QPushButton("EJECUTAR TAREA IA"); self.btn_execute.setObjectName("ExecuteBtn"); self.btn_execute.setEnabled(False)
        footer.addWidget(self.btn_cancel); footer.addStretch(); footer.addWidget(self.btn_delete); footer.addWidget(self.btn_download); footer.addWidget(self.btn_execute)
        main_layout.addLayout(footer)

        self.pbar = QProgressBar(); self.pbar.setStyleSheet("height: 4px; border: none; background: #111;"); self.pbar.hide(); main_layout.addWidget(self.pbar)
        self.lbl_msg = QLabel(""); self.lbl_msg.setStyleSheet("color: #007acc; font-size: 12px; font-weight: bold;"); main_layout.addWidget(self.lbl_msg)

        self.combo_type.currentIndexChanged.connect(self._request_refresh); self.combo_util.currentIndexChanged.connect(self._request_refresh); self.combo_vram.currentIndexChanged.connect(self._request_refresh)
        self.btn_cancel.clicked.connect(self.close); self.btn_delete.clicked.connect(self._delete_model); self.btn_download.clicked.connect(self._start_download); self.btn_execute.clicked.connect(self._run_task_selected); self.btn_clear.clicked.connect(self._deselect_model); self._refresh_grid()

    def _request_refresh(self):
        """Usa un timer para evitar crashes al borrar el widget que envió la señal."""
        QTimer.singleShot(0, self._refresh_grid)

    def _refresh_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        
        filter_type = self.combo_type.currentText().lower()
        filter_util = self.combo_util.currentText().lower()
        filter_vram = self.combo_vram.currentText().split(" ")[0].lower()
        
        # Ordenar modelos por requisito de VRAM (de menor a mayor)
        def get_vram_mb(cfg):
            v_str = cfg.get('vram', '0 MB')
            return float(v_str.replace("GB", "")) * 1024 if "GB" in v_str else float(v_str.replace("MB", ""))
            
        sorted_models = sorted(MODELS_CONFIG.items(), key=lambda x: get_vram_mb(x[1]))
        
        col, row = 0, 0
        for name, cfg in sorted_models:
            # 1. Filtro por Tipo (Realista/Anime)
            sub_cat = cfg.get('sub', 'universal')
            type_map = {"realista": "real", "anime": "anime"}
            target_type = type_map.get(filter_type)
            if filter_type != "todos" and sub_cat != target_type and sub_cat != "universal": continue
            
            # 2. Filtro por Utilidad
            util_map = {"upscaling": "upscale", "quitar fondo": "rmbg", "profundidad": "depth"}
            target_util = util_map.get(filter_util)
            if filter_util != "cualquiera" and cfg['cat'] != target_util: continue
            
            # 3. Filtro por Requisitos (VRAM Real)
            if filter_vram != "cualquiera":
                v_str = cfg['vram']
                v_mb = float(v_str.replace("GB", "")) * 1024 if "GB" in v_str else float(v_str.replace("MB", ""))
                
                calc_tier = "lite"
                if v_mb >= 8192: calc_tier = "ultra"
                elif v_mb >= 4096: calc_tier = "pro"
                elif v_mb >= 2048: calc_tier = "mid"
                
                if calc_tier != filter_vram: continue
            
            card = ModelCard(name, cfg, is_selected=(name == self.selected_model))
            card.clicked.connect(self._on_model_selected)
            self.grid.addWidget(card, row, col)
            col += 1
            if col > 2: col = 0; row += 1
        self.grid.setRowStretch(row + 1, 1)

    def _on_model_selected(self, name):
        self.selected_model = name; self.lbl_current.setText(name); self.btn_clear.show(); self.status_badge.setStyleSheet("QFrame { background-color: #0d0d0d; border: 1px solid #007acc; border-radius: 15px; } QLabel { color: #007acc; font-weight: bold; font-size: 15px; }")
        base = get_base_path(); exists = os.path.exists(os.path.join(base, MODELS_CONFIG[name]['path']))
        self.btn_delete.setEnabled(exists); self.btn_execute.setEnabled(exists); self.btn_download.setEnabled(not exists)
        self._request_refresh()

    def _deselect_model(self, *args):
        self.selected_model = None; self.lbl_current.setText("ESPERANDO SELECCIÓN"); self.btn_clear.hide(); self.status_badge.setStyleSheet("QFrame { background-color: #050505; border: 1px dashed #222; border-radius: 15px; } QLabel { color: #444; font-weight: bold; font-size: 15px; }")
        self.btn_delete.setEnabled(False); self.btn_execute.setEnabled(False); self.btn_download.setEnabled(False)
        self._request_refresh()

    @log_action("Borrando Modelo IA")
    def _delete_model(self, *args):
        if not self.selected_model: return
        cfg = MODELS_CONFIG[self.selected_model]
        base = get_base_path()
        full_path = os.path.join(base, cfg['path'])
        
        if QMessageBox.question(self, "Confirmar Borrado", f"¿Deseas eliminar {self.selected_model} del disco?") == QMessageBox.StandardButton.Yes:
            try:
                if os.path.exists(full_path):
                    if os.path.isdir(full_path):
                        shutil.rmtree(full_path) # Borra carpetas (Snapshots)
                    else:
                        os.remove(full_path)    # Borra archivos únicos
                    
                    self.lbl_msg.setText(f"🗑️ {self.selected_model} eliminado.")
                    self._deselect_model()
                else:
                    self.lbl_msg.setText("⚠️ El modelo no existe físicamente.")
            except Exception as e: 
                self.lbl_msg.setText(f"❌ Error: {str(e)}")

    def _start_download(self, *args):
        if not self.selected_model: return
        cfg = MODELS_CONFIG[self.selected_model]
        self.btn_download.setEnabled(False)
        self.pbar.setRange(0, 0)
        self.pbar.show()
        self.lbl_msg.setText(f"📥 Descargando {self.selected_model}...")
        self.worker = DownloadWorker(cfg)
        self.worker.finished.connect(self._on_download_finished)
        self.worker.start()

    def _on_download_finished(self, success, msg):
        self.pbar.hide()
        if success: self.lbl_msg.setText("✅ Descarga completa."); self._on_model_selected(self.selected_model)
        else: self.lbl_msg.setText(f"❌ Error: {msg}"); self.btn_download.setEnabled(True)

    def _run_task_selected(self, *args):
        if self.selected_model: self._run_task(MODELS_CONFIG[self.selected_model])

    def _run_task(self, cfg):
        rel_path = cfg['path']
        if cfg['cat'] == "upscale": self.actions.on_run_upscale(rel_path)
        elif cfg['cat'] == "rmbg": self.actions.on_run_rmbg(rel_path)
        elif cfg['cat'] == "depth": self.actions.on_run_depth(rel_path)
        self.close()
