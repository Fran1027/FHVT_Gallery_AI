import os
import sys
import re
import time
import urllib.request
import urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def extract_hf_targets(project_root):
    project_root = Path(project_root).resolve()
    targets = {}

    # 1. First, try importing MODELS_CONFIG directly from tools.ai_tool if available
    sys.path.insert(0, str(project_root))
    try:
        from tools.ai_tool import MODELS_CONFIG
        for model_name, cfg in MODELS_CONFIG.items():
            repo = cfg.get("repo")
            filename = cfg.get("file")
            if repo:
                key = f"{repo}/{filename}" if filename else repo
                url = f"https://huggingface.co/{repo}/resolve/main/{filename}" if filename else f"https://huggingface.co/{repo}"
                targets[key] = {
                    "type": "ONNX Model File" if filename else "HF Repository",
                    "repo": repo,
                    "file": filename,
                    "url": url,
                    "source": "tools/ai_tool.py (MODELS_CONFIG)",
                    "label": model_name
                }
    except Exception as e:
        print(f"[!] Warning: Could not import MODELS_CONFIG: {e}")

    # 2. Extract repos from tools/generative_tool.py (available_models_data or string literals)
    try:
        pass
        # We can extract defaults by inspecting AST or regex
    except Exception:
        pass

    # 3. Regex scan all python files for repo IDs and URLs
    repo_pattern = re.compile(r'["\']([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)["\']')
    url_pattern = re.compile(r'["\'](https://huggingface\.co/[^"\']+)["\']')

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in {".venv", ".git", "build", "__pycache__", ".ruff_cache", "scratch", "audit_tools"}]
        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file
                rel_path = os.path.relpath(file_path, project_root).replace("\\", "/")
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    for url in url_pattern.findall(content):
                        if "{" in url or "}" in url:
                            continue
                        if url not in targets:
                            targets[url] = {
                                "type": "Direct HF URL",
                                "repo": url.replace("https://huggingface.co/", "").split("/resolve/")[0],
                                "file": None,
                                "url": url,
                                "source": rel_path,
                                "label": os.path.basename(url)
                            }

                    # Filter known valid HuggingFace namespaces
                    for repo in repo_pattern.findall(content):
                        # Filter out non-repo paths like PyQt keys or local directories
                        if "/" in repo and not repo.startswith(("models/", "ui/", "editor/", "core/", "tools/", "assets/")):
                            parts = repo.split("/")
                            if len(parts) == 2 and "." not in parts[0] and not parts[0].endswith(".py"):
                                if repo not in targets and not any(t.get("repo") == repo for t in targets.values()):
                                    # Candidate repo
                                    if any(keyword in repo.lower() for keyword in ["stable-diffusion", "triposr", "mobilesam", "rmbg", "clip", "upscaler", "dino", "briaai", "yuvraj", "tangalbert", "pulpcut", "bytedance", "runwayml", "stabilityai", "tencentarc"]):
                                        targets[repo] = {
                                            "type": "HF Repository",
                                            "repo": repo,
                                            "file": None,
                                            "url": f"https://huggingface.co/{repo}",
                                            "source": rel_path,
                                            "label": repo
                                        }
                except Exception as e:
                    print(f"[!] Error scanning {file_path}: {e}")

    return targets

def check_single_url(target_info):
    url = target_info["url"]
    headers = {
        "User-Agent": "FHVT-Studio-Auditor/1.0 (HF-Link-Verifier)"
    }
    req = urllib.request.Request(url, headers=headers, method="HEAD")
    start_t = time.time()

    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            latency = (time.time() - start_t) * 1000
            content_length = response.headers.get("Content-Length")
            size_mb = int(content_length) / (1024 * 1024) if content_length and content_length.isdigit() else None
            return {
                "success": True,
                "status_code": response.status,
                "latency_ms": latency,
                "size_mb": size_mb,
                "error": None,
                "target": target_info
            }
    except urllib.error.HTTPError as e:
        latency = (time.time() - start_t) * 1000
        # If HEAD returned 405 Method Not Allowed, fallback to GET with stream/range
        if e.code == 405:
            try:
                get_req = urllib.request.Request(url, headers={"Range": "bytes=0-10", "User-Agent": headers["User-Agent"]})
                with urllib.request.urlopen(get_req, timeout=8) as get_resp:
                    return {
                        "success": True,
                        "status_code": get_resp.status,
                        "latency_ms": latency,
                        "size_mb": None,
                        "error": None,
                        "target": target_info
                    }
            except Exception:
                pass

        return {
            "success": False,
            "status_code": e.code,
            "latency_ms": latency,
            "size_mb": None,
            "error": f"HTTP {e.code}: {e.reason}",
            "target": target_info
        }
    except Exception as e:
        latency = (time.time() - start_t) * 1000
        return {
            "success": False,
            "status_code": 0,
            "latency_ms": latency,
            "size_mb": None,
            "error": str(e),
            "target": target_info
        }

def verify_all_hf_links(project_root, max_workers=8):
    targets = extract_hf_targets(project_root)
    results = []

    print(f"[*] Extracting and testing {len(targets)} Hugging Face links concurrently (Workers={max_workers})...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(check_single_url, t): t for t in targets.values()}
        for future in as_completed(future_map):
            res = future.result()
            results.append(res)

    results.sort(key=lambda r: (r["success"], r["target"]["label"]))
    return results

def print_hf_report(results):
    total = len(results)
    valid = [r for r in results if r["success"]]
    invalid = [r for r in results if not r["success"]]

    print("=" * 80)
    print("🌐 HUGGING FACE LINK & METADATA VERIFIER REPORT")
    print("=" * 80)
    print(f"Total Model Links & Repos: {total}")
    print(f"✅ Verified & Live:        {len(valid)}")
    print(f"❌ Broken / Inaccessible:  {len(invalid)}")
    print("-" * 80)

    if invalid:
        print(f"\n❌ BROKEN / UNREACHABLE MODEL REPOSITORIES OR FILES ({len(invalid)}):")
        for r in invalid:
            t = r["target"]
            print(f"  • [{r['status_code'] or 'ERR'}] {t['label']} ({t['type']})")
            print(f"      URL:    {t['url']}")
            print(f"      Source: {t['source']}")
            print(f"      Error:  {r['error']}")
    else:
        print("\n✅ All referenced Hugging Face model repositories and weight URLs are active and downloadable!")

    print("\n📊 LIVE MODEL CATALOG SUMMARY:")
    for r in valid:
        t = r["target"]
        size_str = f"{r['size_mb']:.1f} MB" if r['size_mb'] else "N/A"
        print(f"  • [HTTP {r['status_code']}] {t['label']:<24} | {t['type']:<16} | Latency: {r['latency_ms']:4.0f}ms | Size: {size_str}")

    print("=" * 80)

if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    results = verify_all_hf_links(base_dir)
    print_hf_report(results)
