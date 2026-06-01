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
    ):
        super().__init__()
        self.mode = mode  # "img2img" o "txt2img"
        self.base_image = base_image  # numpy array (RGB)
        self.prompt = prompt
        self.base_model_path = base_model_path
        self.lora_path = lora_path
        self.denoising_strength = denoising_strength
        self.num_images = num_images
        self.num_inference_steps = num_inference_steps

    def execute_task(self):
        import torch
        from diffusers import StableDiffusionImg2ImgPipeline, StableDiffusionPipeline

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

            # 1. Preparar imagen (Solo para img2img)
            init_image = None
            if self.mode == "img2img" and self.base_image is not None:
                self.progress.emit(10, 100)
                self.status.emit("Preparando imagen base...")
                init_image = Image.fromarray(self.base_image).convert("RGB")

                # Redimensionar optimizando el ÁREA TOTAL (512x512 = 262144 píxeles)
                max_area = 512 * 512
                w, h = init_image.size
                current_area = w * h

                if current_area > max_area:
                    scale = math.sqrt(max_area / current_area)
                    new_w = w * scale
                    new_h = h * scale
                else:
                    new_w, new_h = w, h

                # SD requiere que las dimensiones sean múltiplos de 8
                new_w_8 = int(round(new_w / 8.0)) * 8
                new_h_8 = int(round(new_h / 8.0)) * 8

                if new_w_8 != w or new_h_8 != h:
                    init_image = init_image.resize((new_w_8, new_h_8), Image.LANCZOS)

            if self._is_cancelled:
                return

            # Cargar modelo base
            self.progress.emit(20, 100)
            self.status.emit("Cargando modelo base...")

            # Usar float32 para evitar el bug de imágenes negras (NaNs en VRAM) en tarjetas GTX 16xx.
            model_dtype = torch.float32

            pipeline_class = (
                StableDiffusionImg2ImgPipeline
                if self.mode == "img2img"
                else StableDiffusionPipeline
            )

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

            # Optimización de cálculo para contener el consumo de VRAM
            pipeline.enable_attention_slicing()

            # Usar xformers si está disponible (vital para evitar NaNs en GTX 1650/1660 en float16)
            try:
                import xformers  # noqa: F401

                pipeline.enable_xformers_memory_efficient_attention()
            except ImportError:
                pass

            # 3. Cargar LoRA si existe (¡DEBE HACERSE ANTES DEL CPU OFFLOAD!)
            if self.lora_path and os.path.isfile(self.lora_path):
                self.progress.emit(40, 100)
                self.status.emit(
                    f"Inyectando LoRA de estilo: {os.path.basename(self.lora_path)}..."
                )

                pipeline.load_lora_weights(
                    os.path.dirname(self.lora_path),
                    weight_name=os.path.basename(self.lora_path),
                )

                # Forzar que los módulos del LoRA inyectados adopten el dtype correcto
                pipeline.unet.to(dtype=model_dtype)
                if (
                    hasattr(pipeline, "text_encoder")
                    and pipeline.text_encoder is not None
                ):
                    pipeline.text_encoder.to(dtype=model_dtype)

            # Descarga automática secuencial de componentes (Crucial para tarjetas de 4GB)
            pipeline.enable_model_cpu_offload()

            if self._is_cancelled:
                return

            # 4. Generar
            self.progress.emit(50, 100)

            # El Negative Prompt es OBLIGATORIO en modelos de Anime/Arte para evitar resultados horrendos
            negative_prompt = "(worst quality, low quality, normal quality:1.4), bad anatomy, bad hands, missing fingers, extra digit, blurry, ugly, watermark, signature, artifacts, deformed, noise, ugly face"

            results_np = []
            for i in range(self.num_images):
                if self._is_cancelled:
                    return
                self.status.emit(f"Generando variación {i + 1} de {self.num_images}...")

                # Semilla única para cada iteración para asegurar variaciones
                seed = torch.randint(0, 1000000, (1,)).item()
                generator = torch.Generator(device="cpu").manual_seed(seed)

                base_steps = self.num_inference_steps
                actual_steps = (
                    base_steps
                    if self.mode == "txt2img"
                    else max(1, int(base_steps * self.denoising_strength))
                )

                # Parámetros comunes
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

                # Inyección condicional
                if self.mode == "img2img" and init_image is not None:
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

                # Progreso proporcional
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

            # Moondream no necesita reducir tanto la imagen como BLIP, pero lo hacemos por seguridad de RAM
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

            prompt = "Describe this image in detail. Specifically mention its art style (e.g., anime, realistic photography, oil painting, 3d render, cartoon), its composition, and its main subject or actions."

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
