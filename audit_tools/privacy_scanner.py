import os
import sys
import re
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TEXT_EXTENSIONS = {".py", ".md", ".txt", ".bat", ".spec", ".json", ".yaml", ".yml", ".ini", ".toml", ".cfg", ".sh", ".gitignore"}
EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", ".ruff_cache", "build", "dist", "models", "logs"}

PATTERNS = {
    "HuggingFace Token": re.compile(r'hf_[a-zA-Z0-9]{30,}', re.IGNORECASE),
    "OpenAI / Anthropic API Key": re.compile(r'sk-[a-zA-Z0-9_-]{20,}', re.IGNORECASE),
    "GitHub Token": re.compile(r'(ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{40,})', re.IGNORECASE),
    "AWS Access Key": re.compile(r'AKIA[0-9A-Z]{16}', re.IGNORECASE),
    "Google API Key": re.compile(r'AIza[0-9A-Za-z-_]{35}', re.IGNORECASE),
    "Generic Private Key": re.compile(r'-----BEGIN (RSA|EC|OPENSSH|PGP|PRIVATE) KEY-----'),
    "Personal Email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
    "Hardcoded User Path": re.compile(r'([a-zA-Z]:[/\\]Users[/\\][a-zA-Z0-9_-]+|/home/[a-zA-Z0-9_-]+|/Users/[a-zA-Z0-9_-]+)', re.IGNORECASE),
    "Private IPv4 Address": re.compile(r'\b(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b'),
}

def scan_file_content(file_path, project_root):
    findings = []
    rel_path = os.path.relpath(file_path, project_root).replace("\\", "/")
    
    # Do not report patterns inside the privacy scanner itself
    if "privacy_scanner.py" in rel_path:
        return findings

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for line_idx, line in enumerate(lines, 1):
            line_str = line.strip()
            for pattern_name, regex in PATTERNS.items():
                matches = regex.findall(line_str)
                if matches:
                    for match in matches:
                        match_val = match if isinstance(match, str) else str(match[0] if match else "")
                        # Ignore generic placeholders
                        if pattern_name == "Personal Email" and any(p in match_val.lower() for p in ["example.com", "domain.com", "placeholder"]):
                            continue
                        if pattern_name == "Hardcoded User Path" and any(p in match_val.lower() for p in ["<user>", "{user}", "username"]):
                            continue
                        findings.append({
                            "file": rel_path,
                            "line": line_idx,
                            "type": pattern_name,
                            "match": match_val,
                            "snippet": line_str[:120]
                        })
    except Exception as e:
        print(f"[!] Error reading {rel_path}: {e}")
    return findings

def scan_assets_metadata(project_root):
    exif_findings = []
    assets_dir = Path(project_root) / "assets"
    if not assets_dir.exists():
        return exif_findings

    for root, _, files in os.walk(assets_dir):
        for file in files:
            file_path = Path(root) / file
            rel_path = os.path.relpath(file_path, project_root).replace("\\", "/")
            if file_path.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp", ".tiff"]:
                try:
                    with Image.open(file_path) as img:
                        info = img._getexif() if hasattr(img, "_getexif") and img._getexif() else {}
                        text_meta = img.info if hasattr(img, "info") and img.info else {}
                        
                        sensitive_keys = ["GPSInfo", "Artist", "Author", "CameraOwnerName", "Software"]
                        for k, v in info.items():
                            tag = TAGS.get(k, k)
                            if tag in sensitive_keys:
                                exif_findings.append({
                                    "file": rel_path,
                                    "tag": str(tag),
                                    "value": str(v)
                                })
                        for k, v in text_meta.items():
                            if any(w in str(k).lower() for w in ["author", "user", "comment", "path", "source"]):
                                exif_findings.append({
                                    "file": rel_path,
                                    "tag": f"PNG Text: {k}",
                                    "value": str(v)[:80]
                                })
                except Exception:
                    pass
    return exif_findings

def run_privacy_audit(project_root):
    project_root = Path(project_root).resolve()
    all_findings = []

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix.lower() in TEXT_EXTENSIONS or file in {"Get-Process", ".gitignore"}:
                findings = scan_file_content(file_path, project_root)
                all_findings.extend(findings)

    exif_findings = scan_assets_metadata(project_root)

    return {
        "findings": all_findings,
        "exif_findings": exif_findings
    }

def print_privacy_report(results):
    print("=" * 80)
    print("🔒 FHVT STUDIO - AUDITORÍA DE PRIVACIDAD, SECRETOS Y FUGA DE INFORMACIÓN")
    print("=" * 80)
    
    findings = results["findings"]
    exif = results["exif_findings"]

    print("\n1. ANÁLISIS DE METADATOS EXIF / PNG INFO EN ASSETS:")
    if exif:
        print(f"   ⚠️  Se detectaron {len(exif)} metadatos en imágenes:")
        for e in exif:
            print(f"     • [{e['file']}] {e['tag']}: {e['value']}")
    else:
        print("   ✅ CERO metadatos personales (GPS, Autor, Software, Rutas) en los assets.")

    print("\n2. BÚSQUEDA DE TOKENS, API KEYS, RUTAS PERSONALES Y SECRETOS:")
    if findings:
        print(f"   ⚠️  SE DETECTARON {len(findings)} POSIBLES COINCIDENCIAS:")
        for f in findings:
            print(f"     • [{f['type']}] en {f['file']}:{f['line']}")
            print(f"       Coincidencia: {f['match']}")
            print(f"       Fragmento:    {f['snippet']}")
    else:
        print("   ✅ CERO tokens, claves API, contraseñas ni rutas personales encontradas.")

    print("\n" + "=" * 80)
    if not findings and not exif:
        print("🎉 ESTADO: CÓDIGO 100% LIMPIO Y SEGURO PARA SUBIR A GITHUB PÚBLICO O PRIVADO")
    else:
        print("⚠️  ATENCIÓN: Revisa los puntos señalados antes de hacer git push.")
    print("=" * 80)

if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    res = run_privacy_audit(base_dir)
    print_privacy_report(res)
