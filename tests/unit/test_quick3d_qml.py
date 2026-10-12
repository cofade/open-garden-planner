"""The engine package's QML, read as text (Phase 17 L1.2, #385 — gate G3).

``Garden.qml`` cannot be rendered in the default (GPU-less) run, but the rules
it must obey can be read from its source: no user-visible strings (``pylupdate6``
does not extract ``qsTr``, so text in QML would never be translated — §8.3), the
part components the Python side asks for exist, the look it starts with is
``NEUTRAL_DAY``, every shader it names ships beside it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from open_garden_planner.core.scene3d import MATERIAL_KINDS
from open_garden_planner.ui.view3d.quick3d.look import NEUTRAL_DAY
from open_garden_planner.ui.view3d.quick3d.materials import PART_COMPONENTS

QML_DIR = (Path(__file__).resolve().parents[2] / "src" / "open_garden_planner" / "ui" / "view3d"
           / "quick3d" / "qml")
SCENE = QML_DIR / "Garden.qml"

# Visual text items and controls: none belongs in the 3D scene file.
TEXT_TYPES = ("Text", "Label", "TextInput", "TextEdit", "TextField", "TextArea", "Button",
              "ToolTip", "MenuItem", "Action", "Dialog")
TRANSLATION_CALLS = ("qsTr", "qsTranslate", "qsTrId", "QT_TR_NOOP", "QT_TRANSLATE_NOOP",
                     "QT_TRID_NOOP")
TEXT_PROPERTIES = ("text", "title", "placeholderText", "toolTip", "description", "label")
# What a string literal in the scene file may be: a colour, a shader file, a built-in
# primitive (#Rectangle), or a bare key. Anything with a space or punctuation is prose.
ALLOWED_LITERAL = re.compile(
    r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?|[\w.-]+\.(?:frag|vert)|#[A-Za-z]+|[A-Za-z_][A-Za-z0-9_]*|")


def strip_comments(text: str) -> str:
    """QML without ``//`` and ``/* */`` comments; string literals are kept intact."""
    out: list[str] = []
    index, length = 0, len(text)
    while index < length:
        char = text[index]
        if char in "\"'":
            end = index + 1
            while end < length and text[end] != char:
                end += 2 if text[end] == "\\" else 1
            out.append(text[index:end + 1])
            index = end + 1
        elif text.startswith("//", index):
            index = text.find("\n", index) if "\n" in text[index:] else length
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = length if end < 0 else end + 2
        else:
            out.append(char)
            index += 1
    return "".join(out)


def string_literals(code: str) -> list[str]:
    return [match.group(2) for match in re.finditer(r"""(["'])((?:\\.|(?!\1).)*)\1""", code)]


def user_visible_strings(text: str) -> list[str]:
    """Everything in a QML source that could put text in front of a user."""
    code = strip_comments(text)
    problems: list[str] = []
    for name in TEXT_TYPES:
        if re.search(rf"(?<![\w.]){name}\s*\{{", code):
            problems.append(f"a {name} element")
    for name in TRANSLATION_CALLS:
        if re.search(rf"\b{name}\s*\(", code):
            problems.append(f"a {name}() call")
    for name in TEXT_PROPERTIES:
        if re.search(rf"(?<![\w.]){name}\s*:", code):
            problems.append(f"a `{name}:` property")
    problems.extend(f"the string literal {literal!r}" for literal in string_literals(code)
                    if not ALLOWED_LITERAL.fullmatch(literal))
    return problems


def test_there_is_qml_to_scan() -> None:
    assert [path.name for path in sorted(QML_DIR.glob("*.qml"))] == ["Garden.qml"]


