# FHVT Gallery AI

Este proyecto es una galería inteligente con herramientas integradas impulsadas por Inteligencia Artificial (Upscale, Quitar Fondo, Mapas de Profundidad, Normales, Segmentación con SAM y Generación). 

Esta guía detalla los pasos para instalar y ejecutar el proyecto localmente.

## 1. Requisitos Previos

*   **Python:** Instalar Python 3.10 o 3.11 (x64) desde [python.org](https://www.python.org/).
    *   **IMPORTANTE:** Durante la instalación en Windows, asegúrate de marcar la casilla **"Add Python to PATH"**.
*   **Git:** Instalar Git para Windows desde [git-scm.com](https://git-scm.com/).
*   *(Opcional)* **Aceleración por GPU:**
    *   Tarjetas NVIDIA: Drivers actualizados (CUDA Toolkit es opcional).
    *   Tarjetas AMD / Intel / NVIDIA: El proyecto incluye soporte universal automático mediante ONNX Runtime DirectML.

## 2. Instalación Paso a Paso

Abre una terminal (PowerShell o CMD) y sigue estos pasos:

### 2.1 Clonar el repositorio
```bash
git clone https://github.com/tu-usuario/FHVT_Gallery_AI.git
cd FHVT_Gallery_AI
```
*(Nota: Si ya descargaste el proyecto, simplemente abre la terminal dentro de la carpeta del proyecto y ve al paso 2.2)*

### 2.2 Crear el entorno virtual e instalar dependencias
Es necesario crear un entorno virtual para aislar las dependencias del proyecto:

```bash
python -m venv .venv
```

Luego, instala los requerimientos (ejecuta desde la carpeta principal en Windows):
```bash
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip install -r requirements.txt
```

### 2.3 Iniciar la aplicación
Puedes iniciar la aplicación fácilmente haciendo **doble clic en el archivo `run_app.bat`**, o si prefieres usar la consola, ejecuta:

```bash
.\.venv\Scripts\python.exe main.py
```

## 3. Modelos de Inteligencia Artificial

El sistema gestiona los modelos de IA de forma eficiente. No es necesario descargarlos manualmente por adelantado ni lidiar con archivos pesados.
*   En el primer inicio, la aplicación creará automáticamente las carpetas necesarias en `models/`.
*   Al utilizar cada herramienta por primera vez en la interfaz de usuario, el software descargará automáticamente el modelo oficial correspondiente desde Hugging Face.

## 4. Auditoría y Verificación

El proyecto incluye herramientas para comprobar que toda la arquitectura, las dependencias y las conexiones funcionen correctamente en tu equipo. Para ejecutar la validación:

Doble clic en **`run_audit.bat`**, o desde consola:
```bash
.\.venv\Scripts\python.exe audit_tools\run_audit_suite.py
```

## 5. Compilar Ejecutable Independiente (Opcional)

Si deseas crear un archivo ejecutable portable (`.exe`), el proyecto ya incluye la configuración preparada en `FHVT_Gallery_AI.spec`.

Para compilarlo:
```bash
.\.venv\Scripts\pyinstaller FHVT_Gallery_AI.spec
```

El archivo ejecutable final se generará en la ruta:
`dist/FHVT_Gallery_AI/FHVT_Gallery_AI.exe`
