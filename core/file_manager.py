import os
import ctypes
from ctypes import wintypes
from PyQt6.QtWidgets import QApplication, QMessageBox, QInputDialog, QLineEdit
from PyQt6.QtCore import QMimeData, QUrl


def send_to_trash(file_paths):
    """Envía múltiples archivos a la papelera en una sola operación atómica."""

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    # La API de Windows espera una lista de rutas terminadas en nulo,
    # y la lista completa terminada en un doble nulo.
    p_from = "\0".join(os.path.abspath(p) for p in file_paths) + "\0\0"

    fileop = SHFILEOPSTRUCTW()
    fileop.wFunc = 3  # FO_DELETE
    fileop.pFrom = p_from
    fileop.fFlags = 0x40 | 0x10  # FOF_ALLOWUNDO | FOF_NOCONFIRMATION

    # Una sola llamada al sistema para todos los archivos es mucho más eficiente
    ctypes.windll.shell32.SHFileOperationW(ctypes.byref(fileop))


def copy_to_clipboard(file_paths, move=False):
    """Copia o Corta archivos al portapapeles del sistema."""
    mime = QMimeData()
    urls = [QUrl.fromLocalFile(os.path.abspath(p)) for p in file_paths]
    mime.setUrls(urls)

    if move:
        # Windows espera un DWORD de 32 bits en Little-Endian (2 = DROPEFFECT_MOVE)
        # Si le enviamos sólo 1 byte, el Explorador lo ignora y hace "Copiar" por defecto.
        data = b"\x02\x00\x00\x00"
        mime.setData("Preferred DropEffect", data)

    QApplication.clipboard().setMimeData(mime)


def show_rename_dialog(parent, old_path):
    """Renombrado con validación de existencia y manejo de bloqueos de archivo."""
    old_name = os.path.basename(old_path)
    new_name, ok = QInputDialog.getText(
        parent, "Renombrar", "Nuevo nombre:", QLineEdit.EchoMode.Normal, old_name
    )

    if ok and new_name and new_name != old_name:
        new_path = os.path.join(os.path.dirname(old_path), new_name)

        # Validación preventiva
        if os.path.exists(new_path):
            QMessageBox.warning(
                parent,
                "Error de conflicto",
                "Ya existe un archivo con ese nombre en esta carpeta.",
            )
            return None

        try:
            os.rename(old_path, new_path)
            return new_path
        except PermissionError:
            QMessageBox.critical(
                parent,
                "Archivo Bloqueado",
                "No se puede renombrar porque el archivo está siendo usado por otro proceso.\n\n"
                "Esto ocurre frecuentemente mientras se generan las miniaturas.",
            )
        except Exception as e:
            QMessageBox.critical(
                parent, "Error", f"Ocurrió un error inesperado al renombrar:\n{str(e)}"
            )

    return None


def open_windows_properties(path):
    """Abre la ventana de propiedades nativa de Windows."""
    abs_path = os.path.abspath(path)
    ctypes.windll.shell32.SHObjectProperties(None, 2, abs_path, None)
