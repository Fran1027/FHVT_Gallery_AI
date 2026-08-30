import os
import sys


def get_base_path():
    """Detecta la ruta base de ejecución, compatible con Nuitka/Freeze/PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def format_size(bytes_val):
    """Versión optimizada y escalable (hasta Terabytes o más)."""
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.2f} EB"


def excede_limite_megapixeles(pixmap, max_mp=4.0):
    if pixmap.isNull():
        return False
    w, h = pixmap.width(), pixmap.height()
    mp = (w * h) / 1_000_000
    return mp > max_mp


# --- REGISTRO DE SOPORTE AVIF / HEIC VÍA PILLOW ---
try:
    import pillow_avif  # noqa: F401
except ImportError:
    pass

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass


def load_qimage_pillow(file_path, target_size=None):
    """Fallback para decodificar formatos no nativos de Qt (AVIF, HEIC, etc.) usando Pillow."""
    try:
        from PIL import Image, ImageOps
        from PyQt6.QtGui import QImage
        with Image.open(file_path) as im:
            im = ImageOps.exif_transpose(im)
            width, height = im.size
            if target_size:
                im.thumbnail(target_size, Image.Resampling.LANCZOS)
            im = im.convert("RGBA")
            data = im.tobytes("raw", "RGBA")
            qim = QImage(data, im.width, im.height, QImage.Format.Format_RGBA8888)
            return qim.copy(), width, height
    except Exception:
        from PyQt6.QtGui import QImage
        return QImage(), 0, 0


def load_pixmap_safely(file_path):
    """Carga un QPixmap de manera segura, probando QPixmap nativo y luego fallback con Pillow (AVIF/HEIC/etc)."""
    from PyQt6.QtGui import QPixmap
    if not file_path or not os.path.exists(file_path):
        return QPixmap()
    pix = QPixmap(file_path)
    if not pix.isNull():
        return pix
    qim, _, _ = load_qimage_pillow(file_path)
    if not qim.isNull():
        return QPixmap.fromImage(qim)
    return QPixmap()

