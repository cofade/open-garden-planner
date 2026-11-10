"""The engine package's QML, read as text (Phase 17 L1.2, #385 — gate G3).

``Garden.qml`` cannot be rendered in the default (GPU-less) run, but the rules
it must obey can be read from its source: no user-visible strings (``pylupdate6``
does not extract ``qsTr``, so text in QML would never be translated — §8.3), the
part components the Python side asks for exist, the look it starts with is
``NEUTRAL_DAY``, every shader it names ships beside it.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from open_garden_planner.core.scene3d import MATERIAL_KINDS
from open_garden_planner.ui.view3d.quick3d.look import (
    COLOR_PROPERTIES,
    LINEAR_COLOR_PROPERTIES,
    NEUTRAL_DAY,
    VECTOR_PROPERTIES,
    scene_properties,
)
from open_garden_planner.ui.view3d.quick3d.materials import (
    PART_COMPONENTS,
    TWO_SIDED_KINDS,
    two_sided_kinds,
)

#: What the L0 spike measured, frozen when L1.10 deleted it (its provenance field says how).
SPIKE = json.loads((Path(__file__).resolve().parents[1] / "data" / "l0_spike_reference.json")
                   .read_text(encoding="utf-8"))

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
    # Garden.qml, since L7 (#391) the atmosphere sky it creates, and photo mode's blur (#743)
    assert [path.name for path in sorted(QML_DIR.glob("*.qml"))] == [
        "AtmosphereSky.qml", "Garden.qml", "PhotoBlur.qml"]


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
    blocks = [block for block in re.split(r"Component\s*\{\s*id:\s*", code)[1:]
              if block.split()[0].endswith("Part")]   # the others build the sky (L1.4) or a ground tile (L1.5)
    assert len(blocks) == len(PART_COMPONENTS)
    for block in blocks:
        name = block.split()[0]
        for needed in ("property string itemId", "property int partIndex", "property string kind",
                       "property color tint", "property vector3d tintLinear",
                       "receivesShadows: true", "property bool retired: false",
                       # L2.4 (X-ray): pickable unless it fades as an occluder of the selection
                       "property real fade: 1.0", "pickable: fade >= 1.0"):
            assert needed in block, (name, needed)
    # a custom shader takes the LINEAR tint as a uniform — read from the scene, which
    # is the one place that says which kinds have a shader of their own
    custom = {block.split()[0] for block in blocks if "CustomMaterial" in block}
    # vc and roof carry a custom screen door beside their principled look (L2.4)
    assert custom == {PART_COMPONENTS[kind] for kind in ("water", "foliage", "grass", "vc", "roof")}
    for block in blocks:
        if "CustomMaterial" in block:
            assert re.search(r"property vector3d uTint: (?:tintLinear|Qt.vector3d\(tintLinear.x \* seasonTint.x, tintLinear.y \* seasonTint.y, tintLinear.z \* seasonTint.z\))", block), block.split()[0]


def test_the_two_sided_kinds_are_the_components_that_never_cull() -> None:
    """``materials.TWO_SIDED_KINDS`` is what the selection oracle keeps from behind on
    Qt 6.12 (its pick honours the cull mode). A component counts as two-sided when
    every cull mode in it is ``NoCulling``; vc's is conditional (a Cutaway shows the
    walls' inner faces), so with the roofs on it culls."""
    code = _scene()
    blocks = {block.split()[0]: block for block in re.split(r"Component\s*\{\s*id:\s*", code)[1:]
              if block.split()[0].endswith("Part")}
    two_sided = set()
    for kind, component in PART_COMPONENTS.items():
        modes = re.findall(r"cullMode:\s*([^\n]+)", blocks[component])
        if modes and all(mode.strip() == "Material.NoCulling" for mode in modes):
            two_sided.add(kind)
    assert two_sided == TWO_SIDED_KINDS
    assert two_sided_kinds(cutaway=False) == TWO_SIDED_KINDS
    assert two_sided_kinds(cutaway=True) == TWO_SIDED_KINDS | {"vc"}


