from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QMessageBox
)
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QFont

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.setFixedSize(450, 200)
        self.settings = QSettings("FHVT_Studio", "ImageEditor")
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Option 1: Dev Diagnostic
        h1 = QHBoxLayout()
        self.chk_dev_diag = QCheckBox("Mostrar recursos del sistema (CPU, VRAM, etc.)")
        self.chk_dev_diag.setChecked(self.settings.value("show_dev_diag", True, type=bool))
        
        btn_info1 = QPushButton("\ue946") # info icon
        btn_info1.setFont(QFont("Segoe MDL2 Assets", 12))
        btn_info1.setFixedSize(28, 28)
        btn_info1.setToolTip("Información")
        btn_info1.setStyleSheet("QPushButton { border: none; background: transparent; color: #007acc; } QPushButton:hover { color: #005999; }")
        btn_info1.clicked.connect(lambda: QMessageBox.information(
            self, "Información", 
            "Muestra u oculta la barra inferior de diagnóstico que indica el consumo de CPU, RAM y VRAM en tiempo real."
        ))
        
        h1.addWidget(self.chk_dev_diag)
        h1.addWidget(btn_info1)
        h1.addStretch()
        
        # Option 2: Model Caching
        h2 = QHBoxLayout()
        self.chk_model_cache = QCheckBox("Mantener último modelo IA en memoria (caché)")
        self.chk_model_cache.setChecked(self.settings.value("cache_ai_models", True, type=bool))
        
        btn_info2 = QPushButton("\ue946")
        btn_info2.setFont(QFont("Segoe MDL2 Assets", 12))
        btn_info2.setFixedSize(28, 28)
        btn_info2.setToolTip("Información")
        btn_info2.setStyleSheet("QPushButton { border: none; background: transparent; color: #007acc; } QPushButton:hover { color: #005999; }")
        btn_info2.clicked.connect(lambda: QMessageBox.information(
            self, "Información", 
            "Mantiene cargado el último modelo de IA usado en la tarjeta de video para que las próximas ejecuciones sean instantáneas.\n\n"
            "Desactívalo si necesitas que se libere la VRAM inmediatamente al terminar el procesamiento."
        ))
        
        h2.addWidget(self.chk_model_cache)
        h2.addWidget(btn_info2)
        h2.addStretch()
        
        layout.addLayout(h1)
        layout.addLayout(h2)
        layout.addStretch()
        
        btn_save = QPushButton("Guardar Configuración")
        btn_save.setFixedSize(160, 35)
        btn_save.clicked.connect(self.save_settings)
        
        h_btn = QHBoxLayout()
        h_btn.addStretch()
        h_btn.addWidget(btn_save)
        layout.addLayout(h_btn)
        
    def save_settings(self):
        self.settings.setValue("show_dev_diag", self.chk_dev_diag.isChecked())
        self.settings.setValue("cache_ai_models", self.chk_model_cache.isChecked())
        self.accept()
