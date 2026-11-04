"""Enforce module-level layering, allowing local and TYPE_CHECKING adapters.

The empty exception set is a shrink-only baseline. A future exception requires
an ADR and independent review; never regenerate it from violations.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

LAYERS = {
    "models": {"models"},
    "config": {"config", "models"},
    "core": {"core", "models", "config"},
    "services": {"services", "core", "models", "config"},
    "agent_api": {"agent_api", "services", "core", "models", "config"},
    "ui": {"ui", "services", "core", "models", "config"},
}
# Compatibility paths are part of the same leaf, not an app dependency.
COMPATIBILITY = {"app.settings": "config.settings", "app.paths": "config.paths"}
EXCEPTIONS: frozenset[tuple[str, str]] = frozenset()


def _type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def eager_imports(tree: ast.AST, module: str) -> Iterator[tuple[int, str]]:
    """Imports executed at module/class scope, including try/if/with blocks."""

    def visit(node: ast.AST) -> Iterator[tuple[int, str]]:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            return
        if isinstance(node, ast.If) and _type_checking(node.test):
            for child in node.orelse:
                yield from visit(child)
            return
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = module.split(".")[: -node.level]
                target = ".".join([*base, *([node.module] if node.module else [])])
            else:
                target = node.module or ""
            # Include imported names, so `from open_garden_planner import ui`
            # and `from . import ui` cannot escape the rule.
            for alias in node.names:
                yield node.lineno, target + "." + alias.name
        for child in ast.iter_child_nodes(node):
            yield from visit(child)

    yield from visit(tree)


def check_source(source: str, relative: str) -> list[str]:
    layer = relative.split("/")[0]
    if layer not in LAYERS:
        return []
    module = "open_garden_planner." + relative.removesuffix(".py").replace("/", ".")
    errors = []
    for line, target in eager_imports(ast.parse(source), module):
        if not target.startswith("open_garden_planner."):
            continue
        target = target.removeprefix("open_garden_planner.")
        for old, new in COMPATIBILITY.items():
            if target == old or target.startswith(old + "."):
                target = new + target[len(old) :]
                break
        destination = target.split(".")[0]
        if (
            destination in {*LAYERS, "app"}
            and destination not in LAYERS[layer]
            and (relative, target) not in EXCEPTIONS
        ):
            errors.append(f"{relative}:{line}: {layer} -> {target}")
    return errors


def check_repo(root: Path) -> list[str]:
    errors = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        errors.extend(check_source(path.read_text(encoding="utf-8"), relative))
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "src/open_garden_planner"
    errors = check_repo(root)
    if errors:
        print("\n".join(errors))
        return 1
    print("Import boundaries passed (zero exceptions).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
