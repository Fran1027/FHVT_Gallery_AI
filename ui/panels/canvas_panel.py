from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLabel, QSpinBox
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt

class CanvasToolsPanel(QFrame):
    def __init__(self, editor):
        super().__init__(editor.viewer_stack)
        self.editor = editor
        
        self.setFixedWidth(140)
        self.setMinimumHeight(350)
        self.setObjectName("FloatingCanvas")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("""
            QFrame#FloatingCanvas {
                background-color: rgba(30, 30, 30, 0.6);
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
        btn_style = """
            QPushButton {
                background-color: rgba(45, 45, 45, 0.8);
                color: #ccc;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px 10px;
                text-align: left;
            }
            QPushButton:hover { background-color: rgba(60, 60, 60, 0.9); color: white; }
            QPushButton:pressed { background-color: #007acc; }
        """

        self.canvas_color_btn = QPushButton("Color")
        self.canvas_color_btn.setFont(QFont("Segoe UI", 9))
        self.canvas_color_btn.setStyleSheet(btn_style)
        self.canvas_color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.canvas_color_indicator = QPushButton()
        self.canvas_color_indicator.setFixedSize(18, 18)
        self.canvas_color_indicator.setToolTip("Cambiar color...")
        c_hex = QColor(self.editor.canvas_bg_color).name()
        self.canvas_color_indicator.setStyleSheet(f"background-color: {c_hex}; border: 1px solid #aaa; border-radius: 2px;")
        
        btn_layout = QHBoxLayout(self.canvas_color_btn)
        btn_layout.setContentsMargins(0, 0, 5, 0)
        btn_layout.addStretch()
        btn_layout.addWidget(self.canvas_color_indicator)
        
        self.canvas_color_btn.clicked.connect(self.editor.activate_current_canvas_color)
        self.canvas_color_indicator.clicked.connect(self.editor.choose_custom_color)
        
        self.canvas_trans_btn = QPushButton("Transparente")
        self.canvas_trans_btn.setFont(QFont("Segoe UI", 9))
        self.canvas_trans_btn.setStyleSheet(btn_style)
        self.canvas_trans_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.canvas_trans_btn.clicked.connect(self.editor.activate_canvas_trans)

        self.layout.addWidget(self.canvas_color_btn)
        self.layout.addWidget(self.canvas_trans_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #444;")
        self.layout.addWidget(sep)
        
        unit_layout = QHBoxLayout()
        lbl_params = QLabel("Dimensiones:")
        lbl_params.setStyleSheet("color: #888; font-size: 10px; font-weight: bold;")
        
        self.canvas_unit_combo = QComboBox()
        self.canvas_unit_combo.addItems(["Píxeles (px)", "Porcentaje (%)"])
        self.canvas_unit_combo.setStyleSheet("""
            QComboBox { background-color: #1a1a1a; color: white; border: 1px solid #444; border-radius: 3px; padding: 2px; font-size: 10px; }
            QComboBox::drop-down { border: none; }
        """)
        self.canvas_unit_combo.currentIndexChanged.connect(self.editor._on_canvas_unit_changed)
        
        unit_layout.addWidget(lbl_params)
        unit_layout.addStretch()
        unit_layout.addWidget(self.canvas_unit_combo)
        self.layout.addLayout(unit_layout)

        self.spinboxes = {}
        spin_style = "QSpinBox { background-color: #1a1a1a; color: white; border: 1px solid #444; border-radius: 3px; padding: 3px; } QSpinBox::up-button, QSpinBox::down-button { width: 0px; }"
        for direction, icon in [("T", "Arriba"), ("B", "Abajo"), ("L", "Izquierda"), ("R", "Derecha")]:
            row = QHBoxLayout()
            lbl = QLabel(icon)
            lbl.setStyleSheet("color: #ccc; font-size: 11px;")
            sb = QSpinBox()
            sb.setRange(0, 5000)
            sb.setStyleSheet(spin_style)
            sb.valueChanged.connect(self.editor._on_canvas_spinbox_changed)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(sb)
            self.layout.addLayout(row)
            self.spinboxes[direction] = sb
            
        self.layout.addSpacing(10)
        
        self.canvas_action_layout = QHBoxLayout()
        self.canvas_action_layout.setSpacing(8)
        icon_font = QFont("Segoe MDL2 Assets", 12)
        
        def _make_action_btn(icon, tooltip, is_primary=True):
            btn = QPushButton(icon)
            btn.setFont(icon_font)
            btn.setToolTip(tooltip)
            btn.setFixedHeight(30)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if is_primary:
                btn.setStyleSheet("QPushButton { background-color: #007acc; color: white; border: none; border-radius: 4px; } QPushButton:hover { background-color: #0088dd; }")
            else:
                btn.setStyleSheet("QPushButton { background-color: transparent; color: #ccc; border: 1px solid #444; border-radius: 4px; } QPushButton:hover { background-color: rgba(255,255,255,0.1); color: white; }")
            self.canvas_action_layout.addWidget(btn)
            return btn
            
        self.btn_canvas_ok = _make_action_btn("\uE73E", "Aplicar Lienzo (Enter)")
        self.btn_canvas_cancel = _make_action_btn("\uE711", "Cancelar (Esc)", is_primary=False)
        self.btn_canvas_ok.clicked.connect(self.editor.confirm_canvas)
        self.btn_canvas_cancel.clicked.connect(self.editor.cancel_canvas_action)
        
        self.layout.addLayout(self.canvas_action_layout)

    def update_btn_styles(self, mode):
        ACTIVE = "QPushButton { background-color: rgba(0, 122, 204, 0.4); color: white; border: 1px solid #007acc; border-radius: 4px; padding: 8px 10px; text-align: left; }"
        NORMAL = "QPushButton { background-color: rgba(45, 45, 45, 0.8); color: #ccc; border: 1px solid #444; border-radius: 4px; padding: 8px 10px; text-align: left; } QPushButton:hover { background-color: rgba(60, 60, 60, 0.9); color: white; } QPushButton:pressed { background-color: #007acc; }"
        
        self.canvas_color_btn.setStyleSheet(ACTIVE if mode == 'color' else NORMAL)
        self.canvas_trans_btn.setStyleSheet(ACTIVE if mode == 'trans' else NORMAL)
        
        c_hex = QColor(self.editor.canvas_bg_color).name()
        self.canvas_color_indicator.setStyleSheet(f"background-color: {c_hex}; border: 1px solid #aaa; border-radius: 2px;")
