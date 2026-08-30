import os
import gc
import math
import numpy as np
import traceback
from PyQt6.QtCore import QThread, pyqtSignal
from PIL import Image

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


class BaseMLWorker(QThread):
    """Clase base que maneja hilos, errores y limpieza de GPU para todos los modelos."""

    status = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def _setup_torch_threads(self):
        import torch

        try:
            torch.set_num_threads(1)
        except RuntimeError:
            pass

    def _cleanup_vram(self, *objects_to_delete):
        """Fuerza la limpieza de VRAM destruyendo los objetos pasados."""
        for obj in objects_to_delete:
            if obj is not None:
                del obj

        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

        gc.collect()

    def run(self):
        """Estructura de plantilla. Las clases hijas solo deben sobrescribir execute_task"""
        try:
            self._setup_torch_threads()
            self.execute_task()
        except Exception as e:
            err_str = traceback.format_exc()
            self._cleanup_vram()  # Limpieza de emergencia ANTES de emitir error
            self.error.emit(
                f"Error en {self.__class__.__name__}:\n{str(e)}\n\nDetalles:\n{err_str}"
            )

    def execute_task(self):
        """Sobrescribir en las clases hijas. La lógica real va aquí."""
        raise NotImplementedError


class GenerativeAIWorker(BaseMLWorker):
    progress = pyqtSignal(int, int)
    result_ready = pyqtSignal(object)

    def __init__(
        self,
        mode,
        base_image,
        prompt,
        base_model_path,
        lora_path=None,
        denoising_strength=0.5,
        num_images=1,
        num_inference_steps=30,
        mask_image=None,
    ):
        super().__init__()
        self.mode = mode  # "img2img" o "txt2img" o "inpaint"
        self.base_image = base_image  # numpy array (RGB)
        self.prompt = prompt
        self.base_model_path = base_model_path
        self.lora_path = lora_path
        self.denoising_strength = denoising_strength
        self.num_images = num_images
        self.num_inference_steps = num_inference_steps
        self.mask_image = mask_image

    def execute_task(self):
        import torch
        from diffusers import StableDiffusionImg2ImgPipeline, StableDiffusionPipeline, StableDiffusionInpaintPipeline

        pipeline = None

        try:
            self.progress.emit(5, 100)
            self.status.emit("Iniciando motor Generativo (PyTorch)...")

            # --- PARCHE PARA SAFETENSORS (Evita Access Violation en Windows) ---
            try:
                import safetensors.torch

                if not hasattr(safetensors.torch, "_original_load_file"):
                    safetensors.torch._original_load_file = safetensors.torch.load_file

                    def patched_load_file(filename, device="cpu"):
                        with open(filename, "rb") as f:
                            buffer = f.read()
                        return safetensors.torch.load(buffer)

                    safetensors.torch.load_file = patched_load_file
            except ImportError:
                pass
            # -------------------------------------------------------------------

            # Preparar imagen para img2img
            init_image = None
            if self.mode == "img2img" and self.base_image is not None:
                self.progress.emit(10, 100)
                self.status.emit("Preparando imagen base...")
                init_image = Image.fromarray(self.base_image).convert("RGB")

                # Ejecutar redimensionamiento optimizando área total (Max 262144 píxeles)
                max_area = 512 * 512
                w, h = init_image.size
                current_area = w * h

                if current_area > max_area:
                    scale = math.sqrt(max_area / current_area)
                    new_w = w * scale
                    new_h = h * scale
                else:
                    new_w, new_h = w, h

                # Asegurar dimensiones múltiplo de 8 para SD
                new_w_8 = int(round(new_w / 8.0)) * 8
                new_h_8 = int(round(new_h / 8.0)) * 8

                if new_w_8 != w or new_h_8 != h:
                    init_image = init_image.resize((new_w_8, new_h_8), Image.LANCZOS)
                    
            mask_pil = None
            if self.mode == "inpaint" and self.mask_image is not None:
                self.progress.emit(10, 100)
                self.status.emit("Preparando máscara de Inpainting...")
                
                # init_image ya se preparó si base_image fue provista
                if init_image is None and self.base_image is not None:
                    init_image = Image.fromarray(self.base_image).convert("RGB")
                    # Escalar al igual que img2img
                    max_area = 512 * 512
                    w, h = init_image.size
                    current_area = w * h
                    if current_area > max_area:
                        scale = math.sqrt(max_area / current_area)
                        new_w = w * scale
                        new_h = h * scale
                    else:
                        new_w, new_h = w, h
                    new_w_8 = int(round(new_w / 8.0)) * 8
                    new_h_8 = int(round(new_h / 8.0)) * 8
                    if new_w_8 != w or new_h_8 != h:
                        init_image = init_image.resize((new_w_8, new_h_8), Image.LANCZOS)
                        
                mask_pil = Image.fromarray(self.mask_image).convert("L")
                if init_image:
                    mask_pil = mask_pil.resize(init_image.size, Image.NEAREST)

            if self._is_cancelled:
                return

            # Cargar modelo base
            self.progress.emit(20, 100)
            self.status.emit("Cargando modelo base...")

            # Forzar float32 para prevenir imágenes negras (NaNs) en GTX 16xx
            model_dtype = torch.float32

            if self.mode == "inpaint":
                pipeline_class = StableDiffusionInpaintPipeline
            elif self.mode == "img2img":
                pipeline_class = StableDiffusionImg2ImgPipeline
            else:
                pipeline_class = StableDiffusionPipeline

            if os.path.isfile(self.base_model_path):
                pipeline = pipeline_class.from_single_file(
                    self.base_model_path,
                    torch_dtype=model_dtype,
                    use_safetensors=True,
                    safety_checker=None,
                    requires_safety_checker=False,
                    local_files_only=True,
                    low_cpu_mem_usage=False,
                )
            else:
                pipeline = pipeline_class.from_pretrained(
                    self.base_model_path,
                    torch_dtype=model_dtype,
                    use_safetensors=True,
                    safety_checker=None,
                    requires_safety_checker=False,
                    local_files_only=True,
                    low_cpu_mem_usage=False,
                )

            # Optimizar cálculos para reducir consumo VRAM
            pipeline.enable_attention_slicing()

            # PyTorch 2.0 usa Scaled Dot-Product Attention de forma nativa.
            # No forzamos xformers porque en GPUs viejas (ej. Compute 7.5) causa crash si no está compilado a medida.

            # Cargar LoRA previo a CPU OFFLOAD
            if self.lora_path and os.path.isfile(self.lora_path):
                self.progress.emit(40, 100)
                self.status.emit(
                    f"Inyectando LoRA de estilo: {os.path.basename(self.lora_path)}..."
                )

                pipeline.load_lora_weights(
                    os.path.dirname(self.lora_path),
                    weight_name=os.path.basename(self.lora_path),
                )

                # Forzar dtype correcto en módulos LoRA inyectados
                pipeline.unet.to(dtype=model_dtype)
                if (
                    hasattr(pipeline, "text_encoder")
                    and pipeline.text_encoder is not None
                ):
                    pipeline.text_encoder.to(dtype=model_dtype)

            # Descargar componentes secuencialmente (vital para 4GB VRAM)
            pipeline.enable_model_cpu_offload()

            if self._is_cancelled:
                return

            # Generar inferencia
            self.progress.emit(50, 100)

            # Forzar Negative Prompt en modelos anime/arte
            negative_prompt = "(worst quality, low quality, normal quality:1.4), bad anatomy, bad hands, missing fingers, extra digit, blurry, ugly, watermark, signature, artifacts, deformed, noise, ugly face"

            results_np = []
            for i in range(self.num_images):
                if self._is_cancelled:
                    return
                self.status.emit(f"Generando variación {i + 1} de {self.num_images}...")

                # Inyectar semilla única por iteración
                seed = torch.randint(0, 1000000, (1,)).item()
                generator = torch.Generator(device="cpu").manual_seed(seed)

                base_steps = self.num_inference_steps
                actual_steps = (
                    base_steps
                    if self.mode == "txt2img"
                    else max(1, int(base_steps * self.denoising_strength))
                )

                # Configurar parámetros comunes
                def step_callback(step_idx: int, timestep, latents):
                    if self._is_cancelled:
                        raise InterruptedError("Generación cancelada por el usuario")
                    self.status.emit(
                        f"Generando variación {i + 1} de {self.num_images} — Paso {step_idx + 1}/{actual_steps}"
                    )

                gen_kwargs = {
                    "prompt": self.prompt,
                    "negative_prompt": negative_prompt,
                    "guidance_scale": 7.0,
                    "num_inference_steps": base_steps,
                    "generator": generator,
                    "callback": step_callback,
                    "callback_steps": 1,
                }

                if self.mode == "inpaint" and init_image is not None and mask_pil is not None:
                    gen_kwargs["image"] = init_image
                    gen_kwargs["mask_image"] = mask_pil
                    gen_kwargs["strength"] = self.denoising_strength
                    gen_kwargs["width"] = init_image.width
                    gen_kwargs["height"] = init_image.height
                elif self.mode == "img2img" and init_image is not None:
                    gen_kwargs["image"] = init_image
                    gen_kwargs["strength"] = self.denoising_strength
                else:
                    gen_kwargs["width"] = 512
                    gen_kwargs["height"] = 512

                try:
                    result = pipeline(**gen_kwargs).images[0]
                    results_np.append(np.array(result))
                except InterruptedError:
                    return

                # Calcular progreso proporcional
                prog = 50 + int(40 * (i + 1) / self.num_images)
                self.progress.emit(prog, 100)

            if self._is_cancelled:
                return

            self.progress.emit(90, 100)
            self.status.emit("Finalizando y limpiando VRAM...")

        finally:
            self._cleanup_vram(pipeline)

        self.progress.emit(100, 100)
        self.status.emit("¡Completado!")
        self.result_ready.emit(results_np)


