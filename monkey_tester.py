import sys
import os
import random
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt, QPoint, QPointF, QEvent
from PyQt6.QtGui import QMouseEvent, QFont, QImageReader

# 1. Configuración del Path de Python
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from core.utils import get_base_path
from studio_logger import logger

# Hacer la aplicación 100% portable redirigiendo la caché de IA localmente
hf_local_cache = os.path.join(get_base_path(), "models", "generative", "hf_cache")
os.environ["HF_HOME"] = hf_local_cache
os.environ["HF_HUB_CACHE"] = hf_local_cache
os.environ["TRANSFORMERS_CACHE"] = hf_local_cache
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# 2. Configurar el motor de hardware antes de cargar librerías pesadas
from core.env_setup import ensure_optimal_onnx_runtime
ensure_optimal_onnx_runtime()

from ui.gallery_window import ImageGallery

class MonkeyTester:
    def __init__(self, window):
        self.window = window
        self.timer = QTimer()
        self.timer.timeout.connect(self.act_like_a_monkey)
        self.clicks = 0
        
    def start(self, interval_ms=50):
        """Inicia la tortura al sistema (default: 20 clicks por segundo)"""
        self.timer.start(interval_ms)
        logger.warning(f"🐒 MONKEY TESTER INICIADO a {1000/interval_ms} clics por segundo 🐒")
        
    def act_like_a_monkey(self):
        # 1. Generar coordenadas totalmente aleatorias dentro de la ventana
        x = random.randint(0, self.window.width() - 1)
        y = random.randint(0, self.window.height() - 1)
        
        # 2. Buscar si hay algún widget interactuable en esas coordenadas
        widget = self.window.childAt(x, y)
        if widget:
            # 3. Convertir coordenadas globales a locales del widget
            local_pos = widget.mapFrom(self.window, QPoint(x, y))
            
            local_pos_f = QPointF(local_pos)
            
            # Evento Press
            press_event = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                local_pos_f,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier
            )
            QApplication.postEvent(widget, press_event)
            
            # Evento Release
            release_event = QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                local_pos_f,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier
            )
            QApplication.postEvent(widget, release_event)
            
            self.clicks += 1
            if self.clicks % 100 == 0:
                logger.info(f"🐒 El mono ha realizado {self.clicks} clics aleatorios...")

if __name__ == "__main__":
    # --- BLINDAJE DE DISTRIBUCIÓN ---
    for folder in [
        "models/upscale",
        "models/rmbg",
        "models/depth",
        "models/generative/base_models",
        "models/generative/loras",
        "models/generative/hf_cache",
    ]:
        os.makedirs(os.path.join(get_base_path(), folder), exist_ok=True)

    # Elevar el límite de asignación de Qt
    QImageReader.setAllocationLimit(1024)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Inter", 10))

    window = ImageGallery()

    # --- ENCIERRO DE SEGURIDAD ---
    # Forzar la ruta a la carpeta de pruebas y deshabilitar el botón de abrir carpeta
    # para evitar que el mono abra un cuadro de diálogo del SO y escape.
    test_folder = r"C:\Users\pisci\Desktop\img\Imagenes random - copia\Imagenes random\img carpeta para pruebas"
    if os.path.exists(test_folder):
        window.set_current_folder(test_folder)
    else:
        logger.error("¡Cuidado! La carpeta de pruebas no existe. Abortando la prueba.")
        sys.exit(1)
        
    window.btn_open_folder.setEnabled(False)
    window.path_edit.setEnabled(False)

    window.show()

    # --- INYECTAR EL MONO ---
    tester = MonkeyTester(window)
    tester.start(interval_ms=50) # Cambia esto a 100 si va muy rápido o a 10 para estrés masivo

    sys.exit(app.exec())
