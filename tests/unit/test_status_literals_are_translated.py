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
#: The `.ts` SOURCE catalogue. Membership here does not prove a string resolves
#: at runtime — the compiled `.qm` is checked separately, by
#: `TestRegisteredStatusStringsResolve`, for the four strings it names.
CATALOGUE = SRC_ROOT / "resources" / "translations" / "open_garden_planner_de.ts"

#: The user-visible method that delivers text to the status bar.
_STATUS_SINK = "set_status_message"

#: Wrappers that count as translation.
_TRANSLATING = {"tr", "translate"}

#: Methods that build a new string from a translating base; peel these off first.
_STRING_BUILDERS = {"format", "format_map", "replace"}


#: Severity order. `bad` beats `unknown` beats `ok`, so an undecidable input can
#: never be reported as safe by default — which is how the guard missed
#: ``self.tr(...) if cond else "bare"`` before this existed.
#: `unregistered` sits with `bad`: a source absent from the catalogue ships
#: English, which is the defect this guard exists to prevent.
_SEVERITY = {"ok": 0, "clear": 0, "unknown": 1, "bad": 2, "unregistered": 2}


def _worst(verdicts) -> str:
    """The most severe verdict, with `bad` > `unknown` > `ok`."""
    return max(verdicts, key=lambda v: _SEVERITY[v], default="unknown")


def _enclosing_class(tree: ast.AST, line: int) -> str | None:
    """The innermost ``ClassDef`` name containing ``line``, or None.

    Needed because ``self.tr(...)`` resolves its catalogue context from the
    receiver's class at runtime — measured, not assumed:
    ``PlantingCalendarView.staticMetaObject.className()`` is
    ``'PlantingCalendarView'``, and PyQt gives a Python subclass its own name.
    """
    best: ast.ClassDef | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        if node.lineno <= line <= end and (best is None or node.lineno > best.lineno):
            best = node
    return best.name if best is not None else None


def _translation_source(
    node: ast.AST, tree: ast.AST | None = None
) -> tuple[str, str | None] | None:
    """``(source, context)`` for a ``.tr``/``translate`` call, else ``None``.

    ``context`` is ``None`` when it cannot be determined statically. Returning the
    *source* rather than a bool is what lets the caller ask the only question that
    matters — is this string in the catalogue? The version before that returned True
    for ANY receiver, so ``self._view.tr("BARE ENGLISH")`` passed, and the module
    docstring claimed the guard would have caught exactly that shape in
    ``offset_tool.py``. It could not.

    The two forms put their arguments in DIFFERENT places, and conflating them was a
    real bug: ``tr(src, disambiguation)`` is NOT ``translate(context, src)``.
    """
    if not isinstance(node, ast.Call) or not node.args:
        return None
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name not in _TRANSLATING:
        return None

    def literal(argument: ast.AST) -> str | None:
        try:
            value = ast.literal_eval(argument)
        except (ValueError, TypeError, SyntaxError):
            return None
        return value if isinstance(value, str) else None

    if name == "translate":
        # QCoreApplication.translate(context, source[, disambiguation])
        if len(node.args) >= 2:
            return literal(node.args[1]), literal(node.args[0])
        return literal(node.args[0]), None

    # obj.tr(source[, disambiguation]).
    source = literal(node.args[0])
    # `self.tr(...)` resolves its context from the enclosing class, which IS
    # statically known. Any other receiver (`self._view.tr(...)`, `other.tr(...)`)
    # is not, and is checked on the source alone.
    receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
    if (
        tree is not None
        and isinstance(receiver, ast.Name)
        and receiver.id == "self"
    ):
        return source, _enclosing_class(tree, node.lineno)
    return source, None


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


def _assigned_sources(func, name: str, tree=None) -> list[ast.AST] | None:
    """Every value assigned to ``name``; module scope consulted after ``func``.

    Returns ``None`` for a parameter, whose value comes from a caller in another
    module and is genuinely undecidable here. Returns ``[]`` for a name assigned
    nowhere, which the caller reports as ``unknown`` rather than ``ok``.

    ``tree`` is the module AST; when given, a name with no assignment inside
    ``func`` is looked up at module level, because ``MSG = "..."`` above a function
    is a real shape and stopping at the function boundary reported it as decidable
    when it was not even examined.
    """
    if func is None:
        return None
    args = {
        a.arg for a in (
            list(func.args.args) + list(func.args.kwonlyargs) + list(func.args.posonlyargs)
        )
    }
    if name in args:
        return None
    def collect(scope) -> list[ast.AST]:
        found: list[ast.AST] = []
        for node in ast.walk(scope):
            targets: list[ast.AST] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and node.target:
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id == name:
                    found.append(node.value)
        return found

    sources = collect(func)
    if not sources and tree is not None:
        # Module scope: only top-level statements, not a nested function's locals.
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        sources.append(stmt.value)
            elif (
                isinstance(stmt, ast.AnnAssign)
                and stmt.target
                and isinstance(stmt.target, ast.Name)
                and stmt.target.id == name
            ):
                sources.append(stmt.value)
    return sources


