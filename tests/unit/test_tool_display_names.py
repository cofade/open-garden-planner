"""A tool's name is written twice; the two must stay one name (#792, review round 1).

A tool class whose ``display_name`` is a class attribute holds the English source
(``QT_TR_NOOP("Select")``, or a ``translate()`` call that ran at import, before any
translator was loaded). What the status bar shows comes from a second literal, in
``_translated_name``: ``QCoreApplication.translate("SelectTool", "Select")``. The
translation gate needs that call to be literal, so the pair cannot be derived; this
test holds the two together. Rename one and forget the other, and the status bar
shows a name no catalog knows, in English, in every language.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path

import open_garden_planner.core.tools as tools_package
from open_garden_planner.core.tools.base_tool import BaseTool

TOOLS_DIR = Path(tools_package.__file__).parent
#: The tool classes with a class-level English name (the reviewed count).
EXPECTED = 19


def _literal_pair(call: ast.AST) -> tuple[str | None, str] | None:
    """``(context, source)`` of ``QT_TR_NOOP("X")`` or ``...translate("Ctx", "X")``."""
    if not isinstance(call, ast.Call):
        return None
    name = call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", "")
    texts = [arg.value for arg in call.args
             if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
    if name == "QT_TR_NOOP" and len(texts) == 1 and len(call.args) == 1:
        return None, texts[0]
    if name == "translate" and len(texts) == 2 and len(call.args) == 2:
        return texts[0], texts[1]
    return None


def _named_tools() -> dict[str, tuple[tuple[str | None, str], tuple[str | None, str] | None]]:
    """Class name -> (its display_name pair, the pair its _translated_name returns)."""
    found: dict[str, tuple[tuple[str | None, str], tuple[str | None, str] | None]] = {}
    for path in sorted(TOOLS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            declared = looked_up = None
            for item in node.body:
                if (isinstance(item, ast.Assign) and len(item.targets) == 1
                        and isinstance(item.targets[0], ast.Name)
                        and item.targets[0].id == "display_name"):
                    declared = _literal_pair(item.value)
                if isinstance(item, ast.FunctionDef) and item.name == "_translated_name":
                    returns = [part.value for part in ast.walk(item)
                               if isinstance(part, ast.Return)]
                    looked_up = _literal_pair(returns[0]) if len(returns) == 1 else None
            if declared is not None:
                found[node.name] = (declared, looked_up)
    return found


def test_every_tool_looks_up_the_name_it_declares() -> None:
    tools = _named_tools()
    assert len(tools) == EXPECTED, sorted(tools)
    problems = []
    for name, (declared, looked_up) in sorted(tools.items()):
        if looked_up is None or looked_up[0] is None:
            problems.append(f"{name}: _translated_name must return a literal "
                            'QCoreApplication.translate("Context", "Name")')
            continue
        if looked_up[1] != declared[1]:
            problems.append(f"{name}: display_name is {declared[1]!r} but _translated_name "
                            f"looks up {looked_up[1]!r}")
        if declared[0] is not None and declared[0] != looked_up[0]:
            problems.append(f"{name}: display_name is translated in context {declared[0]!r}, "
                            f"_translated_name in {looked_up[0]!r}")
    assert not problems, "\n".join(problems)


def test_the_running_classes_agree_with_their_source(qapp) -> None:
    """The same pairs on the imported classes, in the English UI the suite runs in:
    what ``localized_name`` returns is the class's own ``display_name``."""
    checked = 0
    for module_info in pkgutil.iter_modules(tools_package.__path__):
        module = importlib.import_module(f"{tools_package.__name__}.{module_info.name}")
        for _name, cls in inspect.getmembers(module, inspect.isclass):
            if (cls.__module__ != module.__name__ or not issubclass(cls, BaseTool)
                    or not isinstance(vars(cls).get("display_name"), str)):
                continue
            checked += 1
            assert "_translated_name" in vars(cls), cls.__name__
            tool = cls.__new__(cls)          # no view: only the name is asked
            assert tool.localized_name() == cls.display_name, cls.__name__
    assert checked == EXPECTED
