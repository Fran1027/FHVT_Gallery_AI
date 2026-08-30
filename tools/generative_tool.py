import os
import shutil
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QSlider,
    QLineEdit,
    QFileDialog,
    QMessageBox,
    QComboBox,
    QProgressBar,
    QSpinBox,
    QWidget,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

def hf_download_process(repo_id, cache_dir, q):
    """
    Se ejecuta en un proceso 100% aislado.
    Usa una cola (queue) para comunicarse con el hilo principal.
    """
    import os
    from huggingface_hub import snapshot_download
    
    os.environ["HF_HOME"] = cache_dir

    # Inyectar tqdm global en subproceso
    from huggingface_hub.utils import tqdm as hf_tqdm_class
    
    _original_hf_update = hf_tqdm_class.update

    def _custom_hf_update(self, n=1):
        _original_hf_update(self, n)
        # Enviar actualizaciones bytes
        if getattr(self, "unit", "") == "B" and getattr(self, "total", 0):
            q.put(("PROGRESS", self.desc, self.n, self.total))

    hf_tqdm_class.update = _custom_hf_update

    allow_patterns = [
        "*.json", "*.txt", "scheduler/*", "text_encoder/*",
        "tokenizer/*", "unet/*", "vae/*", "feature_extractor/*",
        "safety_checker/*",
    ]
    
    ignore_patterns = [
        "*fp16*",         # Ignorar pesos 16-bits
        "*non_ema*",      # Ignorar pesos non-ema
        "*.msgpack",      # Ignorar pesos flax
        "*.ckpt",         # Ignorar checkpoints viejos
        "*.h5",           # Ignorar pesos keras
        "*.ot",           # Ignorar pesos rust
    ]
    
    try:
        snapshot_download(
            repo_id=repo_id, 
            allow_patterns=allow_patterns,
            ignore_patterns=ignore_patterns
        )
        q.put(("SUCCESS", f"Modelo '{repo_id}' descargado con éxito."))
    except Exception as e:
        q.put(("ERROR", str(e)))


from core.utils import get_base_path  # noqa: E402
from core.generative import CaptioningWorker, PromptEnhancerWorker  # noqa: E402


def is_model_downloaded(repo_id):
    cache_dir = os.path.join(get_base_path(), "models", "generative", "hf_cache")
    folder_name = f"models--{repo_id.replace('/', '--')}"
    model_path = os.path.join(cache_dir, folder_name)
    snapshots_path = os.path.join(model_path, "snapshots")
    if os.path.exists(snapshots_path):
        try:
            snapshots = os.listdir(snapshots_path)
            for snapshot in snapshots:
                snapshot_dir = os.path.join(snapshots_path, snapshot)
                if os.path.isdir(snapshot_dir):
                    # Verificar model_index.json
                    if not os.path.exists(
                        os.path.join(snapshot_dir, "model_index.json")
                    ):
                        continue
                    # Verificar carpetas críticas
                    valid = True
                    for subfolder in ["unet", "vae", "text_encoder"]:
                        subfolder_path = os.path.join(snapshot_dir, subfolder)
                        if not os.path.exists(subfolder_path) or not os.listdir(
                            subfolder_path
                        ):
                            valid = False
                            break
                    if valid:
                        return True
        except Exception:
            pass
    return False