def test_a_faded_or_cut_part_is_a_screen_door_not_a_blend() -> None:
    """L2.4, 3D review of #386: a blended or hidden part drops out of the shadow map —
    Cutaway took the house's shadow off the lawn and X-ray a faded tree's. So no part
    material blends for a fade (glass alone blends, as it always did) and no roof hides:
    a faded part DISCARDS pixels (a screen door, still opaque), a cut roof discards all
    of them, and both keep casting their shadows. The principled look stays the material
    while nothing fades, so the L1 frames do not change."""
    code = _scene()
    blocks = {block.split()[0]: block for block in re.split(r"Component\s*\{\s*id:\s*", code)[1:]
              if block.split()[0].endswith("Part")}
    for name, block in blocks.items():
        if name == "glassPart":
            continue
        assert "sourceBlend" not in block and "opacity: fade" not in block, name
        assert "visible:" not in block, name     # nothing hides a part to cut or fade it
    # #801: a detail picture first (its shader carries the snow); #800: a plant's wood sways
    # while the wind blows; #687: snow swaps in only where no screen door is drawn
    # (test_snow_lies_on_the_built_tops...)
    assert ("materials: fade < 1.0 ? [vcScreen] : detailMap ? [vcDetail] : swayFrame.x > 0.0 "
            "&& root.windBlowing ? [vcSway] : root.builtSnow > 0.0 && partName !== \"floor\" "
            "? [vcSnow] : [vcLook]") in " ".join(blocks["vcPart"].split())
    for name, door in (("waterPart", "waterDoor"), ("foliagePart", "foliageDoor"),
                       ("grassPart", "grassDoor")):
        assert f"materials: fade < 1.0 ? [{door}] : [" in blocks[name], name
    # every screen door collapses in the depth pass (ambient occlusion's depth texture
    # does not run the discard: a cut roof left a ghost — 3D review round 2)
    assert blocks["vcPart"].count('vertexShader: "screen.vert"') == 1
    assert blocks["roofPart"].count('vertexShader: "screen.vert"') == 1
    assert blocks["waterPart"].count('vertexShader: "screen.vert"') == 1
    assert 'vertexShader: "foliage_door.vert"' in blocks["foliagePart"]
    assert 'vertexShader: "grass_door.vert"' in blocks["grassPart"]
    for name in ("screen.vert", "foliage_door.vert", "grass_door.vert"):
        source = (QML_DIR / name).read_text(encoding="utf-8")
        assert "#if QSSG_ENABLE_DEPTH_PASS" in source and "if (uOpacity < 1.0)" in source, name
    assert ("materials: root.roofsHidden || fade < 1.0 ? [roofScreen] : detailMap ? [roofDetail] "
            ": root.builtSnow > 0.0 ? [roofSnow] : [roofLook]") in " ".join(blocks["roofPart"].split())
    assert "property real uOpacity: root.roofsHidden ? 0.0 : fade" in blocks["roofPart"]
    assert "pickable: fade >= 1.0 && !root.roofsHidden" in blocks["roofPart"]
    # the roofless house reads as a room: its walls drop back-face culling (the look, the
    # door, the detail material of #801, the snowy look of #687 and a plant's swaying wood
    # of #800, as its look)
    assert blocks["vcPart"].count("cullMode: root.roofsHidden ? Material.NoCulling") == 5
    for name in ("screen.frag", "foliage_door.frag", "water_door.frag"):
        source = (QML_DIR / name).read_text(encoding="utf-8")
        assert "screenDoor(FRAGCOORD.xy) >= uOpacity" in source and "discard;" in source, name
        assert "BASE_COLOR = vec4(" in source and ", 1.0);" in source, name   # never translucent
    # the LOOK shaders carry no discard: nothing changes while no part fades (a discard
    # costs early depth testing on the heaviest fragment load - senior review round 2)
    for name in ("foliage.frag", "water.frag"):
        assert "discard" not in (QML_DIR / name).read_text(encoding="utf-8"), name


@pytest.mark.parametrize("look", ["foliage.frag", "water.frag"])
def test_a_door_shader_is_its_look_shader_with_the_screen_door_added(look: str) -> None:
    """Drift guard: ``*_door.frag`` is a COPY of its look shader plus the screen-door
    block and the discard — a fix to the look that misses its door shows here."""
    source = (QML_DIR / look).read_text(encoding="utf-8")
    door = (QML_DIR / look.replace(".frag", "_door.frag")).read_text(encoding="utf-8")
    start = door.index("// The screen door of a faded part")
    end = door.index("void MAIN()")
    stripped = door[:start] + door[end:]
    stripped = stripped.replace(
        "    if (screenDoor(FRAGCOORD.xy) >= uOpacity)\n        discard;\n", "", 1)
    assert stripped == source


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


@pytest.mark.parametrize("shader", ["foliage.vert", "grass.vert", "plant_sway.vert"])
def test_the_wind_shaders_move_nothing_at_rest(shader: str) -> None:
    """Review P2-11, read from the source (the render tier measures it in pixels): every
    displacement is multiplied by ``rest``, which is exactly 0 while the scene's clock
    stands at 0 — and the clock's default IS 0. The lawn's blades move by two lines; a
    plant (#800) by one, the whole ``plantSway`` (test_scene3d_wind.py pins its text)."""
    source = (QML_DIR / shader).read_text(encoding="utf-8")
    assert "float rest = smoothstep(0.0, 2.0, uTime);" in source
    moves = [line.strip() for line in source.splitlines() if re.match(r"\s*VERTEX(\.\w)?\s*\+=", line)]
    assert len(moves) == (2 if shader == "grass.vert" else 1), moves
    assert all(line.endswith("* rest;") for line in moves), moves
    assert re.search(r"property real windTime:\s*0\s*$", _scene(), re.MULTILINE)



def _overlay_block(code: str, model_id: str) -> str:
    start = code.index(f"id: {model_id}")
    return code[start:code.index("Model {", start) if "Model {" in code[start:] else len(code)]


def test_the_overlays_blend_as_their_layer_says() -> None:
    """3D review of #386 (PF-L3D-06): the 2D shadows MULTIPLY the frame (darker in every
    mood — blended over, the unlit shadow colour went through night's exposure and
    brightened the night garden); the hours-of-sun map blends over it keeping the
    frame's alpha; the lines are opaque. Every overlay but the shade divides its colour
    by the exposure, so it reads the same from noon to night."""
    code = _scene()
    shade, drape, lines = (_overlay_block(code, name) for name in
                           ("shadeOverlay", "drapeOverlay", "linesOverlay"))
    assert "sourceBlend: CustomMaterial.DstColor" in shade
    assert "destinationBlend: CustomMaterial.Zero" in shade
    assert "property real uExposure: 1.0" in shade
    assert "sourceBlend: CustomMaterial.SrcAlpha" in drape
    assert "destinationBlend: CustomMaterial.OneMinusSrcAlpha" in drape
    assert "sourceBlend: CustomMaterial.SrcAlpha" in lines
    assert "destinationBlend: CustomMaterial.OneMinusSrcAlpha" in lines
    for block in (shade, drape, lines):
        assert "sourceAlphaBlend: CustomMaterial.Zero" in block        # the frame's alpha stays
        assert "destinationAlphaBlend: CustomMaterial.One" in block
    for block in (shade, drape):
        assert "depthDrawMode: Material.NeverDepthDraw" in block
    for block in (drape, lines):
        assert "property real uExposure: root.topDown ? 1.0 : root.exposure" in block
    overlay = (QML_DIR / "overlay.frag").read_text(encoding="utf-8")
    assert "FRAGCOLOR = vec4(vColor.rgb / uExposure, vColor.a);" in overlay