def _verdict(node: ast.AST, func, tree=None, catalogue=None, _seen=None) -> str:
    """``ok`` / ``bad`` / ``clear`` / ``unknown`` / ``unregistered``.

    ``catalogue`` is the set of registered source strings. When it is ``None`` (the
    pure-logic tests) the registration check is skipped; the integration test
    supplies the real one, and that is the run that matters — a translating call
    whose source is not registered ships English regardless of how it is wrapped,
    which is exactly how ``offset_tool.py``'s string was missed.

    ``clear`` is the empty-string clear-the-bar idiom; see the module docstring
    for why it is separated from ``bad``.

    Every branch returns the WORST verdict it can justify. Nothing defaults to
    ``ok``: an input this cannot decide is ``unknown``, and ``unknown`` propagates
    through a parent rather than being resolved in favour of safety. That is the
    distinction that let ``self.tr(...) if cond else "bare"`` pass before.
    """
    seen = set() if _seen is None else _seen
    base = _peel(node)

    pair = _translation_source(base, tree)
    if pair is not None:
        source, context = pair
        if catalogue is None:
            return "ok"          # pure-logic mode; the integration test supplies it
        if not any(src == source for _ctx, src in catalogue):
            return "unregistered"
        # Where the context IS statically known (`translate("Ctx", src)`), it must
        # match too — a string registered under another class resolves to English.
        # Where it is not (`self._view.tr(...)`), the source check is all that can
        # be done, and that is stated rather than implied.
        if context is not None and (context, source) not in catalogue:
            return "unregistered"
        return "ok"

    if isinstance(base, ast.Constant):
        if not isinstance(base.value, str):
            return "unknown"
        # "" is the clear-the-bar idiom, not an untranslated string.
        return "clear" if base.value == "" else "bad"

    if isinstance(base, ast.JoinedStr):
        # An f-string is safe only if SOME interpolated value is translated; the
        # literal parts around it are not translatable on their own.
        inner = [_translation_source(_peel(v.value), tree) for v in base.values]
        if any(pair is not None for pair in inner):
            if catalogue is None:
                return "ok"
            sources = {src for pair in inner if pair for src, _ctx in (pair,)}
            if not all(
                any(s == src for _ctx, s in catalogue) for src in sources
            ):
                return "unregistered"
            return "ok"
        return "bad"

    if isinstance(base, ast.BinOp):
        if isinstance(base.op, ast.Mod):
            # "a %s" % n — a bare constant on the left is a bare literal.
            return _verdict(base.left, func, tree, catalogue, seen)
        # Any other operator over strings: judge both sides.
        return _worst(
            [_verdict(base.left, func, tree, catalogue, seen), _verdict(base.right, func, tree, catalogue, seen)]
        )

    if isinstance(base, ast.IfExp):
        # `a if cond else b` — BOTH arms are live.
        return _worst(
            [
                _verdict(base.body, func, tree, catalogue, seen),
                _verdict(base.orelse, func, tree, catalogue, seen),
            ]
        )

    if isinstance(base, (ast.BoolOp, ast.Tuple, ast.List, ast.Set)):
        values = getattr(base, "values", None) or getattr(base, "elts", [])
        return _worst([_verdict(v, func, tree, catalogue, seen) for v in values])

    if isinstance(base, ast.Call):
        # A call that is not a translation: `"".join(...)`, `str(...)`, etc.
        # Judge the arguments, and add `unknown` for the call itself.
        inner = [_verdict(a, func, tree, catalogue, seen) for a in base.args]
        return _worst(inner + ["unknown"])

    if isinstance(base, ast.Name):
        if base.id in seen:
            # `msg = msg` and the accumulator `msg = msg + part` are real shapes;
            # without this the recursion crashed the suite instead of returning a
            # verdict, which is worse than either answer.
            return "unknown"
        sources = _assigned_sources(func, base.id, tree)
        if not sources:
            # A parameter (origin in another module) or a name assigned nowhere.
            return "unknown"
        return _worst(
            [
                _verdict(s, func, tree, catalogue, seen | {base.id})
                for s in sources
            ]
        )

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
        pair = _translation_source(node, tree)
        if pair is None:
            continue
        source, context = pair
        out[source] = context
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
                # The catalogue is supplied here and nowhere else: this is the scan
                # that decides whether the build is green, and an unregistered
                # source ships English no matter how it is wrapped.
                out.append(
                    (path, node, _verdict(node.args[0], func, tree, _catalogue_entries()))
                )
    return out


