import os
import sys
from pathlib import Path
from PIL import Image

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def generate_ico(png_path, ico_path):
    """Genera un archivo .ico multi-resolución de alta calidad a partir de un PNG."""
    try:
        with Image.open(png_path) as img:
            img_rgba = img.convert("RGBA")
            sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
            img_rgba.save(ico_path, format="ICO", sizes=sizes)
            print(f"[+] Icono generado exitosamente en: {ico_path}")
            return True
    except Exception as e:
        print(f"[!] Error generando .ico: {e}")
        return False

def create_windows_shortcut(target_exe, script_path, work_dir, ico_path, shortcut_path, description="FHVT Studio Image Editor"):
    """Crea un acceso directo .lnk de Windows usando WScript.Shell."""
    import win32com.client # O fallback con PowerShell / VBScript
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.TargetPath = str(target_exe)
        shortcut.Arguments = f'"{script_path}"'
        shortcut.WorkingDirectory = str(work_dir)
        shortcut.Description = description
        if ico_path and os.path.exists(ico_path):
            shortcut.IconLocation = f"{ico_path},0"
        shortcut.Save()
        print(f"[+] Acceso directo creado en: {shortcut_path}")
        return True
    except Exception as e:
        # Fallback a PowerShell si win32com no está listo
        print(f"[!] Intentando fallback con PowerShell: {e}")
        ps_cmd = f"""
        $WshShell = New-Object -comObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut('{shortcut_path}')
        $Shortcut.TargetPath = '{target_exe}'
        $Shortcut.Arguments = '"{script_path}"'
        $Shortcut.WorkingDirectory = '{work_dir}'
        $Shortcut.Description = '{description}'
        $Shortcut.IconLocation = '{ico_path},0'
        $Shortcut.Save()
        """
        import subprocess
        res = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True)
        if res.returncode == 0:
            print(f"[+] Acceso directo creado con éxito vía PowerShell en: {shortcut_path}")
            return True
        else:
            print(f"[!] Error en fallback: {res.stderr}")
            return False

def main():
    script_dir = Path(__file__).resolve().parent
    # Si este script está en audit_tools, subimos a la raíz del proyecto
    if script_dir.name == "audit_tools":
        project_root = script_dir.parent
    else:
        project_root = script_dir

    pythonw_exe = project_root / ".venv" / "Scripts" / "pythonw.exe"
    main_py = project_root / "main.py"
    assets_dir = project_root / "assets"
    
    png_icon = assets_dir / "artificial-intelligence.png"
    ico_icon = assets_dir / "app_icon.ico"

    if not pythonw_exe.exists():
        print(f"[ERROR] No se encontró pythonw.exe en: {pythonw_exe}")
        sys.exit(1)

    # 1. Generar .ico si no existe
    if png_icon.exists() and not ico_icon.exists():
        generate_ico(png_icon, ico_icon)

    # 2. Rutas de destino para los accesos directos
    # a) En el Escritorio del usuario
    desktop_dir = Path(os.path.expanduser("~")) / "Desktop"
    desktop_shortcut = desktop_dir / "FHVT Studio Image Editor.lnk"
    
    # b) En la carpeta del proyecto
    project_shortcut = project_root / "FHVT Studio Image Editor.lnk"
    outer_project_shortcut = project_root.parent / "FHVT Studio Image Editor.lnk"

    print("=" * 70)
    print("🚀 CREANDO ACCESOS DIRECTOS DE FHVT STUDIO IMAGE EDITOR")
    print("=" * 70)

    # Crear en el Escritorio
    if desktop_dir.exists():
        create_windows_shortcut(
            target_exe=pythonw_exe,
            script_path=main_py,
            work_dir=project_root,
            ico_path=ico_icon if ico_icon.exists() else None,
            shortcut_path=desktop_shortcut
        )

    # Crear en la carpeta del proyecto
    create_windows_shortcut(
        target_exe=pythonw_exe,
        script_path=main_py,
        work_dir=project_root,
        ico_path=ico_icon if ico_icon.exists() else None,
        shortcut_path=project_shortcut
    )

    # Crear en la carpeta exterior
    if outer_project_shortcut.parent.exists():
        create_windows_shortcut(
            target_exe=pythonw_exe,
            script_path=main_py,
            work_dir=project_root,
            ico_path=ico_icon if ico_icon.exists() else None,
            shortcut_path=outer_project_shortcut
        )

    print("=" * 70)
    print("✅ ¡Listo! Puedes anclar el acceso directo a la Barra de Tareas o al Menú Inicio.")
    print("=" * 70)

if __name__ == "__main__":
    main()