def test_shaders_named_by_the_scene_ship_beside_it_and_none_is_orphaned() -> None:
    """A shader the scene names but the bundle lacks only fails when a Model uses it —
    in front of a user. The data loop of ``installer/ogp.spec`` ships this directory."""
    sky = strip_comments((QML_DIR / "AtmosphereSky.qml").read_text(encoding="utf-8"))
    blur = strip_comments((QML_DIR / "PhotoBlur.qml").read_text(encoding="utf-8"))
    named = set(re.findall(r'"([^"\n]+\.(?:vert|frag))"', _scene() + sky + blur))
    shipped = {path.name for path in QML_DIR.iterdir() if path.suffix in (".frag", ".vert")}
    assert named == shipped == {"foliage.vert", "foliage.frag", "grass.vert", "water.frag",
                                # the atmosphere sky's: L7 (#391; its two look-up
                                # tables are computed on the CPU, atmosphere_lut.py)
                                "atmosphere.frag",
                                "ring.vert", "ring.frag",           # the selection ring: L1.8
                                "overlay.vert", "overlay.frag",     # the analysis overlays: L2
                                "screen.frag", "screen.vert",       # X-ray and Cutaway: L2.4
                                "foliage_door.frag", "water_door.frag",
                                "foliage_door.vert", "grass_door.vert",
                                "ground.frag", "lawn.frag",         # detail normals and lawn lighting
                                "precipitation.vert", "precipitation.frag",   # rain, snow: L5
                                "ambient.vert", "ambient.frag",     # leaves, butterflies, fireflies, bulbs
                                # photo mode's depth of field (#743)
                                "photoblur_layer.frag", "photoblur_rows.frag",
                                "photoblur_compose.frag",
                                # a built surface's detail picture: roof tiles, wall courses (#801)
                                "built_detail.vert", "built_detail.frag",
                                "built_snow.frag", "built_snow.vert",   # snow on built tops (#687)
                                "plant_sway.vert"}   # a plant's wood and fruit in the wind (#800)
    # L7 (#391): the atmosphere sky came from Qt with its provenance and licence texts
    assert {path.name for path in QML_DIR.iterdir()} == shipped | {
        "Garden.qml", "AtmosphereSky.qml", "PhotoBlur.qml", "PROVENANCE.md",
        "LICENSE-qt-skymaterial.txt"}


def test_the_ground_detail_shader_flips_v_itself() -> None:
    """PF-L3D-11: a ``TextureInput`` ignores its ``Texture``'s ``flipV`` (measured, L4.5,
    #388) — ``ground.frag`` samples the north-up tile at ``1 - v`` itself, and every
    sample it takes goes through that flipped coordinate."""
    code = "\n".join(line.split("//")[0] for line in
                     (QML_DIR / "ground.frag").read_text(encoding="utf-8").splitlines())
    assert re.search(r"\buv\s*=\s*vec2\(\s*UV0\.x\s*,\s*1\.0\s*-\s*UV0\.y\s*\)", code)
    samples = re.findall(r"texture\(\s*uBaseMap\s*,\s*([^;]*?)\)\s*\.rgb", code)
    assert len(samples) == 5 and all(sample.startswith("uv") for sample in samples), samples


def test_the_scene_uses_no_order_independent_transparency() -> None:
    """PF-L3D-12: weighted-blended OIT re-blends L2's multiply drapes (measured: pixels
    under a shadow drape up to 243 levels lighter). Glass stays the sorted material."""
    assert "oitMethod" not in strip_comments(_scene())


def test_every_custom_shader_multiplies_with_the_tint() -> None:
    """The albedo of every custom kind is its vertex colour times the part's tint.

    Water also takes the plan's own picture (``uFill``, a raised pool: #627) - its
    flat path must still be the tint, both in the look and in its screen door, and
    the picture must reach ``BASE_COLOR``. A shader string match cannot see a
    constant-UV defect (the picture sampled at one texel looked "fixed" while it
    was not), so the BEHAVIOUR is pinned by the raised-pool render gate; this test
    holds the albedo's shape, anchored at the assignment, not a loose search."""
    foliage = strip_comments((QML_DIR / "foliage.frag").read_text(encoding="utf-8"))
    assert re.search(r"BASE_COLOR = vec4\(vColor\.rgb \* uTint, 1\.0\);", foliage)
    for name in ("water.frag", "water_door.frag"):
        source = strip_comments((QML_DIR / name).read_text(encoding="utf-8"))
        assert re.search(r"vec3 base = VAR_COLOR\.rgb \* uTint;", source), name
        assert re.search(r"BASE_COLOR = vec4\(base, 1\.0\);", source), name
        assert re.search(r"if \(uHasFill > 0\.5\)\s*\{[^}]*texture\(uFill, UV0\)", source), name
        # the flat tint is the value the picture overrides, never the reverse
        assert source.index("vec3 base = VAR_COLOR.rgb * uTint;") < source.index(
            "if (uHasFill > 0.5)")


#: Root properties of the look block that are STATE of the wind's clock, not look.
WIND_STATE = {"windTime", "windRunning"}


def _look_block() -> dict[str, tuple[str, str]]:
    """The scene file's look properties: name -> (QML type, default as written)."""
    code = SCENE.read_text(encoding="utf-8")
    block = code[code.index("// ---- look"):code.index("// ---- key light")]
    found = re.findall(r"^\s*property (\w+) (\w+):\s*(Qt\.vector3d\([^)]*\)|[^\s/]+)",
                       strip_comments(block), re.MULTILINE)
    return {name: (kind, default.strip('"')) for kind, name, default in found}


