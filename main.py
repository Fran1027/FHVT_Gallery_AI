import sys
import os

# Configurar path local de Python
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from core.utils import get_base_path  # noqa: E402

# Redirigir caché de IA al directorio de la app
hf_local_cache = os.path.join(get_base_path(), "models", "generative", "hf_cache")
os.environ["HF_HOME"] = hf_local_cache
os.environ["HF_HUB_CACHE"] = hf_local_cache
os.environ["TRANSFORMERS_CACHE"] = hf_local_cache
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Iniciar motor de hardware
from core.env_setup import ensure_optimal_onnx_runtime
ensure_optimal_onnx_runtime()

from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtGui import QFont, QImageReader  # noqa: E402
from ui.gallery_window import ImageGallery  # noqa: E402

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    # Crear directorios base
    for folder in [
        "models/upscale",
        "models/rmbg",
        "models/depth",
        "models/generative/base_models",
        "models/generative/loras",
        "models/generative/hf_cache",
    ]:
        os.makedirs(os.path.join(get_base_path(), folder), exist_ok=True)

    # Aumentar límite de RAM para QImageReader
    QImageReader.setAllocationLimit(1024)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Inter", 10))

    window = ImageGallery()

    # Cargar imagen desde argumentos (Abrir como...)
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if os.path.exists(path) and os.path.isfile(path):
            window.pending_folder_load = os.path.dirname(os.path.abspath(path))
            window.open_image_tab(path)

    window.show()
    sys.exit(app.exec())
