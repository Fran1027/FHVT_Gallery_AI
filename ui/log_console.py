import os
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
from PyQt6.QtCore import QFileSystemWatcher, Qt
from studio_logger import get_base_path

class LogConsoleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Console (Solo visualización)")
        self.resize(750, 500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        self.setStyleSheet("""
            QDialog { background-color: #0a0a0a; color: white; }
            QTextEdit { background-color: #111; color: #00ff00; font-family: Consolas; font-size: 12px; border: 1px solid #333; padding: 5px; }
            QPushButton { background-color: #1a1a1a; color: white; border: 1px solid #333; border-radius: 4px; padding: 6px 15px; font-weight: bold; }
            QPushButton:hover { background-color: #333; }
        """)
        
        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)
        
        btn_layout = QHBoxLayout()
        self.btn_clear = QPushButton("Limpiar Consola (Clear)")
        self.btn_clear.clicked.connect(self.text_edit.clear)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_clear)
        layout.addLayout(btn_layout)
        
        self.log_file = os.path.join(get_base_path(), "logs", "fhvt_session.log")
        self.last_pos = 0
        
        # Cargar contenido inicial
        self._read_logs()
        
        # Vigilar archivo en tiempo real
        self.watcher = QFileSystemWatcher(self)
        if os.path.exists(self.log_file):
            self.watcher.addPath(self.log_file)
        self.watcher.fileChanged.connect(self._on_file_changed)

    def _read_logs(self):
        if not os.path.exists(self.log_file):
            return
        try:
            import re
            LOG_PATTERN = re.compile(r"^(\d{2}:\d{2}:\d{2}) \| (\s*[\w\-]+) \| ([A-Z]) \| ([^:]+):\s*(.*)$")
            
            with open(self.log_file, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self.last_pos)
                lines = f.readlines()
                self.last_pos = f.tell()
                
                if lines:
                    for line in lines:
                        line = line.rstrip()
                        if not line:
                            continue
                        
                        match = LOG_PATTERN.match(line)
                        if match:
                            timestamp, thread, level, tag, msg = match.groups()
                            
                            time_html = f'<span style="color: #888888;">{timestamp}</span>'
                            
                            # Color de hilo
                            thread_stripped = thread.strip()
                            thread_col = '#c586c0' if thread_stripped == 'MainThread' else '#888888'
                            thread_html = f'<span style="color: {thread_col};">{thread}</span>'
                            
                            # Color de nivel
                            level_colors = {'I': '#4af626', 'D': '#888888', 'W': '#fce94f', 'E': '#ff5555', 'C': '#ff0000'}
                            lvl_col = level_colors.get(level, '#ffffff')
                            lvl_html = f'<span style="color: {lvl_col}; font-weight: bold;">{level}</span>'
                            
                            # Color de tag
                            tag_html = f'<span style="color: #4dc5e6;">{tag}</span>'
                            
                            msg_escaped = msg.replace("<", "&lt;").replace(">", "&gt;")
                            if level in ['E', 'C']:
                                msg_html = f'<span style="color: #ff5555;">{msg_escaped}</span>'
                            elif 'SLOW TASK DETECTED' in msg:
                                msg_html = f'<span style="color: #fce94f;">{msg_escaped}</span>'
                            else:
                                msg_html = f'<span style="color: #d4d4d4;">{msg_escaped}</span>'
                                
                            sep = '<span style="color: #888888;">|</span>'
                            formatted = f'{time_html} {sep} {thread_html} {sep} {lvl_html} {sep} {tag_html}: {msg_html}'
                            self.text_edit.append(formatted)
                        else:
                            # Si no coincide (ej. Tracebacks multilínea)
                            line_escaped = line.replace("<", "&lt;").replace(">", "&gt;")
                            self.text_edit.append(f'<span style="color: #ffaa00;">{line_escaped}</span>')
                            
                    # Auto-scroll
                    sb = self.text_edit.verticalScrollBar()
                    sb.setValue(sb.maximum())
        except Exception:
            pass

    def _on_file_changed(self, path):
        self._read_logs()