class CaptioningWorker(BaseMLWorker):
    progress = pyqtSignal(str)
    result_ready = pyqtSignal(str)

    MODEL_ID = "vikhyatk/moondream2"
    REVISION = "2024-08-26"

    def __init__(self, base_image_np):
        super().__init__()
        self.base_image_np = base_image_np

    def execute_task(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        model = None
        tokenizer = None
        enc_image = None

        try:
            self.progress.emit(
                "Cargando modelo avanzado VLM (~3.5GB la primera vez)..."
            )

            image = Image.fromarray(self.base_image_np)

            # Reducir imagen preventivamente para Moondream
            max_dim = 768
            w, h = image.size
            if max(w, h) > max_dim:
                scale = max_dim / max(w, h)
                new_w, new_h = int(w * scale), int(h * scale)
                image = image.resize((new_w, new_h), Image.LANCZOS)

            device = "cuda" if torch.cuda.is_available() else "cpu"

            model = AutoModelForCausalLM.from_pretrained(
                self.MODEL_ID,
                trust_remote_code=True,
                revision=self.REVISION,
                torch_dtype=torch.float16,
            ).to(device)
            tokenizer = AutoTokenizer.from_pretrained(
                self.MODEL_ID, revision=self.REVISION
            )

            if self._is_cancelled:
                return

            self.progress.emit("Analizando composición y estilo...")

            prompt = "Provide maximum 15 comma-separated keywords describing this image. Focus purely on art style, main subject, and key visual elements. Do not use full sentences."

            enc_image = model.encode_image(image)

            if self._is_cancelled:
                return

            caption = model.answer_question(enc_image, prompt, tokenizer)

        finally:
            self.progress.emit("Liberando 3.5GB de VRAM...")
            self._cleanup_vram(model, tokenizer, enc_image)

        self.result_ready.emit(caption)


class PromptEnhancerWorker(BaseMLWorker):
    progress = pyqtSignal(str)
    result_ready = pyqtSignal(str)

    MODEL_ID = "Gustavosta/MagicPrompt-Stable-Diffusion"
    LENGTHS = {"Poco": 20, "Medio": 45, "Largo": 80}

    def __init__(self, initial_prompt, length_mode):
        super().__init__()
        self.initial_prompt = initial_prompt
        self.length_mode = length_mode

    def execute_task(self):
        import torch
        from transformers import pipeline

        enhancer = None

        try:
            self.progress.emit("Cargando IA de expansión (GPT-2)...")

            max_new = self.LENGTHS.get(self.length_mode, 45)
            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if torch.cuda.is_available() else torch.float32

            enhancer = pipeline(
                "text-generation", model=self.MODEL_ID, device=device, torch_dtype=dtype
            )

            if self._is_cancelled:
                return

            self.progress.emit(f"Expandiendo prompt ({self.length_mode})...")

            result = enhancer(
                self.initial_prompt,
                max_new_tokens=max_new,
                num_return_sequences=1,
                repetition_penalty=1.2,
                do_sample=True,
                temperature=0.8,
            )

            enhanced_text = result[0]["generated_text"].strip()

        finally:
            self.progress.emit("Liberando memoria...")
            self._cleanup_vram(enhancer)

        self.result_ready.emit(enhanced_text)

class AutoMaskingWorker(BaseMLWorker):
    progress = pyqtSignal(str)
    result_ready = pyqtSignal(object)  # Returns QPixmap mask

    def __init__(self, base_image_np, target_object):
        super().__init__()
        self.base_image_np = base_image_np
        self.target_object = target_object
        self.MODEL_ID = "google/owlvit-base-patch32"

    def execute_task(self):
        import torch
        import cv2
        import numpy as np
        from PyQt6.QtGui import QImage, QPixmap
        from transformers import pipeline
        from core.threads import _load_model
        from tools.sam_tool import _load_sam_decoder
        from tools.ai_tool import get_base_path
        import os

        # 1. Ejecutar OwlViT para detectar la caja delimitadora (Bounding Box)
        self.progress.emit(f"Buscando '{self.target_object}' en la imagen...")
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        detector = pipeline(model=self.MODEL_ID, task="zero-shot-object-detection", device=device)
        
        image = Image.fromarray(self.base_image_np).convert("RGB")
        
        # TRUCO: Expandir automáticamente el prompt para burlar el sesgo fotográfico
        search_terms = [
            self.target_object, 
            f"anime {self.target_object}", 
            f"illustration of {self.target_object}",
            f"2d character {self.target_object}"
        ]
        
        # Reducimos el umbral al 2% (0.02). Como buscamos el 'max' luego, 
        # no importa si detecta basura, nos quedaremos con el que tenga mayor puntaje real.
        preds = detector(image, candidate_labels=search_terms, threshold=0.02)
        
        del detector
        self._cleanup_vram()

        if self._is_cancelled:
            return

        if not preds:
            raise ValueError(f"No se pudo encontrar '{self.target_object}' en la imagen.")
            
        # Tomar la predicción con mayor confianza
        best_pred = max(preds, key=lambda x: x["score"])
        box = best_pred["box"]
        xmin, ymin, xmax, ymax = box["xmin"], box["ymin"], box["xmax"], box["ymax"]

        # 2. Cargar MobileSAM para generar la máscara
        self.progress.emit("Generando máscara semántica perfecta (SAM)...")
        
        base_path = get_base_path()
        enc_path = os.path.normpath(os.path.join(base_path, "models/sam/mobilesam.encoder.onnx"))
        
        if not os.path.exists(enc_path):
            self.progress.emit("Descargando MobileSAM (única vez, ~40MB)...")
            from huggingface_hub import hf_hub_download
            import shutil
            os.makedirs(os.path.dirname(enc_path), exist_ok=True)
            
            enc_cache = hf_hub_download(repo_id="PulpCut/mobilesam-onnx", filename="mobilesam.encoder.onnx")
            shutil.copy2(enc_cache, enc_path)
            
            dec_cache = hf_hub_download(repo_id="PulpCut/mobilesam-onnx", filename="mobilesam.decoder.onnx")
            dec_path = os.path.join(os.path.dirname(enc_path), "mobilesam.decoder.onnx")
            shutil.copy2(dec_cache, dec_path)
            
        # Ejecutar Encoder (redimensionar a 1024x1024)
        session_enc = _load_model(enc_path)
        img_resized = cv2.resize(self.base_image_np, (1024, 1024), interpolation=cv2.INTER_CUBIC)
        img_input = img_resized.astype(np.float32)
        
        out_enc = session_enc.run(None, {"input_image": img_input})
        embedding = out_enc[0]
        
        if self._is_cancelled:
            return
            
        # Ejecutar Decoder
        session_dec = _load_sam_decoder()
        
        # Escalar coordenadas de la caja a 1024x1024
        orig_w, orig_h = image.size
        scale_x = 1024.0 / orig_w
        scale_y = 1024.0 / orig_h
        
        pts = np.array([[xmin * scale_x, ymin * scale_y], [xmax * scale_x, ymax * scale_y]], dtype=np.float32)
        lbls = np.array([2, 3], dtype=np.float32) # 2 y 3 representan TopLeft y BottomRight de una caja
        
        point_coords = pts.reshape(1, 2, 2)
        point_labels = lbls.reshape(1, 2)
        mask_input = np.zeros((1, 1, 256, 256), dtype=np.float32)
        has_mask_input = np.zeros((1,), dtype=np.float32)
        orig_im_size = np.array([float(1024), float(1024)], dtype=np.float32)
        
        out_dec = session_dec.run(None, {
            "image_embeddings": embedding,
            "point_coords": point_coords,
            "point_labels": point_labels,
            "mask_input": mask_input,
            "has_mask_input": has_mask_input,
            "orig_im_size": orig_im_size
        })
        
        mask = out_dec[0][0, 0, :, :]
        
        # Redimensionar máscara al original
        mask_cv = cv2.resize(mask, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
        mask_cv = (mask_cv > 0.0).astype(np.uint8) * 255 # Binarizar
        
        # Convertir a QPixmap (Blanco y Negro)
        # Blanco = Máscara, Negro = Fondo
        color_mask = np.zeros((orig_h, orig_w, 4), dtype=np.uint8)
        color_mask[:, :, 0] = mask_cv # R
        color_mask[:, :, 1] = mask_cv # G
        color_mask[:, :, 2] = mask_cv # B
        color_mask[:, :, 3] = 255     # Alpha sólido
        
        bytes_per_line = 4 * orig_w
        qimg = QImage(color_mask.data, orig_w, orig_h, bytes_per_line, QImage.Format.Format_RGBA8888).copy()
        mask_pixmap = QPixmap.fromImage(qimg)
        
        self.result_ready.emit(mask_pixmap)
