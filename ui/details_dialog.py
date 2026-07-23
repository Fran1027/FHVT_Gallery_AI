import os
import datetime
from PIL import Image
from PIL.ExifTags import TAGS
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QCheckBox,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
    QFormLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

class DetallesDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.setWindowTitle("Detalles de la Imagen")
        self.setMinimumWidth(400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.layout = QVBoxLayout(self)

        # Información Básica
        self.form_layout = QFormLayout()
        
        self.lbl_name = QLabel()
        self.lbl_path = QLabel()
        self.lbl_path.setWordWrap(True)
        self.lbl_size = QLabel()
        self.lbl_dimensions = QLabel()
        self.lbl_created = QLabel()
        self.lbl_modified = QLabel()

        self.form_layout.addRow("Nombre:", self.lbl_name)
        self.form_layout.addRow("Ruta:", self.lbl_path)
        self.form_layout.addRow("Peso:", self.lbl_size)
        self.form_layout.addRow("Dimensiones:", self.lbl_dimensions)
        self.form_layout.addRow("Creado:", self.lbl_created)
        self.form_layout.addRow("Modificado:", self.lbl_modified)
        
        self.layout.addLayout(self.form_layout)

        # Checkbox Avanzado
        self.cb_advanced = QCheckBox("Mostrar Detalles Avanzados")
        self.cb_advanced.stateChanged.connect(self.toggle_advanced)
        self.layout.addWidget(self.cb_advanced)

        # Área de texto avanzado
        self.text_advanced = QTextEdit()
        self.text_advanced.setReadOnly(True)
        self.text_advanced.setVisible(False)
        self.layout.addWidget(self.text_advanced)

        # Botón Cerrar
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)
        self.layout.addLayout(btn_layout)

        self.load_basic_info()
        self.advanced_loaded = False

    def load_basic_info(self):
        stat = os.stat(self.file_path)
        
        # Nombre y Ruta
        self.lbl_name.setText(os.path.basename(self.file_path))
        self.lbl_path.setText(self.file_path)
        
        # Peso
        size_bytes = stat.st_size
        if size_bytes < 1024 * 1024:
            size_str = f"{size_bytes / 1024:.2f} KB"
        else:
            size_str = f"{size_bytes / (1024 * 1024):.2f} MB"
        self.lbl_size.setText(size_str)
        
        # Dimensiones rápidas con QPixmap
        pix = QPixmap(self.file_path)
        if not pix.isNull():
            self.lbl_dimensions.setText(f"{pix.width()} x {pix.height()} px")
        else:
            self.lbl_dimensions.setText("Desconocido")
            
        # Fechas
        created = datetime.datetime.fromtimestamp(stat.st_ctime)
        modified = datetime.datetime.fromtimestamp(stat.st_mtime)
        self.lbl_created.setText(created.strftime("%Y-%m-%d %H:%M:%S"))
        self.lbl_modified.setText(modified.strftime("%Y-%m-%d %H:%M:%S"))

    def toggle_advanced(self, state):
        is_checked = state == Qt.CheckState.Checked.value
        self.text_advanced.setVisible(is_checked)
        if is_checked:
            if not self.advanced_loaded:
                self.load_advanced_info()
            self.resize(500, 600)
        else:
            self.resize(400, self.minimumHeight())

    def load_advanced_info(self):
        self.advanced_loaded = True
        lines = []
        try:
            with Image.open(self.file_path) as img:
                lines.append("=== INFORMACIÓN DE PIL ===")
                lines.append(f"Formato: {img.format}")
                lines.append(f"Modo: {img.mode}")
                lines.append(f"Tamaño: {img.size}")
                lines.append(f"Animado: {getattr(img, 'is_animated', False)}")
                if getattr(img, 'n_frames', 1) > 1:
                    lines.append(f"Frames: {img.n_frames}")
                
                info = img.info
                if info:
                    lines.append("\n=== METADATOS INTERNOS ===")
                    for k, v in info.items():
                        if k == "exif":
                            continue # Se procesa por separado
                        # Truncar valores muy largos (ej. perfiles ICC binarios)
                        val_str = str(v)
                        if len(val_str) > 500:
                            val_str = val_str[:500] + "... [truncado]"
                        lines.append(f"{k}: {val_str}")

                # EXIF
                exif_data = img.getexif()
                if exif_data:
                    lines.append("\n=== DATOS EXIF ===")
                    for tag_id, value in exif_data.items():
                        tag_name = TAGS.get(tag_id, tag_id)
                        # Evitar imprimir binarios gigantes
                        if isinstance(value, bytes):
                            if len(value) > 100:
                                value = f"<Datos binarios: {len(value)} bytes>"
                        lines.append(f"{tag_name}: {value}")
                else:
                    lines.append("\n=== DATOS EXIF ===")
                    lines.append("No se encontró información EXIF.")
                    
        except Exception as e:
            lines.append(f"Error extrayendo detalles avanzados:\n{str(e)}")
            
        self.text_advanced.setPlainText("\n".join(lines))
