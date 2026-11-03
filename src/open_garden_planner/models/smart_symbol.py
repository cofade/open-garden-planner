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

import math
from dataclasses import dataclass, field
from typing import Any

from open_garden_planner.models.parametric_eval import safe_eval

_PARAM_TYPES = {"number", "length", "choice"}
_ELEMENT_KINDS = {"rect", "line", "polyline", "polygon", "circle"}

# Valid ObjectType names per primitive kind (mirrors core.object_types
# get_valid_types_for_shape; kept Qt-free here and pinned by unit test).
VALID_OBJECT_TYPES_BY_KIND: dict[str, frozenset[str]] = {
    "rect": frozenset({
        "GENERIC_RECTANGLE",
        "HOUSE",
        "GARAGE_SHED",
        "GREENHOUSE",
        "GARDEN_BED",
        "HEDGE_SECTION",
        "TABLE_RECTANGULAR",
        "CHAIR",
        "BENCH",
        "LOUNGER",
        "BBQ_GRILL",
        "RAISED_BED",
        "COMPOST_BIN",
        "COLD_FRAME",
        "TOOL_SHED",
        "SANDBOX",
        "HOT_TUB",
        "SWING",
        "PICNIC_TABLE",
        "HAMMOCK",
        "WHEELBARROW",
        "PERGOLA",
        "CONTAINER",
        "WALL_PLANTER",
        "TRELLIS",
    }),
    "line": frozenset({"FENCE", "WALL", "PATH", "STRING_LIGHTS"}),
    "polyline": frozenset({"FENCE", "WALL", "PATH", "STRING_LIGHTS"}),
    "polygon": frozenset({
        "GENERIC_POLYGON",
        "HOUSE",
        "GARAGE_SHED",
        "TERRACE_PATIO",
        "DRIVEWAY",
        "POND_POOL",
        "GREENHOUSE",
        "GARDEN_BED",
        "LAWN",
        "HEDGE_POLYGON",
    }),
    "circle": frozenset({
        "GENERIC_CIRCLE",
        "TREE",
        "SHRUB",
        "PERENNIAL",
        "TABLE_ROUND",
        "PARASOL",
        "FIRE_PIT",
        "BBQ_GRILL",
        "PLANTER_POT",
        "CONTAINER_ROUND",
        "RAIN_BARREL",
        "WATER_TAP",
        "TRAMPOLINE",
        "BIRD_BATH",
        "POND_POOL",
        "GARDEN_BED",
        "GARDEN_LIGHT",
    }),
}
ALL_KNOWN_OBJECT_TYPES: frozenset[str] = frozenset().union(*VALID_OBJECT_TYPES_BY_KIND.values())


def validate_kind_object_type(
    kind: str,
    object_type: Any,
    *,
    guide: Any = False,
    plain_panel: Any = False,
) -> tuple[str | None, bool, bool]:
    """Validate primitive ``kind``, ``object_type``, ``guide``, and ``plain_panel``."""
    if kind not in _ELEMENT_KINDS:
        raise ValueError(f"unknown element kind: {kind!r}")
    if not isinstance(guide, bool):
        raise ValueError(f"element 'guide' must be a bool, got {guide!r}")
    if not isinstance(plain_panel, bool):
        raise ValueError(f"element 'plain_panel' must be a bool, got {plain_panel!r}")
    if plain_panel and (kind not in ("line", "polyline") or object_type != "FENCE"):
        raise ValueError(
            "element 'plain_panel' is only supported on 'line'/'polyline' elements with object_type 'FENCE'"
        )
    if object_type is None:
        return None, guide, plain_panel
    if not isinstance(object_type, str) or not object_type:
        raise ValueError(f"element 'object_type' must be a non-empty string, got {object_type!r}")
    if guide:
        raise ValueError(
            f"guide element ({kind!r}) cannot also declare object_type {object_type!r}"
        )
    if object_type not in ALL_KNOWN_OBJECT_TYPES:
        raise ValueError(f"unknown object_type {object_type!r}")
    valid_for_kind = VALID_OBJECT_TYPES_BY_KIND[kind]
    if object_type not in valid_for_kind:
        raise ValueError(
            f"object_type {object_type!r} is incompatible with primitive kind {kind!r}"
        )
    return object_type, guide, plain_panel


