import os
import sys
import py_compile
import subprocess
import time
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from audit_tools.reachability_analyzer import analyze_reachability, print_reachability_report  # noqa: E402
from audit_tools.layer_boundary_checker import analyze_dependencies, print_layer_report  # noqa: E402
from audit_tools.asset_scanner import scan_assets_and_usage, print_asset_report  # noqa: E402
from audit_tools.check_hf_links import verify_all_hf_links, print_hf_report  # noqa: E402
from audit_tools.privacy_scanner import run_privacy_audit, print_privacy_report  # noqa: E402


def run_syntax_compilation_check(project_root):
    print("=" * 80)
    print("⚙️  STRICT PYTHON AST SYNTAX & COMPILATION CHECK")
    print("=" * 80)
    py_files = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in {".venv", ".git", "build", "__pycache__", ".ruff_cache", "scratch", "audit_tools"}]
        for file in files:
            if file.endswith(".py"):
                py_files.append(Path(root) / file)

    errors = []
    for f in py_files:
        rel = os.path.relpath(f, project_root)
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append((rel, str(e)))

    print(f"Total Python Files Compiled: {len(py_files)}")
    if errors:
        print(f"\n❌ SYNTAX / COMPILATION ERRORS DETECTED ({len(errors)}):")
        for rel, err in errors:
            print(f"  • {rel}:\n    {err}")
    else:
        print("✅ 100% of Python source files compiled with valid AST syntax without errors!")
    print("=" * 80)
    return len(errors) == 0


def run_ruff_linter(project_root):
    print("=" * 80)
    print("⚡ DETERMINISTIC STATIC ANALYSIS & RUFF LINTER")
    print("=" * 80)
    
    python_exe = sys.executable
    cmd = [python_exe, "-m", "ruff", "check", project_root]
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        print(res.stdout if res.stdout else res.stderr)
        if res.returncode == 0:
            print("✅ Ruff static analysis passed cleanly with zero warnings.")
        else:
            print("⚠️  Ruff reported static warnings/lint errors.")
    except Exception as e:
        print(f"[!] Could not run ruff: {e}")
    print("=" * 80)


def main():
    start_total = time.time()
    print("\n" + "#" * 80)
    print("🚀 FHVT GALLERY AI - COMPLETE ARCHITECTURAL AUDIT & DEBUGGING SUITE")
    print("#" * 80 + "\n")

    # 1. AST Syntax compilation check
    run_syntax_compilation_check(PROJECT_ROOT)
    print("\n")

    # 2. Dependency & Layer Boundary Checker
    layer_res = analyze_dependencies(PROJECT_ROOT)
    print_layer_report(layer_res)
    print("\n")

    # 3. Whole-Program Call Graph & Dead Code Reachability
    reach_res = analyze_reachability(PROJECT_ROOT)
    print_reachability_report(reach_res)
    print("\n")

    # 4. Unused Resource & Asset Scanner
    asset_res = scan_assets_and_usage(PROJECT_ROOT)
    print_asset_report(asset_res)
    print("\n")

    # 5. Hugging Face Link & Model Metadata Verifier
    hf_res = verify_all_hf_links(PROJECT_ROOT)
    print_hf_report(hf_res)
    print("\n")

    # 6. Ruff Linter
    run_ruff_linter(PROJECT_ROOT)
    print("\n")

    # 7. Privacy, Secrets & Leaks Scanner
    priv_res = run_privacy_audit(PROJECT_ROOT)
    print_privacy_report(priv_res)
    print("\n")

    elapsed = time.time() - start_total
    print("#" * 80)
    print(f"🏁 AUDIT COMPLETED IN {elapsed:.2f}s")
    print("#" * 80 + "\n")


if __name__ == "__main__":
    main()
