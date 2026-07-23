from PyQt6.QtWidgets import QGraphicsObject
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QImage, QPixmap
from PyQt6.QtCore import Qt, QRectF
import numpy as np
import cv2
import time
from tools.ai_tool import get_base_path
import os
import onnxruntime as ort
import gc

def _load_sam_decoder():
    import os
    from tools.ai_tool import MODELS_CONFIG, get_base_path
    
    cfg = MODELS_CONFIG["MobileSAM"]
    base = get_base_path()
    dec_path = os.path.join(base, os.path.dirname(cfg["path"]), cfg["extra_files"][0])
    if not os.path.exists(dec_path):
        from huggingface_hub import hf_hub_download
        import shutil
        os.makedirs(os.path.dirname(dec_path), exist_ok=True)
        dec_cache = hf_hub_download(repo_id="PulpCut/mobilesam-onnx", filename="mobilesam.decoder.onnx")
        shutil.copy2(dec_cache, dec_path)
        # Also grab encoder to be safe if they only clicked manual tool first
        enc_path = os.path.join(os.path.dirname(dec_path), "mobilesam.encoder.onnx")
        if not os.path.exists(enc_path):
            enc_cache = hf_hub_download(repo_id="PulpCut/mobilesam-onnx", filename="mobilesam.encoder.onnx")
            shutil.copy2(enc_cache, enc_path)

    import onnxruntime as ort
    return ort.InferenceSession(dec_path, providers=['CPUExecutionProvider'])
    
class SAMTool(QGraphicsObject):
    def __init__(self, viewer, embedding, original_pixmap):
        super().__init__()
        self.viewer = viewer
        self.embedding = embedding
        self.original_pixmap = original_pixmap
        self.scene_rect = viewer.pixmap_item.sceneBoundingRect()
        
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        self.setZValue(1000)
        
        self.points = []
        self.labels = []
        self.mask_overlay = None
        self.current_mask_alpha = None
        
        # Instanciar ONNX Decoder
        self.dec_sess = _load_sam_decoder()

    def boundingRect(self):
        return self.scene_rect

    def paint(self, painter, option, widget=None):
        if self.mask_overlay:
            painter.drawPixmap(self.scene_rect.toRect(), self.mask_overlay)
            
        for pt, lbl in zip(self.points, self.labels):
            color = Qt.GlobalColor.green if lbl == 1.0 else Qt.GlobalColor.red
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawEllipse(QRectF(pt[0] - 5, pt[1] - 5, 10, 10))

    def mousePressEvent(self, event):
        pos = event.pos()
        x = pos.x()
        y = pos.y()
        
        if event.button() == Qt.MouseButton.LeftButton:
            self.points.append([x, y])
            self.labels.append(1.0)
        elif event.button() == Qt.MouseButton.RightButton:
            self.points.append([x, y])
            self.labels.append(0.0)
            
        self.run_decoder()

    def undo_point(self):
        if self.points:
            self.points.pop()
            self.labels.pop()
            if self.points:
                self.run_decoder()
            else:
                self.mask_overlay = None
                self.current_mask_alpha = None
            self.update()
        
    def run_decoder(self):
        if not self.points:
            return
            
        # Transformar puntos origen a grilla 1024
        orig_w = self.scene_rect.width()
        orig_h = self.scene_rect.height()
        
        scale_x = 1024.0 / orig_w
        scale_y = 1024.0 / orig_h
        
        pts = np.array(self.points, dtype=np.float32)
        pts[:, 0] *= scale_x
        pts[:, 1] *= scale_y
        
        lbls = np.array(self.labels, dtype=np.float32)
        
        # Definir inputs de modelo estrictos
        point_coords = pts.reshape(1, len(self.points), 2)
        point_labels = lbls.reshape(1, len(self.labels))
        mask_input = np.zeros((1, 1, 256, 256), dtype=np.float32)
        has_mask_input = np.zeros((1,), dtype=np.float32)
        orig_im_size = np.array([float(1024), float(1024)], dtype=np.float32)
        
        out = self.dec_sess.run(None, {
            "image_embeddings": self.embedding,
            "point_coords": point_coords,
            "point_labels": point_labels,
            "mask_input": mask_input,
            "has_mask_input": has_mask_input,
            "orig_im_size": orig_im_size
        })
        
        mask = out[0][0, 0, :, :] # (1024, 1024)
        
        # Ejecutar redimensionamiento al original
        mask_cv = cv2.resize(mask, (int(orig_w), int(orig_h)), interpolation=cv2.INTER_LINEAR)
        
        # Binarizar máscara (umbral > 0)
        mask_cv = (mask_cv > 0.0).astype(np.uint8) * 255
        self.current_mask_alpha = mask_cv
        
        # Generar Overlay QPixmap (Verde Alfa)
        color_mask = np.zeros((int(orig_h), int(orig_w), 4), dtype=np.uint8)
        color_mask[:, :, 0] = 0   # R
        color_mask[:, :, 1] = 255 # G
        color_mask[:, :, 2] = 0   # B
        color_mask[:, :, 3] = (mask_cv > 0) * 100 # Alpha
        
        bytes_per_line = 4 * int(orig_w)
        qimg = QImage(color_mask.data, int(orig_w), int(orig_h), bytes_per_line, QImage.Format.Format_RGBA8888).copy()
        self.mask_overlay = QPixmap.fromImage(qimg)
        self.update()

    def get_result(self):
        if self.current_mask_alpha is None:
            return self.original_pixmap
            
        orig_img = self.original_pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        ptr = orig_img.bits()
        ptr.setsize(orig_img.sizeInBytes())
        arr = np.array(ptr, copy=True).reshape((orig_img.height(), orig_img.width(), 4))
        
        # Transferir Alpha de máscara a Alpha objetivo
        arr[:, :, 3] = np.minimum(arr[:, :, 3], self.current_mask_alpha)
        
        bytes_per_line = 4 * orig_img.width()
        qimg = QImage(arr.data, orig_img.width(), orig_img.height(), bytes_per_line, QImage.Format.Format_ARGB32).copy()
        return QPixmap.fromImage(qimg)