def test_the_look_properties_are_exactly_the_mapping_and_start_as_the_neutral_day() -> None:
    """The QML's defaults are what a host shows before ``set_look`` — they must BE
    ``NEUTRAL_DAY`` through the mapping, not a second set of numbers; and the scene
    declares exactly the properties the mapping writes (a look property nobody sets,
    or one the scene does not have, fails here and not in front of a GPU)."""
    declared = _look_block()
    mapped = scene_properties(NEUTRAL_DAY)
    assert set(declared) - WIND_STATE == set(mapped)
    assert set(declared) >= WIND_STATE
    for name, value in mapped.items():
        kind, default = declared[name]
        if name in COLOR_PROPERTIES:
            assert (kind, default) == ("color", value), name
        elif name in LINEAR_COLOR_PROPERTIES:  # the engine-space colour, to 8 bits
            written = "#" + "".join(f"{round(channel * 255):02x}" for channel in value)
            assert (kind, default) == ("color", written), name
        elif isinstance(value, bool):
            assert (kind, default) == ("bool", "true" if value else "false"), name
        elif isinstance(value, int):
            assert kind == "int" and int(default) == value, name
        elif isinstance(value, float):
            assert kind == "real" and float(default) == value, name
        elif name in VECTOR_PROPERTIES:  # L5: a vector3d, written as Qt.vector3d(x, y, z)
            written = tuple(float(v) for v in default[len("Qt.vector3d("):-1].split(","))
            assert kind == "vector3d" and written == pytest.approx(value), name
        else:
            assert (kind, default) == ("string", value), name
    assert declared["windTime"] == ("real", "0") and declared["windRunning"] == ("bool", "false")


def test_every_key_the_look_can_hold_is_one_the_scene_understands() -> None:
    """The scene turns four string properties into engine enums; a value it does not
    name falls through to a default silently. Every value a ``PresetSpec`` may hold
    must appear in the binding that reads it."""
    code = _scene()
    for prop, values in (("shadowMapQuality", ("high", "ultra")),          # very_high: the else
                         ("softShadows", ("pcf4", "pcf8", "pcf32")),       # pcf16: the else
                         ("antialiasing", ("msaa", "fxaa")),
                         ("antialiasingQuality", ("very_high", "medium"))):  # high: the else
        for value in values:
            assert f'root.{prop} === "{value}"' in code, (prop, value)
    from open_garden_planner.core.scene3d.look import PRESET_SPECS

    assert {spec.shadow_map_quality for spec in PRESET_SPECS.values()} == {"very_high", "ultra"}
    assert {spec.antialiasing for spec in PRESET_SPECS.values()} == {"msaa"}
    assert {spec.soft_shadows for spec in PRESET_SPECS.values()} == {"pcf4", "pcf8", "pcf16", "pcf32"}


def test_the_look_rules_the_spike_paid_for() -> None:
    """``ogp-lush-cinematic`` §2 and ``ogp-3d-renderer`` §4, read from the source."""
    code = _scene()
    assert re.search(r"sharpnessAmount:\s*0\.0\s", code), "no sharpening, at any preset"
    assert re.search(r"ssgiEnabled:\s*false\s", code), "SSGI: no preset turns it on"
    fog = code[code.index("fog: Fog {"):]
    fog = fog[:fog.index("}")]
    assert "enabled: !root.topDown && root.fog" in fog and "color: root.fogColor" in fog
    # the truth view: no sky, no fog, no post effect, no tone mapping, always multisampled
    for effect in ("aoEnabled", "glowEnabled", "fxaaEnabled", "ssrEnabled", "ditheringEnabled",
                   "colorAdjustmentsEnabled", "specularAAEnabled"):
        assert re.search(rf"{effect}:\s*!root\.topDown", code), effect
    # a sky (painted, or L7's atmosphere) backs and lights the PERSPECTIVE view only
    assert "readonly property bool paintedShown: skyTexture !== null && !root.topDown" in code
    assert ("readonly property bool atmosphereShown: atmosphereOn && atmosphere !== null "
            "&& !root.topDown") in code
    assert "readonly property bool skyShown: paintedShown || atmosphereShown" in code
    assert "lightProbe: view.paintedShown ? view.skyTexture : null" in code
    assert "skyMaterial: view.atmosphereShown ? view.atmosphere : null" in code
    assert "root.topDown ? SceneEnvironment.TonemapModeNone" in code
    assert "csmNumSplits: root.topDown ? 0 : root.shadowCascades" in code
    assert '(root.topDown || root.antialiasing === "msaa")' in code
    # reflections, blur and glow in one chain took Qt's render thread down on Ultra (PF-E3D-21):
    # with glow on, two effects ahead of Qt's own scene effect break the chain (#744)
    assert re.search(r"ssrEnabled:\s*!root\.topDown\s*&&\s*root\.reflections\s*&&\s*"
                     r"!root\.depthOfFieldActive", code), "reflections stand down under blur"
    assert "readonly property bool depthOfFieldActive: !root.topDown && root.photoBlur > 0" in code
    # photo mode's blur is the app's own (#743), in the chain only while it is drawn; Qt's
    # half-resolution depth of field is never switched on
    assert "effects: root.depthOfFieldActive ? [photoBlur] : []" in code
    assert "depthOfField" not in code.replace("depthOfFieldActive", ""), "Qt's blur is not used"
    # with a sky the sky is the fill (and in twilight the look's twilight fill, #802: an
    # ambient lights the garden, never the skybox); without one, the look's flat fill
    assert "ambientColor: view.skyShown ? root.twilightFill : root.fillColor" in code