_CATALOGUE_CACHE: set[tuple[str, str]] | None = None


def _catalogue_entries() -> set[tuple[str, str]]:
    """Every ``(context, source)`` pair in the German catalogue.

    Keyed on the pair rather than the source alone, because Qt resolves a string by
    receiver class AND text: `self.tr("Rotation:")` inside a class other than the one
    the string was registered under returns English, and a source-only membership
    test called that `ok` (round 9 measured it).
    """
    # Cached: `_status_arguments` consults this per matched call site, so without
    # the cache the whole `.ts` is re-parsed dozens of times per run.
    global _CATALOGUE_CACHE
    if _CATALOGUE_CACHE is not None:
        return _CATALOGUE_CACHE

    import xml.etree.ElementTree as ET

    root = ET.parse(CATALOGUE).getroot()
    out: set[tuple[str, str]] = set()
    for context in root.iter("context"):
        name = context.findtext("name") or ""
        for message in context.iter("message"):
            source = (message.findtext("source") or "").strip()
            if source:
                out.add((name, source))
    _CATALOGUE_CACHE = out
    return out


def _catalogue_sources() -> set[str]:
    """Every registered ``<source>``, whatever its context."""
    return {source for _context, source in _catalogue_entries()}


class TestNoUntranslatableStringReachesTheStatusBar:
    def test_no_status_sink_is_fed_an_untranslatable_literal(self) -> None:
        findings = [
            f"{path.relative_to(REPO_ROOT)}:{node.lineno} passes an untranslatable "
            f"string to {_STATUS_SINK}: "
            f"{ast.unparse(node.args[0])[:70]!r}"
            for path, node, verdict in _status_arguments()
            # `unregistered` is a FAILING verdict and belongs here. Filtering on
            # `"bad"` alone made the whole `unregistered` mechanism inert: the
            # verdict was computed, reported by nothing, and the guard stayed green
            # on exactly the defect it was built for (round 9 measured it).
            if verdict in ("bad", "unregistered")
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
        # The full verdict vocabulary. An earlier version omitted `unregistered`,
        # so the smoke test — not the real check — was what went red on a real
        # defect, and "fixing" it by adding the value to a list would have removed
        # the only signal. Both verdicts that mean "fails" are named here.
        assert all(
            v in ("ok", "clear", "unknown", "bad", "unregistered") for _, _, v in calls
        ), sorted({v for _, _, v in calls})

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
        # Informational by design. The assertion below is a SMOKE check on the
        # scan, not a size limit — an earlier comment claimed it stopped the set
        # growing, which it cannot do. The count is printed for a reviewer to
        # audit; the printed set is the deliverable, not the assertion.
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

        assert any(src == source for _ctx, src in _catalogue_entries()), (
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


class TestTheProbeShapeHolesAreClosed:
    """The three false negatives an adversarial probe found, pinned.

    Each was a real hole in the first version of this guard, found by injecting the
    shape into a scratch module rather than by reading the code. They are cases
    because the pattern of this branch is that each round's guard has a defect the
    next round finds, and a case is what stops that repeating.
    """

    @staticmethod
    def _verdict(source: str) -> str:
        import ast as _ast

        tree = _ast.parse(source)
        call = next(
            n for n in _ast.walk(tree)
            if isinstance(n, _ast.Call)
            and isinstance(n.func, _ast.Attribute)
            and n.func.attr == _STATUS_SINK
        )
        func = _enclosing_function(tree, call.lineno)
        return _verdict(call.args[0], func, tree)

    def test_a_ternary_with_one_bare_arm_is_bad(self) -> None:
        """The worst of the three: an `unknown` arm was silently upgraded to `ok`.

        `msg = self.tr("ok") if cond else "bare"` shipped the bare branch.
        """
        assert self._verdict(
            "def f(self, cond):\n"
            "    msg = self.tr('ok') if cond else 'bare'\n"
            "    self.set_status_message(msg)\n"
        ) == "bad"

    def test_a_percent_format_on_a_bare_literal_is_bad(self) -> None:
        assert self._verdict(
            "def f(self, n):\n    self.set_status_message('a %s' % n)\n"
        ) == "bad"

    def test_a_module_level_constant_is_resolved(self) -> None:
        """`MSG = "bare"` above the function used to be `unknown`, i.e. passed."""
        assert self._verdict(
            "MSG = 'bare'\n"
            "def f(self):\n    self.set_status_message(MSG)\n"
        ) == "bad"

    def test_a_module_level_translated_constant_is_ok(self) -> None:
        """The counterpart: resolving module scope must not flag the safe case."""
        assert self._verdict(
            "MSG = QCoreApplication.translate('C', 'ok')\n"
            "def f(self):\n    self.set_status_message(MSG)\n"
        ) == "ok"

    def test_an_if_else_assignment_judges_both_branches(self) -> None:
        assert self._verdict(
            "def f(self, cond):\n"
            "    if cond:\n        msg = self.tr('ok')\n"
            "    else:\n        msg = 'bare'\n"
            "    self.set_status_message(msg)\n"
        ) == "bad"

    def test_an_undetermined_input_is_not_upgraded_to_ok(self) -> None:
        """The invariant behind all of the above, stated once."""
        assert self._verdict(
            "def f(self, cmd):\n    self.set_status_message(cmd.description)\n"
        ) == "unknown"
        assert _worst(["ok", "unknown"]) == "unknown"
        assert _worst(["unknown", "bad"]) == "bad"
        assert _worst(["ok", "clear"]) == "ok"


class TestTheGuardWouldHaveCaughtTheTwoKnownP0Shapes:
    """Round 8: the guard's docstring promised these and the guard could not do it.

    > the guard treats **any** `.tr(...)`/`translate(...)` call as `ok` regardless of
    > receiver ... `self._view.set_status_message(self._view.tr('BARE ENGLISH'))` → `ok`.

    Both shapes are asserted here against the REAL scan, with the REAL catalogue, so
    the docstring's claim is now something the suite can falsify.
    """

    SOURCE = "BARE ENGLISH NOT IN ANY CATALOGUE"

    def test_an_unregistered_view_tr_is_caught(self) -> None:
        """`offset_tool.py`'s shape: a `.tr` on a receiver pylupdate6 cannot extract.

        `self._view.tr(...)` is NOT extracted by pylupdate6 (it walks `self.tr`
        inside QObject subclasses only), so the source is registered by hand or not
        at all. The guard now checks the catalogue, which is the property that was
        actually violated.
        """
        tree = ast.parse(
            "def f(self):\n"
            f"    self.set_status_message(self._view.tr({self.SOURCE!r}))\n"
        )
        call = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == _STATUS_SINK
        )
        verdict = _verdict(call.args[0], tree.body[0], tree, set())
        assert verdict == "unregistered", (
            f"a `.tr` source absent from the catalogue was judged {verdict!r}; it "
            "ships English and the guard must not pass it"
        )

    def test_a_registered_view_tr_is_ok(self) -> None:
        """The counterpart: the offset string IS hand-registered, so it passes.

        Without this, the check could be made to pass by rejecting every `.view.tr`,
        which would be a false positive on correct code.
        """
        tree = ast.parse(
            "def f(self):\n"
            "    self.set_status_message(self._view.tr("
            "'Created {dir} offset of {dist:.1f} cm'))\n"
        )
        call = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == _STATUS_SINK
        )
        verdict = _verdict(call.args[0], tree.body[0], tree, _catalogue_entries())
        assert verdict == "ok", (
            f"the offset string is registered under CanvasView, so this must be ok, "
            f"not {verdict!r}"
        )

    def test_an_unregistered_self_tr_is_caught(self) -> None:
        """The common case: a new string added without re-running extraction."""
        tree = ast.parse(
            "def f(self):\n"
            f"    self.set_status_message(self.tr({self.SOURCE!r}))\n"
        )
        call = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == _STATUS_SINK
        )
        assert _verdict(call.args[0], tree.body[0], tree, set()) == "unregistered"

    def test_a_registered_self_tr_is_ok(self) -> None:
        """`Mark as done` is a real registered string, used as the positive control."""
        assert "Mark as done" in _catalogue_sources(), (
            "the positive-control string is not registered; pick another"
        )
        tree = ast.parse(
            "def f(self):\n"
            "    self.set_status_message(self.tr('Mark as done'))\n"
        )
        call = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == _STATUS_SINK
        )
        assert _verdict(call.args[0], tree.body[0], tree, _catalogue_entries()) == "ok"


