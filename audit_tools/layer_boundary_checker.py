import ast
import os
import sys
from pathlib import Path
from collections import defaultdict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LAYER_PRIORITIES = {
    "core": 0,
    "models": 1,
    "tools": 2,
    "editor": 3,
    "ui": 4,
    "root": 5,  # main.py, studio_logger.py
}

def get_module_layer(rel_path):
    parts = rel_path.split(os.sep)
    if len(parts) > 1 and parts[0] in LAYER_PRIORITIES:
        return parts[0]
    return "root"

def extract_imports(file_path):
    imports = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            tree = ast.parse(f.read(), filename=file_path)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((alias.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.append((module, node.lineno))
    except Exception as e:
        print(f"[!] Error parsing imports in {file_path}: {e}")
    return imports

def build_import_graph(project_root):
    project_root = Path(project_root).resolve()
    module_files = {}
    graph = defaultdict(list)
    import_details = defaultdict(list)

    # Collect project modules
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in {".venv", ".git", "build", "__pycache__", ".ruff_cache", "scratch", "audit_tools"}]
        for file in files:
            if file.endswith(".py"):
                full_path = Path(root) / file
                rel_path = os.path.relpath(full_path, project_root)
                # Compute python module name
                mod_name = rel_path.replace(os.sep, ".").rstrip(".py")
                if mod_name.endswith(".__init__"):
                    mod_name = mod_name[:-9]
                module_files[mod_name] = (str(full_path), rel_path)

    # Build dependency edges
    for mod_name, (full_path, rel_path) in module_files.items():
        imports = extract_imports(full_path)
        for imp_name, lineno in imports:
            # Check if imported module belongs to this project
            matched_mod = None
            for candidate in module_files:
                if imp_name == candidate or imp_name.startswith(candidate + "."):
                    matched_mod = candidate
                    break
            
            if matched_mod and matched_mod != mod_name:
                if matched_mod not in graph[mod_name]:
                    graph[mod_name].append(matched_mod)
                import_details[(mod_name, matched_mod)].append((imp_name, lineno, rel_path))

    return module_files, graph, import_details

def find_cycles(graph):
    cycles = []
    visited = {}
    rec_stack = []

    def dfs(node):
        visited[node] = True
        rec_stack.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in rec_stack:
                cycle_start = rec_stack.index(neighbor)
                cycle = rec_stack[cycle_start:] + [neighbor]
                # Normalize cycle representation to avoid duplicates
                norm_cycle = cycle[:-1]
                min_idx = norm_cycle.index(min(norm_cycle))
                canonical = tuple(norm_cycle[min_idx:] + norm_cycle[:min_idx])
                if canonical not in [tuple(c[:-1]) for c in cycles]:
                    cycles.append(cycle)

        rec_stack.pop()

    for node in list(graph.keys()):
        if node not in visited:
            dfs(node)

    return cycles

def check_layer_violations(module_files, graph, import_details):
    violations = []
    
    for source_mod, targets in graph.items():
        _, src_rel = module_files[source_mod]
        src_layer = get_module_layer(src_rel)

        for target_mod in targets:
            _, tgt_rel = module_files[target_mod]
            tgt_layer = get_module_layer(tgt_rel)

            # Rule: Lower layer must not import higher layer (e.g. core -> ui/editor)
            if src_layer in ("core", "models") and tgt_layer in ("ui", "editor", "ui.panels"):
                details = import_details.get((source_mod, target_mod), [])
                violations.append({
                    "type": "LAYER_INVERSION",
                    "source": source_mod,
                    "source_file": src_rel,
                    "source_layer": src_layer,
                    "target": target_mod,
                    "target_layer": tgt_layer,
                    "details": details,
                    "description": f"Core/Foundation layer '{src_layer}' directly depends on high-level UI layer '{tgt_layer}'"
                })

    return violations

def analyze_dependencies(project_root):
    module_files, graph, import_details = build_import_graph(project_root)
    cycles = find_cycles(graph)
    violations = check_layer_violations(module_files, graph, import_details)
    return {
        "modules_count": len(module_files),
        "edges_count": sum(len(v) for v in graph.values()),
        "cycles": cycles,
        "violations": violations,
        "graph": dict(graph)
    }

def print_layer_report(results):
    print("=" * 80)
    print("🏛️  DEPENDENCY & LAYER BOUNDARY CHECKER REPORT")
    print("=" * 80)
    print(f"Total Internal Modules: {results['modules_count']}")
    print(f"Dependency Connections: {results['edges_count']}")
    print(f"Circular Dependencies:  {len(results['cycles'])}")
    print(f"Layer Boundary Violations: {len(results['violations'])}")
    print("-" * 80)

    if results["cycles"]:
        print(f"\n❌ CIRCULAR DEPENDENCY CYCLES FOUND ({len(results['cycles'])}):")
        for i, cycle in enumerate(results["cycles"], 1):
            cycle_str = " -> ".join(cycle)
            print(f"  [{i}] {cycle_str}")
    else:
        print("\n✅ Zero circular dependencies detected between modules.")

    if results["violations"]:
        print(f"\n⚠️  CLEAN ARCHITECTURE LAYER VIOLATIONS ({len(results['violations'])}):")
        for i, v in enumerate(results["violations"], 1):
            print(f"  [{i}] {v['description']}")
            print(f"      Source: {v['source_file']} ({v['source_layer']})")
            for imp_name, line, rel_file in v['details']:
                print(f"      Import: Line {line}: import/from {imp_name}")
    else:
        print("✅ Clean architectural layer hierarchy strictly preserved!")
    print("=" * 80)

if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    res = analyze_dependencies(base_dir)
    print_layer_report(res)