def test_the_sky_is_built_on_request_and_never_bound_live() -> None:
    """The generator recomputes the whole sky on the GUI thread for every input change,
    and the environment filters its probe once per Texture object: so the scene
    declares NO sky — it builds one when the host asks, as a fresh Texture whose data
    object is its own child, quality raised last, and only ever destroys the Texture."""
    code = _scene()
    assert code.count("ProceduralSkyTextureData {") == 1, "one declaration: inside the Component"
    data = code[code.index("id: skyDataComponent"):]
    data = data[:data.index("}") + 1]
    assert "root." not in data and "SkyTextureQualityLow" in data, "no live binding; born cheap"
    assert "property var skyTexture: null" in code, "no sky before the first sun is known"
    build = code[code.index("function buildSky"):code.index("function buildAtmosphere")]
    order = [build.index(step) for step in (
        "skyTextureComponent.createObject(view.scene)", "skyDataComponent.createObject(texture)",
        "data[key] = inputs[key]", "data.textureQuality = ProceduralSkyTextureData.SkyTextureQualityMedium",
        "texture.textureData = data", "view.skyTexture = texture", "old.destroy()")]
    assert order == sorted(order), "inputs first, quality last, the new sky shown before the old goes"
    assert "data.destroy()" not in code and ".textureData = null" not in code
    assert build.count(".destroy()") == 1


def test_the_atmosphere_is_made_once_and_never_destroyed_nor_re_pointed() -> None:
    """L7 (#391): ONE AtmosphereSky, made with the cloud volume's ONE Texture at the
    first build and from then on only written — a SkyMaterial re-renders by itself, and
    a data object attached to a second Texture draws white (``ogp-3d-renderer`` §2). A
    painted sky (or none) only switches it off; the atmosphere leaves the painted sky in
    place — its texture is the light probe under both models (PF-E3D-17)."""
    code = _scene()
    build = code[code.index("function buildAtmosphere"):code.index("function dropSky")]
    assert build.count("createObject") == 3 and "if (!sky) {" in build, "made once"
    assert "cloudVolumeComponent.createObject(view.scene, {\"textureData\": volumeData})" in build
    assert "skyViewComponent.createObject(view.scene, {\"textureData\": skyViewData})" in build
    assert "atmosphereComponent.createObject(view.scene, {\"noiseVolume\": volume," in build
    assert "\"skytextureBuffer\": skyView})" in build
    assert "sky[key] = inputs[key]" in build and "view.atmosphereOn = true" in build
    assert "view.skyTexture" not in build, "the painted sky stays: it is the light probe"
    assert ".destroy()" not in build, "the atmosphere destroys nothing"
    assert "atmosphere.destroy" not in code and "volume.destroy" not in code
    assert code.count("AtmosphereSky {") == 1, "one declaration: inside its Component"
    for function in ("function buildSky", "function dropSky"):
        body = code[code.index(function):]
        body = body[:body.index("return")]
        assert "view.atmosphereOn = false" in body, function
    background = re.search(r"backgroundMode:([^\n]*\n[^\n]*)", code)
    assert background is not None and " ".join(background.group(1).split()) == (
        "view.atmosphereShown ? SceneEnvironment.SkyMaterial : view.paintedShown ? "
        "SceneEnvironment.SkyBox : SceneEnvironment.Color")
    volume = code[code.index("id: cloudVolumeComponent"):]
    volume = volume[:volume.index("}") + 1]
    for axis in ("Horizontal", "Vertical", "Depth"):
        assert f"tilingMode{axis}: Texture.Repeat" in volume, "the volume tiles in 3D"


def test_the_light_probe_is_put_back_when_an_earlier_sky_is_destroyed() -> None:
    """Qt 6.12 (PF-E3D-16): destroying an EARLIER sky Texture fires its stale
    destroyed-watcher and sets the environment's light probe to null although the probe
    is the current sky - the painted sky drew the clear colour after the first sun change.
    The environment restores the SAME binding in the change signal, before a frame can
    render. The render tier's sky-sequence test is the engine half of this pin."""
    code = (QML_DIR / "Garden.qml").read_text(encoding="utf-8")
    wanted = "view.paintedShown ? view.skyTexture : null"
    assert f"lightProbe: {wanted}\n" in code
    handler = code[code.index("onLightProbeChanged: {"):]
    handler = handler[:handler.index("\n            }\n")]
    assert f"if (lightProbe !== ({wanted}))" in handler
    assert f"lightProbe = Qt.binding(function() {{ return {wanted} }})" in handler


def test_the_atmosphere_never_builds_the_cube_that_crashed_qt_6_12_0() -> None:
    """PF-E3D-17 (#391, owner's manual test): Qt 6.12.0's SkyMaterial pre-filters its
    light cube with a freed QRhi resource — an access violation in Qt6Gui
    (``sanityCheckResourceOwnership``) under ``QSSGRenderSkyMaterialManager::
    runPrefilterCycle``. Qt builds that cube only for image-based light, the Cubemap
    skybox mode, reflection probes or a screen texture (``resolveLayerIblTexture``), so
    the atmosphere asks for none of them and the painted sky's texture lights the
    garden under both models."""
    sky = (QML_DIR / "AtmosphereSky.qml").read_text(encoding="utf-8")
    assert re.search(r"^\s*enableIBL:\s*false\s*$", sky, re.MULTILINE), "no light from the atmosphere"
    mode = re.search(r"^\s*skyboxMode:\s*SkyMaterial\.(\w+)\s*$", sky, re.MULTILINE)
    assert mode is not None and mode.group(1).startswith("ScreenSpace"), "drawn on screen, no cube"
    for cube_only in ("iblSampleCount", "iblRenderFrames", "radianceMapSize", "iblSamplesPerFrame"):
        assert cube_only not in sky, f"{cube_only} tunes the cube this sky never builds"
    frag = (QML_DIR / "atmosphere.frag").read_text(encoding="utf-8")
    assert frag.count("FRAGCOLOR = ") == 2 and frag.count("FRAGCOLOR = vec4(skyExposed(") == 2, (
        "Qt's screen path applies no exposure under the post effects: both exits do it "
        "themselves, or the sky reads 1.8x too bright by day and 2.9x at night")
    assert "vec3(1.0) - exp(-radiance * skyExposure)" in frag, "the curve of Qt's qt_exposure"
    code = _scene()
    assert "AtmosphereSky { skyExposure: root.probeExposure }" in code
    assert "lightProbe: view.paintedShown ? view.skyTexture : null" in code, (
        "the painted texture lights, whichever sky backs the view")
    assert "ReflectionProbe" not in code, "a reflection probe would build the cube"
    shaders = " ".join(path.read_text(encoding="utf-8") for path in QML_DIR.glob("*.frag"))
    assert "SCREEN_TEXTURE" not in shaders and "SCREEN_MIP_TEXTURE" not in shaders, (
        "a screen texture would build the cube")
    scenes = " ".join(path.read_text(encoding="utf-8") for path in QML_DIR.glob("*.qml"))
    assert "transmissionFactor" not in scenes, "transmission needs a screen texture too"


