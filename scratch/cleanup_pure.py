import os
import shutil

cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'models', 'generative', 'hf_cache'))
print(f"Buscando en: {cache_dir}")

def is_model_downloaded(model_path):
    snapshots_path = os.path.join(model_path, "snapshots")
    if os.path.exists(snapshots_path):
        try:
            snapshots = os.listdir(snapshots_path)
            for snapshot in snapshots:
                snapshot_dir = os.path.join(snapshots_path, snapshot)
                if os.path.isdir(snapshot_dir):
                    if not os.path.exists(os.path.join(snapshot_dir, "model_index.json")):
                        continue
                    valid = True
                    for subfolder in ["unet", "vae", "text_encoder"]:
                        subfolder_path = os.path.join(snapshot_dir, subfolder)
                        if not os.path.exists(subfolder_path) or not os.listdir(subfolder_path):
                            valid = False
                            break
                    if valid:
                        return True
        except Exception:
            pass
    return False

if os.path.exists(cache_dir):
    folders = [f for f in os.listdir(cache_dir) if f.startswith("models--")]
    removed_bytes = 0
    for folder in folders:
        folder_path = os.path.join(cache_dir, folder)
        if not is_model_downloaded(folder_path):
            print(f"Borrando modelo incompleto: {folder}")
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
    print("No existe la carpeta hf_cache.")
