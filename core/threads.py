import os
import sys
import math
import warnings
import numpy as np
import cv2
import onnxruntime as ort
from pathlib import Path
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QSize, Qt
from PyQt6.QtGui import QImage, QImageReader, QColor
from studio_logger import logger, log_action
from .utils import get_base_path

warnings.filterwarnings("ignore", category=UserWarning)

def _clean_exception_msg(e):
    """Extrae y formatea de forma segura un mensaje de excepción sin riesgo de UnicodeDecodeError."""
    if isinstance(e, UnicodeDecodeError):
        return "Error del driver oculto por acentos (Posible VRAM agotada)", "memoria"
    try:
        err_str = str(e)
    except (UnicodeDecodeError, UnicodeEncodeError):
        err_str = repr(e)
        if err_str.startswith("RuntimeError('") and err_str.endswith("')"):
            err_str = err_str[14:-2]
    return err_str, err_str.lower()

AI_MODELS = {}

# --- DETECCIÓN DE VRAM ---
def _get_vram_info():
    """Retorna información de VRAM disponible en GB. 
    Intenta detectar VRAM real de GPU, no RAM del sistema."""
    try:
        import subprocess
        
        # Añadir bandera para ejecución silenciosa (Evita falsos positivos de AV y parpadeos de consola)
        import sys
        CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
        
        # Intenta nvidia-smi para GPUs NVIDIA
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.free', '--format=csv,nounits,noheader'],
                capture_output=True, text=True, timeout=2, creationflags=CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                free_vram_mb = float(result.stdout.strip().split('\n')[0])
                return max(0.5, free_vram_mb / 1024)
        except:
            pass
            
        # Fallback universal para Windows (AMD / Intel) via WMIC (Más amigable con Antivirus que PowerShell)
        if sys.platform == "win32":
            try:
                res = subprocess.run(
                    ['wmic', 'path', 'win32_VideoController', 'get', 'AdapterRAM'], 
                    capture_output=True, text=True, timeout=2, creationflags=CREATE_NO_WINDOW
                )
                if res.returncode == 0 and res.stdout.strip():
                    # WMIC devuelve un header, leemos la segunda línea válida
                    lines = [line.strip() for line in res.stdout.split('\n') if line.strip() and line.strip().isdigit()]
                    if lines:
                        bytes_vram = float(lines[0])
                        if bytes_vram > 0:
                            return bytes_vram / (1024 ** 3)
            except:
                pass
                
        # Devuelve None para indicar que no se pudo detectar
        return None
        
    except:
        return None

def _format_vram_warning(vram_available):
    """Formatea el mensaje de VRAM de manera inteligente."""
    if vram_available is None:
        # No se pudo detectar VRAM real
        return (
            "Tu Tarjeta Gráfica se ha quedado sin memoria (VRAM) suficiente.\n\n"
            "Soluciones:\n"
            "• Selecciona un modelo más ligero (busca FP16 o Lite)\n"
            "• Procesa imágenes con menor resolución\n"
            "• Cierra otras aplicaciones que usen GPU"
        )
    else:
        # Se detectó VRAM real
        return (
            f"La memoria de tu Tarjeta Gráfica (VRAM) se ha llenado por completo.\n\n"
            f"Al momento del error, solo quedaban ~{vram_available:.1f} GB libres, lo cual impidió procesar la imagen.\n\n"
            "Soluciones:\n"
            "• Selecciona un modelo más ligero (FP16, Lite, comprimidos)\n"
            "• Procesa imágenes con menor resolución\n"
            "• Cierra otras aplicaciones pesadas que usen GPU"
        )

# --- SELECCIÓN DE PROVIDERS (DirectML > CUDA > CPU) ---
def _get_providers():
    """Detecta y retorna los providers disponibles en orden de preferencia."""
    available = ort.get_available_providers()
    if 'DmlExecutionProvider' in available:
        return ['DmlExecutionProvider', 'CPUExecutionProvider']
    if 'CUDAExecutionProvider' in available:
        return ['CUDAExecutionProvider', 'CPUExecutionProvider']
    return ['CPUExecutionProvider']