class ModelDownloadWorker(QThread):
    finished = pyqtSignal(bool, str)  # Emitir estado y mensaje
    progress_updated = pyqtSignal(str, int, int) # Emitir progreso descarga

    def __init__(self, repo_id):
        super().__init__()
        self.repo_id = repo_id
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        from core.utils import get_base_path
        import os
        from huggingface_hub import snapshot_download
        
        cache_dir = os.path.join(get_base_path(), "models", "generative", "hf_cache")
        folder_name = f"models--{self.repo_id.replace('/', '--')}"
        model_path = os.path.join(cache_dir, folder_name)

        if os.path.exists(model_path) and not is_model_downloaded(self.repo_id):
            import shutil
            try:
                shutil.rmtree(model_path)
            except Exception:
                pass

        os.environ["HF_HOME"] = cache_dir

        # Inyectar tqdm global en el mismo proceso para leer progreso y cancelar
        from huggingface_hub.utils import tqdm as hf_tqdm_class
        _original_hf_update = hf_tqdm_class.update

        def _custom_hf_update(tqdm_self, n=1):
            if self.is_cancelled:
                raise InterruptedError("Descarga cancelada por el usuario.")
            
            _original_hf_update(tqdm_self, n)
            if getattr(tqdm_self, "unit", "") == "B" and getattr(tqdm_self, "total", 0):
                self.progress_updated.emit(tqdm_self.desc or "Descargando", tqdm_self.n, tqdm_self.total)
                
                # Loggear progreso sin spam
                pct = int((tqdm_self.n / tqdm_self.total) * 100)
                last_pct = getattr(self, "_last_log_pct", -1)
                if pct % 10 == 0 and pct != last_pct:
                    from studio_logger import logger
                    from core.utils import format_size
                    logger.info(f"Descargando {tqdm_self.desc}: {pct}% ({format_size(tqdm_self.n)} / {format_size(tqdm_self.total)})")
                    self._last_log_pct = pct

        hf_tqdm_class.update = _custom_hf_update

        allow_patterns = [
            "*.json", "*.txt", "scheduler/*", "text_encoder/*",
            "tokenizer/*", "unet/*", "vae/*", "feature_extractor/*",
            "safety_checker/*",
        ]
        
        ignore_patterns = [
            "*fp16*",         # Ignorar pesos 16-bits
            "*non_ema*",      # Ignorar pesos non-ema
            "*.msgpack",      # Ignorar pesos flax
            "*.ckpt",         # Ignorar checkpoints viejos
            "*.h5",           # Ignorar pesos keras
            "*.ot",           # Ignorar pesos rust
        ]

        max_retries = 20
        try:
            for attempt in range(max_retries):
                try:
                    snapshot_download(
                        repo_id=self.repo_id, 
                        allow_patterns=allow_patterns,
                        ignore_patterns=ignore_patterns,
                        resume_download=True,
                        max_workers=8
                    )
                    if not self.is_cancelled:
                        self.finished.emit(True, f"Modelo '{self.repo_id}' descargado con éxito.")
                    break
                except InterruptedError:
                    self.finished.emit(False, "Descarga cancelada por el usuario.")
                    break
                except Exception as e:
                    if self.is_cancelled:
                        break
                    if attempt < max_retries - 1:
                        from studio_logger import logger
                        logger.warning(f"Error de red detectado (Intento {attempt+1}/{max_retries}): {e}. Auto-reanudando...")
                        import time
                        time.sleep(2)
                    else:
                        self.finished.emit(False, f"Fallo al descargar después de {max_retries} intentos: {str(e)}")
        finally:
            # Restaurar tqdm original
            hf_tqdm_class.update = _original_hf_update


