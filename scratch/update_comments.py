import os

filepath = 'tools/generative_tool.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

replacements = {
    "# Secuestramos el tqdm global de huggingface_hub dentro del subproceso\n    # porque snapshot_download no pasa tqdm_class a las descargas internas.": "# Inyectar tqdm global en subproceso",
    "# Solo enviamos actualizaciones de bytes": "# Enviar actualizaciones bytes",
    "# Ignoramos pesos 16-bits porque la app usa float32 (evita bug GTX 16xx)": "# Ignorar pesos 16-bits",
    "# Ignoramos pesos non-ema (solo sirven para entrenar, pesan ~3.5GB)": "# Ignorar pesos non-ema",
    "# Ignoramos pesos para Flax": "# Ignorar pesos flax",
    "# Ignoramos checkpoints viejos": "# Ignorar checkpoints viejos",
    "# Ignoramos pesos para Keras": "# Ignorar pesos keras",
    "# Ignoramos pesos para Rust": "# Ignorar pesos rust",
    "# Verificar que contenga model_index.json para asegurar que no está incompleto": "# Verificar model_index.json",
    "# Verificar que las carpetas críticas de diffusers no estén vacías": "# Verificar carpetas críticas",
    "# MATAMOS el proceso desde el Sistema Operativo": "# Matar proceso OS",
    "# Esperamos a que el sistema limpie la memoria": "# Esperar limpieza memoria",
    "# 1. Creamos la cola de comunicación": "# Crear cola comunicación",
    "# 2. Lanzamos la descarga en el proceso aislado": "# Iniciar descarga aislada",
    "# 3. Escuchando actualizaciones": "# Escuchar actualizaciones",
    "# Si el usuario canceló, el método cancel() ya se encargó": "# Ignorar si cancelado",
    "# Leer mensajes. Timeout para no bloquear el hilo infinitamente": "# Leer mensajes timeout",
    "# 4. Manejo de seguridad": "# Manejar cierre inesperado",
    "# Botón de Acción": "# Configurar botón acción",
    "# 0. Modo de Operación": "# Configurar modo operación",
    "# 1. Base Model": "# Configurar modelo base",
    "# Contenedor de la tarjeta del modelo": "# Crear contenedor tarjeta",
    "# 2. LoRA": "# Configurar lora",
    "# 2.5. Trigger Word": "# Configurar trigger word",
    "# 3. Denoising Strength": "# Configurar denoising",
    "# 3.2. Pasos de Inferencia": "# Configurar pasos inferencia",
    "# 3.5. Batch Size": "# Configurar batch size",
    "# 4. Prompt": "# Configurar prompt",
    "# Downloader Progress Layout": "# Configurar layout descarga",
    "# Botones finales": "# Configurar botones finales",
    "# El botón de prompt siempre está visible, pero cambia su función/texto": "# Actualizar botón prompt",
    "# Mostrar el progreso en formato (0.25GB / 5.0GB)": "# Mostrar progreso formateado",
    "# Inyectar trigger de forma inteligente al momento de ejecución": "# Inyectar trigger inteligente",
    "# Use native finished signal for safe deletion": "# Borrar worker terminado",
    "# Moondream2 ya es inteligente y describe el estilo, ya no necesitamos hardcodear prefijos.": "# Procesar texto moondream"
}

for old, new in replacements.items():
    content = content.replace(old, new)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
