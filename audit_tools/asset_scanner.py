import os
import sys
import re
from pathlib import Path
from collections import defaultdict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".ico", ".webp", ".bmp"}

def scan_assets_and_usage(project_root):
    project_root = Path(project_root).resolve()
    assets_dir = project_root / "assets"

    physical_assets = {}
    if assets_dir.exists() and assets_dir.is_dir():
        for root, _, files in os.walk(assets_dir):
            for file in files:
                file_path = Path(root) / file
                rel_path = os.path.relpath(file_path, project_root).replace("\\", "/")
                size_bytes = file_path.stat().st_size
                physical_assets[file] = {
                    "filename": file,
                    "rel_path": rel_path,
                    "full_path": str(file_path),
                    "size_bytes": size_bytes,
                    "references": []
                }

    # Scan python files
    code_files = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in {".venv", ".git", "build", "__pycache__", ".ruff_cache", "scratch", "audit_tools"}]
        for file in files:
            if file.endswith(".py"):
                code_files.append(Path(root) / file)

    code_asset_mentions = defaultdict(list)
    missing_assets = []

    # Regex for finding string literals ending in image extensions or containing assets/
    asset_pattern = re.compile(r'["\']([^"\']+\.(?:png|jpg|jpeg|svg|gif|ico|webp|bmp))["\']', re.IGNORECASE)
    general_asset_pattern = re.compile(r'["\'](assets/[^"\']+)["\']', re.IGNORECASE)

    for py_file in code_files:
        try:
            with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                
            rel_py = os.path.relpath(py_file, project_root)
            for line_idx, line in enumerate(lines, 1):
                # Search exact image filenames
                for match in asset_pattern.findall(line):
                    base_name = os.path.basename(match)
                    code_asset_mentions[base_name].append((rel_py, line_idx, match.strip()))
                    if base_name in physical_assets:
                        physical_assets[base_name]["references"].append((rel_py, line_idx))
                    else:
                        missing_assets.append((base_name, rel_py, line_idx, match))

                # Search assets/ path mentions
                for match in general_asset_pattern.findall(line):
                    base_name = os.path.basename(match)
                    if base_name in physical_assets:
                        if (rel_py, line_idx) not in physical_assets[base_name]["references"]:
                            physical_assets[base_name]["references"].append((rel_py, line_idx))
                    elif not any(m[0] == base_name and m[1] == rel_py for m in missing_assets):
                        missing_assets.append((base_name, rel_py, line_idx, match))

        except Exception as e:
            print(f"[!] Error reading {py_file}: {e}")

    unused_assets = [a for a in physical_assets.values() if len(a["references"]) == 0]
    used_assets = [a for a in physical_assets.values() if len(a["references"]) > 0]

    return {
        "total_physical_assets": len(physical_assets),
        "used_assets": used_assets,
        "unused_assets": unused_assets,
        "missing_assets": missing_assets,
        "total_code_files": len(code_files)
    }

def print_asset_report(results):
    print("=" * 80)
    print("🎨 UNUSED RESOURCE & ASSET SCANNER REPORT")
    print("=" * 80)
    print(f"Total Python Files Scanned: {results['total_code_files']}")
    print(f"Physical Assets in assets/: {results['total_physical_assets']}")
    print(f"Active / Referenced Assets: {len(results['used_assets'])}")
    print(f"Unused Assets (Disk bloat): {len(results['unused_assets'])}")
    print(f"Broken / Missing Assets:    {len(results['missing_assets'])}")
    print("-" * 80)

    if results["unused_assets"]:
        print(f"\n⚠️  UNUSED ASSETS ON DISK ({len(results['unused_assets'])}):")
        for asset in results["unused_assets"]:
            kb = asset["size_bytes"] / 1024
            print(f"  • {asset['rel_path']} ({kb:.1f} KB) - Never referenced in Python code")
    else:
        print("\n✅ All physical assets are actively referenced in code.")

    if results["missing_assets"]:
        print(f"\n❌ BROKEN ASSET REFERENCES IN CODE ({len(results['missing_assets'])}):")
        for name, py_file, line, raw in results["missing_assets"]:
            print(f"  • {py_file}:{line} references '{raw}' -> File not found on disk!")
    else:
        print("✅ No broken local asset references detected in code.")
    print("=" * 80)

if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    res = scan_assets_and_usage(base_dir)
    print_asset_report(res)