def _get_active_provider(session):
    """Retorna el provider activo de una sesión ONNX."""
    providers = session.get_providers()
    if 'DmlExecutionProvider' in providers: return 'DirectML (GPU)'
    if 'CUDAExecutionProvider' in providers: return 'CUDA (GPU)'
    return 'CPU'

# --- FUNCIONES AUXILIARES DE MODELOS ---
def _resolve_model_path(path):
    """Busca el archivo de pesos correcto si se pasa un directorio."""
    if not os.path.isdir(path): return path
    files = [os.path.join(r, f) for r, _, fs in os.walk(path) for f in fs if f.lower().endswith('.onnx')]
    if not files: return path
    return sorted(files)[0]

def _load_model(path):
    """Carga un modelo ONNX con el mejor provider disponible."""
    global AI_MODELS
    if path in AI_MODELS: return AI_MODELS[path]
    
    # Liberar memoria de modelos anteriores para no acumular VRAM
    if len(AI_MODELS) > 0:
        AI_MODELS.clear()
        import gc
        gc.collect()
        logger.info("Caché de modelos IA limpiada para ahorrar VRAM.")
    
    if not path.lower().endswith('.onnx'):
        raise RuntimeError(
            f"Solo se aceptan modelos ONNX (.onnx).\n"
            f"El archivo '{os.path.basename(path)}' no es compatible.\n"
            f"Por favor descarga la versión ONNX del modelo desde el Catálogo IA."
        )
    
    providers = _get_providers()
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    
    session = ort.InferenceSession(path, sess_options=opts, providers=providers)
    
    # Prevenir que ONNX falle silenciosamente hacia la CPU si el usuario tiene GPU
    active_providers = session.get_providers()
    if 'DmlExecutionProvider' in providers and 'DmlExecutionProvider' not in active_providers:
        # ONNX descartó DirectML (probablemente por falta de VRAM o error interno de decodificación)
        # Bloqueamos la ejecución porque procesar IA de imágenes gigantes en CPU tomará una eternidad.
        raise RuntimeError(
            "❌ RECHAZO DE HARDWARE (Fallback a CPU detectado)\n\n"
            "El modelo intentó cargarse en la Tarjeta Gráfica pero falló "
            "(posiblemente por falta de memoria o incompatibilidad del modelo) "
            "y ONNX Runtime lo forzó a ejecutarse en el Procesador (CPU).\n\n"
            "Para evitar que la PC se congele durante horas, la operación ha sido cancelada.\n"
            "Por favor, selecciona un modelo más ligero (Lite/FP16)."
        )
        
    AI_MODELS[path] = session
    logger.info(f"Modelo ONNX cargado | Provider: {_get_active_provider(session)} | {os.path.basename(path)}")
    return session