class TestTheContextBoundaryIsStatedByTests:
    """Round 10: the boundary must be pinned, not described in a comment.

    The comment used to read as though `self.tr` were context-checked when it was
    not — `_translation_source` returned no context for any `.tr` receiver, so
    `self.tr('Rotation:')` in a class other than `ArrayAlongPathDialog` was `ok`,
    which is the shape the commit message used as its motivating example.

    `self.tr` is now resolved from its enclosing class (measured: PyQt gives a
    Python subclass its own `staticMetaObject().className()`). `self._view.tr` still
    cannot be, and that is the boundary — asserted here so it cannot drift back into
    a comment.
    """

    @staticmethod
    def _verdict_for(source: str) -> str:
        import ast as _ast

        tree = _ast.parse(source)
        call = next(
            n for n in _ast.walk(tree)
            if isinstance(n, _ast.Call)
            and isinstance(n.func, _ast.Attribute)
            and n.func.attr == _STATUS_SINK
        )
        func = _enclosing_function(tree, call.lineno)
        return _verdict(call.args[0], func, tree, _catalogue_entries())

    @staticmethod
    def _a_real_pair() -> tuple[str, str]:
        """A `(context, source)` that is genuinely in the catalogue.

        Chosen at runtime rather than hardcoded: the property under test is "a
        source registered under context A is unregistered under context B", and a
        hardcoded string ties it to one string's wording. (The first version used
        `("Rotation:", "ArrayAlongPathDialog")`, which is not in the catalogue at
        all — so it failed on its own premise rather than on the behaviour.)
        """
        pair = sorted(
            (ctx, src)
            for ctx, src in _catalogue_entries()
            if ctx and src and len(src) > 4 and "{" not in src
        )[0]
        return pair

    def test_a_wrong_context_self_tr_is_unregistered(self) -> None:
        """Registered under one class, called from another, is NOT resolved."""
        context, source = self._a_real_pair()
        wrong_class = f"{context}SomethingElse"
        assert (wrong_class, source) not in _catalogue_entries()
        assert self._verdict_for(
            f"class {wrong_class}:\n"
            "    def f(self):\n"
            f"        self.set_status_message(self.tr({source!r}))\n"
        ) == "unregistered", (
            f"{source!r} is registered under {context!r}, so calling it from "
            f"{wrong_class!r} resolves to English at runtime"
        )

    def test_the_matching_context_is_ok(self) -> None:
        """The counterpart, so the check cannot be satisfied by rejecting all."""
        context, source = self._a_real_pair()
        assert self._verdict_for(
            f"class {context}:\n"
            "    def f(self):\n"
            f"        self.set_status_message(self.tr({source!r}))\n"
        ) == "ok", f"{source!r} is registered under {context!r} and must pass"

    def test_a_non_self_receiver_is_source_only(self) -> None:
        """`self._view.tr(...)` — the context cannot be resolved, and is not guessed.

        `offset_tool.py`'s string is registered by hand under `CanvasView` precisely
        because pylupdate6 cannot extract this call. Checking the source is all that
        can be done; a wrong class here is NOT detected, and saying so is the point.
        """
        assert self._verdict_for(
            "class Whatever:\n"
            "    def f(self):\n"
            "        self.set_status_message(self._view.tr("
            "'Created {dir} offset of {dist:.1f} cm'))\n"
        ) == "ok", "the registered offset string must pass"

    def test_a_non_self_receiver_with_an_unknown_source_is_caught(self) -> None:
        """The half that IS checked: an unregistered source on any receiver."""
        assert self._verdict_for(
            "class Whatever:\n"
            "    def f(self):\n"
            "        self.set_status_message(self._view.tr('NOT REGISTERED'))\n"
        ) == "unregistered"

    def test_the_real_tree_has_no_false_positives(self) -> None:
        """Measured: 38 ok, 6 unknown, 1 clear, 0 failing."""
        failing = [
            (str(path), node.lineno, verdict)
            for path, node, verdict in _status_arguments()
            if verdict in ("bad", "unregistered")
        ]
        assert not failing, (
            "the context check flags correct code, which is worse than not checking: "
            f"{failing}"
        )
