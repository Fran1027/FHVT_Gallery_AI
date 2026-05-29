import os
import gc
import math
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
from PIL import Image

class GenerativeAIWorker(QThread):
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, mode, base_image, prompt, base_model_path, lora_path=None, denoising_strength=0.5, num_images=1, num_inference_steps=30):
        super().__init__()
        self.mode = mode # "img2img" o "txt2img"
        self.base_image = base_image # numpy array (RGB)
        self.prompt = prompt
        self.base_model_path = base_model_path
        self.lora_path = lora_path
        self.denoising_strength = denoising_strength
        self.num_images = num_images
        self.num_inference_steps = num_inference_steps
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            self.progress.emit(5, 100)
            self.status.emit("Iniciando motor Generativo (PyTorch)...")
            
            import torch
            # Forzar un solo hilo en CPU para evitar conflictos de OpenMP en hilos secundarios de Qt
            try:
                torch.set_num_threads(1)
            except RuntimeError:
                pass
            
            from diffusers import StableDiffusionImg2ImgPipeline, StableDiffusionPipeline
            
            # --- PARCHE PARA SAFETENSORS (Evita Access Violation en Windows) ---
            # La implementación C++ de mmap de safetensors suele colisionar con hilos secundarios en Qt.
            # Al leer el archivo como bytes y usar .load(), evitamos mmap por completo.
            try:
                import safetensors.torch
                if not hasattr(safetensors.torch, '_original_load_file'):
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
            
            if self._is_cancelled: return
            
            # Cargar modelo base
            self.progress.emit(20, 100)
            self.status.emit("Cargando modelo base...")
            
            # Usar float32 para evitar el bug de imágenes negras (NaNs en VRAM) en tarjetas GTX 16xx.
            # Al compensarlo con enable_model_cpu_offload() y xformers, el consumo es aceptable en 4GB de VRAM.
            model_dtype = torch.float32
            
            pipeline_class = StableDiffusionImg2ImgPipeline if self.mode == "img2img" else StableDiffusionPipeline
            
            if os.path.isfile(self.base_model_path):
                pipeline = pipeline_class.from_single_file(
                    self.base_model_path,
                    torch_dtype=model_dtype,
                    use_safetensors=True,
                    safety_checker=None,
                    requires_safety_checker=False,
                    local_files_only=True,
                    low_cpu_mem_usage=False
                )
            else:
                pipeline = pipeline_class.from_pretrained(
                    self.base_model_path,
                    torch_dtype=model_dtype,
                    use_safetensors=True,
                    safety_checker=None,
                    requires_safety_checker=False,
                    local_files_only=True,
                    low_cpu_mem_usage=False
                )
            
            # Optimización de cálculo para contener el consumo de VRAM
            pipeline.enable_attention_slicing()
            
            # Usar xformers si está disponible (vital para evitar NaNs en GTX 1650/1660 en float16)
            try:
                import xformers
                pipeline.enable_xformers_memory_efficient_attention()
            except ImportError:
                pass
            
            # Como usamos float32, no es necesario hacer el parche del VAE.
            # 3. Cargar LoRA si existe (¡DEBE HACERSE ANTES DEL CPU OFFLOAD!)
            if self.lora_path and os.path.isfile(self.lora_path):
                self.progress.emit(40, 100)
                self.status.emit(f"Inyectando LoRA de estilo: {os.path.basename(self.lora_path)}...")
                
                pipeline.load_lora_weights(
                    os.path.dirname(self.lora_path), 
                    weight_name=os.path.basename(self.lora_path)
                )
                
                # Forzar que los módulos del LoRA inyectados adopten el dtype correcto
                pipeline.unet.to(dtype=model_dtype)
                if hasattr(pipeline, "text_encoder") and pipeline.text_encoder is not None:
                    pipeline.text_encoder.to(dtype=model_dtype)
            
            # Descarga automática secuencial de componentes (Crucial para tarjetas de 4GB)
            pipeline.enable_model_cpu_offload()
            
            if self._is_cancelled: return
            
            # 4. Generar
            self.progress.emit(50, 100)
            
            # El Negative Prompt es OBLIGATORIO en modelos de Anime/Arte para evitar resultados horrendos
            negative_prompt = "(worst quality, low quality, normal quality:1.4), bad anatomy, bad hands, missing fingers, extra digit, blurry, ugly, watermark, signature, artifacts, deformed, noise, ugly face"
            
            results_np = []
            for i in range(self.num_images):
                if self._is_cancelled: return
                self.status.emit(f"Generando variación {i+1} de {self.num_images}...")
                
                # Semilla única para cada iteración para asegurar variaciones
                seed = torch.randint(0, 1000000, (1,)).item()
                generator = torch.Generator(device="cpu").manual_seed(seed)
                
                base_steps = self.num_inference_steps
                actual_steps = base_steps if self.mode == "txt2img" else max(1, int(base_steps * self.denoising_strength))
                
                # Parámetros comunes
                def step_callback(step_idx: int, timestep, latents):
                    if self._is_cancelled:
                        raise InterruptedError("Generación cancelada por el usuario")
                    self.status.emit(f"Generando variación {i+1} de {self.num_images} — Paso {step_idx+1}/{actual_steps}")
                
                gen_kwargs = {
                    "prompt": self.prompt,
                    "negative_prompt": negative_prompt,
                    "guidance_scale": 7.0,
                    "num_inference_steps": base_steps,
                    "generator": generator,
                    "callback": step_callback,
                    "callback_steps": 1
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
            
            if self._is_cancelled: return
            
            # 5. Convertir de vuelta a numpy RGB
            self.progress.emit(90, 100)
            self.status.emit("Finalizando y limpiando VRAM...")
            
            # Limpieza segura de tensores
            del pipeline
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()
            
            self.progress.emit(100, 100)
            self.status.emit("¡Completado!")
            self.finished.emit(results_np)
            
        except Exception as e:
            import traceback
            err_str = traceback.format_exc()
            self.error.emit(f"Error Generativo:\n{str(e)}\n\nDetalles técnicos:\n{err_str}")
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                gc.collect()
            except:
                pass

class CaptioningWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, base_image_np):
        super().__init__()
        self.base_image_np = base_image_np

    def run(self):
        try:
            self.progress.emit("Cargando modelo avanzado VLM (~3.5GB la primera vez)...")
            import torch
            # Forzar un solo hilo en CPU para evitar conflictos en hilos secundarios de Qt
            try:
                torch.set_num_threads(1)
            except RuntimeError:
                pass
            
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from PIL import Image

            image = Image.fromarray(self.base_image_np)
            
            # Moondream no necesita reducir tanto la imagen como BLIP, pero lo hacemos por seguridad de RAM
            max_dim = 768
            w, h = image.size
            if max(w, h) > max_dim:
                scale = max_dim / max(w, h)
                new_w, new_h = int(w * scale), int(h * scale)
                image = image.resize((new_w, new_h), Image.LANCZOS)

            model_id = "vikhyatk/moondream2"
            revision = "2024-08-26"
            device = "cuda" if torch.cuda.is_available() else "cpu"
            
            model = AutoModelForCausalLM.from_pretrained(
                model_id, 
                trust_remote_code=True, 
                revision=revision,
                torch_dtype=torch.float16
            ).to(device)
            tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)

            self.progress.emit("Analizando composición y estilo...")
            
            prompt = "Describe this image in detail. Specifically mention its art style (e.g., anime, realistic photography, oil painting, 3d render, cartoon), its composition, and its main subject or actions."
            
            enc_image = model.encode_image(image)
            caption = model.answer_question(enc_image, prompt, tokenizer)

            self.progress.emit("Liberando 3.5GB de VRAM...")
            del model
            del tokenizer
            del enc_image
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            import gc
            gc.collect()

            self.finished.emit(caption)
        except Exception as e:
            import traceback
            err_str = traceback.format_exc()
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                import gc
                gc.collect()
            except:
                pass
            self.error.emit(f"Error en Moondream VLM:\n{str(e)}\n\nTraceback:\n{err_str}")

class PromptEnhancerWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, initial_prompt, length_mode):
        super().__init__()
        self.initial_prompt = initial_prompt
        self.length_mode = length_mode

    def run(self):
        try:
            self.progress.emit("Cargando IA de expansión (GPT-2)...")
            import torch
            try:
                torch.set_num_threads(1)
            except RuntimeError:
                pass
            
            from transformers import pipeline
            
            lengths = {
                "Poco": 20,
                "Medio": 45,
                "Largo": 80
            }
            max_new = lengths.get(self.length_mode, 45)
            
            # Cargar pipeline
            enhancer = pipeline(
                "text-generation", 
                model="Gustavosta/MagicPrompt-Stable-Diffusion",
                device="cuda" if torch.cuda.is_available() else "cpu",
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
            )
            
            self.progress.emit(f"Expandiendo prompt ({self.length_mode})...")
            
            result = enhancer(
                self.initial_prompt, 
                max_new_tokens=max_new, 
                num_return_sequences=1,
                repetition_penalty=1.2,
                do_sample=True,
                temperature=0.8
            )
            
            enhanced_text = result[0]["generated_text"].strip()
            
            self.progress.emit("Liberando memoria...")
            del enhancer
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            import gc
            gc.collect()
            
            self.finished.emit(enhanced_text)
            
        except Exception as e:
            import traceback
            err_str = traceback.format_exc()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                import gc
                gc.collect()
            except:
                pass
            self.error.emit(f"Error en Expansión de Prompt:\n{str(e)}\n\nTraceback:\n{err_str}")