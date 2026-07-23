import psutil
import os
import shutil
import sys

# Add root folder to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

print("1. Buscando y eliminando procesos fantasma de python...")
killed = 0
for proc in psutil.process_iter(['pid', 'name', 'exe']):
    try:
        if proc.info['name'] == 'python.exe' and proc.info['exe']:
            if 'pyqt_gallery' in proc.info['exe'].lower():
                if proc.pid != os.getpid():
                    proc.kill()
                    killed += 1
                    print(f"Eliminado proceso zombie PID: {proc.pid}")
        elif proc.info['name'] == 'FHVT_Studio_Image_Editor.exe':
            proc.kill()
            killed += 1
            print(f"Eliminado ejecutable zombie PID: {proc.pid}")
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass

print(f"Total de procesos aniquilados: {killed}")

print("2. Limpiando caché y archivos corruptos/incompletos de HuggingFace...")
from core.utils import get_base_path
cache_dir = os.path.join(get_base_path(), "models", "generative", "hf_cache")

from tools.generative_tool import is_model_downloaded

if os.path.exists(cache_dir):
    folders = [f for f in os.listdir(cache_dir) if f.startswith("models--")]
    removed_bytes = 0
    for folder in folders:
        folder_path = os.path.join(cache_dir, folder)
        repo_id = folder.replace("models--", "").replace("--", "/")
        if not is_model_downloaded(repo_id):
            print(f"Borrando modelo incompleto detectado: {repo_id}")
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    try:
                        removed_bytes += os.path.getsize(os.path.join(root, file))
                    except:
                        pass
            try:
                shutil.rmtree(folder_path)
            except Exception as e:
                print(f"No se pudo borrar {folder_path}: {e}")
    
    print(f"Limpieza completada. Espacio liberado: {removed_bytes / (1024*1024):.2f} MB")
else:
    print("No existe la carpeta hf_cache, nada que limpiar.")
