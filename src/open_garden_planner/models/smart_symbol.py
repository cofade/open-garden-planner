"""Smart-symbol definition model + parametric geometry generation (US-C4).

A smart symbol is a reusable parametric block defined in a versioned JSON file.
This module is **Qt-free**: it loads/validates a definition and turns a set of
parameter values into a list of geometry *specs* (plain dataclasses with float
coordinates). The Qt item layer (``ui/canvas/items/smart_symbol_item.py``) maps
those specs onto concrete ``RectangleItem`` / ``PolylineItem`` / … objects. The
separation keeps generation unit-testable without a ``QApplication``.

Authoring format (see docs §8 "Smart Symbol Authoring"):

    {
      "id": "raised_bed_rows", "version": 1,
      "name": "Raised Bed (rows)", "name_de": "Hochbeet (Reihen)",
      "category": "beds",
      "parameters": [
        {"name": "L", "type": "length", "label": "Length", "label_de": "Länge",
         "default": 200, "min": 20, "max": 1000},
        {"name": "rows", "type": "number", "label": "Rows", "default": 4,
         "min": 1, "max": 20}
      ],
      "elements": [
        {"kind": "rect", "x": 0, "y": 0, "w": "L", "h": "W", "object_type": "RAISED_BED"},
        {"repeat": {"var": "i", "from": 1, "to": "rows - 1"},
         "element": {"kind": "line", "x1": 0, "y1": "W*i/rows", "x2": "L", "y2": "W*i/rows"}}
      ]
    }

Coordinate values are either a number or an arithmetic expression string over
the parameters (and the active ``repeat`` variable), evaluated by
``core.parametric_eval.safe_eval`` (no ``eval``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from open_garden_planner.core.parametric_eval import safe_eval

_PARAM_TYPES = {"number", "length", "choice"}
_ELEMENT_KINDS = {"rect", "line", "polyline", "polygon", "circle"}


class SmartSymbolError(ValueError):
    """A smart-symbol definition could not be turned into geometry.

    Wraps **every** non-structural failure of :meth:`SmartSymbolDefinition.
    generate` — a bad/unknown-variable expression, divide-by-zero or overflow
    (``ArithmeticError``), a bad ``round`` argument (``TypeError``), or an
    over-budget repeat — in ONE exception type, raised at the model boundary.
    It subclasses ``ValueError`` so the two fallback sites (the user-file
    loader and the canvas item's runtime regeneration) each catch a single
    type that cannot drift out of sync with the evaluator's raw exception
    surface. Untrusted JSON must never crash the app; this is the seam that
    guarantees it. Structural load errors (missing ``id``, empty ``elements``,
    etc.) stay plain ``ValueError`` — they are programmer/packaging-visible.
    """

# Guard rails — symbol files (incl. user-dropped JSON) are untrusted input.
# A runaway repeat or expression must not freeze the app; these caps make a
# bad definition raise ``ValueError`` (→ crash-loud at load for bundled files,
# warn-and-skip for user files) rather than generate millions of items.
_MAX_REPEAT = 1000
_MAX_PRIMITIVES = 5000


# ── Geometry specs (Qt-free; consumed by the item layer) ────────────────────
@dataclass(frozen=True)
class RectSpec:
    x: float
    y: float
    w: float
    h: float
    object_type: str | None = None
    kind: str = "rect"


@dataclass(frozen=True)
class LineSpec:
    x1: float
    y1: float
    x2: float
    y2: float
    object_type: str | None = None
    kind: str = "line"


@dataclass(frozen=True)
class PolylineSpec:
    points: tuple[tuple[float, float], ...]
    object_type: str | None = None
    kind: str = "polyline"


@dataclass(frozen=True)
class PolygonSpec:
    points: tuple[tuple[float, float], ...]
    object_type: str | None = None
    kind: str = "polygon"


@dataclass(frozen=True)
class CircleSpec:
    cx: float
    cy: float
    r: float
    object_type: str | None = None
    kind: str = "circle"


PrimitiveSpec = RectSpec | LineSpec | PolylineSpec | PolygonSpec | CircleSpec


# ── Parameter + definition ──────────────────────────────────────────────────
@dataclass
class SmartSymbolParam:
    name: str
    type: str
    label: str = ""
    label_de: str = ""
    default: Any = 0
    min: float | None = None
    max: float | None = None
    choices: list[str] = field(default_factory=list)
    unit: str = ""

    def display_label(self, lang: str = "en") -> str:
        if lang == "de" and self.label_de:
            return self.label_de
        return self.label or self.name

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SmartSymbolParam:
        name = data.get("name")
        ptype = data.get("type")
        if not isinstance(name, str) or not name:
            raise ValueError("smart-symbol parameter missing 'name'")
        if ptype not in _PARAM_TYPES:
            raise ValueError(f"parameter {name!r} has invalid type {ptype!r}")
        choices = data.get("choices", []) or []
        if ptype == "choice" and not choices:
            raise ValueError(f"choice parameter {name!r} needs non-empty 'choices'")
        return cls(
            name=name,
            type=ptype,
            label=data.get("label", ""),
            label_de=data.get("label_de", ""),
            default=data.get("default", choices[0] if choices else 0),
            min=data.get("min"),
            max=data.get("max"),
            choices=list(choices),
            unit=data.get("unit", ""),
        )


@dataclass
class SmartSymbolDefinition:
    id: str
    version: int
    name: str
    name_de: str
    category: str
    parameters: list[SmartSymbolParam]
    elements: list[dict[str, Any]]

    def display_name(self, lang: str = "en") -> str:
        if lang == "de" and self.name_de:
            return self.name_de
        return self.name or self.id

    def param_defaults(self) -> dict[str, Any]:
        return {p.name: p.default for p in self.parameters}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SmartSymbolDefinition:
        sid = data.get("id")
        if not isinstance(sid, str) or not sid:
            raise ValueError("smart symbol missing 'id'")
        version = data.get("version", 1)
        if not isinstance(version, int):
            raise ValueError(f"symbol {sid!r}: 'version' must be an int")
        params_data = data.get("parameters", [])
        if not isinstance(params_data, list):
            raise ValueError(f"symbol {sid!r}: 'parameters' must be a list")
        elements = data.get("elements", [])
        if not isinstance(elements, list) or not elements:
            raise ValueError(f"symbol {sid!r}: 'elements' must be a non-empty list")
        definition = cls(
            id=sid,
            version=version,
            name=data.get("name", sid),
            name_de=data.get("name_de", ""),
            category=data.get("category", ""),
            parameters=[SmartSymbolParam.from_dict(p) for p in params_data],
            elements=elements,
        )
        # Dry-run generation with defaults validates every expression + kind.
        definition.generate(definition.param_defaults())
        return definition

    # ── Geometry generation ─────────────────────────────────────────────────
    def generate(self, params: dict[str, Any]) -> list[PrimitiveSpec]:
        """Resolve ``elements`` against ``params`` into concrete geometry specs.

        Numeric/length params become evaluator variables; non-numeric (choice)
        params are ignored for coordinates. Any failure to produce geometry —
        a bad expression, unknown variable/kind, divide-by-zero, overflow, a
        bad ``round`` argument, or an over-budget repeat — is raised as a single
        :class:`SmartSymbolError` (a ``ValueError`` subclass), so callers that
        must degrade gracefully on untrusted input catch exactly one type.
        """
        try:
            return self._generate(params)
        except SmartSymbolError:
            raise
        except Exception as exc:
            # This seam exists precisely so callers catch ONE type. Generation
            # is a pure function over untrusted data, so any failure — arithmetic
            # (divide-by-zero/overflow), TypeError, a too-complex expression
            # (ValueError), or a deep-recursion RecursionError (RuntimeError) —
            # is a generation failure, not a control-flow signal. A blind catch
            # (not a hand-picked tuple) is deliberate: enumerating families is
            # how RecursionError slipped through before. BaseException
            # (KeyboardInterrupt/SystemExit) still propagates. The evaluator's
            # node cap keeps the common surface to ValueError; this is the
            # backstop that makes "untrusted JSON never crashes the app" total.
            raise SmartSymbolError(str(exc)) from exc

    def _generate(self, params: dict[str, Any]) -> list[PrimitiveSpec]:
        merged = {**self.param_defaults(), **(params or {})}
        variables: dict[str, float] = {}
        for key, value in merged.items():
            try:
                variables[key] = float(value)
            except (TypeError, ValueError):
                continue  # choice/non-numeric param — not usable in coords
        specs: list[PrimitiveSpec] = []
        for element in self.elements:
            specs.extend(self._build_element(element, variables))
            if len(specs) > _MAX_PRIMITIVES:
                raise ValueError(
                    f"smart symbol generated more than {_MAX_PRIMITIVES} primitives"
                )
        return specs

    def _build_element(
        self, element: dict[str, Any], variables: dict[str, float]
    ) -> list[PrimitiveSpec]:
        if "repeat" in element:
            rep = element["repeat"]
            var = rep.get("var")
            if not isinstance(var, str):
                raise ValueError("repeat block missing string 'var'")
            lo = int(round(self._num(rep.get("from", 0), variables)))
            hi = int(round(self._num(rep.get("to", 0), variables)))
            if hi - lo + 1 > _MAX_REPEAT:
                raise ValueError(
                    f"repeat range {lo}..{hi} exceeds the {_MAX_REPEAT}-iteration cap"
                )
            inner = rep.get("element") or element.get("element")
            if not isinstance(inner, dict):
                raise ValueError("repeat block missing 'element'")
            out: list[PrimitiveSpec] = []
            for i in range(lo, hi + 1):
                out.append(self._build_one(inner, {**variables, var: float(i)}))
            return out
        return [self._build_one(element, variables)]

    def _build_one(
        self, element: dict[str, Any], variables: dict[str, float]
    ) -> PrimitiveSpec:
        kind = element.get("kind")
        if kind not in _ELEMENT_KINDS:
            raise ValueError(f"unknown element kind: {kind!r}")
        obj = element.get("object_type")
        n = lambda key: self._num(element.get(key, 0), variables)  # noqa: E731
        if kind == "rect":
            return RectSpec(n("x"), n("y"), n("w"), n("h"), obj)
        if kind == "line":
            return LineSpec(n("x1"), n("y1"), n("x2"), n("y2"), obj)
        if kind == "circle":
            return CircleSpec(n("cx"), n("cy"), n("r"), obj)
        # polyline / polygon — list of [x, y] pairs
        pts = element.get("points")
        if not isinstance(pts, list) or len(pts) < 2:
            raise ValueError(f"{kind} needs a 'points' list of ≥2 pairs")
        points = tuple(
            (self._num(p[0], variables), self._num(p[1], variables)) for p in pts
        )
        if kind == "polyline":
            return PolylineSpec(points, obj)
        return PolygonSpec(points, obj)

    @staticmethod
    def _num(value: Any, variables: dict[str, float]) -> float:
        """A coordinate value: a number, or an expression string over params."""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            return safe_eval(value, variables)
        raise ValueError(f"coordinate must be a number or expression, got {value!r}")