def test_the_water_samples_the_sky_under_a_sky_material_too() -> None:
    """3D review of L7: under a ``SkyMaterial`` Qt 6.12 calls ``IBL_PROBE()`` with
    ``QSSG_ENABLE_LIGHT_PROBE`` false, so a pond guarded by that macro alone went black under
    the atmosphere sky. The guard also accepts Qt's probe-sampler include guard."""
    for name in ("water.frag", "water_door.frag"):
        code = (QML_DIR / name).read_text(encoding="utf-8")
        assert "#if QSSG_ENABLE_LIGHT_PROBE || defined(SAMPLE_PROBE_GLSLLIB)" in code, name
        assert "#if QSSG_ENABLE_LIGHT_PROBE\n" not in code, name


def test_the_winds_clock_runs_only_while_it_is_told_to() -> None:
    code = _scene()
    animation = code[code.index("FrameAnimation {"):]
    animation = animation[:animation.index("}") + 1]
    assert "running: root.windRunning" in animation
    assert "root.windTime += frameTime" in animation
    assert "NumberAnimation" not in code and "Timer {" not in code, "nothing else ticks"
    assert re.search(r"property bool windRunning:\s*false\s", code)


def test_the_environments_constants_are_the_spikes() -> None:
    """The numbers that are the same at every preset were measured on the L0 spike's
    boards — its scene file's values, frozen when L1.10 deleted the spike."""
    environment = SPIKE["qml"]["environment"]
    code = _scene()
    for name in ("aoStrength", "aoDistance", "aoSoftness", "glowStrength", "glowIntensity",
                 "glowBloom", "glowHDRMinimumValue", "depthCurve",
                 "density", "skyboxBlurAmount", "csmBlendRatio", "clipNear"):
        ours = re.findall(rf"\b{name}:\s*([\d.]+)", code)
        assert ours and environment[name], name
        assert sorted({float(v) for v in ours}) == environment[name], name
    # what the fog hid until it followed the camera (3D review of L4's second owner pass):
    # the shadow map reaches as far as the fog begins (the spike's far its floor, and the
    # top-down truth view keeps it), the AO fades out from 45 m to 90 m, and the
    # perspective camera's far plane lies past the midpoints of the meadow's edges (the spike's 800 m cut
    # it in view); the top-down camera keeps the spike's far plane
    (shadow_far,) = environment["shadowMapFar"]
    assert f"shadowMapFar: root.topDown ? {shadow_far:g} : root.shadowFar" in code
    # #687: the weather scales the spike's strength and reach and adds a bias (the look's
    # ``ao*`` properties, 1 / 1 / 0 when clear); the capture's scale stays on the reach
    assert ("aoStrength: 55 * root.aoStrengthGain * (!root.topDown && root.ambientOcclusion "
            "? root.aoFade : 0)") in code
    assert "aoDistance: 14 * root.aoDistanceGain * root.captureAoDistanceScale" in code
    assert "aoBias: root.aoBias * root.captureAoDistanceScale" in code, (
        "the weather's bias reaches the pass, a share of the reach at every picture size")
    assert "aoEnabled: !root.topDown && root.ambientOcclusion && root.aoFade > 0" in code
    assert "(9000 - camPos.minus(camTarget).length()) / 4500" in code
    from open_garden_planner.core.scene3d.camera import MAX_DISTANCE_CM
    from open_garden_planner.core.scene3d.meadow import MEADOW_HALF_CM

    clip_far = sorted(float(v) for v in re.findall(r"\bclipFar:\s*([\d.]+)", code))
    assert clip_far[0] == min(environment["clipFar"])  # the top-down camera
    assert clip_far[1] >= math.sqrt(2.0) * MEADOW_HALF_CM + MAX_DISTANCE_CM > max(environment["clipFar"])
    # the fog's distances follow the camera since L4's owner pass (look.fog_depth_cm):
    # the spike's depthNear / depthFar are their floors and the scene's defaults
    from open_garden_planner.core.scene3d import look

    assert "depthNear: root.fogNear" in code and "depthFar: root.fogFar" in code
    for name, floor, default in (("depthNear", look.FOG_NEAR_CM, "fogNear"),
                                 ("depthFar", look.FOG_FAR_CM, "fogFar")):
        declared = re.findall(rf"\bproperty real {default}:\s*([\d.]+)", code)
        assert environment[name] == [floor] == [float(value) for value in declared], name


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


def test_a_fill_part_shows_the_plans_own_picture() -> None:
    """#628 follow-up: a raised object keeps its fill texture.

    The Model carries ``patternMap`` — a shared ``Texture`` the sink sets and clears —
    and its PrincipledMaterial samples it as ``baseColorMap``. The scene makes every
    picture with its data at birth and never re-points a ``Texture`` at another
    ``QQuick3DTextureData`` (that goes white: ``ogp-3d-renderer`` §5).
    """
    code = _scene()
    blocks = {block.split()[0]: block for block in re.split(r"Component\s*\{\s*id:\s*", code)[1:]}
    assert "property var patternMap: null" in blocks["vcPart"]
    assert "baseColorMap: patternMap ? patternMap : null" in blocks["vcPart"]
    assert "flipV: false" in blocks["patternTexture"]
    assert re.search(r"function createPatternTexture\(data\)\s*\{\s*return patternTexture"
                     r"\.createObject\(view\.scene, \{\"textureData\": data\}\)", code)


