"""Extract live Qt keys, with audited finite sources for dynamic lookups.

Standard literals are extracted by the locked PyQt6 tool. The AST audit also
resolves local aliases/wrappers and requires a source binding for every dynamic
translation. Bindings select production AST nodes, never catalog/mapping data.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.i18n_catalog import CatalogError, Key, active_messages, read_catalog


class Sources:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.base = root / "src/open_garden_planner"
        self.trees = {
            p.relative_to(self.base).as_posix(): ast.parse(
                p.read_text(encoding="utf-8"), filename=str(p)
            )
            for p in sorted(self.base.rglob("*.py"))
        }
        self.keys: dict[Key, set[tuple[str, str]]] = {}
        self.errors: list[str] = []
        path = root / "scripts/i18n_bindings.json"
        self.bindings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.pools: dict[str, list[tuple[str, int]]] = {}
        self.markers: dict[tuple[str, int], str] = {}
        self.used: set[int] = set()
        self.used_contexts: set[int] = set()
        self.wrapper_exports: dict[str, set[str]] = {}

    def add(self, context: str, text: str, file: str, line: int, comment: str = "") -> None:
        if text:
            self.keys.setdefault(Key(context, text, comment), set()).add((file, str(line)))

    def scope(self, file: str, scope: str) -> ast.AST:
        node: ast.AST = self.trees[file]
        for name in scope.split(".") if scope else ():
            children = [
                n
                for n in getattr(node, "body", [])
                if isinstance(n, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
                and n.name == name
            ]
            if len(children) != 1:
                raise CatalogError(f"{file}: missing/ambiguous source scope {scope}")
            node = children[0]
        return node

    def symbol(self, file: str, scope: str, name: str) -> ast.AST:
        if not name:
            return self.scope(file, scope)
        values = []
        for n in ast.walk(self.scope(file, scope)):
            targets = (
                n.targets
                if isinstance(n, ast.Assign)
                else [n.target]
                if isinstance(n, ast.AnnAssign)
                else []
            )
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                values.append(n.value)
        if len(values) != 1 or values[0] is None:
            raise CatalogError(f"{file}:{scope}: missing/ambiguous source symbol {name}")
        return values[0]

    def strings(
        self, node: ast.AST, file: str, seen: frozenset[str] = frozenset()
    ) -> list[tuple[str, int]]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [(node.value, node.lineno)]
        if isinstance(node, ast.Name) and node.id not in seen:
            return self.strings(self.symbol(file, "", node.id), file, seen | {node.id})
        if isinstance(node, ast.Dict):
            return [v for value in node.values for v in self.strings(value, file, seen)]
        if isinstance(node, ast.List | ast.Tuple | ast.Set):
            return [v for value in node.elts for v in self.strings(value, file, seen)]
        if isinstance(node, ast.Call) and ast.unparse(node.func) in {
            "QT_TR_NOOP",
            "QT_TRANSLATE_NOOP",
        }:
            return self.strings(node.args[-1], file, seen)
        raise CatalogError(
            f"{file}:{getattr(node, 'lineno', '?')}: source is not a finite string table: {ast.unparse(node)}"
        )

    def load_pools(self) -> None:
        for name, spec in self.bindings.get("sources", {}).items():
            file, scope = spec["file"], spec.get("scope", "")
            if spec.get("selector", "").startswith("json:"):
                _, table, field = spec["selector"].split(":")
                data = json.loads((self.base / file).read_text(encoding="utf-8"))
                values = [(row[field], 1) for row in data[table]]
                if not values or not all(isinstance(text, str) and text for text, _ in values):
                    raise CatalogError(f"{name}: expected nonempty JSON display names")
                self.pools[name] = values
                for text, line in values:
                    self.add(spec["context"], text, file, line)
                continue
            if file not in self.trees:
                raise CatalogError(f"{name}: source file {file} does not exist")
            node = self.symbol(file, scope, spec.get("symbol", ""))
            selector = spec.get("selector", "values")
            values = []
            if selector == "markers":
                # A table's plain members must be included as well as markers.
                values = self.strings(node, file)
            elif selector.startswith("fields:"):
                constructor = selector.split(":", 1)[1]
                declaration = self.scope(file, constructor)
                fields = [n for n in declaration.body if isinstance(n, ast.AnnAssign)]
                names = [n.target.id for n in fields if isinstance(n.target, ast.Name)]
                selected = spec["fields"]
                if not set(selected) <= set(names):
                    raise CatalogError(f"{name}: unknown display-bearing constructor fields")
                for field in fields:
                    if field.target.id in selected and field.value is not None:
                        values.extend(self.strings(field.value, file))
                for call in ast.walk(node):
                    if isinstance(call, ast.Call) and ast.unparse(call.func) == constructor:
                        if any(isinstance(a, ast.Starred) for a in call.args) or any(
                            k.arg is None for k in call.keywords
                        ):
                            raise CatalogError(f"{file}:{call.lineno}: unpacked display fields")
                        arguments = dict(zip(names, call.args, strict=False))
                        arguments.update({k.arg: k.value for k in call.keywords})
                        for field in selected:
                            if field in arguments:
                                values.extend(self.strings(arguments[field], file))
            elif selector == "first":
                if not isinstance(node, ast.List | ast.Tuple):
                    raise CatalogError(f"{name}: expected a sequence of rows")
                for row in node.elts:
                    if not isinstance(row, ast.Tuple | ast.List) or not row.elts:
                        raise CatalogError(f"{name}: expected a nonempty row")
                    values.extend(self.strings(row.elts[0], file))
            elif selector.startswith("call:"):
                _, function, argument = selector.split(":")
                for call in ast.walk(node):
                    if isinstance(call, ast.Call) and ast.unparse(call.func) == function:
                        value = call.args[int(argument)]
                        if isinstance(value, ast.Constant) and isinstance(value.value, str):
                            values.extend(self.strings(value, file))
                        elif (
                            selector != "call:ParseError:0"
                            or ast.unparse(value) != "template.format(token=token)"
                        ):
                            raise CatalogError(
                                f"{file}:{call.lineno}: nonliteral {function} source"
                            )
            elif selector == "guild_fields":
                for loop in ast.walk(node):
                    if isinstance(loop, ast.For) and isinstance(loop.target, ast.Name):
                        calls = [
                            c
                            for c in ast.walk(loop)
                            if isinstance(c, ast.Call)
                            and ast.unparse(c.func) == "GuildValidationError"
                            and any(
                                k.arg == "field"
                                and isinstance(k.value, ast.Name)
                                and k.value.id == loop.target.id
                                for k in c.keywords
                            )
                        ]
                        if calls:
                            values.extend(self.strings(loop.iter, file))
            elif selector.startswith("argument:"):
                _, function, index = selector.split(":")
                for call in ast.walk(node):
                    if isinstance(call, ast.Call) and ast.unparse(call.func) == function:
                        values.extend(self.strings(call.args[int(index)], file))
            elif selector == "property_calls":
                for source_file, tree in self.trees.items():
                    for call in ast.walk(tree):
                        if (
                            isinstance(call, ast.Call)
                            and ast.unparse(call.func) == "ChangePropertyCommand"
                        ):
                            value = next(
                                (k.value for k in call.keywords if k.arg == "property_name"),
                                call.args[1] if len(call.args) > 1 else None,
                            )
                            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                                self.add(spec["context"], value.value, source_file, call.lineno)
                                values.append((value.value, call.lineno))
                            elif (source_file, ast.unparse(value)) not in {
                                ("ui/plant_traits.py", "field"),
                                ("ui/plant_lifetime.py", "field"),
                                ("ui/panels/properties_panel.py", "label"),
                                ("ui/panels/properties_panel.py", "f'param:{name}'"),
                            }:
                                raise CatalogError(
                                    f"{source_file}:{call.lineno}: unresolved command property {ast.unparse(value)}"
                                )
            elif selector == "values":
                values = self.strings(node, file)
            else:
                raise CatalogError(f"{name}: unsupported source selector {selector!r}")
            if not values:
                raise CatalogError(f"{name}: source declaration selected no strings")
            self.pools[name] = values
            if selector == "property_calls":
                continue  # locations were recorded from the actual caller files
            for text, line in values:
                self.add(spec["context"], text, file, line)
                self.markers.setdefault((file, line), spec["context"])

    def dynamic(
        self, file: str, scope: str, node: ast.Call, context: str, source: ast.AST,
        comment: str = "",
    ) -> None:
        expression = ast.unparse(source)
        for index, binding in enumerate(self.bindings.get("lookups", [])):
            if (binding["file"], binding["scope"], binding["expression"], binding["context"]) == (
                file,
                scope,
                expression,
                context,
            ):
                for pool in binding["sources"]:
                    if pool not in self.pools:
                        raise CatalogError(f"{file}:{node.lineno}: missing source binding {pool}")
                    if self.bindings["sources"][pool]["context"] != context:
                        raise CatalogError(
                            f"{file}:{node.lineno}: source binding {pool} has the wrong Qt context"
                        )
                    if comment:
                        for text, _line in self.pools[pool]:
                            self.add(context, text, file, node.lineno, comment)
                self.used.add(index)
                return
        self.errors.append(
            f"{file}:{node.lineno} [{context}] unresolved dynamic source in {scope}: {expression}"
        )

    def audit(self, file: str) -> None:
        tree = self.trees[file]
        # Resolve actual Qt bindings rather than treating every .translate as
        # localization (QPainter and transforms have that method too).
        qt_names = {
            n.asname or n.name
            for i in ast.walk(tree)
            if isinstance(i, ast.ImportFrom)
            and i.module in {"PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets"}
            for n in i.names
            if n.name in {"QCoreApplication", "QGuiApplication", "QApplication"}
        }
        for imported in ast.walk(tree):
            if isinstance(imported, ast.Import):
                for alias in imported.names:
                    if alias.name == "PyQt6.QtCore":
                        qt_names.add(f"{alias.asname or alias.name}.QCoreApplication")
            elif isinstance(imported, ast.ImportFrom) and imported.module == "PyQt6":
                qt_names.update(
                    f"{alias.asname or alias.name}.QCoreApplication"
                    for alias in imported.names
                    if alias.name == "QtCore"
                )
        translators = {f"{name}.translate" for name in qt_names}
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module == "PyQt6.QtCore":
                for alias in n.names:
                    if alias.name in {"QT_TR_NOOP", "QT_TRANSLATE_NOOP"} and alias.asname:
                        self.errors.append(
                            f"{file}:{n.lineno}: use the full Qt marker name so its declaration can be audited"
                        )
            if (
                isinstance(n, ast.Assign | ast.AnnAssign)
                and isinstance(n.value, ast.Attribute)
                and n.value.attr == "tr"
            ):
                self.errors.append(
                    f"{file}:{n.lineno}: tr aliases need an explicit Qt context; use QCoreApplication.translate"
                )
        changed = True
        while changed:
            previous = set(translators)
            for n in ast.walk(tree):
                if (
                    isinstance(n, ast.Assign | ast.AnnAssign)
                    and n.value is not None
                    and ast.unparse(n.value) in translators
                ):
                    targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                    translators.update(ast.unparse(t) for t in targets)
            changed = previous != translators
        wrappers: dict[str, tuple[str, ast.Call, str]] = {}
        for function in tree.body:
            if (
                isinstance(function, ast.FunctionDef)
                and len(function.args.args) == 1
                and not function.args.posonlyargs
                and not function.args.kwonlyargs
                and function.args.vararg is None
                and function.args.kwarg is None
                and not function.args.defaults
            ):
                returns = [n for n in function.body if isinstance(n, ast.Return)]
                if (
                    len(returns) == 1
                    and isinstance(call := returns[0].value, ast.Call)
                    and ast.unparse(call.func) in translators
                    and len(call.args) == 2
                    and isinstance(call.args[0], ast.Constant)
                    and isinstance(call.args[1], ast.Name)
                    and call.args[1].id == function.args.args[0].arg
                ):
                    wrappers[function.name] = (
                        call.args[0].value,
                        call,
                        function.args.args[0].arg,
                    )

        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        self.wrapper_exports[file] = (
            set(wrappers)
            | {name for name in translators if "." not in name}
            | {name.split(".")[0] for name in qt_names}
        )
        for reference in ast.walk(tree):
            if isinstance(reference, ast.Name) and reference.id in wrappers:
                parent = parents.get(reference)
                if not isinstance(parent, ast.Call) or parent.func is not reference:
                    self.errors.append(
                        f"{file}:{reference.lineno}: translation wrappers must be called directly"
                    )
            if (
                isinstance(reference, ast.Name | ast.Attribute)
                and not isinstance(getattr(reference, "ctx", None), ast.Store)
                and ast.unparse(reference) in translators
            ):
                parent = parents.get(reference)
                direct_call = isinstance(parent, ast.Call) and parent.func is reference
                alias_binding = (
                    isinstance(parent, ast.Assign | ast.AnnAssign)
                    and (parent.value is reference or isinstance(getattr(reference, "ctx", None), ast.Store))
                )
                if not direct_call and not alias_binding:
                    self.errors.append(
                        f"{file}:{reference.lineno}: Qt translation methods must be called directly or bound as aliases"
                    )

        owner = self

        class Audit(ast.NodeVisitor):
            def __init__(self) -> None:
                self.scopes: list[str] = []
                self.classes: list[str] = []

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                self.scopes.append(node.name)
                self.classes.append(node.name)
                self.generic_visit(node)
                self.classes.pop()
                self.scopes.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self.scopes.append(node.name)
                self.generic_visit(node)
                self.scopes.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, node: ast.Call) -> None:
                name = ast.unparse(node.func)
                context = None
                source = None
                comment = ""
                scope = ".".join(self.scopes)
                if name in translators and len(node.args) >= 2:
                    if isinstance(node.args[0], ast.Constant) and isinstance(
                        node.args[0].value, str
                    ):
                        context, source = node.args[0].value, node.args[1]
                        if any(node is wrapper[1] for wrapper in wrappers.values()):
                            source = None  # callsites below are independently audited
                        if len(node.args) > 2 and isinstance(node.args[2], ast.Constant):
                            comment = node.args[2].value or ""
                    else:
                        owner.errors.append(
                            f"{file}:{node.lineno}: dynamic Qt context is unsupported"
                        )
                elif name in wrappers:
                    context, _body, parameter = wrappers[name]
                    arguments = node.args + [k.value for k in node.keywords if k.arg == parameter]
                    if len(arguments) == 1 and len(node.args) <= 1 and all(
                        k.arg == parameter for k in node.keywords
                    ) and not isinstance(arguments[0], ast.Starred):
                        source = arguments[0]
                    else:
                        owner.errors.append(
                            f"{file}:{node.lineno}: unsupported translation wrapper arguments"
                        )
                elif isinstance(node.func, ast.Attribute) and node.func.attr == "tr" and node.args:
                    if self.classes and ast.unparse(node.func.value) in {
                        "self", ".".join(self.classes)
                    }:
                        context, source = ".".join(self.classes), node.args[0]
                    else:
                        # Non-self receiver has no enclosing QObject context.
                        contexts = [
                            b["context"]
                            for b in owner.bindings.get("contexts", [])
                            if (b["file"], b["scope"]) == (file, scope)
                        ]
                        matching = [
                            b
                            for b in owner.bindings.get("lookups", [])
                            if b["file"] == file
                            and b["scope"] == scope
                            and b["expression"] == ast.unparse(node.args[0])
                        ]
                        if len(contexts) == 1:
                            context, source = contexts[0], node.args[0]
                            owner.used_contexts.update(
                                i
                                for i, b in enumerate(owner.bindings.get("contexts", []))
                                if (b["file"], b["scope"]) == (file, scope)
                            )
                        elif len(matching) == 1:
                            context, source = matching[0]["context"], node.args[0]
                        else:
                            owner.errors.append(
                                f"{file}:{node.lineno}: tr() has no explicit QObject context"
                            )
                elif name == "QT_TR_NOOP" and node.args:
                    context = owner.markers.get((file, node.lineno)) or (
                        ".".join(self.classes) if self.classes else None
                    )
                    source = node.args[0]
                    if context is None:
                        owner.errors.append(
                            f"{file}:{node.lineno}: QT_TR_NOOP has no declared context"
                        )
                elif name == "QT_TRANSLATE_NOOP" and len(node.args) == 2:
                    context, source = ast.literal_eval(node.args[0]), node.args[1]
                if context and source is not None:
                    offset = 2 if name in translators else 1
                    if name in translators or (
                        isinstance(node.func, ast.Attribute) and node.func.attr == "tr"
                    ):
                        comments = [node.args[offset]] if len(node.args) > offset else []
                        comments += [k.value for k in node.keywords if k.arg == "disambiguation"]
                        if comments:
                            if (
                                len(comments) != 1
                                or not isinstance(comments[0], ast.Constant)
                                or not isinstance(comments[0].value, str | type(None))
                            ):
                                owner.errors.append(
                                    f"{file}:{node.lineno}: disambiguation must be literal"
                                )
                            else:
                                comment = comments[0].value or ""
                        counts = node.args[offset + 1 :] + [
                            k.value for k in node.keywords if k.arg == "n"
                        ]
                        if any(
                            not isinstance(n, ast.UnaryOp) or ast.unparse(n) != "-1" for n in counts
                        ):
                            owner.errors.append(
                                f"{file}:{node.lineno}: add tested plural compiler support before numerus"
                            )
                    if isinstance(source, ast.Constant) and isinstance(source.value, str):
                        owner.add(context, source.value, file, node.lineno, comment)
                    elif isinstance(source, ast.Name) and source.id.startswith("_"):
                        try:
                            values = owner.strings(source, file)
                        except CatalogError:
                            owner.dynamic(file, scope, node, context, source, comment)
                        else:
                            for text, line in values:
                                owner.add(context, text, file, line, comment)
                    else:
                        owner.dynamic(file, scope, node, context, source, comment)
                self.generic_visit(node)

        Audit().visit(tree)

    def check_wrapper_imports(self) -> None:
        """Local helper calls are supported; cross-module helper forwarding is explicit."""
        def exports_for(module: str) -> set[str]:
            candidates = [module + ".py", module + "/__init__.py"]
            selected = [p for p in candidates if p in self.trees]
            if len(selected) > 1:
                raise CatalogError(f"ambiguous local translation module: {module}")
            return self.wrapper_exports.get(selected[0], set()) if selected else set()

        for file, tree in self.trees.items():
            module_aliases: dict[str, set[str]] = {}
            parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    package = list(Path(file).parent.parts)
                    if node.level:
                        module = package[:len(package) - node.level + 1]
                        module += (node.module or "").split(".") if node.module else []
                    else:
                        module = (node.module or "").split(".")
                        if module and module[0] == "open_garden_planner":
                            module = module[1:]
                    exports = exports_for("/".join(module))
                    if any(a.name in exports or a.name == "*" and exports for a in node.names):
                        self.errors.append(
                            f"{file}:{node.lineno}: imported translation wrapper requires explicit Qt calls"
                        )
                    for alias in node.names:
                        child = exports_for("/".join(module + [alias.name]))
                        if child:
                            module_aliases[alias.asname or alias.name] = child
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name.removeprefix("open_garden_planner.").replace(".", "/")
                        exports = exports_for(module)
                        prefix = alias.asname or alias.name
                        module_aliases[prefix] = exports
            for reference in ast.walk(tree):
                if isinstance(reference, ast.Attribute) and ast.unparse(reference) in {
                    f"{prefix}.{name}" for prefix, names in module_aliases.items() for name in names
                }:
                    self.errors.append(
                        f"{file}:{reference.lineno}: imported translation wrapper requires explicit Qt calls"
                    )
                elif isinstance(reference, ast.Name) and module_aliases.get(reference.id):
                    parent = parents.get(reference)
                    if not isinstance(parent, ast.Attribute) or parent.value is not reference:
                        self.errors.append(
                            f"{file}:{reference.lineno}: imported translation helper modules must not escape"
                        )


def inventory(root: Path) -> dict[Key, set[tuple[str, str]]]:
    sources = Sources(root)
    sources.load_pools()
    for file in sources.trees:
        sources.audit(file)
    sources.check_wrapper_imports()
    for index, binding in enumerate(sources.bindings.get("lookups", [])):
        if index not in sources.used:
            sources.errors.append(
                f"stale source binding: {binding['file']}:{binding['scope']} {binding['expression']}"
            )
    for index, binding in enumerate(sources.bindings.get("contexts", [])):
        if index not in sources.used_contexts:
            sources.errors.append(f"stale context binding: {binding['file']}:{binding['scope']}")
    if sources.errors:
        raise CatalogError("\n".join(sources.errors))
    with tempfile.TemporaryDirectory(prefix="ogp-i18n-") as temporary:
        target = Path(temporary) / "source.ts"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "PyQt6.lupdate.pylupdate",
                str(sources.base),
                "--ts",
                str(target),
                "--no-obsolete",
                "--no-summary",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )
        if result.returncode:
            raise CatalogError(f"Qt extraction failed: {result.stdout}\n{result.stderr}")
        for message in active_messages(read_catalog(target)[1]):
            if message.numerus:
                raise CatalogError(
                    f"{message.key}: add tested plural compiler support before introducing numerus"
                )
            locations = set()
            for file, line in message.locations:
                actual = (target.parent / file).resolve()
                try:
                    relative = actual.relative_to(sources.base.resolve()).as_posix()
                except ValueError as exc:
                    raise CatalogError(
                        f"Qt extraction location is outside the source tree: {file}"
                    ) from exc
                locations.add((relative, line))
            sources.keys.setdefault(message.key, set()).update(locations)
    return sources.keys


def supported_languages(root: Path) -> dict[str, str]:
    path = root / "src/open_garden_planner/core/i18n.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "SUPPORTED_LANGUAGES"
        ):
            value = ast.literal_eval(node.value)
            if (
                isinstance(value, dict)
                and value
                and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())
            ):
                return value
    raise CatalogError(f"{path}: expected a literal SUPPORTED_LANGUAGES registry")
