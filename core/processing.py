import numpy as np
import cv2
from PyQt6.QtGui import QImage, QPixmap, QTransform, QPainter
from PyQt6.QtCore import QRect


def apply_image_transformations(
    base_pix: QPixmap,
    brightness: float,
    contrast: float,
    angle: int,
    flip_h: bool,
    flip_v: bool,
    canvas_L: int,
    canvas_T: int,
    canvas_R: int,
    canvas_B: int,
    canvas_bg_color,
) -> tuple[QPixmap, "QRect"]:
    """
    Aplica de manera secuencial y optimizada todas las transformaciones a un QPixmap.
    Retorna el (nuevo_pixmap, rect_del_contenido_visual).
    """
    # 1. Transformación Color (Brillo / Contraste)
    if brightness != 1.0 or contrast != 1.0:
        qimg = base_pix.toImage().convertToFormat(QImage.Format.Format_RGB888)
        ptr = qimg.bits()
        ptr.setsize(qimg.sizeInBytes())

        h, w, bpl = qimg.height(), qimg.width(), qimg.bytesPerLine()
        arr = np.frombuffer(ptr, np.uint8).reshape((h, bpl))
        arr = arr[:, : w * 3].reshape((h, w, 3)).copy()

        # El contraste multiplica (alpha), el brillo suma (beta).
        # Pivotamos sobre 128 (Gris Medio)
        alpha = contrast
        beta = (brightness - 1.0) * 128 + 128 * (1.0 - alpha)

        # cv2 procesa esto ultra-rápido en C++
        arr = cv2.convertScaleAbs(arr, alpha=alpha, beta=beta)
        base_pix = QPixmap.fromImage(
            QImage(arr.data, w, h, w * 3, QImage.Format.Format_RGB888)
        )

    # 2. Transformación Geométrica (Rotación / Espejo)
    transform = QTransform()
    if flip_h or flip_v:
        transform.scale(-1 if flip_h else 1, -1 if flip_v else 1)
    transform.rotate(angle)

    content_pix = base_pix.transformed(transform)
    content_rect = content_pix.rect()

    # 3. Lienzo Paramétrico (Expansión)
    if canvas_L != 0 or canvas_T != 0 or canvas_R != 0 or canvas_B != 0:
        w, h = content_pix.width(), content_pix.height()
        new_w, new_h = w + canvas_L + canvas_R, h + canvas_T + canvas_B
        canvas = QImage(new_w, new_h, QImage.Format.Format_ARGB32)
        canvas.fill(canvas_bg_color)
        p = QPainter(canvas)
        p.drawPixmap(canvas_L, canvas_T, content_pix)
        p.end()
        content_pix = QPixmap.fromImage(canvas)

    return content_pix, content_rect
