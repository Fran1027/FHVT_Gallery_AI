import sys
import os

# 1. Configuración del Path de Python (Crucial para que ui/ encuentre a core/)
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from core.utils import get_base_path  # noqa: E402

# Hacer la aplicación 100% portable redirigiendo la caché de IA localmente al directorio de la app
hf_local_cache = os.path.join(get_base_path(), "models", "generative", "hf_cache")
os.environ["HF_HOME"] = hf_local_cache
os.environ["HF_HUB_CACHE"] = hf_local_cache
os.environ["TRANSFORMERS_CACHE"] = hf_local_cache
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# 2. Configurar el motor de hardware antes de cargar librerías pesadas
from core.env_setup import ensure_optimal_onnx_runtime
ensure_optimal_onnx_runtime()

from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtGui import QFont, QImageReader  # noqa: E402
from ui.gallery_window import ImageGallery  # noqa: E402

if __name__ == "__main__":
    # --- BLINDAJE DE DISTRIBUCIÓN (Movido aquí) ---
    for folder in [
        "models/upscale",
        "models/rmbg",
        "models/depth",
        "models/generative/base_models",
        "models/generative/loras",
        "models/generative/hf_cache",
    ]:
        os.makedirs(os.path.join(get_base_path(), folder), exist_ok=True)

    # Elevar el límite de asignación de Qt a 1024 Megabytes para soportar upscaling masivos
    QImageReader.setAllocationLimit(1024)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Inter", 10))

    window = ImageGallery()

    # --- SOPORTE PARA ABRIR COMO PREDETERMINADO ---
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if os.path.exists(path) and os.path.isfile(path):
            window.pending_folder_load = os.path.dirname(os.path.abspath(path))
            window.open_image_tab(path)

    window.show()
    sys.exit(app.exec())
