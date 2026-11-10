"""Enforce module-level layering, allowing local and TYPE_CHECKING adapters.

The empty exception set is a shrink-only baseline. A future exception requires
an ADR and independent review; never regenerate it from violations.

A second rule holds the modules that are Qt-free logic with QtCore only
(``QT_CORE_ONLY``): none of them may reach ``PyQt6.QtWidgets`` or
``PyQt6.QtGui`` through the eager imports of the modules it names. The layer
rule cannot see that: ``core`` may use QtGui freely, so a widget class added to
``core/i18n.py`` made the task generator and the soil service depend on widgets
without one forbidden edge (#792, review round 1).
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
#: Modules whose own eager import closure stays off the widget modules. What a
#: PARENT package's ``__init__`` imports is not part of a module's closure:
#: ``services/__init__.py`` loads the autosave service, a different debt.
QT_CORE_ONLY = (
    "core/i18n.py",
    "services/soil_service.py",
    "services/task_generator.py",
)
WIDGET_MODULES = ("PyQt6.QtWidgets", "PyQt6.QtGui")


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


def _first_party_file(root: Path, target: str) -> Path | None:
    """The file an eager import target loads: the longest module path that exists."""
    parts = target.removeprefix("open_garden_planner.").split(".")
    for length in range(len(parts), 0, -1):
        base = root.joinpath(*parts[:length])
        if base.with_suffix(".py").is_file():
            return base.with_suffix(".py")
        if (base / "__init__.py").is_file():
            return base / "__init__.py"
    return None


def check_qt_core_only(root: Path, modules: tuple[str, ...] = QT_CORE_ONLY) -> list[str]:
    """Widget imports reachable through the eager imports of a QtCore-only module."""
    errors = []
    for start in modules:
        via: dict[Path, Path | None] = {}
        pending: list[tuple[Path, Path | None]] = [(root / start, None)]
        while pending:
            path, parent = pending.pop()
            if path in via or not path.is_file():
                continue
            via[path] = parent
            relative = path.relative_to(root).as_posix()
            module = "open_garden_planner." + relative.removesuffix(".py").replace("/", ".")
            for line, target in eager_imports(ast.parse(path.read_text(encoding="utf-8")), module):
                if target.startswith(WIDGET_MODULES):
                    chain, step = [f"{relative}:{line}"], parent
                    while step is not None:
                        chain.append(step.relative_to(root).as_posix())
                        step = via[step]
                    errors.append(
                        f"{start}: QtCore-only, but reaches {target.rsplit('.', 1)[0]} at "
                        + " <- ".join(chain))
                elif target.startswith("open_garden_planner."):
                    found = _first_party_file(root, target)
                    if found is not None:
                        pending.append((found, path))
    return sorted(set(errors))


def check_repo(root: Path) -> list[str]:
    errors = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        errors.extend(check_source(path.read_text(encoding="utf-8"), relative))
    errors.extend(check_qt_core_only(root))
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "src/open_garden_planner"
    errors = check_repo(root)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"Import boundaries passed (zero exceptions; {len(QT_CORE_ONLY)} QtCore-only modules).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