class SmartSymbolError(ValueError):
    """A smart-symbol definition could not be turned into geometry.

    Wraps **every** non-``BaseException`` failure of :meth:`SmartSymbolDefinition.
    generate` — whatever the evaluator throws (a bad/unknown-variable expression,
    divide-by-zero, overflow, a bad ``round`` argument, a too-complex expression,
    an over-budget repeat) — in ONE exception type, raised at the model boundary
    by a blind ``except Exception`` (NOT a hand-picked family list, which is how
    new exception families kept slipping through). It subclasses ``ValueError``
    so the canvas item's runtime regeneration catches a single type. The
    user-file **loader** is the real untrusted-input boundary and catches
    ``Exception`` directly (it must also survive failures of ``from_dict``'s
    *structural* phase, which runs before ``generate``). Structural load errors
    (missing ``id``, non-dict param, empty ``elements``, …) stay plain
    ``ValueError`` so the bundled "crash loud" path still surfaces packaging bugs.
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
    guide: bool = False
    height_cm: float | None = None
    plain_panel: bool = False
    member_key: str = ""


@dataclass(frozen=True)
class LineSpec:
    x1: float
    y1: float
    x2: float
    y2: float
    object_type: str | None = None
    kind: str = "line"
    guide: bool = False
    height_cm: float | None = None
    plain_panel: bool = False
    member_key: str = ""


@dataclass(frozen=True)
class PolylineSpec:
    points: tuple[tuple[float, float], ...]
    object_type: str | None = None
    kind: str = "polyline"
    guide: bool = False
    height_cm: float | None = None
    plain_panel: bool = False
    member_key: str = ""


@dataclass(frozen=True)
class PolygonSpec:
    points: tuple[tuple[float, float], ...]
    object_type: str | None = None
    kind: str = "polygon"
    guide: bool = False
    height_cm: float | None = None
    plain_panel: bool = False
    member_key: str = ""


@dataclass(frozen=True)
class CircleSpec:
    cx: float
    cy: float
    r: float
    object_type: str | None = None
    kind: str = "circle"
    guide: bool = False
    height_cm: float | None = None
    plain_panel: bool = False
    member_key: str = ""


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
        if not isinstance(data, dict):
            raise ValueError(f"smart-symbol parameter must be an object, got {type(data).__name__}")
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
        if not isinstance(data, dict):
            raise ValueError(f"smart symbol must be a JSON object, got {type(data).__name__}")
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
        for elem_idx, element in enumerate(self.elements):
            specs.extend(self._build_element(element, variables, elem_idx=elem_idx))
            if len(specs) > _MAX_PRIMITIVES:
                raise ValueError(
                    f"smart symbol generated more than {_MAX_PRIMITIVES} primitives"
                )
        return specs

    def _build_element(
        self,
        element: dict[str, Any],
        variables: dict[str, float],
        *,
        elem_idx: int = 0,
    ) -> list[PrimitiveSpec]:
        if not isinstance(element, dict):
            raise ValueError(f"smart-symbol element must be an object, got {type(element).__name__}")
        base_key = str(element.get("id") or f"e{elem_idx}")
        if "repeat" in element:
            rep = element["repeat"]
            if not isinstance(rep, dict):
                raise ValueError("repeat block must be an object")
            var = rep.get("var")
            if not isinstance(var, str) or not var:
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
            inner_base = str(inner.get("id") or base_key)
            validate_kind_object_type(
                str(inner.get("kind", "")),
                inner.get("object_type"),
                guide=inner.get("guide", False),
                plain_panel=inner.get("plain_panel", False),
            )
            out: list[PrimitiveSpec] = []
            for i in range(lo, hi + 1):
                out.append(
                    self._build_one(
                        inner,
                        {**variables, var: float(i)},
                        member_key=f"{inner_base}:{var}={i}",
                    )
                )
            return out
        return [self._build_one(element, variables, member_key=base_key)]

    def _build_one(
        self,
        element: dict[str, Any],
        variables: dict[str, float],
        *,
        member_key: str = "",
    ) -> PrimitiveSpec:
        kind = element.get("kind")
        if not isinstance(kind, str) or kind not in _ELEMENT_KINDS:
            raise ValueError(f"unknown element kind: {kind!r}")
        obj, guide, plain_panel = validate_kind_object_type(
            kind,
            element.get("object_type"),
            guide=element.get("guide", False),
            plain_panel=element.get("plain_panel", False),
        )
        height_cm: float | None = None
        if "height_cm" in element and element["height_cm"] is not None:
            height_cm = self._num(element["height_cm"], variables)
            if not math.isfinite(height_cm) or height_cm <= 0.0:
                raise ValueError(f"element 'height_cm' must be positive, got {height_cm!r}")
        def _get_num(key: str) -> float:
            return self._num(element.get(key, 0), variables)

        if kind == "rect":
            w = _get_num("w")
            h = _get_num("h")
            if w <= 0.0 or h <= 0.0:
                raise ValueError(f"rect dimensions must be positive, got w={w!r}, h={h!r}")
            return RectSpec(
                _get_num("x"), _get_num("y"), w, h, obj,
                guide=guide, height_cm=height_cm, plain_panel=plain_panel, member_key=member_key,
            )
        if kind == "line":
            return LineSpec(
                _get_num("x1"), _get_num("y1"), _get_num("x2"), _get_num("y2"), obj,
                guide=guide, height_cm=height_cm, plain_panel=plain_panel, member_key=member_key,
            )
        if kind == "circle":
            r = _get_num("r")
            if r <= 0.0:
                raise ValueError(f"circle radius must be positive, got r={r!r}")
            return CircleSpec(
                _get_num("cx"), _get_num("cy"), r, obj,
                guide=guide, height_cm=height_cm, plain_panel=plain_panel, member_key=member_key,
            )
        # polyline / polygon — list of [x, y] pairs
        pts = element.get("points")
        min_pts = 3 if kind == "polygon" else 2
        if not isinstance(pts, list) or len(pts) < min_pts:
            raise ValueError(f"{kind} needs a 'points' list of ≥{min_pts} pairs")
        points = tuple(
            (self._num(p[0], variables), self._num(p[1], variables)) for p in pts
        )
        if kind == "polyline":
            return PolylineSpec(
                points, obj,
                guide=guide, height_cm=height_cm, plain_panel=plain_panel, member_key=member_key,
            )
        return PolygonSpec(
            points, obj,
            guide=guide, height_cm=height_cm, plain_panel=plain_panel, member_key=member_key,
        )

    @staticmethod
    def _num(value: Any, variables: dict[str, float]) -> float:
        """A coordinate value: a number, or an expression string over params."""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            return safe_eval(value, variables)
        raise ValueError(f"coordinate must be a number or expression, got {value!r}")