@pytest.mark.parametrize("look", ["foliage.vert", "grass.vert"])
def test_a_door_vertex_shader_is_its_look_shader_with_the_collapse_added(look: str) -> None:
    """Drift guard: ``*_door.vert`` is a COPY of the wind shader plus a two-line header
    and the depth-pass collapse after POSITION — a fix to the wind that misses its door
    shows here."""
    source = (QML_DIR / look).read_text(encoding="utf-8")
    door = (QML_DIR / look.replace(".vert", "_door.vert")).read_text(encoding="utf-8")
    body = door.split("\n", 2)[2]   # the two header lines
    collapse = ("    // the screen door's depth-pass collapse (screen.vert): no ghost in the AO depth\n"
                "#if QSSG_ENABLE_DEPTH_PASS\n    if (uOpacity < 1.0)\n        POSITION = vec4(0.0);\n"
                "#endif\n")
    assert body.replace(collapse, "", 1) == source


def _shared_blocks(name: str) -> dict[str, str]:
    """The ``// ---- shared with <file> ... ----`` blocks of a photo blur shader, by partner."""
    text = (QML_DIR / name).read_text(encoding="utf-8")
    found = re.findall(r"// ---- shared with (\S+) .*?----\n(.*?)// ---- end of shared ----",
                       text, re.S)
    return dict(found)


def test_the_photo_blurs_shared_shader_code_is_one_text() -> None:
    """#743: an effect shader includes no file of the app's, so the depth, the amount out of
    focus and the Gaussian are copied between the passes. A copy that drifted would weigh a
    layer by another band than the composition reads, or blur the rows unlike the columns."""
    layer, rows, compose = (_shared_blocks(name) for name in (
        "photoblur_layer.frag", "photoblur_rows.frag", "photoblur_compose.frag"))
    assert set(layer) == {"photoblur_compose.frag"} and set(rows) == {"photoblur_compose.frag"}
    assert set(compose) == {"photoblur_layer.frag", "photoblur_rows.frag"}
    assert layer["photoblur_compose.frag"] == compose["photoblur_layer.frag"]
    assert rows["photoblur_compose.frag"] == compose["photoblur_rows.frag"]


def test_the_photo_blur_is_picture_relative_premultiplied_and_reads_every_texel() -> None:
    """#743's defects of Qt's blur, read from the source: the sigma is a share of the picture's
    height (not pixels of a half-resolution copy), a layer is premultiplied by its weight (no
    in-focus colour reaches a blurred average), every buffer is at the picture's own size, and
    the kernel's REACH is capped, never its spacing (wider taps showed as copies)."""
    rows = (QML_DIR / "photoblur_rows.frag").read_text(encoding="utf-8")
    layer = (QML_DIR / "photoblur_layer.frag").read_text(encoding="utf-8")
    compose = (QML_DIR / "photoblur_compose.frag").read_text(encoding="utf-8")
    assert "float sigma = blurShare * sigmaScale * OUTPUT_SIZE.y;" in rows
    assert "float sigma = blurShare * OUTPUT_SIZE.y;" in compose
    assert "FRAGCOLOR = vec4(colour * weight, weight);" in layer
    assert "for (int i = 1; i <= reach; i += 2)" in rows
    blur = strip_comments((QML_DIR / "PhotoBlur.qml").read_text(encoding="utf-8"))
    assert blur.count("Buffer {") == blur.count("sizeMultiplier: 1.0") == 5


def test_the_photo_blur_weighs_a_layers_silhouette_for_a_fifth() -> None:
    """PF-E3D-27: a silhouette pixel's colour is multisampled while the depth pass puts all of it
    in one layer. At full weight a dark blurred bar took a 47-level light rim from the sharp
    panel beside it (360 px picture). The layer pass looks at the four cross neighbours."""
    layer = (QML_DIR / "photoblur_layer.frag").read_text(encoding="utf-8")
    assert "const float SILHOUETTE_WEIGHT = 0.2;" in layer
    for offset in ("+ vec2(pixel.x, 0.0)", "- vec2(pixel.x, 0.0)", "+ vec2(0.0, pixel.y)",
                   "- vec2(0.0, pixel.y)"):
        assert f"layerAmount(INPUT_UV {offset})" in layer, offset
    assert "if (inside <= 0.0)\n            weight *= SILHOUETTE_WEIGHT;" in layer


def test_the_photo_blur_finds_its_shaders_beside_itself() -> None:
    """Measured (#743): a ``Shader``'s plain relative path in an Effect component resolves against
    the file that INSTANTIATES the component - the bench fixture in tests/ read no shader at
    all. ``Qt.resolvedUrl`` resolves against PhotoBlur.qml's own directory."""
    blur = strip_comments((QML_DIR / "PhotoBlur.qml").read_text(encoding="utf-8"))
    shaders = re.findall(r"shader:\s*(.+)", blur)
    assert len(shaders) == 3
    assert all(re.fullmatch(r'Qt\.resolvedUrl\("photoblur_\w+\.frag"\)', value.strip()) for value in shaders)


