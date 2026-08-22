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

QT_OVERRIDE_METHODS = {
    "__init__", "__del__", "__str__", "__repr__", "__call__", "__enter__", "__exit__",
    "paintEvent", "mousePressEvent", "mouseMoveEvent", "mouseReleaseEvent", "mouseDoubleClickEvent",
    "keyPressEvent", "keyReleaseEvent", "wheelEvent", "resizeEvent", "closeEvent", "showEvent",
    "hideEvent", "enterEvent", "leaveEvent", "focusInEvent", "focusOutEvent", "dragEnterEvent",
    "dragMoveEvent", "dragLeaveEvent", "dropEvent", "contextMenuEvent", "eventFilter", "event",
    "run", "exec", "boundingRect", "shape", "paint", "itemChange", "type", "data", "setData",
    "rowCount", "columnCount", "headerData", "flags", "index", "parent", "selectionChanged",
    "currentChanged", "rowsInserted", "rowsAboutToBeRemoved", "initStyleOption"
}

class CodeDefinition:
    def __init__(self, def_type, name, file_path, line_no, class_name=None):
        self.def_type = def_type  # 'function', 'class', 'method', 'constant'
        self.name = name
        self.file_path = file_path
        self.line_no = line_no
        self.class_name = class_name
        self.full_name = f"{class_name}.{name}" if class_name else name
        self.incoming_refs = 0

    def __repr__(self):
        return f"<{self.def_type} {self.full_name} in {os.path.basename(self.file_path)}:{self.line_no}>"


class CallGraphASTVisitor(ast.NodeVisitor):
    def __init__(self, file_path):
        self.file_path = file_path
        self.definitions = []
        self.references = set()
        self.string_literals = set()
        self.current_class = None

    def visit_ClassDef(self, node):
        self.definitions.append(CodeDefinition("class", node.name, self.file_path, node.lineno))
        prev_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node):
        if self.current_class:
            self.definitions.append(
                CodeDefinition("method", node.name, self.file_path, node.lineno, class_name=self.current_class)
            )
        else:
            self.definitions.append(
                CodeDefinition("function", node.name, self.file_path, node.lineno)
            )
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_Name(self, node):
        self.references.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node):
        self.references.add(node.attr)
        self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            self.string_literals.add(node.value)
            # Also add words from string literals in case of dynamic signal/slot connection or getattr
            for part in node.value.split():
                clean = part.strip("()[],:.'\"")
                if clean.isidentifier():
                    self.references.add(clean)
        self.generic_visit(node)


def analyze_reachability(project_root):
    project_root = Path(project_root).resolve()
    py_files = []

    for root, dirs, files in os.walk(project_root):
        # Exclude .venv, .git, build, __pycache__, scratch
        dirs[:] = [d for d in dirs if d not in {".venv", ".git", "build", "__pycache__", ".ruff_cache", "scratch", "audit_tools"}]
        for file in files:
            if file.endswith(".py"):
                py_files.append(Path(root) / file)

    all_definitions = []
    all_references = set()
    all_strings = set()
    file_visitors = {}

    for py_file in py_files:
        try:
            with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                tree = ast.parse(f.read(), filename=str(py_file))
            visitor = CallGraphASTVisitor(str(py_file))
            visitor.visit(tree)
            file_visitors[str(py_file)] = visitor
            all_definitions.extend(visitor.definitions)
            all_references.update(visitor.references)
            all_strings.update(visitor.string_literals)
        except Exception as e:
            print(f"[!] Error parsing {py_file}: {e}")

    # Trace references
    dead_code = []
    active_code = []

    for defn in all_definitions:
        # Ignore Qt override methods and dunder methods
        if defn.name in QT_OVERRIDE_METHODS:
            defn.incoming_refs += 1
            active_code.append(defn)
            continue

        # Ignore main entry point definitions in main.py
        if "main.py" in defn.file_path and defn.name in {"main", "app"}:
            defn.incoming_refs += 1
            active_code.append(defn)
            continue

        # Check references count across whole program
        # A symbol is considered referenced if its name appears in AST Name/Attribute nodes outside its own definition
        ref_count = 0
        for visitor in file_visitors.values():
            if defn.name in visitor.references or defn.name in visitor.string_literals:
                ref_count += 1

        # Adjust for self-definition
        if ref_count <= 1 and defn.name not in QT_OVERRIDE_METHODS:
            dead_code.append(defn)
        else:
            defn.incoming_refs = ref_count
            active_code.append(defn)

    return {
        "total_files": len(py_files),
        "total_definitions": len(all_definitions),
        "dead_code_count": len(dead_code),
        "active_code_count": len(active_code),
        "dead_code": dead_code,
        "active_code": active_code
    }


def print_reachability_report(results):
    print("=" * 80)
    print("🔍 WHOLE-PROGRAM CALL GRAPH & REACHABILITY AUDIT REPORT")
    print("=" * 80)
    print(f"Total Python Files Analyzed:  {results['total_files']}")
    print(f"Total Symbols Declared:       {results['total_definitions']}")
    print(f"Active / Reachable Symbols:   {results['active_code_count']}")
    print(f"Dead / Unreferenced Symbols:  {results['dead_code_count']}")
    print("-" * 80)

    if results["dead_code"]:
        print(f"\n⚠️  POTENTIALLY DEAD / UNREFERENCED DECLARATIONS ({len(results['dead_code'])} found):")
        # Group by file
        grouped = defaultdict(list)
        for d in results["dead_code"]:
            rel_file = os.path.relpath(d.file_path, os.getcwd())
            grouped[rel_file].append(d)

        for rel_file, defs in grouped.items():
            print(f"\n  📁 {rel_file}:")
            for d in defs:
                kind = f"[{d.def_type.upper()}]"
                print(f"    • Line {d.line_no:4d}: {kind:10s} {d.full_name}")
    else:
        print("\n✅ All declared symbols are actively reachable and referenced across the codebase!")
    print("=" * 80)


if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    res = analyze_reachability(base_dir)
    print_reachability_report(res)
