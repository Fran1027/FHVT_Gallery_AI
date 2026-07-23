import os
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QTransform
from PyQt6.QtCore import Qt, QSize

from core.utils import get_base_path

import sys

BASE_DIR = get_base_path()
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# Asegurar compatibilidad paths PyInstaller (_internal)
if getattr(sys, "frozen", False) and not os.path.exists(ASSETS_DIR):
    internal_assets = os.path.join(os.path.dirname(sys.executable), "_internal", "assets")
    if os.path.exists(internal_assets):
        ASSETS_DIR = internal_assets
    elif hasattr(sys, "_MEIPASS"):
        ASSETS_DIR = os.path.join(sys._MEIPASS, "assets")

# Utilizar caché global previniendo duplicidades memoria
_ICON_CACHE = {}


def get_styled_pixmap(filename, color=Qt.GlobalColor.white, rotation=0):
    """Carga, rota y colorea un pixmap con sistema de cache inteligente."""
    # Generar token único derivado de estilo
    # Prevenir colisión métodos Enum Qt
    if hasattr(color, "name") and callable(color.name):
        color_val = color.name()
    else:
        color_val = str(color)

    cache_key = f"{filename}_{color_val}_{rotation}"

    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]

    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        return QPixmap()

    pix = QPixmap(path)
    if pix.isNull():
        return pix

    # Aplicar rotación CSS
    if rotation != 0:
        pix = pix.transformed(
            QTransform().rotate(rotation), Qt.TransformationMode.SmoothTransformation
        )

    # Aplicar tintado (SourceIn) si corresponde
    if color is not None:
        styled_pix = QPixmap(pix.size())
        styled_pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(styled_pix)
        painter.drawPixmap(0, 0, pix)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(styled_pix.rect(), color)
        painter.end()
        pix = styled_pix

    # Almacenar pixmap en caché
    _ICON_CACHE[cache_key] = pix
    return pix


def make_btn(icon_text, tooltip, font, callback=None, object_name=None):
    """Crea un botón estándar con icono de texto (Segoe MDL2)."""
    b = QPushButton(icon_text)
    b.setToolTip(tooltip)
    b.setFont(font)
    b.setFixedSize(36, 36)
    if object_name:
        b.setObjectName(object_name)
    if callback:
        b.clicked.connect(callback)
    return b


def make_icon_btn(
    filename, tooltip, color=Qt.GlobalColor.white, rotation=0, callback=None
):
    """
    Crea un botón con icono de imagen estilizado.
    Versatilidad: Blanco por defecto, color=None para original, o cualquier QColor.
    """
    b = QPushButton()
    b.setToolTip(tooltip)
    b.setFixedSize(36, 36)

    pix = get_styled_pixmap(filename, color, rotation)
    if not pix.isNull():
        b.setIcon(QIcon(pix))
        b.setIconSize(QSize(20, 20))

    if callback:
        b.clicked.connect(callback)
    return b
