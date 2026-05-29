import os
import datetime
import random

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QFileDialog, QSplitter, QTabWidget, QLineEdit,
                             QTabBar, QScrollArea, QMenu, QMessageBox, QLabel)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import Qt, QFileSystemWatcher, QTimer

from qfluentwidgets import setTheme, Theme, PrimaryPushButton

from studio_logger import log_action, logger
from core.utils import format_size
import core.file_manager as fm

from core.threads import ThumbnailLoaderThread
from ui.gallery_view import GroupListWidget
from ui.widgets import ZoomableViewer, FullScreenViewer
from ui.styles import MAIN_STYLE, CONTEXT_MENU_STYLE
from editor.image_tab import ImageTab

class ImageGallery(QMainWindow):
    def __init__(self):
        super().__init__()
        setTheme(Theme.DARK)
        self.ignore_watcher = False 
        self.setWindowTitle("FHVT gallery")
        self.resize(1300, 800)
        self.setMinimumSize(1000, 680)

        self.current_folder = ""
        self.all_images_data = []
        self.list_widgets = []
        self.loader_thread = None
        self.total_to_load = 0
        
        self.sort_descending = True
        self._clearing_selection = False
        
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.load_images)

        self.dir_watcher = QFileSystemWatcher(self)
        self.dir_watcher.directoryChanged.connect(self.on_directory_changed)

        self.setStyleSheet(MAIN_STYLE)

        self.setup_statusbar()
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.setCentralWidget(self.tabs)

        self.nav_tab = QWidget()
        self.setup_navegador()
        self.tabs.addTab(self.nav_tab, "Navegador")
        self.tabs.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)

    def setup_statusbar(self):
        sb = self.statusBar()
        self.lbl_status_gallery = QLabel("0 Imágenes | Total: 0.00 MB")
        self.lbl_status_selection = QLabel("")
        self.lbl_status_selection.setStyleSheet("color: #007acc; font-weight: bold; margin-left: 20px;")
        
        sb.addWidget(self.lbl_status_gallery)
        sb.addWidget(self.lbl_status_selection)
        
        self.progress_container = QWidget()
        self.progress_layout = QHBoxLayout(self.progress_container)
        self.progress_layout.setContentsMargins(0, 0, 10, 0)
        self.lbl_load_text = QLabel("")
        self.lbl_spinner = QLabel(""); self.lbl_spinner.setFont(QFont("Consolas", 11)); self.lbl_spinner.setStyleSheet("color: #007acc; font-weight: bold;")
        self.progress_layout.addWidget(self.lbl_load_text)
        self.progress_layout.addWidget(self.lbl_spinner)
        sb.addPermanentWidget(self.progress_container)
        
        self.spinner_timer = QTimer(self); self.spinner_timer.timeout.connect(self._rotate_spinner)
        self.spinner_frames = ["|", "/", "-", "\\"]; self.spinner_idx = 0

    def _rotate_spinner(self):
        self.lbl_spinner.setText(self.spinner_frames[self.spinner_idx])
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_frames)

    def close_tab(self, index):
        if index > 0:
            widget = self.tabs.widget(index)
            self.tabs.removeTab(index)
            if widget:
                widget.deleteLater()

    def _create_action_menu(self, options, callback):
        menu = QMenu(self)
        for name in options:
            action = menu.addAction(name)
            action.triggered.connect(lambda checked, n=name: callback(n))
        return menu

    def setup_navegador(self):
        nav_layout = QVBoxLayout(self.nav_tab); nav_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout = QHBoxLayout(); toolbar_layout.setContentsMargins(15, 10, 15, 10)
        icon_font = QFont("Segoe MDL2 Assets", 14)
        
        self.btn_open_new_tab = QPushButton("\uE8B9")
        self.btn_open_new_tab.setToolTip("Abrir en nueva pestaña")
        self.btn_open_new_tab.clicked.connect(self.open_selected_in_new_tab)
        
        self.btn_fullscreen = QPushButton("\uE740")
        self.btn_fullscreen.setToolTip("Pantalla completa")
        self.btn_fullscreen.clicked.connect(self.fullscreen_preview)
        
        self.btn_properties = QPushButton("\uE946")
        self.btn_properties.setToolTip("Propiedades")
        self.btn_properties.clicked.connect(self.open_windows_properties)
        self.path_edit = QLineEdit(); self.path_edit.setReadOnly(True); self.path_edit.setPlaceholderText("Selecciona una carpeta...")
        self.path_edit.setFixedHeight(36)
        
        self.btn_sort = QPushButton("Ordenar: Nombre")
        self.btn_sort.setObjectName("btn_sort")
        self.btn_sort.setFixedHeight(36)
        self.sort_menu = self._create_action_menu(["Nombre", "Tamaño", "Fecha", "Alto", "Ancho", "Total", "Al Azar"], self.on_sort_action_triggered)
        self.btn_sort.setMenu(self.sort_menu)
        
        self.btn_sort_order = QPushButton("\uE74B"); self.btn_sort_order.clicked.connect(self.toggle_sort_order)
        self.btn_group = QPushButton("Agrupar: Ninguno")
        self.btn_group.setObjectName("btn_group")
        self.btn_group.setFixedHeight(36)
        self.group_menu = self._create_action_menu(["Ninguno", "Tamaño", "Extensión", "Fecha (Año)"], self.on_group_action_triggered)
        self.btn_group.setMenu(self.group_menu)
        
        # Inicialmente deshabilitados
        self.btn_sort.setEnabled(False)
        self.btn_sort_order.setEnabled(False)
        self.btn_group.setEnabled(False)
        self.btn_open_new_tab.setEnabled(False)
        self.btn_fullscreen.setEnabled(False)
        self.btn_properties.setEnabled(False)

        self.btn_open_folder = PrimaryPushButton("\uE838")
        self.btn_open_folder.setToolTip("Abrir carpeta")
        self.btn_open_folder.clicked.connect(self.open_folder_dialog)

        for btn in [self.btn_open_new_tab, self.btn_fullscreen, self.btn_properties, self.btn_sort_order, self.btn_open_folder]:
            btn.setFont(icon_font); btn.setFixedSize(36, 36)
        self.btn_open_folder.setFixedWidth(50)
            
        for w in [self.btn_open_new_tab, self.btn_fullscreen, self.btn_properties, self.path_edit, self.btn_sort, self.btn_sort_order, self.btn_group, self.btn_open_folder]:
            toolbar_layout.addWidget(w)
        nav_layout.addLayout(toolbar_layout)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        
        # Lado Izquierdo: Galería
        self.gallery_left_widget = QWidget()
        self.gallery_left_layout = QVBoxLayout(self.gallery_left_widget)
        self.gallery_left_layout.setContentsMargins(10, 0, 5, 10)
        self.gallery_left_layout.setSpacing(10)
        
        self.thumbnail_scroll = QScrollArea(); self.thumbnail_scroll.setWidgetResizable(True)
        self.thumbnail_container = QWidget(); self.thumbnail_layout = QVBoxLayout(self.thumbnail_container)
        self.thumbnail_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.thumbnail_scroll.setWidget(self.thumbnail_container); self.thumbnail_scroll.setMinimumWidth(190)
        self.gallery_left_layout.addWidget(self.thumbnail_scroll)
        
        self.viewer = ZoomableViewer()
        self.viewer.setText("Vista Previa\n\nSeleccione carpeta")
        self.viewer_container = QWidget()
        self.viewer_layout = QVBoxLayout(self.viewer_container)
        self.viewer_layout.setContentsMargins(5, 0, 10, 10)
        self.viewer_layout.addWidget(self.viewer)
        
        self.main_splitter.addWidget(self.gallery_left_widget); self.main_splitter.addWidget(self.viewer_container)
        
        # --- AJUSTE INICIAL 45% - 55% ---
        total_w = self.width()
        self.main_splitter.setSizes([int(total_w * 0.45), int(total_w * 0.55)])
        
        nav_layout.addWidget(self.main_splitter)

    def resizeEvent(self, event):
        """Mantiene los límites mínimos como porcentajes del ancho actual con un piso absoluto."""
        super().resizeEvent(event)
        width = self.width()
        self.gallery_left_widget.setMinimumWidth(max(250, int(width * 0.18)))
        self.viewer_container.setMinimumWidth(max(450, int(width * 0.42)))

    def toggle_sort_order(self):
        sort_name = getattr(self, 'current_sort', "Nombre")
        if sort_name == "Al Azar":
            # Si es azar, simplemente re-mezclamos
            self.render_gallery()
            return
            
        self.sort_descending = not self.sort_descending
        self.btn_sort_order.setText("\uE74B" if self.sort_descending else "\uE74A")
        self.render_gallery()

    def on_sort_action_triggered(self, name):
        self.btn_sort.setText(f"Ordenar: {name}")
        self.current_sort = name
        
        # Cambiar icono si es Azar
        if name == "Al Azar":
            self.btn_sort_order.setText("\uE8B1") # Icono Shuffle
        else:
            self.btn_sort_order.setText("\uE74B" if self.sort_descending else "\uE74A")
            
        self.render_gallery()

    def on_group_action_triggered(self, name):
        self.btn_group.setText(f"Agrupar: {name}"); self.current_group = name; self.render_gallery()

    def open_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta")
        if folder: self.set_current_folder(folder)

    @log_action("Cambiando carpeta de trabajo")
    def set_current_folder(self, folder_path):
        if self.current_folder: self.dir_watcher.removePath(self.current_folder)
        self.current_folder = folder_path; self.dir_watcher.addPath(folder_path); self.path_edit.setText(folder_path)
        self.btn_open_folder.setStyleSheet(""); self.load_images()

    def on_directory_changed(self, path):
        if not self.ignore_watcher: self.refresh_timer.start(1000)

    def on_tab_changed(self, index):
        """Si el usuario vuelve al navegador y hay una carpeta pendiente, cargarla."""
        if index == 0 and hasattr(self, 'pending_folder_load') and self.pending_folder_load:
            folder = self.pending_folder_load
            self.pending_folder_load = None # Consumir la carga
            if folder != self.current_folder:
                self.set_current_folder(folder)
        
        self._update_status_bar()

    @log_action("Cargando imágenes del disco")
    def load_images(self):
        if self.loader_thread: self.loader_thread.stop(); self.loader_thread.wait()
        self.all_images_data = []; self.list_widgets = []; self.lbl_status_selection.setText("")
        while self.thumbnail_layout.count():
            child = self.thumbnail_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
        
        if not os.path.exists(self.current_folder): 
            self.viewer.setText("Vista Previa\n\nSeleccione carpeta")
            return

        valid_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}
        image_files = []
        try:
            for entry in os.scandir(self.current_folder):
                if entry.is_file():
                    _, ext = os.path.splitext(entry.name)
                    if ext.lower() in valid_exts:
                        image_files.append(entry.name)
        except Exception as e:
            logger.error(f"Error escaneando carpeta: {str(e)}")
            return
        
        if not image_files: 
            self.viewer.setText("❌ No se encontraron imágenes en esta carpeta.")
            self.lbl_status_gallery.setText("0 Imágenes | Total: 0.00 MB")
            return
        
        self.total_to_load = len(image_files)
        self.viewer.setText(f"Cargando {self.total_to_load} imágenes...")
        
        self.lbl_load_text.setText(f"Cargando: 0 / {self.total_to_load}")
        self.spinner_timer.start(100)
        
        self.loader_thread = ThumbnailLoaderThread(self.current_folder, image_files)
        self.loader_thread.thumbnail_loaded_batch.connect(self.on_thumbnail_batch_loaded)
        self.loader_thread.finished_loading.connect(self.render_gallery)
        self.loader_thread.start()

    def on_thumbnail_batch_loaded(self, batch):
        for item in batch:
            data = {'file': item['file'], 'file_path': item['file_path'], 'pixmap': QPixmap.fromImage(item['img']), 
                    'size': item['size'], 'mtime': item['mtime'], 'width': item['w'], 'height': item['h'], 
                    'area': item['w']*item['h'], 'ext': item['ext']}
            self.all_images_data.append(data)

        # Actualizar progreso en tiempo real (solo 1 vez por bloque)
        loaded = len(self.all_images_data)
        self.lbl_load_text.setText(f"Cargando: {loaded} / {self.total_to_load}")

    @log_action("Renderizando Galería")
    def render_gallery(self, *_):
        self.spinner_timer.stop(); self.lbl_spinner.setText(""); self.lbl_load_text.setText("")
        
        if not self.all_images_data: 
            self.lbl_status_gallery.setText("0 Imágenes | Total: 0.00 MB")
            if not self.current_folder: self.viewer.setText("Vista Previa\n\nSeleccione carpeta")
            else: self.viewer.setText("❌ No se encontraron imágenes en esta carpeta.")
            for lw in self.list_widgets: lw.clear()
            self.btn_sort.setEnabled(False)
            self.btn_sort_order.setEnabled(False)
            self.btn_group.setEnabled(False)
            self.btn_open_new_tab.setEnabled(False)
            self.btn_fullscreen.setEnabled(False)
            self.btn_properties.setEnabled(False)
            self._update_status_bar()
            return

        self.btn_sort.setEnabled(True)
        self.btn_sort_order.setEnabled(True)
        self.btn_group.setEnabled(True)
        self.viewer.setText("Vista Previa\n\nSeleccione una imagen")

        # 1. Actualizar Estadísticas
        total_bytes = sum(d['size'] for d in self.all_images_data)
        self.lbl_status_gallery.setText(f"{len(self.all_images_data)} Imágenes | Total: {format_size(total_bytes)}")

        # 2. Ordenar
        sort_name = getattr(self, 'current_sort', "Nombre")
        desc = self.sort_descending
        if sort_name == "Nombre": self.all_images_data.sort(key=lambda x: x['file'].lower(), reverse=desc)
        elif sort_name == "Tamaño": self.all_images_data.sort(key=lambda x: x['size'], reverse=desc)
        elif sort_name == "Fecha": self.all_images_data.sort(key=lambda x: x['mtime'], reverse=desc)
        elif sort_name == "Alto": self.all_images_data.sort(key=lambda x: x['height'], reverse=desc)
        elif sort_name == "Ancho": self.all_images_data.sort(key=lambda x: x['width'], reverse=desc)
        elif sort_name == "Total": self.all_images_data.sort(key=lambda x: x['area'], reverse=desc)
        elif sort_name == "Al Azar": random.shuffle(self.all_images_data)

        # 3. Agrupar y Renderizar (OPTIMIZADO)
        group_name = getattr(self, 'current_group', "Ninguno")
        
        # CASO RÁPIDO: Sin grupos (reutilizar widget único)
        if group_name == "Ninguno":
            if len(self.list_widgets) != 1 or not isinstance(self.list_widgets[0], GroupListWidget):
                # Limpiar todo si antes había grupos
                while self.thumbnail_layout.count():
                    child = self.thumbnail_layout.takeAt(0)
                    if child.widget(): child.widget().deleteLater()
                lw = GroupListWidget()
                lw.itemSelectionChanged.connect(lambda l=lw: self.on_group_item_selected(l))
                lw.itemDoubleClicked.connect(self.on_item_double_clicked)
                lw.customContextMenuRequested.connect(lambda pos, l=lw: self.show_gallery_context_menu(pos, l))
                self.thumbnail_layout.addWidget(lw)
                self.list_widgets = [lw]
            
            self.list_widgets[0].model().set_images(self.all_images_data)
            self._update_status_bar()
            return

        # CASO COMPLEJO: Con grupos (reconstrucción necesaria)
        while self.thumbnail_layout.count():
            child = self.thumbnail_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
            
        groups = {}
        for data in self.all_images_data:
            g = "Todas"
            if group_name == "Tamaño":
                mb_val = data['size']/(1024*1024)
                if mb_val < 1: g = "< 1 MB"
                elif mb_val < 10: g = "1 MB - 10 MB"
                else: g = "> 10 MB"
            elif group_name == "Extensión": g = data['ext'].upper()
            elif group_name == "Fecha (Año)": g = str(datetime.datetime.fromtimestamp(data['mtime']).year) if data['mtime'] else "N/A"
            if g not in groups: groups[g] = []
            groups[g].append(data)

        self.list_widgets = []
        for g_title in sorted(groups.keys(), reverse=(group_name=="Fecha (Año)")):
            btn = QPushButton(f"▼ {g_title} ({len(groups[g_title])})")
            btn.setStyleSheet("text-align: left; font-weight: bold; padding: 5px; color: #007acc; border: none; border-bottom: 1px solid #333;")
            self.thumbnail_layout.addWidget(btn)
            
            lw = GroupListWidget()
            lw.itemSelectionChanged.connect(lambda l=lw: self.on_group_item_selected(l))
            lw.itemDoubleClicked.connect(self.on_item_double_clicked)
            lw.customContextMenuRequested.connect(lambda pos, l=lw: self.show_gallery_context_menu(pos, l))
            lw.model().set_images(groups[g_title])
            self.thumbnail_layout.addWidget(lw); self.list_widgets.append(lw)
            btn.clicked.connect(lambda checked, w=lw: w.setVisible(not w.isVisible()))
            
        self._update_status_bar()

    def on_group_item_selected(self, active_lw):
        if self._clearing_selection: return
        self._clearing_selection = True
        for lw in self.list_widgets:
            if lw != active_lw: lw.selectionModel().clearSelection()
        self._clearing_selection = False
        
        indexes = active_lw.selectionModel().selectedIndexes()
        count = len(indexes)
        
        # Estos botones solo tienen sentido si hay exactamente UNA imagen seleccionada
        self.btn_open_new_tab.setEnabled(count == 1)
        self.btn_fullscreen.setEnabled(count == 1)
        self.btn_properties.setEnabled(count == 1)
        
        if count == 1: 
            # Una sola imagen: Mostrar vista previa
            data = indexes[0].data(Qt.ItemDataRole.UserRole)
            self.display_preview(data['file_path'])
            info = f" {data['width']}x{data['height']} | {format_size(data['size'])} | {data['ext'].upper()}"
            self.lbl_status_selection.setText(f"|  {info}")
        elif count > 1:
            # Múltiples imágenes: Ocultar vista previa
            self.viewer.setText(f"Varios archivos seleccionados ({count})\n\nClick derecho para acciones en lote")
            self.lbl_status_selection.setText(f"|  {count} archivos seleccionados")
        else:
            self.viewer.setText("Vista Previa\n\nSeleccione una imagen")
            self.lbl_status_selection.setText("")

    def show_gallery_context_menu(self, pos, lw):
        indexes = lw.selectionModel().selectedIndexes()
        if not indexes: return
        count = len(indexes)
        total_items = lw.model().rowCount()

        menu = QMenu(self); menu.setStyleSheet(CONTEXT_MENU_STYLE)
        
        act_open = None
        if count <= 3:
            act_open = menu.addAction(f"Abrir ({count})" if count > 1 else "Abrir en pestaña")
            menu.addSeparator()
            
        act_copy = menu.addAction("Copiar"); act_cut = menu.addAction("Cortar")
        menu.addSeparator()
        act_rename = menu.addAction("Renombrar"); act_rename.setEnabled(count == 1)
        act_delete = menu.addAction("Mover a la papelera")
        
        act_select_all = None
        if count < total_items:
            menu.addSeparator()
            act_select_all = menu.addAction("Seleccionar todo")

        action = menu.exec(lw.viewport().mapToGlobal(pos))
        if not action: return

        paths = [idx.data(Qt.ItemDataRole.UserRole)['file_path'] for idx in indexes]
        if act_open and action == act_open:
            for idx in indexes: self.on_item_double_clicked(idx)
        elif action in [act_copy, act_cut]:
            fm.copy_to_clipboard(paths, move=(action == act_cut))
        elif action == act_rename:
            self.ignore_watcher = True
            try:
                if fm.show_rename_dialog(self, paths[0]): self.load_images()
            finally:
                self.ignore_watcher = False
        elif action == act_delete:
            if QMessageBox.question(self, "Confirmar", f"¿Mover {count} archivos a la papelera?") == QMessageBox.StandardButton.Yes:
                self.ignore_watcher = True
                try:
                    fm.send_to_trash(paths)
                    self.load_images()
                finally:
                    QTimer.singleShot(300, lambda: setattr(self, 'ignore_watcher', False))
        elif act_select_all and action == act_select_all:
            lw.selectAll()

    def _update_status_bar(self):
        """Actualiza la barra de estado según el contexto actual."""
        idx = self.tabs.currentIndex()
        if idx == 0: # Navegador
            # La lógica de selección ya actualiza esto en on_group_item_selected
            # pero aquí forzamos refresco si es necesario
            pass
        else: # Pestaña de edición
            tab = self.tabs.currentWidget()
            if hasattr(tab, 'current_pixmap'):
                w, h = tab.current_pixmap.width(), tab.current_pixmap.height()
                size_str = ""
                if hasattr(tab, 'file_path') and os.path.exists(tab.file_path):
                    try:
                        size_str = f" | {format_size(os.path.getsize(tab.file_path))}"
                    except Exception:
                        size_str = ""
                self.lbl_status_selection.setText(f"|  {w}x{h}{size_str}")

    def on_item_double_clicked(self, index):
        data = index.data(Qt.ItemDataRole.UserRole)
        if data: self.open_image_tab(data['file_path'])

    def open_selected_in_new_tab(self):
        for lw in self.list_widgets:
            indexes = lw.selectionModel().selectedIndexes()
            if indexes:
                data = indexes[0].data(Qt.ItemDataRole.UserRole)
                self.open_image_tab(data['file_path']); break

    @log_action("Abriendo pestaña de imagen")
    def open_image_tab(self, file_path):
        # --- LÍMITE DE PESTAÑAS (Máx 5 + Navegador = 6) ---
        if self.tabs.count() >= 6:
            QMessageBox.information(self, "Límite alcanzado", "Has alcanzado el límite de 5 pestañas abiertas.\n\nPor favor, cierra alguna para abrir una nueva y mantener el rendimiento del sistema.")
            return

        abs_p = os.path.abspath(file_path)
        for i in range(1, self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, 'file_path') and os.path.abspath(tab.file_path) == abs_p:
                self.tabs.setCurrentIndex(i); return
        new_tab = ImageTab(file_path)
        new_tab.imageUpdated.connect(self._update_status_bar)
        idx = self.tabs.addTab(new_tab, os.path.basename(file_path))
        self.tabs.setCurrentIndex(idx)

    @log_action("Vista previa pantalla completa")
    def fullscreen_preview(self, *_):
        for lw in self.list_widgets:
            indexes = lw.selectionModel().selectedIndexes()
            if indexes:
                data = indexes[0].data(Qt.ItemDataRole.UserRole)
                self.fs = FullScreenViewer(data['file_path']); break
            
    def open_windows_properties(self):
        for lw in self.list_widgets:
            indexes = lw.selectionModel().selectedIndexes()
            if indexes:
                fm.open_windows_properties(indexes[0].data(Qt.ItemDataRole.UserRole)['file_path'])
                break

    @log_action("Mostrando vista previa")
    def display_preview(self, path):
        pix = QPixmap(path); self.viewer.setPixmap(pix)