def test_snow_lies_on_the_built_tops_through_one_shader_only_while_it_snows() -> None:
    """#687 (ADR-070 decision 6 as amended): under snow a roof, a bed's soil, a deck or the
    trampoline's mat lie under the ground's snow. The built parts and the roofs swap to ONE
    shared material (``built_snow.frag``, no shader per part: ADR-060) only while
    ``snowCover`` > 0 — every snowless frame is the principled look; an X-ray door or a cut
    roof keeps its screen door, and a building's floor (under its roof, seen in Cutaway)
    stays bare. Glass and water are unchanged (whether a glasshouse is heated or a pond
    frozen is not in the plan). The snow is ``weather.SNOW_LINEAR`` (drift guard, as the
    ground's) and the albedo goes through the engine's own polynomial, like
    ``ground.frag``'s."""
    from open_garden_planner.core.scene3d.weather import SNOW_LINEAR

    code = _scene()
    blocks = {block.split()[0]: block for block in re.split(r"Component\s*\{\s*id:\s*", code)[1:]}
    vc, roof = blocks["vcPart"], blocks["roofPart"]
    # #801: a part with a detail picture (a roof's tiles, a wall) shades by built_detail.frag,
    # which lays the SAME snow (below) - so the snowy look is the rest's
    assert ("materials: fade < 1.0 ? [vcScreen] : detailMap ? [vcDetail] : swayFrame.x > 0.0 "
            "&& root.windBlowing ? [vcSway] : root.builtSnow > 0.0 && partName !== \"floor\" "
            "? [vcSnow] : [vcLook]") in " ".join(vc.split())
    assert ("materials: root.roofsHidden || fade < 1.0 ? [roofScreen] : detailMap ? [roofDetail] "
            ": root.builtSnow > 0.0 ? [roofSnow] : [roofLook]") in " ".join(roof.split())
    for block, tint in ((vc, "Qt.vector3d(tint.r * seasonTint.x, tint.g * seasonTint.y, "
                             "tint.b * seasonTint.z)"),
                        (roof, "Qt.vector3d(tint.r, tint.g, tint.b)")):
        # the snowy look, and (#800) a plant's swaying wood, which carries the snow too
        assert block.count('fragmentShader: "built_snow.frag"') == (2 if block is vc else 1)
        assert block.count('vertexShader: "built_snow.vert"') == 1   # the colour as COLOR
        # ... and (#801) the detail material, which lays the same snow
        n = 3 if block is vc else 2
        assert block.count(f"property vector3d uTintSrgb: {tint}") == n
        assert block.count("property real uSnowCover: root.builtSnow") == n
        assert block.count("property real uSnowRough: root.groundRoughness") == n
        assert block.count("property real uSnowSpecular: root.groundSpecular") == n
    assert "texture: patternMap ? patternMap : null" in vc.split("id: vcSnow")[1]
    for kind in ("glassPart", "waterPart", "foliagePart"):
        assert "built_snow" not in blocks[kind], kind
    shader = (QML_DIR / "built_snow.frag").read_text(encoding="utf-8")
    found = re.search(r"mix\(albedo, vec3\(([^)]*)\), lying\)", shader)
    assert found and tuple(float(v) for v in found.group(1).split(",")) == SNOW_LINEAR
    assert "c * (c * (c * 0.305306011 + 0.682171111) + 0.012522878)" in shader
    assert "smoothstep(0.35, 0.75, NORMAL.y)" in shader and "VAR_COLOR" not in shader.split("void MAIN")[1]
    assert "vColor = COLOR;" in (QML_DIR / "built_snow.vert").read_text(encoding="utf-8")
    detail = (QML_DIR / "built_detail.frag").read_text(encoding="utf-8")
    found = re.search(r"mix\(albedo, vec3\(([^)]*)\), lying\)", detail)
    assert found and tuple(float(v) for v in found.group(1).split(",")) == SNOW_LINEAR
    assert "smoothstep(0.35, 0.75, n.y)" in detail and "uSnowCover" in detail
    for block in (vc.split("id: vcDetail")[1].split("CustomMaterial")[0],
                  roof.split("id: roofDetail")[1].split("CustomMaterial")[0]):
        assert "property real uSnowCover: root.builtSnow" in block
        assert "property real uSnowRough: root.groundRoughness" in block
    # the first snowy frame compiles nothing new: the warmer draws it with no pixel
    warmer = code[code.index("id: shaderWarmer"):]
    assert 'fragmentShader: "built_snow.frag"' in warmer


def test_a_plant_sways_as_one_by_its_own_frame_and_the_lawn_keeps_its_wind() -> None:
    """#800: the leaves (and their screen door) and a plant's wood and fruit read the SAME
    per-part frame (``swayFrame``, set by ``Quick3DHost.create_part`` from
    ``core.scene3d.wind.sway_frame``), the look's ``windSway`` and the clock; the wood
    swaps to its swaying shader only while the clock runs (every frame at rest is the
    principled look). The lawn's blades keep the strength they had; the first windy frame
    compiles nothing new (the warmer draws the wood's shader)."""
    code = _scene()
    blocks = {block.split()[0]: block for block in re.split(r"Component\s*\{\s*id:\s*", code)[1:]}
    foliage, vc, grass = blocks["foliagePart"], blocks["vcPart"], blocks["grassPart"]
    for block in (foliage, vc):
        assert "property vector3d swayFrame: Qt.vector3d(0, 0, 0)" in block
    for block, materials in ((foliage, ("id: foliageLook", "id: foliageDoor")), (vc, ("id: vcSway",))):
        for material in materials:
            body = block.split(material, 1)[1].split("CustomMaterial", 1)[0]
            assert "property vector3d uSwayFrame: swayFrame" in body, material
            assert "property vector3d uWindSway: root.windSway" in body, material
            assert "property real uTime: root.windTime" in body, material
    assert "uWind:" not in foliage
    # the swap follows a bool that changes only at start and rest, never the clock itself
    # (a binding on windTime would reassign the materials on every frame)
    assert re.search(r"readonly property bool windBlowing:\s*windTime > 0\.0", code)
    assert "root.windTime" not in vc.split("materials:", 1)[1].split("PrincipledMaterial", 1)[0]
    sway = vc.split("id: vcSway", 1)[1]
    assert 'vertexShader: "plant_sway.vert"' in sway and 'fragmentShader: "built_snow.frag"' in sway
    assert grass.count("property real uWind: root.windStrength") == 2
    warmer = code[code.index("id: shaderWarmer"):]
    assert 'vertexShader: "plant_sway.vert"' in warmer
    assert "uWind:" not in warmer.split('vertexShader: "foliage_door.vert"')[0].rsplit("Model {", 1)[1]