class ModelRowWidget(QFrame):
    download_requested = pyqtSignal(str)  # repo_id
    delete_requested = pyqtSignal(str)  # repo_id

    def __init__(self, name, repo_id, desc, size, is_local=False, parent=None):
        super().__init__(parent)
        self.repo_id = repo_id
        self.is_local = is_local

        self.setStyleSheet("""
            QFrame {
                background-color: #111111;
                border: 1px solid #222222;
                border-radius: 6px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Mostrar información
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        self.lbl_name = QLabel(name)
        self.lbl_name.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: white; border: none; background: transparent;"
        )
        info_layout.addWidget(self.lbl_name)

        self.lbl_desc = QLabel(desc)
        self.lbl_desc.setStyleSheet(
            "font-size: 11px; color: #888888; border: none; background: transparent;"
        )
        self.lbl_desc.setWordWrap(True)
        info_layout.addWidget(self.lbl_desc)

        meta_text = f"Local: {repo_id}" if is_local else f"Repo: {repo_id} | {size}"
        self.lbl_meta = QLabel(meta_text)
        self.lbl_meta.setStyleSheet(
            "font-size: 10px; color: #555555; border: none; background: transparent;"
        )
        info_layout.addWidget(self.lbl_meta)

        layout.addLayout(info_layout, stretch=1)

        # Configurar botón acción
        self.btn_action = QPushButton()
        self.btn_action.setFixedWidth(90)
        self.btn_action.setStyleSheet("""
            QPushButton {
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
            }
        """)
        self.btn_action.clicked.connect(self._on_action_clicked)
        layout.addWidget(self.btn_action)

        self.update_status()
        self.setMinimumHeight(75)

    def update_status(self):
        if self.is_local:
            self.btn_action.setText("Quitar")
            self.btn_action.setStyleSheet("""
                QPushButton {
                    background-color: #2a2a2a; color: #ff5555; border: 1px solid #444;
                }
                QPushButton:hover {
                    background-color: #3a1a1a; border-color: #ff5555;
                }
            """)
        else:
            downloaded = is_model_downloaded(self.repo_id)
            if downloaded:
                self.btn_action.setText("Borrar")
                self.btn_action.setStyleSheet("""
                    QPushButton {
                        background-color: #2b1616; color: #ff6666; border: 1px solid #5a2828;
                    }
                    QPushButton:hover {
                        background-color: #4a1e1e;
                    }
                """)
            else:
                self.btn_action.setText("Descargar")
                self.btn_action.setStyleSheet("""
                    QPushButton {
                        background-color: #007acc; color: white; border: none;
                    }
                    QPushButton:hover {
                        background-color: #0098ff;
                    }
                """)

    def _on_action_clicked(self):
        if self.is_local:
            self.delete_requested.emit(self.repo_id)
        else:
            if is_model_downloaded(self.repo_id):
                self.delete_requested.emit(self.repo_id)
            else:
                self.download_requested.emit(self.repo_id)


class GenerativeDialog(QDialog):
    def __init__(self, run_callback, img_np, parent=None):
        super().__init__(parent)
        self.run_callback = run_callback
        self.img_np = img_np
        self.setWindowTitle("Transferencia de Estilo IA")
        self.setFixedSize(550, 720)

        self.setStyleSheet("""
            QDialog { background-color: #050505; color: white; }
            QLabel { font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;}
            QComboBox, QLineEdit { background-color: #1a1a1a; border: 1px solid #333; border-radius: 6px; padding: 6px; color: white; }
            QPushButton { background-color: #1a1a1a; color: white; border: 1px solid #333; border-radius: 6px; padding: 6px 12px; }
            QPushButton:hover { background-color: #333; }
            QPushButton#ExecuteBtn { background-color: #007acc; color: white; border-radius: 8px; padding: 10px; font-weight: bold; border: none; }
            QPushButton#ExecuteBtn:hover:enabled { background-color: #0098ff; }
            QPushButton#ExecuteBtn:disabled { background-color: #333; color: #666; }
            QPushButton#CancelBtn { background-color: transparent; color: #aaa; border: 1px solid #444; border-radius: 8px; padding: 10px; }
            QPushButton#CancelBtn:hover { background-color: #222; color: white; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(12)

        # Configurar modo operación
        layout.addWidget(QLabel("0. Modo de Operación"))
        self.combo_mode = QComboBox()
        self.combo_mode.setMinimumHeight(30)
        self.combo_mode.addItems(
            [
                "Imagen a Imagen (Transferencia de Estilo)",
                "Texto a Imagen (Generar desde cero)",
                "Inpainting Mágico (Auto-Enmascarado por Texto)",
            ]
        )
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self.combo_mode)
        
        # Objeto objetivo para Inpainting Mágico
        self.h_target = QHBoxLayout()
        self.lbl_target = QLabel("Objeto a Modificar (Inglés recomendado):")
        self.input_target = QLineEdit()
        self.input_target.setPlaceholderText("Ej: hat, shirt, face, background...")
        self.input_target.setMinimumHeight(30)
        self.h_target.addWidget(self.lbl_target)
        self.h_target.addWidget(self.input_target)
        
        # Contenedor para h_target para poder ocultarlo fácil
        self.target_container = QWidget()
        self.target_container.setLayout(self.h_target)
        self.target_container.hide()
        layout.addWidget(self.target_container)

        # Configurar modelo base
        layout.addWidget(QLabel("1. Modelo Base (Checkpoint)"))
        lbl_info = QLabel(
            "Selecciona un modelo. La tarjeta abajo mostrará sus detalles y estado."
        )
        lbl_info.setStyleSheet("color: #888; font-size: 11px; font-weight: normal;")
        layout.addWidget(lbl_info)

        h_base = QHBoxLayout()
        self.combo_base = QComboBox()
        self.combo_base.setMinimumHeight(30)
        self.combo_base.setEditable(False)
        self.combo_base.currentIndexChanged.connect(self._on_combo_base_changed)
        h_base.addWidget(self.combo_base, stretch=1)

        self.btn_browse_base = QPushButton("📂 Examinar local...")
        self.btn_browse_base.setMinimumHeight(30)
        self.btn_browse_base.clicked.connect(self._browse_base)
        h_base.addWidget(self.btn_browse_base)

        layout.addLayout(h_base)

        # Crear contenedor tarjeta
        self.model_card_container = QVBoxLayout()
        self.model_card_container.setContentsMargins(0, 2, 0, 8)
        self.current_model_card = None
        layout.addLayout(self.model_card_container)

        # Configurar lora
        layout.addWidget(QLabel("2. Estilo a Aplicar (LoRA)"))
        lbl_lora_info = QLabel(
            "Opcional. Selecciona un archivo de estilo local (.safetensors)."
        )
        lbl_lora_info.setStyleSheet(
            "color: #888; font-size: 11px; font-weight: normal;"
        )
        layout.addWidget(lbl_lora_info)

        h_lora = QHBoxLayout()
        self.combo_lora = QComboBox()
        self.combo_lora.setMinimumHeight(30)
        self.combo_lora.setEditable(True)
        self.combo_lora.setMinimumWidth(350)
        self.combo_lora.currentTextChanged.connect(self._on_lora_changed)
        btn_lora = QPushButton("Examinar...")
        btn_lora.setMinimumHeight(30)
        btn_lora.clicked.connect(self._browse_lora)
        h_lora.addWidget(self.combo_lora)
        h_lora.addWidget(btn_lora)
        layout.addLayout(h_lora)

        # Configurar trigger word
        h_trigger = QHBoxLayout()
        h_trigger.addWidget(QLabel("Palabra Clave (Trigger):"))
        self.input_trigger = QLineEdit()
        self.input_trigger.setMinimumHeight(30)
        self.input_trigger.setPlaceholderText("Opcional. Se añadirá al autocompletar.")
        h_trigger.addWidget(self.input_trigger)
        layout.addLayout(h_trigger)

        # Configurar denoising
        self.lbl_denoising = QLabel("3. Fuerza del Cambio: 50%")
        layout.addWidget(self.lbl_denoising)
        self.slider_denoising = QSlider(Qt.Orientation.Horizontal)
        self.slider_denoising.setMinimumHeight(20)
        self.slider_denoising.setRange(0, 100)
        self.slider_denoising.setValue(50)
        self.slider_denoising.valueChanged.connect(self._on_slider_change)
        layout.addWidget(self.slider_denoising)

        # Configurar pasos inferencia
        self.lbl_steps = QLabel("Pasos Base (Calidad): 30")
        layout.addWidget(self.lbl_steps)
        self.slider_steps = QSlider(Qt.Orientation.Horizontal)
        self.slider_steps.setMinimumHeight(20)
        self.slider_steps.setRange(15, 50)
        self.slider_steps.setValue(30)
        self.slider_steps.valueChanged.connect(self._update_steps_label)
        layout.addWidget(self.slider_steps)

        # Configurar batch size
        h_batch = QHBoxLayout()
        h_batch.addWidget(QLabel("Cantidad de Variaciones (Lote):"))
        self.spin_batch = QSpinBox()
        self.spin_batch.setMinimumHeight(28)
        self.spin_batch.setRange(1, 8)
        self.spin_batch.setValue(1)
        self.spin_batch.setStyleSheet(
            "background-color: #1a1a1a; color: white; border: 1px solid #333; padding: 4px; border-radius: 4px;"
        )
        h_batch.addWidget(self.spin_batch)
        layout.addLayout(h_batch)

        # Configurar prompt
        layout.addWidget(QLabel("4. Descripción (Prompt)"))

        h_prompt = QHBoxLayout()
        self.input_prompt = QLineEdit()
        self.input_prompt.setMinimumHeight(30)
        self.input_prompt.setPlaceholderText("Ej: estilo acuarela, colores vivos...")

        self.combo_enhance_length = QComboBox()
        self.combo_enhance_length.addItems(["Poco", "Medio", "Largo"])
        self.combo_enhance_length.setVisible(False)
        self.combo_enhance_length.setStyleSheet(
            "background-color: #1a1a1a; color: white; border: 1px solid #333; border-radius: 6px; padding: 6px;"
        )

        self.btn_auto_prompt = QPushButton("✨ Autocompletar")
        self.btn_auto_prompt.setMinimumHeight(30)
        self.btn_auto_prompt.setStyleSheet(
            "background-color: #d83b01; font-weight: bold;"
        )
        self.btn_auto_prompt.clicked.connect(self._run_auto_prompt)

        self.input_prompt.textChanged.connect(self._on_prompt_changed)

        h_prompt.addWidget(self.input_prompt)
        h_prompt.addWidget(self.combo_enhance_length)
        h_prompt.addWidget(self.btn_auto_prompt)
        layout.addLayout(h_prompt)

        # Configurar layout descarga
        self.download_layout = QVBoxLayout()
        self.download_layout.setSpacing(4)

        self.lbl_download_status = QLabel("")
        self.lbl_download_status.setStyleSheet(
            "color: #00ff88; font-size: 11px; font-weight: bold;"
        )
        self.lbl_download_status.hide()
        self.download_layout.addWidget(self.lbl_download_status)

        self.download_progress = QProgressBar()
        self.download_progress.setFixedHeight(8)
        self.download_progress.setStyleSheet("""
            QProgressBar {
                background-color: #1a1a1a;
                border: 1px solid #333;
                border-radius: 4px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #007acc;
                border-radius: 3px;
            }
        """)
        self.download_progress.setRange(0, 0)
        self.download_progress.hide()
        self.download_layout.addWidget(self.download_progress)

        layout.addLayout(self.download_layout)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(
            "color: #00ff88; font-size: 11px; font-weight: bold;"
        )
        self.lbl_status.hide()
        layout.addWidget(self.lbl_status, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()

        # Configurar botones finales
        h_btns = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("CancelBtn")
        btn_cancel.setMinimumHeight(36)
        btn_cancel.clicked.connect(self._on_cancel_clicked)

        self.btn_exec = QPushButton("Aplicar Estilo")
        self.btn_exec.setObjectName("ExecuteBtn")
        self.btn_exec.setMinimumHeight(36)
        self.btn_exec.clicked.connect(self._execute)

        h_btns.addWidget(btn_cancel)
        h_btns.addWidget(self.btn_exec)
        layout.addLayout(h_btns)

        self.local_models = []
        self.available_models_data = []
        self.selected_base_model = None
        self.download_worker = None

        self._populate_models()
        self._populate_loras()
        self._on_mode_changed()
        self._on_lora_changed()

    def _on_lora_changed(self):
        text = self.combo_lora.currentText().strip()
        has_lora = bool(text and text != "Ninguno")
        self.input_trigger.setEnabled(has_lora)
        if not has_lora:
            self.input_trigger.clear()

    def _on_prompt_changed(self):
        is_txt2img = self.combo_mode.currentIndex() == 1
        has_text = bool(self.input_prompt.text().strip())
        if is_txt2img:
            self.btn_auto_prompt.setEnabled(has_text)
        else:
            self.btn_auto_prompt.setEnabled(True)

    def _on_mode_changed(self):
        is_txt2img = self.combo_mode.currentIndex() == 1
        is_inpaint = self.combo_mode.currentIndex() == 2
        
        self.lbl_denoising.setVisible(not is_txt2img)
        self.slider_denoising.setVisible(not is_txt2img)
        self.combo_enhance_length.setVisible(is_txt2img)
        self.target_container.setVisible(is_inpaint)

        # Actualizar botón prompt
        if is_txt2img:
            self.btn_auto_prompt.setText("✨ Mejorar Prompt")
        else:
            self.btn_auto_prompt.setText("✨ Autocompletar")

        self._on_prompt_changed()
        self._update_execute_button()
        if hasattr(self, "slider_steps"):
            self._update_steps_label()

    def _populate_models(self):
        self.combo_base.blockSignals(True)
        self.combo_base.clear()
        self.available_models_data = []

        default_models = [
            {
                "name": "DreamShaper 8 [Anime / Semi-Real]",
                "repo": "Lykon/dreamshaper-8",
                "desc": "Anime y semi-realismo de alta calidad. Recomendado.",
                "size": "~2.0 GB",
            },
            {
                "name": "ReV Animated v1.2.2 [Fantasía / 2.5D]",
                "repo": "stablediffusionapi/rev-animated",
                "desc": "Estilo 2.5D, fantasía y semi-realismo increíble.",
                "size": "~2.0 GB",
            },
            {
                "name": "Absolute Reality v1.8.1 [Fotorealismo]",
                "repo": "Lykon/AbsoluteReality",
                "desc": "Realismo fotográfico y retratos excelentes.",
                "size": "~2.0 GB",
            },
            {
                "name": "EpicRealism Pure V5 [Realismo / Paisaje]",
                "repo": "stablediffusionapi/epicrealism",
                "desc": "Fotografía realista extrema y paisajes naturales.",
                "size": "~2.0 GB",
            },
            {
                "name": "Anything V5 [Anime]",
                "repo": "genai-archive/anything-v5",
                "desc": "Modelo enfocado en anime de alta definición.",
                "size": "~2.0 GB",
            },
            {
                "name": "MeinaMix V11 [Anime / Ilustración]",
                "repo": "stablediffusionapi/meinamix",
                "desc": "Ilustración digital y anime de alta gama.",
                "size": "~2.0 GB",
            },
            {
                "name": "Counterfeit V3.0 [Anime Pro]",
                "repo": "stablediffusionapi/counterfeit-v30",
                "desc": "Ilustraciones de anime de nivel profesional.",
                "size": "~2.1 GB",
            },
            {
                "name": "Anything V3.0 [Anime Retro]",
                "repo": "Linaqruf/anything-v3.0",
                "desc": "Clásico de anime retro y moderno.",
                "size": "~2.0 GB",
            },
            {
                "name": "Stable Diffusion 1.5 [Generalista]",
                "repo": "runwayml/stable-diffusion-v1-5",
                "desc": "Modelo realista y generalista estándar.",
                "size": "~2.0 GB",
            },
        ]

        for m in default_models:
            m_data = {
                "name": m["name"],
                "repo": m["repo"],
                "desc": m["desc"],
                "size": m["size"],
                "is_local": False,
            }
            self.available_models_data.append(m_data)
            self.combo_base.addItem(m["name"], m["repo"])

        base_path = get_base_path()
        base_models_dir = os.path.join(base_path, "models", "generative", "base_models")
        if os.path.exists(base_models_dir):
            for f in os.listdir(base_models_dir):
                if f.endswith((".safetensors", ".ckpt")):
                    path = os.path.join(base_models_dir, f)
                    name = f"Local: {f}"
                    m_data = {
                        "name": name,
                        "repo": path,
                        "desc": "Cargado automáticamente desde base_models.",
                        "size": "~2.0 GB",
                        "is_local": True,
                    }
                    self.available_models_data.append(m_data)
                    self.combo_base.addItem(name, path)

        for path in self.local_models:
            name = f"Local: {os.path.basename(path)}"
            m_data = {
                "name": name,
                "repo": path,
                "desc": "Modelo seleccionado manualmente.",
                "size": "Variable",
                "is_local": True,
            }
            self.available_models_data.append(m_data)
            self.combo_base.addItem(name, path)

        self.combo_base.blockSignals(False)

        if self.selected_base_model:
            idx = self.combo_base.findData(self.selected_base_model)
            if idx >= 0:
                self.combo_base.setCurrentIndex(idx)
            elif self.combo_base.count() > 0:
                self.combo_base.setCurrentIndex(0)
        else:
            if self.combo_base.count() > 0:
                self.combo_base.setCurrentIndex(0)

        self._on_combo_base_changed()

    def _on_combo_base_changed(self):
        repo_id = self.combo_base.currentData()
        if not repo_id:
            return
        self.selected_base_model = repo_id

        if self.current_model_card:
            self.model_card_container.removeWidget(self.current_model_card)
            self.current_model_card.deleteLater()
            self.current_model_card = None

        m_data = next(
            (m for m in self.available_models_data if m["repo"] == repo_id), None
        )
        if m_data:
            self.current_model_card = ModelRowWidget(
                m_data["name"],
                m_data["repo"],
                m_data["desc"],
                m_data["size"],
                is_local=m_data["is_local"],
            )
            self.current_model_card.download_requested.connect(
                self._on_download_requested
            )
            self.current_model_card.delete_requested.connect(self._on_delete_requested)
            self.model_card_container.addWidget(self.current_model_card)

        self._update_execute_button()

    def _update_execute_button(self):
        if not self.selected_base_model:
            self.btn_exec.setEnabled(False)
            self.btn_exec.setText("Selecciona un modelo")
            return

        action_text = (
            "Aplicar Estilo"
            if self.combo_mode.currentIndex() == 0
            else "Generar Imagen"
        )

        is_local = os.path.isabs(self.selected_base_model) or os.path.exists(
            self.selected_base_model
        )
        if is_local:
            self.btn_exec.setEnabled(True)
            self.btn_exec.setText(action_text)
        else:
            downloaded = is_model_downloaded(self.selected_base_model)
            if downloaded:
                self.btn_exec.setEnabled(True)
                self.btn_exec.setText(action_text)
            else:
                self.btn_exec.setEnabled(False)
                self.btn_exec.setText("Descarga requerida")

    def _on_download_requested(self, repo_id):
        if self.download_worker and self.download_worker.isRunning():
            QMessageBox.warning(
                self, "Atención", "Ya hay una descarga en curso. Espera a que termine."
            )
            return

        self._set_ui_enabled(False)
        self.lbl_download_status.setText(
            f"Descargando {repo_id}... Esto puede tardar varios minutos."
        )
        self.lbl_download_status.show()
        self.download_progress.show()

        self.download_worker = ModelDownloadWorker(repo_id)
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.progress_updated.connect(self._update_progress)
        self.download_worker.start()

    def _update_progress(self, desc, downloaded, total):
        from core.utils import format_size
        pct = int((downloaded / total) * 100) if total > 0 else 0
        self.download_progress.setMaximum(100)
        self.download_progress.setValue(pct)
        # Mostrar progreso formateado
        self.lbl_download_status.setText(
            f"Descargando {desc}... ({format_size(downloaded)} / {format_size(total)})"
        )

    def _on_cancel_clicked(self):
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.cancel()
        self.close()
        
    def closeEvent(self, event):
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.cancel()
        super().closeEvent(event)

    def _on_download_finished(self, success, message):
        self.lbl_download_status.hide()
        self.download_progress.hide()
        self._set_ui_enabled(True)

        if success:
            QMessageBox.information(self, "Descarga Completada", message)
        else:
            QMessageBox.critical(
                self,
                "Error de Descarga",
                f"Ocurrió un error al descargar el modelo:\n{message}",
            )

        if self.current_model_card:
            self.current_model_card.update_status()

        self._update_execute_button()

    def _on_delete_requested(self, repo_id):
        is_local = os.path.isabs(repo_id) or os.path.exists(repo_id)
        if is_local:
            if repo_id in self.local_models:
                self.local_models.remove(repo_id)
            if self.selected_base_model == repo_id:
                self.selected_base_model = None
            self._populate_models()
        else:
            reply = QMessageBox.question(
                self,
                "Confirmar Eliminación",
                f"¿Estás seguro de que deseas eliminar el modelo '{repo_id}'?\nEsto liberará aproximadamente 2 GB de espacio en disco.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    cache_dir = os.path.join(
                        get_base_path(), "models", "generative", "hf_cache"
                    )
                    folder_name = f"models--{repo_id.replace('/', '--')}"
                    model_path = os.path.join(cache_dir, folder_name)
                    if os.path.exists(model_path):
                        shutil.rmtree(model_path)
                        QMessageBox.information(
                            self,
                            "Eliminado",
                            f"Modelo '{repo_id}' eliminado correctamente.",
                        )
                    else:
                        QMessageBox.warning(
                            self,
                            "Error",
                            "No se encontró la carpeta del modelo en el disco.",
                        )
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Error al eliminar",
                        f"No se pudo eliminar el modelo:\n{str(e)}",
                    )

                if self.current_model_card:
                    self.current_model_card.update_status()
                self._update_execute_button()

    def _populate_loras(self):
        self.combo_lora.clear()
        self.combo_lora.addItem("Ninguno", "")
        base_path = get_base_path()
        loras_dir = os.path.join(base_path, "models", "generative", "loras")
        if os.path.exists(loras_dir):
            for f in os.listdir(loras_dir):
                if f.endswith(".safetensors"):
                    self.combo_lora.addItem(
                        f"📁 Local: {f}", os.path.join(loras_dir, f)
                    )

    def _browse_base(self):
        base_dir = os.path.join(get_base_path(), "models", "generative", "base_models")
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar Modelo Base",
            base_dir,
            "Safetensors (*.safetensors);;Checkpoints (*.ckpt)",
        )
        if path:
            if path not in self.local_models:
                self.local_models.append(path)
            self.selected_base_model = path
            self._populate_models()

    def _browse_lora(self):
        lora_dir = os.path.join(get_base_path(), "models", "generative", "loras")
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar LoRA", lora_dir, "Safetensors (*.safetensors)"
        )
        if path:
            self.combo_lora.addItem(f"📂 Seleccionado: {os.path.basename(path)}", path)
            self.combo_lora.setCurrentIndex(self.combo_lora.count() - 1)

    def _on_slider_change(self, val):
        self.lbl_denoising.setText(f"3. Fuerza del Cambio: {val}%")
        self._update_steps_label()

    def _update_steps_label(self):
        base_steps = self.slider_steps.value()
        is_txt2img = self.combo_mode.currentIndex() == 1
        if not is_txt2img:
            strength = self.slider_denoising.value() / 100.0
            actual_steps = max(1, int(base_steps * strength))
            self.lbl_steps.setText(
                f"Pasos Base (Calidad): {base_steps} (Ejecutará: {actual_steps} pasos)"
            )
        else:
            self.lbl_steps.setText(f"Pasos Base (Calidad): {base_steps}")

    def _execute(self):
        base_model_path = self.selected_base_model

        lora_data = self.combo_lora.currentData()
        lora_path = lora_data if lora_data else self.combo_lora.currentText().strip()

        if not base_model_path:
            QMessageBox.warning(self, "Atención", "Debes seleccionar un Modelo Base.")
            return

        is_cloud = (
            "/" in base_model_path
            and not os.path.exists(base_model_path)
            and not base_model_path.endswith((".safetensors", ".ckpt"))
        )
        if not is_cloud and not os.path.isfile(base_model_path):
            QMessageBox.warning(
                self, "Atención", "El archivo local del modelo base no existe."
            )
            return

        if lora_path and lora_path != "Ninguno" and not os.path.isfile(lora_path):
            QMessageBox.warning(
                self, "Atención", "El archivo LoRA especificado no existe."
            )
            return

        if lora_path == "Ninguno" or lora_path == "":
            lora_path = None

        denoising = self.slider_denoising.value() / 100.0
        prompt = self.input_prompt.text().strip()

        # Inyectar trigger inteligente
        trigger = self.input_trigger.text().strip()
        if trigger and trigger not in prompt:
            prompt = f"{trigger}, {prompt}" if prompt else trigger

        num_images = self.spin_batch.value()

        target_object = self.input_target.text().strip() if self.combo_mode.currentIndex() == 2 else None

        if not lora_path and not prompt:
            QMessageBox.warning(
                self,
                "Atención",
                "Si no usas un LoRA, debes escribir al menos una descripción (Prompt) para guiar a la IA. De lo contrario, no sabrá qué dibujar.",
            )
            return
            
        if self.combo_mode.currentIndex() == 2 and not target_object:
            QMessageBox.warning(self, "Atención", "Debes especificar qué objeto quieres modificar (ej: hat, face, shirt).")
            return

        if self.combo_mode.currentIndex() == 2:
            gen_mode = "inpaint"
        elif self.combo_mode.currentIndex() == 0:
            gen_mode = "img2img"
        else:
            gen_mode = "txt2img"
            
        steps = self.slider_steps.value()
        self.run_callback(
            gen_mode, base_model_path, lora_path, denoising, prompt, num_images, steps, target_object
        )
        self.close()

    def _run_auto_prompt(self):
        is_txt2img = self.combo_mode.currentIndex() == 1

        if is_txt2img:
            current_text = self.input_prompt.text().strip()
            if not current_text:
                QMessageBox.information(
                    self,
                    "Mejorar Prompt",
                    "Escribe al menos una o dos palabras primero (ej: 'un gato') para que la IA sepa qué quieres mejorar.",
                )
                return

            self._set_ui_enabled(False)
            self.lbl_status.setText("Iniciando IA de expansión (GPT-2)...")
            self.lbl_status.show()

            length_mode = self.combo_enhance_length.currentText()
            self.enhancer_worker = PromptEnhancerWorker(current_text, length_mode)
            self.enhancer_worker.progress.connect(self.lbl_status.setText)
            self.enhancer_worker.result_ready.connect(self._on_enhance_finished)
            self.enhancer_worker.error.connect(self._on_auto_prompt_error)
            # Borrar worker terminado
            self.enhancer_worker.finished.connect(self.enhancer_worker.deleteLater)
            self.enhancer_worker.start()
            return

        self._set_ui_enabled(False)
        self.lbl_status.setText("Iniciando motor de visión Moondream2...")
        self.lbl_status.show()

        self.caption_worker = CaptioningWorker(self.img_np)
        self.caption_worker.progress.connect(self.lbl_status.setText)
        self.caption_worker.result_ready.connect(self._on_auto_prompt_finished)
        self.caption_worker.error.connect(self._on_auto_prompt_error)
        # Borrar worker terminado
        self.caption_worker.finished.connect(self.caption_worker.deleteLater)
        self.caption_worker.start()

    def _on_auto_prompt_finished(self, text):
        # Procesar texto moondream
        trigger = self.input_trigger.text().strip()
        if trigger:
            final_text = f"{trigger}, {text}"
        else:
            final_text = text

        self.input_prompt.setText(final_text)
        self.lbl_status.setText("✨ ¡Prompt generado exitosamente!")
        self._set_ui_enabled(True)

    def _on_enhance_finished(self, enhanced_text):
        self.input_prompt.setText(enhanced_text)
        self.lbl_status.setText("✨ ¡Prompt expandido con Inteligencia Artificial!")
        self._set_ui_enabled(True)

    def _on_auto_prompt_error(self, err_msg):
        self.lbl_status.hide()
        self._set_ui_enabled(True)
        QMessageBox.critical(self, "Error al generar prompt", err_msg)

    def _set_ui_enabled(self, enabled):
        self.combo_base.setEnabled(enabled)
        self.btn_browse_base.setEnabled(enabled)
        if self.current_model_card:
            self.current_model_card.setEnabled(enabled)
        self.combo_lora.setEnabled(enabled)
        self.input_trigger.setEnabled(enabled)
        self.slider_denoising.setEnabled(enabled)
        self.slider_steps.setEnabled(enabled)
        self.spin_batch.setEnabled(enabled)
        self.input_prompt.setEnabled(enabled)
        self.btn_auto_prompt.setEnabled(enabled)
        self.btn_exec.setEnabled(enabled)
