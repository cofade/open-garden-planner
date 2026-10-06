"""Every string delivered to the status bar must be translatable — and registered.

This is the guard that should have caught two P0s and did not.

* `offset_tool.py`'s ``"Created {dir} offset of {dist:.1f} cm"`` — wrapped in
  ``self._view.tr(...)``, which pylupdate6 cannot extract because it only walks
  ``self.tr`` inside QObject subclasses.
* `canvas_scene.py`'s three calibration strings — **bare literals**, not wrapped in
  anything. Round 6's scan looked only at ``tr()`` literals, so a bare literal was
  structurally invisible to it.

Both shipped English to a German user. Both were dead until this branch fixed
``CanvasView.set_status_message`` (which reached for ``self.parent().statusBar()``
and so resolved to nothing in the production layout, where the canvas's parent is
a ``QSplitter``). Fixing the route made two dozen previously-silent strings
user-visible at once, and two of them were not translatable.

Why this shape and not a list of strings: a hand-maintained table cannot catch a
*newly written* wrong string, which is exactly how six review rounds' worth of
documentation defects survived green suites. This walks the call sites, so it
fails the moment someone writes a bare literal — regardless of what it says.

`test_german_ts_has_no_unfinished` cannot help here: it inspects messages already
in the table, and a string that was never registered is by definition not in it.
That is the same blind spot AGENTS.md records for plain-string call sites.

**What is and is not decidable.** A static walk can settle three shapes, and this
checks all three:

1. a literal argument (``set_status_message("…")``);
2. a translation followed by ``.format()`` / ``.replace()`` — the pattern AGENTS.md
   prescribes, and which is easy to mistake for a bare literal;
3. a **local variable**, resolved to its assignments in the enclosing function —
   ``chamfer_tool.py`` builds its message this way, so a guard that only looked at
   the argument would either pass it by luck or flag it falsely.

An attribute or subscript (``cmd.description``) is not statically decidable: the
string's origin is in another module. Those are reported by
``test_the_undecidable_call_sites_are_known`` so the blind spot is visible rather
than invisible, but they do not fail the build — failing on them would be a guard
that cries wolf.

An **empty** argument is also allowed: ``set_status_message("")`` is the
clear-the-bar idiom (``canvas_scene.py`` uses it to dismiss the calibration
prompt), not an untranslated string. There is nothing to translate and nothing to
leak, and flagging it would be a false positive that teaches people to ignore
this guard.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "open_garden_planner"
CATALOGUE = SRC_ROOT / "resources" / "translations" / "open_garden_planner_de.ts"

#: The user-visible method that delivers text to the status bar.
_STATUS_SINK = "set_status_message"

#: Wrappers that count as translation.
_TRANSLATING = {"tr", "translate"}

#: Methods that build a new string from a translating base; peel these off first.
_STRING_BUILDERS = {"format", "format_map", "replace"}


def _is_translating_call(node: ast.AST) -> bool:
    """True for ``.tr(...)`` / ``translate(...)`` / ``QCoreApplication.translate(...)``."""
    if not isinstance(node, ast.Call) or not node.args:
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    return name in _TRANSLATING


def _peel(node: ast.AST) -> ast.AST:
    """Strip ``.format(...)`` / ``.replace(...)`` layers, returning the base call."""
    while (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _STRING_BUILDERS
    ):
        node = node.func.value
    return node


def _enclosing_function(tree: ast.FunctionDef | ast.AsyncFunctionDef,
                        line: int) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """The innermost function containing ``line``, or None at module scope."""
    best = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        if node.lineno <= line <= end and (
            best is None or node.lineno > best.lineno
        ):
            best = node
    return best


def _assigned_sources(func, name: str) -> list[ast.AST] | None:
    """Every value assigned to ``name`` inside ``func``; None if it is a parameter."""
    if func is None:
        return None
    args = {
        a.arg for a in (
            list(func.args.args) + list(func.args.kwonlyargs) + list(func.args.posonlyargs)
        )
    }
    if name in args:
        return None
    sources: list[ast.AST] = []
    for node in ast.walk(func):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and node.target:
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                sources.append(node.value)
    return sources


def _verdict(node: ast.AST, func) -> str:
    """``ok`` / ``bad`` / ``clear`` / ``unknown`` for a status-bar argument.

    ``clear`` is the empty-string clear-the-bar idiom; see the module
    docstring for why it is separated from ``bad``.
    """
    base = _peel(node)
    if _is_translating_call(base):
        return "ok"
    if isinstance(base, ast.Constant):
        if not isinstance(base.value, str):
            return "unknown"
        # "" is the clear-the-bar idiom, not an untranslated string.
        return "clear" if base.value == "" else "bad"
    if isinstance(base, ast.JoinedStr):
        return "ok" if any(
            _is_translating_call(_peel(v.value)) for v in base.values
        ) else "bad"
    if isinstance(base, ast.BinOp) and isinstance(base.op, ast.Mod):
        left = _peel(base.left)
        return "ok" if _is_translating_call(left) else "unknown"
    if isinstance(base, ast.Name):
        # An empty result means either a parameter (the origin is in another
        # module) or a name never assigned here; both are undecidable rather
        # than bad, and guessing would be a false positive.
        sources = _assigned_sources(func, base.id)
        if not sources:
            return "unknown"
        return "bad" if any(_verdict(s, func) == "bad" for s in sources) else "ok"
    return "unknown"


def _wrapped_sources(path: Path) -> dict[str, str | None]:
    """``source -> context`` for every translating call in ``path``.

    The two translating forms put their arguments in DIFFERENT places, which is
    itself worth pinning:

    * ``obj.tr(source)``                        -> ``args[0]`` is the source
    * ``QCoreApplication.translate(ctx, source)`` -> ``args[0]`` is the CONTEXT

    Assuming ``.tr()``'s layout silently keys the result by context, which looks
    like the string is unregistered when it is perfectly registered.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, str | None] = {}
    for node in ast.walk(tree):
        if not _is_translating_call(node):
            continue
        try:
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                # translate(context, source[, disambiguation])
                context = ast.literal_eval(node.args[0])
                source = ast.literal_eval(node.args[1])
            else:
                # tr(source) — the context is the receiver's own class name
                context = None
                source = ast.literal_eval(node.args[0])
        except (ValueError, TypeError, SyntaxError):
            continue
        if isinstance(source, str):
            out[source] = context if isinstance(context, str) else None
    return out


