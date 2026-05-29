from PyQt6.QtWidgets import QHBoxLayout
from qfluentwidgets import FlyoutViewBase
from .factory import make_icon_btn

class MirrorTool(FlyoutViewBase):
    def __init__(self, on_flip_h, on_flip_v, parent=None):
        super().__init__(parent)
        # Usamos un layout con márgenes y espaciado simplificado
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Definimos los botones de forma declarativa (más fácil de ampliar)
        button_configs = [
            ("Espejo Horizontal", 0, on_flip_h),
            ("Espejo Vertical", 90, on_flip_v),
        ]

        for tooltip, rotation, callback in button_configs:
            btn = make_icon_btn("flip.png", tooltip, rotation=rotation, callback=callback)
            layout.addWidget(btn)