@pytest.mark.parametrize("path", sorted(QML_DIR.glob("*.qml")), ids=lambda p: p.name)
def test_qml_carries_no_user_visible_strings(path: Path) -> None:
    """G3. Any text the 3D view needs is a QWidget overlay with ``self.tr()``."""
    assert user_visible_strings(path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(("snippet", "found"), [
    ('Text { text: "Hello" }', "a Text element"),
    ('Label {\n  color: "#ffffff"\n}', "a Label element"),
    ('Window { title: "Garden" }', "a `title:` property"),
    ('property string caption: qsTr("Sun")', "a qsTr() call"),
    ('property string caption: "Two words"', "the string literal 'Two words'"),
    ('property string caption: "Sun!"', "the string literal 'Sun!'"),
    ("property string caption: 'single quoted prose'", "the string literal 'single quoted prose'"),
])
def test_the_scanner_finds_text(snippet: str, found: str) -> None:
    assert found in user_visible_strings(snippet)


@pytest.mark.parametrize("snippet", [
    'property color sky: "#cfe2f2"',
    'fragmentShader: "water.frag"',
    'source: "#Rectangle"',
    'return {"hit": false, "id": r.objectHit.itemId || ""}',
    '// a comment may say "anything at all", with spaces\nproperty real x: 1',
    '/* Text { text: "commented out" } */ property real x: 1',
    "property bool textured: false",  # `text` inside a longer name is not the property
])
def test_the_scanner_accepts_what_is_not_text(snippet: str) -> None:
    assert user_visible_strings(snippet) == []


def _scene() -> str:
    return strip_comments(SCENE.read_text(encoding="utf-8"))


def test_every_material_kind_has_its_part_component() -> None:
    """Python asks ``createPart(kind, …)``; the QML table and ``materials.PART_COMPONENTS``
    must name the same kinds and the same components — and each component must exist."""
    code = _scene()
    table = re.search(r"partComponents\s*:\s*\(\{(.*?)\}\)", code, re.DOTALL)
    assert table is not None
    entries = dict(re.findall(r'"(\w+)"\s*:\s*(\w+)', table.group(1)))
    assert entries == dict(PART_COMPONENTS)
    assert set(entries) == MATERIAL_KINDS
    for component in entries.values():
        assert re.search(rf"Component\s*\{{\s*id:\s*{component}\b", code), component


def test_every_part_component_is_a_pickable_model_with_the_tint_properties() -> None:
    code = _scene()
    blocks = re.split(r"Component\s*\{\s*id:\s*", code)[1:]
    assert len(blocks) == len(PART_COMPONENTS)
    for block in blocks:
        name = block.split()[0]
        for needed in ("property string itemId", "property int partIndex", "property string kind",
                       "property color tint", "property vector3d tintLinear", "pickable: true",
                       "receivesShadows: true", "property bool retired: false"):
            assert needed in block, (name, needed)
    # a custom shader takes the LINEAR tint as a uniform — read from the scene, which
    # is the one place that says which kinds have a shader of their own
    custom = {block.split()[0] for block in blocks if "CustomMaterial" in block}
    assert custom == {PART_COMPONENTS[kind] for kind in ("water", "foliage", "grass")}
    for block in blocks:
        if "CustomMaterial" in block:
            assert "property vector3d uTint: tintLinear" in block, block.split()[0]


def test_a_destroyed_model_is_retired_not_merely_hidden() -> None:
    """Review P2-10: ``listParts()`` used to skip every INVISIBLE Model, so "destroyed"
    and "hidden on purpose" were one thing. Destruction has its own flag; ``visible``
    is reported, and stays free for a story that hides a Model."""
    code = _scene()
    destroy = code[code.index("function destroyPart"):code.index("function listParts")]
    assert destroy.index("part.retired = true") < destroy.index("part.visible = false")
    listing = code[code.index("function listParts"):code.index("function projectToView")]
    assert "if (p.retired)" in listing and "continue" in listing
    assert '"visible": p.visible' in listing
    assert "p.visible)" not in listing and "!p.visible" not in listing, "visibility must not filter"


@pytest.mark.parametrize("shader", ["foliage.vert", "grass.vert"])
def test_the_wind_shaders_move_nothing_at_rest(shader: str) -> None:
    """Review P2-11, read from the source (the render tier measures it in pixels): every
    displacement is multiplied by ``rest``, which is exactly 0 while the scene's clock
    stands at 0 — and the clock's default IS 0."""
    source = (QML_DIR / shader).read_text(encoding="utf-8")
    assert "float rest = smoothstep(0.0, 2.0, uTime);" in source
    moves = [line.strip() for line in source.splitlines() if re.match(r"\s*VERTEX\.\w\s*\+=", line)]
    assert len(moves) == 2, moves
    assert all(line.endswith("* rest;") for line in moves), moves
    assert re.search(r"property real windTime:\s*0\s*$", _scene(), re.MULTILINE)


def test_shaders_named_by_the_scene_ship_beside_it_and_none_is_orphaned() -> None:
    """A shader the scene names but the bundle lacks only fails when a Model uses it —
    in front of a user. The data loop of ``installer/ogp.spec`` ships this directory."""
    named = set(re.findall(r'(?:vertexShader|fragmentShader):\s*"([^"]+)"', _scene()))
    shipped = {path.name for path in QML_DIR.iterdir() if path.suffix in (".frag", ".vert")}
    assert named == shipped == {"foliage.vert", "foliage.frag", "grass.vert", "water.frag"}
    assert {path.name for path in QML_DIR.iterdir()} == shipped | {"Garden.qml"}


def test_every_custom_shader_multiplies_with_the_tint() -> None:
    for name in ("foliage.frag", "water.frag"):
        source = (QML_DIR / name).read_text(encoding="utf-8")
        assert re.search(r"BASE_COLOR\s*=\s*vec4\([\w.]+\s*\*\s*uTint\s*,", source), name


def test_the_scene_starts_with_the_neutral_day_look() -> None:
    """The QML's defaults are what a host shows before ``set_look`` — they must BE the
    one look L1.2 has, not a second set of numbers."""
    code = _scene()

    def default(name: str) -> str:
        match = re.search(rf"property (?:color|real) {name}:\s*([^\n]+)", code)
        assert match is not None, name
        return match.group(1).strip().strip('"')

    assert default("sunColor") == NEUTRAL_DAY.sun_color
    assert float(default("sunBrightness")) == NEUTRAL_DAY.sun_brightness
    assert default("fillColor") == NEUTRAL_DAY.fill_color
    assert float(default("exposure")) == NEUTRAL_DAY.exposure
    assert default("skyColor") == NEUTRAL_DAY.sky_color
    assert default("meadowColor") == NEUTRAL_DAY.meadow_albedo
    assert float(default("windStrength")) == NEUTRAL_DAY.wind_strength


def test_the_scene_obeys_the_measured_engine_rules() -> None:
    """Traps the L0 spike paid for (``ogp-3d-renderer`` §2, §4, §11), read from the source."""
    code = _scene()
    assert "Repeater3D" not in code, "per-item Models, never a Repeater3D over a JS array"
    light = code[code.index("DirectionalLight {"):]
    assert re.search(r"\bcastsShadow: true", light)            # Lights: castsShadow …
    assert not re.search(r"\bcastsShadow:", code[:code.index("DirectionalLight {")])
    assert "castsShadows: false" in code and "lookAt" in code  # … Models: castsShadows
    assert "rotation: root.sunRotation" in code, "the sun is oriented by a quaternion from Python"
    assert not re.search(r"sharpnessAmount:\s*0\.0*[1-9]", code), "no sharpening (spike: speckles)"
    assert "function destroyPart" in code and "part.geometry = null" in code