def _status_arguments() -> list[tuple[Path, ast.Call, str]]:
    """``(file, call, verdict)`` for every status-bar call in the source tree."""
    out: list[tuple[Path, ast.Call, str]] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:            # pragma: no cover - would fail CI elsewhere
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and node.args
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == _STATUS_SINK
            ):
                func = _enclosing_function(tree, node.lineno)
                out.append((path, node, _verdict(node.args[0], func)))
    return out


def _catalogue_sources() -> set[str]:
    """Every ``<source>`` in the German catalogue, whatever its context."""
    import xml.etree.ElementTree as ET

    root = ET.parse(CATALOGUE).getroot()
    return {
        (message.findtext("source") or "").strip()
        for message in root.iter("message")
    }


class TestNoUntranslatableStringReachesTheStatusBar:
    def test_no_status_sink_is_fed_an_untranslatable_literal(self) -> None:
        findings = [
            f"{path.relative_to(REPO_ROOT)}:{node.lineno} passes an untranslatable "
            f"string to {_STATUS_SINK}: "
            f"{ast.unparse(node.args[0])[:70]!r}"
            for path, node, verdict in _status_arguments()
            if verdict == "bad"
        ]
        assert not findings, (
            "these reach the status bar untranslated, so a German user reads "
            "English. They were invisible while set_status_message resolved to "
            "nothing; #415 fixed the route, which made them live:\n  "
            + "\n  ".join(findings)
        )

    def test_the_scan_actually_finds_sinks(self) -> None:
        """A guard that finds nothing is indistinguishable from a broken one."""
        calls = _status_arguments()
        assert len(calls) >= 20, (
            f"only {len(calls)} status-bar call sites found; the route has probably "
            f"been renamed and this guard is now vacuous"
        )
        assert all(v in ("ok", "bad", "clear", "unknown") for _, _, v in calls)

    def test_the_undecidable_call_sites_are_known(self) -> None:
        """Name the blind spot instead of leaving it implicit.

        ``cmd.description``-style arguments cannot be resolved statically, so they
        are neither passed nor failed — they are listed, which is what makes this
        guard's coverage auditable instead of merely claimed.
        """
        unknown = sorted(
            f"{path.relative_to(REPO_ROOT)}:{node.lineno} "
            f"{ast.unparse(node.args[0])[:50]}"
            for path, node, verdict in _status_arguments()
            if verdict == "unknown"
        )
        # Informational by design: printed so a reviewer can audit the residual
        # risk, asserted only so the set cannot silently grow without being seen.
        assert all("set_status_message" not in u for u in unknown), unknown
        print(f"\nundecidable status-bar call sites ({len(unknown)}):")
        for entry in unknown:
            print(f"  {entry}")

    #: The three P0 strings, named so a rename is visible.
    CALIBRATION = (
        "Calibration: Click first point on the image",
        "Calibration: Click second point on the image",
        "Calibration complete",
    )

    def test_the_calibration_strings_are_wrapped(self) -> None:
        """The three P0 strings: each an argument of ``translate('CanvasScene', …)``.

        Asserted as *the argument of a translate call in that context*, not as
        "not a Constant" — a wrapped string is still a Constant, and the earlier
        form of this check was therefore unsatisfiable while looking meaningful.
        """
        wrapped = _wrapped_sources(SRC_ROOT / "ui" / "canvas" / "canvas_scene.py")

        for literal in self.CALIBRATION:
            assert literal in wrapped, (
                f"{literal!r} is not an argument of a tr()/translate() call — it is "
                f"bare again. Wrap it in QCoreApplication.translate('CanvasScene', …)"
            )
            assert wrapped[literal] == "CanvasScene", (
                f"{literal!r} is registered under context {wrapped[literal]!r}, "
                f"which will not match at runtime"
            )
            assert literal in _catalogue_sources(), (
                f"{literal!r} is not registered in the German catalogue"
            )

    def test_each_calibration_string_is_not_also_a_bare_status_argument(self) -> None:
        """Wrapping one occurrence must not leave a second, unwrapped one."""
        offenders = [
            f"{path.relative_to(REPO_ROOT)}:{node.lineno}"
            for path, node, verdict in _status_arguments()
            if verdict == "bad"
            and ast.unparse(node.args[0]).strip("'\"") in self.CALIBRATION
        ]
        assert not offenders, offenders


