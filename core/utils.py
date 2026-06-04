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
