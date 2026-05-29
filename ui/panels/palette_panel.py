from PyQt6.QtWidgets import QFrame, QVBoxLayout, QPushButton
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

class PaletteToolsPanel(QFrame):
    def __init__(self, editor):
        super().__init__(editor.viewer_stack)
        self.editor = editor
        
        self.setFixedWidth(120)
        self.setMinimumHeight(210)
        self.setObjectName("FloatingPalette")
        self.setStyleSheet("""
            QFrame#FloatingPalette {
                background-color: rgba(20, 20, 20, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
            }
        """)
        self.setVisible(False)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(8)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._setup_ui()

    def _setup_ui(self):
        modes = [
            ("color",   "A todo color"),
            ("bright",  "Claros"),
            ("muted",   "Apagados"),
            ("intense", "Intensos"),
            ("dark",    "Oscuros")
        ]
        
        self.side_btns = {}
        for mode, label in modes:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.setFont(QFont("Segoe UI", 9))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # Pass mode explicitly to avoid lambda late binding issues
            btn.clicked.connect(lambda ch, m=mode: self.editor._handle_side_palette_click(m))
            self.layout.addWidget(btn)
            self.side_btns[mode] = btn

    def update_btn_styles(self, mode):
        ACTIVE = "QPushButton { background-color: #007acc; color: white; border: 1px solid #007acc; border-radius: 4px; padding-left: 10px; text-align: left; } QPushButton:hover { background-color: #0088dd; }"
        NORMAL = "QPushButton { background-color: rgba(45, 45, 45, 0.8); color: #ccc; border: 1px solid #444; border-radius: 4px; padding-left: 10px; text-align: left; } QPushButton:hover { background-color: rgba(60, 60, 60, 0.9); color: white; } QPushButton:pressed { background-color: #007acc; }"
        
        for m, btn in self.side_btns.items():
            btn.setStyleSheet(ACTIVE if m == mode else NORMAL)