# --- WORKERS ---
class PaletteWorker(QObject):
    finished = pyqtSignal(list)
    def __init__(self, pixmap, mode):
        super().__init__(); self.pixmap = pixmap; self.mode = mode

    @log_action("Analizando Paleta de Colores")
    def run(self):
        img = self.pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        w, h = img.width(), img.height()
        step = max(1, int(math.sqrt((w * h) // 5000)) or 1)
        
        ptr = img.bits()
        ptr.setsize(img.sizeInBytes())
        arr = np.frombuffer(ptr, np.uint8).reshape((h, w, 4))
        
        sampled_arr = arr[::step, ::step]
        y_indices, x_indices = np.where(sampled_arr[:, :, 3] > 128)
        
        data = []
        for yi, xi, (b, g, r, a) in zip(y_indices, x_indices, sampled_arr[y_indices, x_indices]):
            data.append({
                'color': QColor(int(r), int(g), int(b), int(a)),
                'x': int(xi * step),
                'y': int(yi * step)
            })

        if not data: 
            return self.finished.emit([])

        def get_score(item):
            c = item['color']
            s, v = c.saturation(), c.value()
            scores = { "bright": v * 2 - s, "muted": (255 - s) * 2 - abs(v - 128), "intense": s * 2 + v, "dark": (255 - v) * 2 + s }
            return scores.get(self.mode, s + v)

        data.sort(key=get_score, reverse=True)
        result = []
        for item in data:
            if len(result) >= 5: break
            c = item['color']
            # Evitar colores repetidos
            if not any(abs(c.red()-r['color'].red()) + abs(c.green()-r['color'].green()) + abs(c.blue()-r['color'].blue()) < 60 for r in result): 
                result.append(item)
        
        self.finished.emit(result)


class AIWorker(QObject):
    finished = pyqtSignal(QImage); progress = pyqtSignal(int, int); error = pyqtSignal(str)
    
    def __init__(self, pixmap, mode, model_rel_path):
        super().__init__(); self.pixmap = pixmap; self.mode = mode; self.model_rel_path = model_rel_path
    
    @log_action("Motor IA: Procesando Imagen")
    def run(self):
        try:
            from PyQt6.QtGui import QImage
            if isinstance(self.pixmap, QImage):
                qimg = self.pixmap.convertToFormat(QImage.Format.Format_ARGB32)
            else:
                qimg = self.pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
            ptr = qimg.bits(); ptr.setsize(qimg.sizeInBytes())
            arr = np.frombuffer(ptr, np.uint8).reshape((qimg.height(), qimg.width(), 4))
            img_rgba = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGBA)
            
            model_full_path = _resolve_model_path(os.path.normpath(os.path.join(get_base_path(), self.model_rel_path)))
            if not os.path.exists(model_full_path):
                return self.error.emit(f"Modelo no encontrado: {self.model_rel_path}")

            self.progress.emit(20, 100)
            
            if self.mode == "rmbg":   result_rgba = self._process_rmbg(img_rgba, model_full_path)
            elif self.mode == "depth": result_rgba = self._process_depth(img_rgba, model_full_path)
            elif self.mode == "upscale": result_rgba = self._process_upscale_tiled(img_rgba, model_full_path)
            else: result_rgba = None

            self.progress.emit(100, 100)

            if result_rgba is not None:
                bgra = cv2.cvtColor(result_rgba, cv2.COLOR_RGBA2BGRA)
                h, w, _ = bgra.shape
                self.finished.emit(QImage(bgra.data, w, h, w * 4, QImage.Format.Format_ARGB32).copy())
            else: self.error.emit("Error en el motor de IA.")
            
        except Exception as e: 
            self.error.emit(f"Error IA: {str(e)}")
            
            # Limpiar caché de modelos para liberar VRAM tras un fallo crítico
            global AI_MODELS
            AI_MODELS.clear()
            import gc
            gc.collect()
            logger.info("VRAM liberada de emergencia debido a fallo en IA.")

    def _run_onnx(self, session, input_tensor):
        """Ejecuta inferencia ONNX y retorna el resultado como numpy array (FP32)."""
        inp = session.get_inputs()[0]
        input_name = inp.name
        expected_type = inp.type
        
        # Conversión dinámica (Auto-Cast) según lo que el modelo requiera
        if 'float16' in expected_type and input_tensor.dtype != np.float16:
            input_tensor = input_tensor.astype(np.float16)
        elif 'float' in expected_type and 'float16' not in expected_type and input_tensor.dtype != np.float32:
            input_tensor = input_tensor.astype(np.float32)
            
        out = session.run(None, {input_name: input_tensor})[0]
        
        # OpenCV/NumPy prefieren trabajar en FP32, convertimos la salida de vuelta
        if out.dtype == np.float16:
            out = out.astype(np.float32)
            
        return out

    def _process_rmbg(self, img_rgba, model_path, force_size=None):
        # Normalizar ruta para evitar errores de codificación con caracteres especiales
        model_path = os.path.normpath(str(Path(model_path).resolve()))
        session = _load_model(model_path)
        h, w = img_rgba.shape[:2]
        
        # PASO 1: Inspeccionar si el modelo tiene dimensiones fijas
        inp_shape = session.get_inputs()[0].shape
        fixed_h, fixed_w = None, None
        
        if len(inp_shape) >= 4:
            h_dim = inp_shape[2]
            w_dim = inp_shape[3]
            if isinstance(h_dim, int) and h_dim > 0:
                fixed_h = h_dim
            if isinstance(w_dim, int) and w_dim > 0:
                fixed_w = w_dim

        # PASO 2: Determinar el tamaño óptimo de redimensionamiento
        if fixed_h and fixed_w:
            # Si el modelo ONNX exige un tamaño exacto (ej. 1024x1024), lo respetamos
            target_h, target_w = fixed_h, fixed_w
            logger.info(f"RMBG: Usando dimensiones rígidas del modelo: {target_h}x{target_w}")
        elif force_size:
            target_h = target_w = force_size
        else:
            # Si el modelo es dinámico, aplicamos tu lógica de optimización de VRAM
            max_dim = max(h, w)
            if max_dim > 2048:
                target_size = 768
            elif max_dim > 1024:
                target_size = 512
            else:
                target_size = 1024
            target_h = target_w = target_size

        try:
            # Redimensionamos la imagen al tamaño objetivo
            img_input = cv2.resize(img_rgba[:,:,:3], (target_w, target_h)).astype(np.float32) / 255.0
            img_input = (img_input - 0.5) / 0.5
            tensor = np.expand_dims(np.transpose(img_input, (2, 0, 1)), axis=0)
            
            output = self._run_onnx(session, tensor)
            mask = output[0][0] if output.ndim == 4 else output[0]
            
            mask_resized = cv2.resize(
                (mask - mask.min()) / (mask.max() - mask.min() + 1e-8),
                (w, h), interpolation=cv2.INTER_LINEAR
            )
            res = img_rgba.copy()
            res[:, :, 3] = (mask_resized * 255).astype(np.uint8)
            return res
            
        except Exception as e:
            err_str, err_clean = _clean_exception_msg(e)

            logger.error(f"Error en RMBG: {err_str}")
            
            # 2. Análisis inteligente del error: ¿Es un problema de memoria?
            # Detectamos códigos de VRAM agotada en DML (8007000E), fallos de DML genéricos que implican colapso de GPU
            is_out_of_memory = (
                "8007000e" in err_clean or 
                "memoria" in err_clean or 
                "memory" in err_clean or 
                "allocat" in err_clean or
                "dmlfusednode" in err_clean or
                "non-zero status code" in err_clean
            )

            if is_out_of_memory:
                # Si el modelo es rígido, no podemos bajarle la resolución. Fallamos con estilo.
                if fixed_h:
                    vram_available = _get_vram_info()
                    # Lanzamos el error usando la misma función de formateo amigable que ya tenías
                    raise RuntimeError(
                        "❌ LIMITACIÓN DE HARDWARE\n\n"
                        "El modelo actual requiere demasiada memoria y tu tarjeta gráfica no puede procesarlo.\n\n"
                        + _format_vram_warning(vram_available)
                    )
                
                # Si el modelo es dinámico y falló, intentamos reintentar con la mitad del tamaño (Fallback)
                elif target_h > 256:
                    logger.warning(f"RMBG: Insuficiente VRAM. Reintentando con {target_h // 2}")
                    return self._process_rmbg(img_rgba, model_path, force_size=target_h // 2)

            # 3. Si no es de memoria o ya agotamos los fallbacks, lanzamos un error general limpio
            raise RuntimeError(
                "❌ ERROR EN PROCESAMIENTO DE IA\n\n"
                "Ocurrió un error inesperado al procesar la imagen.\n"
                "Intenta cerrar y abrir la aplicación o usar una imagen más pequeña."
            )

    def _process_depth(self, img_rgba, model_path):
        session = _load_model(model_path)
        h, w = img_rgba.shape[:2]
        img_resized = cv2.resize(img_rgba[:,:,:3], (518, 518), interpolation=cv2.INTER_CUBIC)
        
        self.progress.emit(50, 100)
        
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std  = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img_input = (img_resized.astype(np.float32) / 255.0 - mean) / std
        tensor = np.expand_dims(np.transpose(img_input, (2, 0, 1)), axis=0)
        
        output = self._run_onnx(session, tensor)
        depth = output[0] if output.ndim == 3 else output[0][0]
        
        depth = cv2.resize(
            (depth - depth.min()) / (depth.max() - depth.min() + 1e-8),
            (w, h), interpolation=cv2.INTER_LINEAR
        )
        depth_uint8 = (depth * 255).astype(np.uint8)
        return np.dstack((depth_uint8, depth_uint8, depth_uint8, np.full((h, w), 255, dtype=np.uint8)))

    def _process_upscale_tiled(self, img_rgba, model_path, force_fixed_dim=None, force_batch_size=1):
        # Normalizar ruta para evitar errores de codificación con caracteres especiales
        model_path = os.path.normpath(str(Path(model_path).resolve()))
        session = _load_model(model_path)
        img_rgb = img_rgba[:,:,:3]
        h, w = img_rgb.shape[:2]
        
        # Detectar escala desde el nombre del archivo (ahora con encoding limpio)
        name_lower = os.path.basename(model_path).lower()
        if "x2" in name_lower or "2x" in name_lower: scale = 2
        elif "x3" in name_lower or "3x" in name_lower: scale = 3
        else: scale = 4
        
        # PASO 1: Inspeccionar la forma de entrada del modelo
        inp_shape = session.get_inputs()[0].shape
        logger.info(f"Forma de entrada del modelo: {inp_shape}")
        
        # Detectar dimensiones rígidas y batch size
        fixed_batch = None
        fixed_h, fixed_w = None, None
        
        if len(inp_shape) >= 4:
            # inp_shape es una lista que puede contener int, str o None
            # Ejemplo para modelos dinámicos: [1, 3, 'H', 'W'] o ['batch', 3, 'H', 'W']
            # Ejemplo para RGT: [16, 3, 256, 256] o similar
            
            batch_dim = inp_shape[0]
            h_dim = inp_shape[2]
            w_dim = inp_shape[3]
            
            # Si son números enteros, son dimensiones fijas
            if isinstance(batch_dim, int) and batch_dim > 0 and batch_dim != 1:
                fixed_batch = batch_dim
                logger.info(f"Batch size rígido detectado: {fixed_batch}")
            
            if isinstance(h_dim, int) and isinstance(w_dim, int):
                fixed_h, fixed_w = h_dim, w_dim
                logger.info(f"Dimensiones de tile rígidas detectadas: {fixed_h}x{fixed_w}")
            
        # Aplicar forzados (por fallback después de error)
        if force_fixed_dim:
            fixed_h = fixed_w = force_fixed_dim
        if force_batch_size and force_batch_size > 1:
            fixed_batch = force_batch_size
        
        # PASO 2: Usar batch size fijo si está disponible
        batch_size = fixed_batch if fixed_batch else 1
        
        # ======================================================================
        # PASO 3: Configurar el mosaico adaptativo (Arquitectura de Tensor Fijo)
        # ======================================================================
        tile_pad = 16
        
        if fixed_h and fixed_w:
            # Si el modelo tiene un tamaño exigido por defecto
            tensor_h, tensor_w = fixed_h, fixed_w
            batch_size = fixed_batch if fixed_batch else 1
        else:
            # Si el modelo miente y dice ser dinámico, le FORZAMOS un tamaño estándar
            vram_libre = _get_vram_info()
            if vram_libre is not None:
                if vram_libre >= 20.0:   tensor_h = tensor_w = 1024
                elif vram_libre >= 10.0: tensor_h = tensor_w = 768
                elif vram_libre >= 6.0:  tensor_h = tensor_w = 512
                else:                    tensor_h = tensor_w = 256
            else:
                tensor_h = tensor_w = 256
            batch_size = 1

        # El avance real del mosaico es el tamaño del tensor MENOS los bordes superpuestos
        tile_size_h = max(16, tensor_h - 2 * tile_pad)
        tile_size_w = max(16, tensor_w - 2 * tile_pad)
        
        # Truco Maestro: Inyectamos el tamaño del tensor como fixed_h/w 
        # Esto obliga al Paso 4 a rellenar TODOS los mosaicos para que midan exactamente esto
        fixed_h, fixed_w = tensor_h, tensor_w
        # PASO 4: Recopilar todos los tiles primero
        tiles_data = []
        for y in range(0, h, tile_size_h):
            for x in range(0, w, tile_size_w):
                xs, ys = max(0, x - tile_pad), max(0, y - tile_pad)
                xe, ye = min(w, x + tile_size_w + tile_pad), min(h, y + tile_size_h + tile_pad)
                tile = img_rgb[ys:ye, xs:xe]
                
                orig_th, orig_tw = tile.shape[:2]
                
                if fixed_h and fixed_w:
                    ph = max(0, fixed_h - orig_th)
                    pw = max(0, fixed_w - orig_tw)
                else:
                    # Modelos avanzados (SwinIR, HAT, RealESRGAN) requieren múltiplos de 64
                    # debido a sus jerarquías de downsampling/ventanas de atención profunda.
                    ph = (64 - orig_th % 64) % 64
                    pw = (64 - orig_tw % 64) % 64
                    
                if ph > 0 or pw > 0:
                    tile = cv2.copyMakeBorder(tile, 0, ph, 0, pw, cv2.BORDER_REFLECT)
                
                # Formato (3, H, W) float32 (Manteniendo RGB nativo, sin invertir)
                t_arr = np.transpose(tile.astype(np.float32) / 255.0, (2, 0, 1))
                tiles_data.append({
                    'tensor': t_arr, 'x': x, 'y': y, 'xs': xs, 'ys': ys, 
                    'orig_th': orig_th, 'orig_tw': orig_tw, 'ph': ph, 'pw': pw
                })

        total_tiles = len(tiles_data)
        current_tile = 0
        output_img = np.zeros((h * scale, w * scale, 3), dtype=np.uint8)

        # PASO 5: PROCESAR EN LOTES (BATCHES) CON TAMAÑO RÍGIDO SI ES NECESARIO
        try:
            for i in range(0, total_tiles, batch_size):
                batch_meta = tiles_data[i:i + batch_size]
                batch_tensors = [t['tensor'] for t in batch_meta]
                
                # Si el modelo requiere un batch size rígido, rellenamos con copias del primer tensor
                if batch_size > 1 and len(batch_tensors) < batch_size:
                    padding_needed = batch_size - len(batch_tensors)
                    logger.debug(f"Batch size rígido ({batch_size}). Rellenando con {padding_needed} copias del primer tensor.")
                    batch_tensors.extend([batch_tensors[0]] * padding_needed)
                
                # Apilar todos los tensores en la dimensión 0. Shape: (Batch, 3, H, W)
                tensor_batch = np.stack(batch_tensors, axis=0)
                logger.debug(f"Batch shape: {tensor_batch.shape}")
                
                out_batch = self._run_onnx(session, tensor_batch)
                
                # Procesar la salida y escribir en la imagen final
                for b_idx, meta in enumerate(batch_meta):
                    out = out_batch[b_idx] # Extraer el resultado individual del batch
                    out_np = np.clip(out.transpose(1, 2, 0) * 255, 0, 255).astype(np.uint8)
                    # out_np = out_np[:, :, ::-1] # (Eliminado) Ya estamos en RGB
                    
                    if meta['ph'] > 0 or meta['pw'] > 0:
                        out_np = out_np[:meta['orig_th'] * scale, :meta['orig_tw'] * scale, :]
                        
                    x, y, xs, ys = meta['x'], meta['y'], meta['xs'], meta['ys']
                    oxs, oys = x * scale, y * scale
                    oxe = min(w * scale, (x + tile_size_w) * scale)
                    oye = min(h * scale, (y + tile_size_h) * scale)
                    txs, tys = (x - xs) * scale, (y - ys) * scale
                    
                    output_img[oys:oye, oxs:oxe] = out_np[tys:tys + (oye - oys), txs:txs + (oxe - oxs)]
                    current_tile += 1
                
                self.progress.emit(current_tile, total_tiles)
                
        except Exception as e:
            err_str, err_clean = _clean_exception_msg(e)
            
            logger.error(f"Error en upscale tiling: {err_str}")
            
            # Detectar errores de memoria (VRAM insuficiente)
            if "memoria" in err_clean or "memory" in err_clean or "out of memory" in err_clean:
                vram_available = _get_vram_info()
                
                # Si el fallback es la primera vez
                if not force_fixed_dim or force_fixed_dim > 128:
                    logger.warning("Insuficiente VRAM. Fallback: tiles de 128x128")
                    return self._process_upscale_tiled(img_rgba, model_path, force_fixed_dim=128, force_batch_size=1)
                
                # Si ya estábamos en fallback, lanzar error clara
                raise RuntimeError(
                    "❌ LIMITACIÓN DE HARDWARE\n\n"
                    + _format_vram_warning(vram_available)
                )
            
            # Detectar errores de shape, "incompatible dimensions" o fallos de parámetros de DirectML (80070057)
            if "shape mismatch" in err_clean or "reshape" in err_clean or "dimensions" in err_clean or "80070057" in err_clean:
                if not force_fixed_dim and not (force_batch_size and force_batch_size > 1):
                    logger.warning("Fallback automático: Conflicto geométrico en el grafo. Probando mosaico rígido seguro de 512x512")
                    # Reintentamos con un tamaño de 512x512 y batch_size de 1 para máxima seguridad
                    return self._process_upscale_tiled(img_rgba, model_path, force_fixed_dim=512, force_batch_size=1)
            
            # Error genérico - mostrar el error técnico real
            raise RuntimeError(
                f"❌ ERROR EN PROCESAMIENTO DE IA\n\n"
                f"Error técnico: {err_str}\n\n"
                f"Si persiste:\n"
                f"• Intenta con otro modelo del catálogo\n"
                f"• Reduce el tamaño de la imagen\n"
                f"• Revisa los logs para más detalles"
            )

        # Restaurar canal alpha escalado (si existe)
        if img_rgba.shape[2] == 4:
            alpha = cv2.resize(img_rgba[:,:,3], (w * scale, h * scale), interpolation=cv2.INTER_LANCZOS4)
        else:
            alpha = np.full((h * scale, w * scale), 255, dtype=np.uint8)
        
        return np.dstack((output_img, alpha))


class ThumbnailLoaderThread(QThread):
    # Emitimos un bloque (lista de diccionarios) en lugar de una por una
    thumbnail_loaded_batch = pyqtSignal(list)
    finished_loading = pyqtSignal(int)
    
    def __init__(self, folder_path, image_files):
        super().__init__(); self.folder_path = folder_path; self.image_files = image_files; self._is_running = True
        
    @log_action("Cargando Miniaturas del Disco")
    def run(self):
        loaded_count = 0
        batch = []
        BATCH_SIZE = 15
        
        def load_single_image(file):
            if not self._is_running: return None
            file_path = os.path.join(self.folder_path, file)
            try:
                reader = QImageReader(file_path)
                reader.setAutoTransform(True)  # Importante para fotos de celular
                osz = reader.size()
                if osz.isValid():
                    width, height = osz.width(), osz.height()
                    osz.scale(QSize(140, 140), Qt.AspectRatioMode.KeepAspectRatio)
                    reader.setScaledSize(osz)
                    img = reader.read()
                    if not img.isNull():
                        return {
                            'file': file, 'file_path': file_path, 'img': img, 
                            'size': os.path.getsize(file_path), 'mtime': os.path.getmtime(file_path), 
                            'w': width, 'h': height, 'ext': os.path.splitext(file_path)[1].lower()
                        }
            except Exception as e: 
                logger.debug(f"Archivo ignorado/corrupto ({file}): {str(e)}")
            return None

        import concurrent.futures
        import os
        
        # Usar todos los núcleos disponibles para decodificar imágenes en paralelo
        max_workers = min(32, (os.cpu_count() or 4) * 2)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # executor.map garantiza que los resultados se devuelven en el mismo orden original
            for result in executor.map(load_single_image, self.image_files):
                if not self._is_running:
                    break
                if result:
                    batch.append(result)
                    loaded_count += 1
                    
                    if len(batch) >= BATCH_SIZE:
                        self.thumbnail_loaded_batch.emit(batch)
                        batch = []
                        
        # Emitir el remanente si quedó algo en el buffer
        if batch and self._is_running:
            self.thumbnail_loaded_batch.emit(batch)
            
        if self._is_running: self.finished_loading.emit(loaded_count)
        
    def stop(self): self._is_running = False
