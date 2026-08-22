from __future__ import annotations
import ast
from pathlib import Path


def test_runtime_dashboard_keeps_multiuser_signature():
    tree = ast.parse(Path("openscanstation/web_runtime.py").read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_dashboard")
    assert [argument.arg for argument in function.args.args] == ["message", "error", "username", "is_admin", "allowed_scanners"]
