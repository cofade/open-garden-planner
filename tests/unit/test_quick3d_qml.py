"""The engine package's QML, read as text (Phase 17 L1.2, #385 — gate G3).

``Garden.qml`` cannot be rendered in the default (GPU-less) run, but the rules
it must obey can be read from its source: no user-visible strings (``pylupdate6``
does not extract ``qsTr``, so text in QML would never be translated — §8.3), the
part components the Python side asks for exist, the look it starts with is
``NEUTRAL_DAY``, every shader it names ships beside it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from open_garden_planner.core.scene3d import MATERIAL_KINDS
from open_garden_planner.ui.view3d.quick3d.look import (
    COLOR_PROPERTIES,
    LINEAR_COLOR_PROPERTIES,
    NEUTRAL_DAY,
    scene_properties,
)
from open_garden_planner.ui.view3d.quick3d.materials import PART_COMPONENTS

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
            assert "property vector3d uTint: tintLinear" in block, block.split()[0]


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
    assert "materials: fade < 1.0 ? [vcScreen] : [vcLook]" in blocks["vcPart"]
    assert "materials: root.roofsHidden || fade < 1.0 ? [roofScreen] : [roofLook]" in blocks["roofPart"]
    assert "property real uOpacity: root.roofsHidden ? 0.0 : fade" in blocks["roofPart"]
    assert "pickable: fade >= 1.0 && !root.roofsHidden" in blocks["roofPart"]
    # the roofless house reads as a room: its walls drop back-face culling
    assert blocks["vcPart"].count("cullMode: root.roofsHidden ? Material.NoCulling") == 2
    for name in ("screen.frag", "foliage.frag", "water.frag"):
        source = (QML_DIR / name).read_text(encoding="utf-8")
        assert "screenDoor(FRAGCOORD.xy) >= uOpacity" in source and "discard;" in source, name
        assert "BASE_COLOR = vec4(" in source and ", 1.0);" in source, name   # never translucent


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
    for block in (shade, drape):
        assert "sourceAlphaBlend: CustomMaterial.Zero" in block        # the frame's alpha stays
        assert "destinationAlphaBlend: CustomMaterial.One" in block
        assert "depthDrawMode: Material.NeverDepthDraw" in block
    assert "Blend" not in lines
    for block in (drape, lines):
        assert "property real uExposure: root.topDown ? 1.0 : root.exposure" in block
    overlay = (QML_DIR / "overlay.frag").read_text(encoding="utf-8")
    assert "FRAGCOLOR = vec4(vColor.rgb / uExposure, vColor.a);" in overlay

def test_shaders_named_by_the_scene_ship_beside_it_and_none_is_orphaned() -> None:
    """A shader the scene names but the bundle lacks only fails when a Model uses it —
    in front of a user. The data loop of ``installer/ogp.spec`` ships this directory."""
    named = set(re.findall(r'(?:vertexShader|fragmentShader):\s*"([^"]+)"', _scene()))
    shipped = {path.name for path in QML_DIR.iterdir() if path.suffix in (".frag", ".vert")}
    assert named == shipped == {"foliage.vert", "foliage.frag", "grass.vert", "water.frag",
                                "ring.vert", "ring.frag",           # the selection ring: L1.8
                                "overlay.vert", "overlay.frag",     # the analysis overlays: L2
                                "screen.frag"}                      # X-ray and Cutaway: L2.4
    assert {path.name for path in QML_DIR.iterdir()} == shipped | {"Garden.qml"}


def test_every_custom_shader_multiplies_with_the_tint() -> None:
    for name in ("foliage.frag", "water.frag"):
        source = (QML_DIR / name).read_text(encoding="utf-8")
        assert re.search(r"BASE_COLOR\s*=\s*vec4\([\w.]+\s*\*\s*uTint\s*,", source), name


#: Root properties of the look block that are STATE of the wind's clock, not look.
WIND_STATE = {"windTime", "windRunning"}


def _look_block() -> dict[str, tuple[str, str]]:
    """The scene file's look properties: name -> (QML type, default as written)."""
    code = SCENE.read_text(encoding="utf-8")
    block = code[code.index("// ---- look"):code.index("// ---- key light")]
    found = re.findall(r"^\s*property (\w+) (\w+):\s*([^\s/]+)", strip_comments(block), re.MULTILINE)
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
    assert "readonly property bool skyShown: skyTexture !== null && !root.topDown" in code
    assert "lightProbe: view.skyShown ? view.skyTexture : null" in code
    assert "root.topDown ? SceneEnvironment.TonemapModeNone" in code
    assert "csmNumSplits: root.topDown ? 0 : root.shadowCascades" in code
    assert '(root.topDown || root.antialiasing === "msaa")' in code
    # with a sky the sky is the fill; without one, the look's flat fill
    assert "ambientColor: view.skyShown ? Qt.rgba(0, 0, 0, 1) : root.fillColor" in code


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
    build = code[code.index("function buildSky"):code.index("function dropSky")]
    order = [build.index(step) for step in (
        "skyTextureComponent.createObject(view.scene)", "skyDataComponent.createObject(texture)",
        "data[key] = inputs[key]", "data.textureQuality = ProceduralSkyTextureData.SkyTextureQualityMedium",
        "texture.textureData = data", "view.skyTexture = texture", "old.destroy()")]
    assert order == sorted(order), "inputs first, quality last, the new sky shown before the old goes"
    assert "data.destroy()" not in code and ".textureData = null" not in code
    assert build.count(".destroy()") == 1


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
                 "glowBloom", "glowHDRMinimumValue", "depthNear", "depthFar", "depthCurve",
                 "density", "skyboxBlurAmount", "csmBlendRatio", "shadowMapFar", "clipNear",
                 "clipFar"):
        ours = re.findall(rf"\b{name}:\s*([\d.]+)", code)
        assert ours and environment[name], name
        assert sorted({float(v) for v in ours}) == environment[name], name


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