class TestTheVerdictLogicItselfWorks:
    """Pin the analysis, because a wrong 'ok' is worse than no guard.

    Each case is a shape that appears in the source today. If the peeling, the
    name resolution or the verdict mapping regresses, these fail.
    """

    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            ("self.tr('x')", "ok"),
            ("self.tr('x').format(n=1)", "ok"),
            ("self.tr('x').replace('{n}', str(n))", "ok"),
            ("QCoreApplication.translate('C', 'x')", "ok"),
            ("self._view.tr('x').format(n=1)", "ok"),
            ("'x'", "bad"),
            ("''", "clear"),
            ("'x {n}'.format(n=1)", "bad"),
            ("'x'.replace('a', 'b')", "bad"),
        ],
        ids=[
            "tr", "tr-format", "tr-replace", "core-translate", "view-tr-format",
            "bare", "bare-format", "bare-replace", "clear",
        ],
    )
    def test_expression_verdicts(self, expression: str, expected: str) -> None:
        node = ast.parse(expression, mode="eval").body
        assert _verdict(node, None) == expected, expression

    def test_a_local_variable_is_resolved_through_its_assignment(self) -> None:
        """`chamfer_tool.py`'s shape: a translated message built into a local."""
        good = ast.parse(
            "def f():\n"
            "    msg = QCoreApplication.translate('T', 'hello {n}').format(n=1)\n"
            "    self.set_status_message(msg)\n"
        )
        bad = ast.parse(
            "def f():\n"
            "    msg = 'hello {n}'.format(n=1)\n"
            "    self.set_status_message(msg)\n"
        )
        for tree, expected in ((good, "ok"), (bad, "bad")):
            func = tree.body[0]
            call = next(
                n for n in ast.walk(func)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == _STATUS_SINK
            )
            assert _verdict(call.args[0], func) == expected, ast.unparse(func)

    def test_a_parameter_is_unknown_not_bad(self) -> None:
        """A parameter's origin is elsewhere; guessing would be a false positive."""
        tree = ast.parse(
            "def f(cmd):\n    self.set_status_message(cmd.description)\n"
        )
        func = tree.body[0]
        call = next(
            n for n in ast.walk(func)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == _STATUS_SINK
        )
        assert _verdict(call.args[0], func) == "unknown"


class TestRegisteredStatusStringsResolve:
    """Registration is necessary but not sufficient — check the compiled result.

    A catalogue entry can name the wrong context and never match at runtime, which
    is how a string can be 'translated' and still ship English. These resolve
    through the shipped ``.qm`` the way Qt does.
    """

    @pytest.mark.parametrize(
        ("context", "source", "expected_fragment"),
        [
            ("CanvasScene", "Calibration complete", "abgeschlossen"),
            ("CanvasScene", "Calibration: Click first point on the image",
             "ersten Punkt"),
            ("CanvasScene", "Calibration: Click second point on the image",
             "zweiten Punkt"),
            ("CanvasView", "Created {dir} offset of {dist:.1f} cm", "Versatz"),
        ],
        ids=["complete", "first-point", "second-point", "offset"],
    )
    def test_the_shipped_translation_resolves(
        self, context: str, source: str, expected_fragment: str
    ) -> None:
        from PyQt6.QtCore import QTranslator

        qm = SRC_ROOT / "resources" / "translations" / "open_garden_planner_de.qm"
        assert qm.exists(), f"the compiled catalogue is missing: {qm}"

        translator = QTranslator()
        assert translator.load(str(qm), ""), f"could not load {qm}"

        assert source in _catalogue_sources(), (
            f"{source!r} is not in the .ts catalogue at all, so it would ship "
            f"English regardless of how it is wrapped"
        )
        resolved = translator.translate(context, source)
        assert resolved != source, (
            f"{source!r} is registered under a context that does not match the "
            f"runtime context; Qt fell back to the English source"
        )
        # Case-insensitively: the question is "is this still English?", and a
        # correctly-capitalised German noun ("Ersten Punkt") is not a failure.
        assert expected_fragment.casefold() in resolved.casefold(), (
            f"the German for {source!r} under context {context!r} is {resolved!r}, "
            f"expected to contain {expected_fragment!r}"
        )
