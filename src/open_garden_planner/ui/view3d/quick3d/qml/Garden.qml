// The garden in Qt Quick 3D (Phase 17 L1.2, ADR-048). Ported from the L0 spike's
// GardenSpike.qml: its measured core — frame, light, shadows, materials, picking
// (L1.2) — and its look: the sky from the sun, fog, the presets' post effects, wind
// (L1.4). The baked ground texture is L1.5.
//
// THE LOOK IS DATA FROM PYTHON. Every look property below is written by
// Quick3DHost.set_look from a core.scene3d.look.LookSpec (quick3d/look.py is the
// mapping); nothing in this file decides a mood or knows a preset by name, and the
// defaults ARE look.NEUTRAL_DAY (pinned by tests/unit/test_quick3d_qml.py).
//
// Rules of this file:
//  - NO user-visible strings (pinned by tests/unit/test_quick3d_qml.py): pylupdate6
//    does not extract qsTr, so any text is a QWidget overlay with tr().
//  - The scene is in the ENGINE frame (x = East, y = up, z = -North, centimetres).
//    The mapping from the plan's frame happens once, in Python (quick3d/adapter.py
//    through core/scene3d); nothing here converts a coordinate.
//  - Python (quick3d/host.py) drives everything through the root's properties and
//    functions. One Model per mesh part, created by createPart() and destroyed by
//    destroyPart(): never a Repeater3D over a JS array (any change of the array
//    recreates every delegate, and a geometry does not survive its Model).
import QtQuick
import QtQuick3D
import QtQuick3D.Helpers

Item {
    id: root
    width: 1280
    height: 720

    // ---- look (Quick3DHost.set_look; defaults = look.NEUTRAL_DAY) ----
    // the mood: follows the sun's elevation
    property color sunColor: "#fff1dc"      // the key light: the sun, at night the moon
    property real sunBrightness: 1.9
    property real exposure: 0.85
    property real probeExposure: 0.55       // how bright the sky texture is drawn and lights
    // The three colours the look derives in LINEAR light arrive as the colour the
    // engine's own linearisation turns back into that value (quick3d/look.py:
    // engine_srgb) - Qt linearises a colour property with a polynomial, not the sRGB
    // curve, and reads a dark sRGB code up to three times too dark.
    property color fogColor: "#8f9ca8"      // sky horizon x sky energy x probe exposure x 0.8
    property real saturation: 1.06
    property real contrast: 1.04
    // where NO sky texture lights the view (the top-down truth view; a host without a
    // sky: the software fallback, the self-test): a plain background and a flat fill
    property color skyColor: "#8f9ca8"
    property color fillColor: "#56657c"
    property color meadowColor: "#487f34"   // ONE albedo for the meadow and for bare plan ground
    // the key light's shadows: the preset's cost, the mood's softness
    property string shadowMapQuality: "very_high"   // high | very_high | ultra
    property int shadowCascades: 2                   // perspective view only
    property string softShadows: "pcf16"            // pcf4 | pcf8 | pcf16 | pcf32
    property real shadowBias: 10
    property real shadowFactor: 82
    property real pcfFactor: 2
    // the preset: what the frame costs
    property string antialiasing: "msaa"            // msaa | fxaa
    property string antialiasingQuality: "high"     // medium (2x) | high (4x) | very_high (8x)
    property bool ambientOcclusion: true
    property int aoSampleRate: 3
    property bool glow: true
    property bool glowHighQuality: false
    property bool reflections: false
    property bool fog: true
    // wind
    property real windStrength: 2.5
    // the shaders' clock, in seconds. At 0 the wind is at REST: every vertex is exactly
    // where its mesh puts it (the shaders ease the sway in over the first two seconds),
    // so what is drawn is what the CPU measured. ONLY at 0: a clock paused anywhere
    // else leaves the sway in the frame. A truth probe pins windTime to 0 (or
    // windStrength to 0); "paused" is not "at rest".
    property real windTime: 0
    // the animation policy's switch (Quick3DHost.set_wind_running): the clock runs
    // only while this is true — while it is false nothing ticks at all
    property bool windRunning: false
    // L4.5: a lawn's blades (parts named "lawn_blades") are drawn from the High preset
    // up; the controller admits their geometry only at High/Ultra (#607)
    property bool lawnBlades: true
    // L4.5: the ground's detail normals (0 = flat), see the groundTile component
    property real detailNormals: 3.0
    // ---- the living garden (Phase 17 L5, ADR-070; look.AtmosphereSpec) ----
    // A LOOK and nothing else: no property here moves the sun, a shadow or a plant.
    // The defaults are look.CLEAR_STILL: clear, dry and still.
    property real wetness: 0.0              // leaves, blades: rain 1, morning dew up to 0.6
    property real snowCover: 0.0            // snow on the ground and the leaves
    property real fogHaze: 1.0              // the depth fog's distances x this
    // the ground's (meadow, bare plan, baked tiles) ONE multiplier, roughness and
    // specular: the plan meets the meadow without a step in every weather
    property color groundTint: "#ffffff"
    property real groundRoughness: 1.0
    property real groundSpecular: 0.15
    property int precipKind: 0              // 0 none, 1 rain, 2 snow
    property real precipDensity: 0.0        // the share of the precipitation's particles drawn
    property vector3d windDrift: Qt.vector3d(0, 0, 0)       // cm/s, engine frame
    property vector3d particleLight: Qt.vector3d(1, 1, 1)   // linear: what lights an unlit particle
    property real leafLife: 0.0             // falling leaves, butterflies, fireflies: when (0..1)
    property real butterflyLife: 0.0
    property real fireflyLife: 0.0
    property real lampGlow: 0.0             // the garden lights: off by day, on at night

    // ---- key light (Quick3DHost: the sun the pipeline sent, or a night look's moon) ----
    property bool sunUp: false              // false until the first sun, and whenever there is no key light
    property quaternion sunRotation: Qt.quaternion(1, 0, 0, 0)   // rotates -Z onto the light's travel

    // ---- ground (Quick3DSink.set_ground) ----
    property bool groundVisible: false
    property vector3d groundCenter: Qt.vector3d(0, 0, 0)
    property real groundWidth: 1000         // along x (East), cm
    property real groundDepth: 1000         // along z (North), cm
    // true while baked tiles lie on the plan (quick3d/ground_tiles.py, L1.5): the bare
    // rectangle below is then not drawn — two coplanar surfaces would fight for the depth
    property bool groundTiled: false

    // ---- the living garden's host side (Quick3DHost, L5) ----
    // where the precipitation falls: a box around the camera's target, engine frame
    // (particles.precipitation_volume, set with every set_camera)
    property vector3d volumeCenter: Qt.vector3d(0, 0, 0)
    property real volumeSize: 4000
    property real volumeHeight: 2000
    // the "Wildlife and Falling Leaves" switch of the 3D strip (Quick3DHost.set_life_enabled)
    property bool lifeEnabled: true
    property bool ambientVisible: false     // the ambient buffer holds something
    // the garden lights that light (Quick3DHost.set_lamps): up to lampSlots of
    // {x, y, z, w} in the engine frame (w = strength), the nearest to the camera's target
    readonly property int lampSlots: 6
    property var lamps: []
    property color lampColor: "#ffc98a"
    // constantFade lampNear with brightness 9.4: the same pool at 1.5 m as 1.0 with 7.0,
    // a third of the light in the lantern's own glass (its specular saturated to white)
    property real lampBrightness: 9.4
    property real lampNear: 4.0
    property real lampFade: 3.5
    // centimetres per pixel per centimetre of depth: a particle is never thinner than a
    // pixel or so, near or far (the selection ring's measure)
    readonly property real particlePerDepth: 2.0 * Math.tan(camFov * Math.PI / 360.0)
                                             / Math.max(pictureHeight, 1.0)

    // ---- camera (Quick3DHost.set_shot) ----
    property bool topDown: false
    property vector3d camPos: Qt.vector3d(0, 1000, 2000)
    property vector3d camTarget: Qt.vector3d(0, 0, 0)
    property real camFov: 40
    property real shadowFar: 9000 // camera state: includes every plan corner
    property int camVersion: 0
    property real topDownScale: 0.5         // logical pixels per centimetre
    // where the depth fog begins and is full, cm: from the camera's distance to its
    // target (set_camera, core/scene3d/look.fog_depth_cm; L4 owner pass). The
    // defaults are its floors, the L0 spike's measured constants
    property real fogNear: 2600
    property real fogFar: 16000
    // what the fog hid until it followed the camera (3D review of L4's second owner
    // pass): the ambient-occlusion pass draws a hard line about 101 m out, so its
    // strength fades out between 45 m and 90 m from the camera's target
    readonly property real aoFade: Math.max(0, Math.min(1, (9000 - camPos.minus(camTarget).length()) / 4500))

    onCamVersionChanged: {
        cam.position = camPos
        cam.lookAt(camTarget)
    }

    // ---- photo mode (Quick3DHost.set_photo; L6.1, #390, ADR-071) ----
    // How a picture is DEVELOPED, never what stands in the garden. Python decides the
    // numbers (quick3d/look.py: photo_properties, from core/scene3d/photo.py). The
    // defaults are photo.NO_PHOTO: every effect off, the view itself, pixel for pixel.
    property real photoExposure: 1.0        // a factor on the look's exposure
    property real photoVignette: 0.0        // Qt's vignetteRadius; 0 is off
    property real photoFocusDistance: 600.0 // cm, from the camera to the focused point
    property real photoFocusRange: 100.0    // cm that stay sharp around it
    property real photoBlur: 0.0            // Qt's depthOfFieldBlurAmount; 0 is off
    property bool photoGraded: false        // a colour grade is on (showPhotoGrade)

    // A grade's table: ONE Texture per grade, with its data object, for the host's life
    // (Quick3DHost holds both). A Texture is never pointed at a second data object: that
    // draws white (ogp-3d-renderer section 5). Switching grades re-points the ENVIRONMENT.
    Component {
        id: gradeTexture
        Texture {
            tilingModeHorizontal: Texture.ClampToEdge
            tilingModeVertical: Texture.ClampToEdge
            magFilter: Texture.Linear
            minFilter: Texture.Linear
        }
    }

    function createPhotoGrade(data) {
        return gradeTexture.createObject(view.scene, {"textureData": data})
    }

    function showPhotoGrade(texture) {
        gardenEnvironment.lutTexture = texture
        root.photoGraded = true
        return true
    }

    // ---- the capture view (Quick3DHost.capture; L6, #390, ADR-071) ----
    // Pictures for a file, a video or an agent: a second View3D of the SAME scene, same
    // camera, same environment - so a capture at the view's size IS the view, pixel for
    // pixel, and no Model exists twice. It is not visible while captureWanted is false and
    // costs nothing then. Python moves the camera for the frame it takes and puts it back
    // before anything is presented. It is never destroyed: making and destroying a View3D
    // per picture left 20 MB behind each time at 4K, linearly (measured on WARP). What a
    // resting view must not keep is its render targets (500 MB after a 4K picture), so
    // Python renders it once at MIN_CAPTURE_SIDE before it hides it.
    property bool captureWanted: false
    property int captureWidth: 16           // device pixels of the picture
    property int captureHeight: 16
    property real capturePixelRatio: 1.0
    // the height the screen-sized measures go by (a particle's and the ring's minimum size)
    readonly property real pictureHeight: captureWanted ? captureHeight / capturePixelRatio
                                                        : view.height

    function captureItem() {
        return captureView
    }

    // The wind's clock. A FrameAnimation advances with the frames Qt draws, holds its
    // value when it stops (hidden is "stopped", not "at rest": showing the view again
    // goes on where it was) and has no timer of its own while it is not running.
    FrameAnimation {
        running: root.windRunning
        onTriggered: root.windTime += frameTime
    }

    // ---- sky (Quick3DHost.set_sky) ----
    // Built on request and never bound live: the generator recomputes the whole sky
    // synchronously on the GUI thread for EVERY input change, and the environment
    // filters its light probe once per Texture OBJECT (later textureData changes are
    // ignored: the sky's sun stayed in the north). So every build is a fresh Texture
    // with a fresh data object of its own; the inputs are set at the cheapest quality
    // and the quality is raised last: one full generation (spike: QML load 1709 ->
    // 70 ms, a sun change 2192 -> 344 ms on llvmpipe).
    //
    // MEDIUM quality (1024 x 512 float texels, 8 MB), not the spike's High (2048 x
    // 1024, 32 MB): the sky is a smooth gradient and a soft glow, and the build is
    // GUI-thread time while the user drags the time slider. Measured (L1.4 round 3,
    // RTX 4070, bench_small at 960 x 540, all seven shots): the build 215 -> 95 ms,
    // every shot's mean luma within 0.02, the sun's azimuth read back within 0.07
    // degrees (0.03 at High), the horizon step 3.4 -> 2.9.
    //
    // The pair lives and dies TOGETHER: the data object is the Texture's child, and
    // only the Texture is ever destroyed. A Texture loses its textureData when a data
    // object it held EARLIER is destroyed (measured by the ground bake, GPU and WARP:
    // a re-pointed Texture drew white) - so no Texture here is ever re-pointed, and no
    // data object outlives or predeceases its Texture.
    function buildSky(inputs) {
        var texture = skyTextureComponent.createObject(view.scene)
        var data = skyDataComponent.createObject(texture)
        for (var key in inputs)
            data[key] = inputs[key]
        data.textureQuality = ProceduralSkyTextureData.SkyTextureQualityMedium
        texture.textureData = data
        var old = view.skyTexture
        view.skyTexture = texture      // the scene shows the new sky ...
        view.atmosphereOn = false      // ... instead of an atmosphere (L7) ...
        if (old)
            old.destroy()              // ... and only then the old pair goes (deferred)
        root.skyBuilds += 1
        return {"builds": root.skyBuilds}
    }

    // ---- the atmosphere sky (Phase 17 L7, #391; Quick3DHost.set_sky, model "atmosphere") ----
    // ONE AtmosphereSky (a Qt 6.12 SkyMaterial: Hillaire's atmosphere and volumetric
    // clouds over the painted sky, AtmosphereSky.qml / atmosphere.frag), made at the
    // first call with its two textures - the cloud volume and the sky-view table, both
    // texture DATA from Python (quick3d/cloud_volume.py), ready before the first frame -
    // and from then on only written: a SkyMaterial redraws itself when an input changes,
    // so it is never rebuilt, and the host refills the sky-view table's data in place
    // for a new sun. Neither it nor a Texture of it is ever destroyed or re-pointed while
    // the scene lives (a data object attached to a second Texture draws white:
    // ogp-3d-renderer §2) - a painted sky only switches it off. It only BACKS the view:
    // the host builds the painted sky first (buildSky), whose texture stays the light
    // probe under the atmosphere too (PF-E3D-17: the atmosphere's own light crashed).
    function buildAtmosphere(inputs, volumeData, skyViewData) {
        var sky = view.atmosphere
        if (!sky) {
            var volume = cloudVolumeComponent.createObject(view.scene, {"textureData": volumeData})
            var skyView = skyViewComponent.createObject(view.scene, {"textureData": skyViewData})
            sky = atmosphereComponent.createObject(view.scene, {"noiseVolume": volume,
                                                                "skytextureBuffer": skyView})
            view.atmosphere = sky
        }
        for (var key in inputs)
            sky[key] = inputs[key]
        view.atmosphereOn = true       // the painted sky (if any) stays: the light probe
        root.skyBuilds += 1
        return {"builds": root.skyBuilds}
    }

    function dropSky() {
        var old = view.skyTexture
        view.skyTexture = null
        view.atmosphereOn = false
        if (old)
            old.destroy()
        return {"builds": root.skyBuilds}
    }

    property int skyBuilds: 0
    // read-backs for the host and its tests: is there a sky, and which object is it
    readonly property bool skyBuilt: view.skyTexture !== null || view.atmosphereOn
    readonly property var skyTextureObject: view.skyTexture
    readonly property bool atmosphereBuilt: view.atmosphereOn
    readonly property var atmosphereObject: view.atmosphere

    // MeshPart.material_kind -> part Component (keys = core.scene3d.MATERIAL_KINDS,
    // pinned against quick3d/materials.py PART_COMPONENTS)
    readonly property var partComponents: ({
        "vc": vcPart,
        "roof": roofPart,
        "foliage": foliagePart,
        "grass": grassPart,
        "glass": glassPart,
        "water": waterPart
    })

    function createPart(kind, itemId, partIndex, geometry, castsShadows) {
        var component = partComponents[kind]
        if (!component)
            return null
        return component.createObject(parts, {
            "itemId": itemId, "partIndex": partIndex, "kind": kind,
            "geometry": geometry, "castsShadows": castsShadows
        })
    }

    // The plan's own fill pictures (#628 follow-up): ONE Texture per (pattern,
    // colour), created with its data object and never re-pointed (a Texture pointed
    // at a second QQuick3DTextureData goes white: ogp-3d-renderer section 5). A
    // fill_texture Model shows one through `patternMap`; Python destroys it with its
    // last user (release_fill).
    Component {
        id: patternTexture
        Texture {
            tilingModeHorizontal: Texture.Repeat
            tilingModeVertical: Texture.Repeat
            flipV: false          // uv = item coordinates / 256, row 0 at the item's y = 0
            generateMipmaps: true
            mipFilter: Texture.Linear
        }
    }

    function createPatternTexture(data) {
        return patternTexture.createObject(view.scene, {"textureData": data})
    }

    // Plant Forge: material state only. A date scrub keeps every Model and buffer.
    property var plantSeasons: ({})
    function applyPlantSeason(part) {
        var state = plantSeasons[part.itemId]
        var foliage = part.kind === "foliage" || part.kind === "grass"
        var fruit = part.partName === "fruits"
        part.seasonDensity = state && foliage ? state[0] : 1.0
        part.seasonSnow = state && foliage ? state[6] : 0.0
        part.seasonTint = state && foliage ? Qt.vector3d(state[1], state[2], state[3]) :
                          state && fruit ? Qt.vector3d(state[7], state[8], state[9]) : Qt.vector3d(1, 1, 1)
        part.seasonOpacity = !state ? 1.0 : part.partName === "flowers" ? state[4] :
                             part.partName === "fruits" ? (state[5] > 0.0 ? 1.0 : 0.0) : 1.0
        // Seasonal absence removes its shadow too. X-ray's independent fade keeps it.
        // A lawn's blades show only at the presets that draw them (lawnBlades).
        part.visible = !part.retired && part.seasonOpacity > 0.0
                       && (part.partName !== "lawn_blades" || root.lawnBlades)
        return true
    }
    function setPlantSeasons(states) {
        plantSeasons = states
        for (var i = 0; i < parts.children.length; ++i) {
            var part = parts.children[i]
            if (!part.retired)
                applyPlantSeason(part)
        }
        return true
    }

    function destroyPart(part) {
        // retired first: destroy() is deferred, and until the delete arrives the Model
        // must be neither drawn, nor picked, nor listed
        part.retired = true
        part.visible = false
        part.pickable = false
        part.geometry = null
        part.destroy()
    }

    function listParts() {
        var out = []
        for (var i = 0; i < parts.children.length; ++i) {
            var p = parts.children[i]
            if (p.retired)
                continue   // destroyed, waiting for its deferred delete
            // the share of its pixels the ACTIVE material draws: 1 for a principled look,
            // the screen door's uOpacity while a part fades or a roof is cut (L2.4)
            var m = p.materials.length > 0 ? p.materials[0] : null
            out.push({
                "id": p.itemId, "part": p.partIndex, "kind": p.kind,
                "x": p.position.x, "y": p.position.y, "z": p.position.z,
                "yaw": p.eulerRotation.y,
                "r": p.tint.r, "g": p.tint.g, "b": p.tint.b,
                "casts": p.castsShadows, "geometry": p.geometry !== null,
                "visible": p.visible, "fade": p.fade,
                "drawn": (m && m.uOpacity !== undefined) ? m.uOpacity : 1.0
            })
        }
        return out
    }

    // ---- baked ground tiles (quick3d/ground_tiles.py drives these four) ----
    function createGroundTile(column, row, data) {
        return groundTile.createObject(groundTiles, {
            "tileColumn": column, "tileRow": row, "tileData": data
        })
    }

    function placeGroundTile(tile, x, z, width, depth) {
        tile.position = Qt.vector3d(x, 0, z)
        tile.scale = Qt.vector3d(width / 100, depth / 100, 1)
    }

    function destroyGroundTile(tile) {
        tile.retired = true
        tile.visible = false
        tile.tileData = null
        tile.destroy()
    }

    function listGroundTiles() {
        var out = []
        for (var i = 0; i < groundTiles.children.length; ++i) {
            var t = groundTiles.children[i]
            if (t.retired)
                continue   // destroyed, waiting for its deferred delete
            out.push({
                "column": t.tileColumn, "row": t.tileRow,
                "x": t.position.x, "y": t.position.y, "z": t.position.z,
                "width": t.scale.x * 100, "depth": t.scale.y * 100,
                "textured": t.tileData !== null, "visible": t.visible
            })
        }
        return out
    }

    function projectToView(x, y, z) {
        var p = view.mapFrom3DScene(Qt.vector3d(x, y, z))
        return {"x": p.x, "y": p.y}
    }

    function pickAt(x, y) {
        // every hit along the ray, nearest first (L1.8): the first is THE hit, the rest
        // go along as "behind" - a click on an item of a locked layer falls through to
        // what is behind it, as it does on the 2D canvas
        var all = view.pickAll(x, y)
        var hits = []
        for (var i = 0; i < all.length; ++i) {
            var r = all[i]
            if (!r.objectHit)
                continue
            hits.push({
                "id": r.objectHit.itemId || "",
                "part": r.objectHit.partIndex === undefined ? -1 : r.objectHit.partIndex,
                "x": r.scenePosition.x, "y": r.scenePosition.y, "z": r.scenePosition.z
            })
        }
        if (hits.length === 0)
            return {"hit": false}
        var first = hits[0]
        first["hit"] = true
        first["behind"] = hits.slice(1)
        return first
    }

    // ---- selection ring (Quick3DSink.set_selection; L1.8, ADR-060) ----
    // ONE Model for the life of the scene (selectionRing, at the end of the View3D):
    // Python loads the ring mesh into its one geometry and switches it on and off.
    // No Model is created or destroyed by a selection change.
    property bool selectionVisible: false
    property color selectionColor: "#0078d7"        // core.scene3d.selection.SELECTION_RGB
    property vector3d selectionColorLinear: Qt.vector3d(0.0, 0.1878, 0.6795)   // the same, linear
    readonly property real ringWidthPx: 3.0         // core.scene3d.selection.RING_WIDTH_PX
    // 0.01: the ring is drawn in front of everything further than a hand's breadth from
    // the camera - a highlight is found, not searched for. 1.0 would depth-test it, and
    // it would be hidden inside a wall's body (a wall is built 30 cm thick on a 5 cm
    // stroke) and under a crown seen from above.
    property real ringDepthScale: 0.01

    function meadowModel() {
        return meadow
    }

    function setMeadowGeometry(geometry) {
        meadow.geometry = geometry
        return true
    }

    function selectionRingModel() {
        return selectionRing
    }

    function setSelectionGeometry(geometry) {
        selectionRing.geometry = geometry
        return true
    }

    // ---- analysis (Phase 17 L2, #386; Quick3DHost.set_overlay / set_roofs_hidden) ----
    // Three Models for the life of the scene, like the selection ring: Python loads a
    // mesh into each one's geometry and switches it on and off; no analysis change
    // creates or destroys a Model. None writes depth: what stands on the ground still
    // hides a drape.
    //  - "shade": the 2D shadows on the ground (core/scene3d/drape.py shadow_drape) -
    //    a MULTIPLIER of what lies under it, so a shadow darkens in every mood (blended
    //    over, an unlit colour brightened the night: 3D review of #386);
    //  - "drape": the hours-of-sun map on the ground (sun_hours_drape) - blended over;
    //  - "lines": the sun path, the compass and the probe's pin (core/scene3d/sun_path.py).
    property bool shadeVisible: false
    property bool drapeVisible: false
    property bool linesVisible: false
    // Cutaway (L2.4): every roof part is cut - one switch, no Model created or destroyed.
    // A cut roof is a screen door with nothing left (screen.frag), so it still casts its
    // shadow; the walls drop back-face culling so the house reads as a room, not as one
    // wall and a free gable.
    property bool roofsHidden: false
    onLawnBladesChanged: {
        for (var i = 0; i < parts.children.length; ++i) {
            var part = parts.children[i]
            if (!part.retired && part.partName === "lawn_blades")
                applyPlantSeason(part)
        }
    }
    function overlayModel(layer) {
        return layer === "shade" ? shadeOverlay : layer === "drape" ? drapeOverlay
             : layer === "lines" ? linesOverlay : null
    }

    // ---- the living garden (L5): one geometry per Model, loaded by Python ----
    function precipitationModel() {
        return precipitation
    }
    function setPrecipitationGeometry(geometry) {
        precipitation.geometry = geometry
        return true
    }
    function ambientModel() {
        return ambientLife
    }
    function setAmbientGeometry(geometry) {
        ambientLife.geometry = geometry
        return true
    }

    function setOverlayGeometry(layer, geometry) {
        var model = overlayModel(layer)
        if (!model)
            return false
        model.geometry = geometry
        return true
    }

    // ---- one Component per material kind: a Model with its OWN material instance ----
    // albedo = vertex colour x tint (linear) for every kind. `tint` is the sRGB colour
    // the principled materials take; `tintLinear` the same in linear light for the
    // custom shaders (computed in Python with the exact sRGB curve). `retired` marks a
    // Model that was destroyed and waits for its deferred delete: `visible` stays free
    // for a story that hides a Model on purpose.
    //
    // `fade` (L2.4, X-ray): 1 draws the part as it is; below 1 the part switches to a
    // SCREEN DOOR of that share of its pixels (screen.frag; foliage_door.frag and
    // water_door.frag for the custom kinds - copies of their look shaders with the
    // discard added) and cannot be picked - a click meets what is behind it. Python
    // writes it for the occluders of the selection (Quick3DHost.set_faded_items). A
    // screen door is opaque: the part keeps casting its shadow and sorts like a solid
    // (a blended part dropped out of the shadow map: 3D review of #386). The look
    // material stays exactly as it was, so nothing changes while no part fades.
    Component {
        id: vcPart
        Model {
            property string itemId
            property int partIndex: 0
            property string kind
            property string partName: ""
            property real seasonDensity: 1.0
            property real seasonOpacity: 1.0
            property vector3d seasonTint: Qt.vector3d(1, 1, 1)
            property real seasonSnow: 0.0
            property color tint: "#ffffff"
            property vector3d tintLinear: Qt.vector3d(1, 1, 1)
            property var patternMap: null  // #628: the item's own fill picture, or null
            property bool retired: false   // set by destroyPart(); never a reason to hide
            property real fade: 1.0        // X-ray (L2.4)
            property bool groundDetail: false   // L4: relief on painted ground — never picked
            receivesShadows: true
            pickable: fade >= 1.0 && !groundDetail
            materials: fade < 1.0 ? [vcScreen] : [vcLook]
            PrincipledMaterial {
                id: vcLook
                vertexColorsEnabled: true
                baseColor: Qt.rgba(tint.r * seasonTint.x, tint.g * seasonTint.y, tint.b * seasonTint.z, 1)
                baseColorMap: patternMap ? patternMap : null
                roughness: 0.78
                specularAmount: 0.35
                // Cutaway: the inner faces of a roofless house's walls
                cullMode: root.roofsHidden ? Material.NoCulling : Material.BackFaceCulling
            }
            CustomMaterial {
                id: vcScreen
                property vector3d uTint: Qt.vector3d(tintLinear.x * seasonTint.x, tintLinear.y * seasonTint.y, tintLinear.z * seasonTint.z)
                property real uOpacity: fade
                property real uRough: 0.78
                property real uSpecular: 0.35
                shadingMode: CustomMaterial.Shaded
                cullMode: root.roofsHidden ? Material.NoCulling : Material.BackFaceCulling
                vertexShader: "screen.vert"
                fragmentShader: "screen.frag"
            }
        }
    }
    Component {
        id: roofPart
        Model {
            property string itemId
            property int partIndex: 0
            property string kind
            property string partName: ""
            property real seasonDensity: 1.0
            property real seasonOpacity: 1.0
            property vector3d seasonTint: Qt.vector3d(1, 1, 1)
            property real seasonSnow: 0.0
            property color tint: "#ffffff"
            property vector3d tintLinear: Qt.vector3d(1, 1, 1)
            property bool retired: false   // set by destroyPart(); never a reason to hide
            property real fade: 1.0        // X-ray (L2.4)
            property bool groundDetail: false   // L4: relief on painted ground — never picked
            receivesShadows: true
            pickable: fade >= 1.0 && !root.roofsHidden && !groundDetail
            // Cutaway (L2.4): a binding, so a roof built while it is on is born cut - a
            // screen door with nothing left, still casting its shadow
            materials: root.roofsHidden || fade < 1.0 ? [roofScreen] : [roofLook]
            // roof tiles and shingles (ogp-lush-cinematic 4: roughness 0.70-0.85)
            PrincipledMaterial {
                id: roofLook
                vertexColorsEnabled: true
                baseColor: tint
                roughness: 0.80
                specularAmount: 0.15
            }
            CustomMaterial {
                id: roofScreen
                property vector3d uTint: tintLinear
                property real uOpacity: root.roofsHidden ? 0.0 : fade
                property real uRough: 0.80
                property real uSpecular: 0.15
                shadingMode: CustomMaterial.Shaded
                vertexShader: "screen.vert"
                fragmentShader: "screen.frag"
            }
        }
    }
    Component {
        id: glassPart
        Model {
            property string itemId
            property int partIndex: 0
            property string kind
            property string partName: ""
            property real seasonDensity: 1.0
            property real seasonOpacity: 1.0
            property vector3d seasonTint: Qt.vector3d(1, 1, 1)
            property real seasonSnow: 0.0
            property color tint: "#ffffff"
            property vector3d tintLinear: Qt.vector3d(1, 1, 1)
            property bool retired: false   // set by destroyPart(); never a reason to hide
            property real fade: 1.0        // X-ray (L2.4)
            property bool groundDetail: false   // L4: relief on painted ground — never picked
            receivesShadows: true
            pickable: fade >= 1.0 && !groundDetail
            materials: PrincipledMaterial {
                vertexColorsEnabled: true
                baseColor: tint
                roughness: 0.04
                metalness: 0.0
                specularAmount: 1.0
                opacity: 0.28 * fade
                alphaMode: PrincipledMaterial.Blend
                cullMode: Material.NoCulling
                depthDrawMode: Material.NeverDepthDraw
            }
        }
    }
    Component {
        id: waterPart
        Model {
            property string itemId
            property int partIndex: 0
            property string kind
            property string partName: ""
            property real seasonDensity: 1.0
            property real seasonOpacity: 1.0
            property vector3d seasonTint: Qt.vector3d(1, 1, 1)
            property real seasonSnow: 0.0
            property color tint: "#ffffff"
            property vector3d tintLinear: Qt.vector3d(1, 1, 1)
            property bool retired: false   // set by destroyPart(); never a reason to hide
            property real fade: 1.0        // X-ray (L2.4)
            property bool groundDetail: false   // L4: relief on painted ground — never picked
            property var patternMap: null  // #627: the item's own water picture, or null
            receivesShadows: true
            pickable: fade >= 1.0 && !groundDetail
            // a custom shader keeps the water's hue in every mood; see water.frag for why
            // this is not a PrincipledMaterial (measured in the spike: lavender at golden hour)
            materials: fade < 1.0 ? [waterDoor] : [waterLook]
            CustomMaterial {
                id: waterLook
                // a raised pool shows the plan's own water picture, in the canvas's
                // phase; a ground pond has none and keeps the flat tint (water.frag)
                property TextureInput uFill: TextureInput {
                    texture: patternMap ? patternMap : null
                }
                property real uHasFill: patternMap ? 1.0 : 0.0
                property vector3d uTint: tintLinear
                property real uBody: 0.5      // = the principled diffuse's (1 - specularAmount)
                property real uReflect: 0.15
                // a crisp sun glint: 0.3 blew it over the pond, 0.05 still clipped ~23 %
                // of the visible pond at morning (spike, creator round 2)
                property real uRough: 0.02
                shadingMode: CustomMaterial.Shaded
                fragmentShader: "water.frag"
            }
            CustomMaterial {   // the same water as a screen door (X-ray, L2.4)
                id: waterDoor
                // the raised pool's own water picture travels with it (water.frag has
                // the same branch: the door is the look plus the dither)
                property TextureInput uFill: TextureInput {
                    texture: patternMap ? patternMap : null
                }
                property real uHasFill: patternMap ? 1.0 : 0.0
                property vector3d uTint: tintLinear
                property real uBody: 0.5
                property real uReflect: 0.15
                property real uRough: 0.02
                property real uOpacity: fade
                shadingMode: CustomMaterial.Shaded
                vertexShader: "screen.vert"
                fragmentShader: "water_door.frag"
            }
        }
    }
    // One baked ground tile (L1.5): a quad in the plan's plane with its own texture.
    //  - flipV: a tile's pixel rows are north-up, the engine samples bottom-up
    //    (measured in the spike: without it the plan is mirrored north-south);
    //  - ClampToEdge: with the default Repeat, linear filtering at a tile's edge
    //    blends in the texels of its OPPOSITE edge - a line along every tile border;
    //  - not pickable, like the bare plan rectangle: a click on the ground hits no item.
    Component {
        id: groundTile
        Model {
            property int tileColumn: 0
            property int tileRow: 0
            property var tileData: null
            property bool retired: false   // set by destroyGroundTile()
            source: "#Rectangle"
            eulerRotation.x: -90
            receivesShadows: true
            castsShadows: false
            // ONE Texture for the tile's life, shared by its two materials (a Texture
            // re-pointed at another texture goes white: ogp-3d-renderer section 5)
            Texture {
                id: tileTexture
                textureData: tileData
                flipV: true
                tilingModeHorizontal: Texture.ClampToEdge
                tilingModeVertical: Texture.ClampToEdge
                generateMipmaps: true
                mipFilter: Texture.Linear
            }
            // L4.5: from the Medium preset up the ground shades with detail normals of its
            // own picture (ground.frag); Low and the compatibility mode keep the flat look
            // — unless snow lies on it (L5): a texture is only multiplied by a principled
            // material, and snow is a mix
            materials: root.detailNormals > 0.0 || root.snowCover > 0.0 ? [tileDetail] : [tileFlat]
            PrincipledMaterial {
                id: tileFlat
                baseColorMap: tileTexture
                baseColor: root.groundTint     // L5: the rain darkens the ground (white: as it is)
                // the endless meadow's values (below): PrincipledMaterial scales the
                // sky's diffuse light by (1 - specularAmount), so any other pair puts a
                // luma step where a baked lawn meets the meadow at the plan's edge
                // (the L1.4 look review measured 2-8 luma for 0.92 / 0.2). L5: the
                // weather changes them for every piece of ground at once
                roughness: root.groundRoughness
                specularAmount: root.groundSpecular
            }
            CustomMaterial {
                id: tileDetail
                property TextureInput uBaseMap: TextureInput { texture: tileTexture }
                property real uDetail: root.detailNormals
                // L5: the weather (ground.frag) - the same values the meadow takes
                property vector3d uGroundTint: Qt.vector3d(root.groundTint.r, root.groundTint.g, root.groundTint.b)
                property real uRough: root.groundRoughness
                property real uSpecular: root.groundSpecular
                property real uSnowCover: root.snowCover
                shadingMode: CustomMaterial.Shaded
                fragmentShader: "ground.frag"
            }
        }
    }
    Component {
        id: foliagePart
        Model {
            property string itemId
            property int partIndex: 0
            property string kind
            property string partName: ""
            property real seasonDensity: 1.0
            property real seasonOpacity: 1.0
            property vector3d seasonTint: Qt.vector3d(1, 1, 1)
            property real seasonSnow: 0.0
            property color tint: "#ffffff"
            property vector3d tintLinear: Qt.vector3d(1, 1, 1)
            property bool retired: false   // set by destroyPart(); never a reason to hide
            property real fade: 1.0        // X-ray (L2.4)
            property bool groundDetail: false   // L4: relief on painted ground — never picked
            receivesShadows: true
            pickable: fade >= 1.0 && !groundDetail
            materials: fade < 1.0 ? [foliageDoor] : [foliageLook]
            CustomMaterial {
                id: foliageLook
                property vector3d uTint: Qt.vector3d(tintLinear.x * seasonTint.x, tintLinear.y * seasonTint.y, tintLinear.z * seasonTint.z)
                property real uLeafDensity: seasonDensity
                property real uSnow: Math.max(seasonSnow, root.snowCover)
                property real uWet: root.wetness
                property real uTime: root.windTime
                property real uWind: root.windStrength * 0.35
                shadingMode: CustomMaterial.Shaded
                cullMode: Material.NoCulling
                vertexShader: "foliage.vert"
                fragmentShader: "foliage.frag"
            }
            CustomMaterial {   // the same leaves as a screen door (X-ray, L2.4)
                id: foliageDoor
                property vector3d uTint: Qt.vector3d(tintLinear.x * seasonTint.x, tintLinear.y * seasonTint.y, tintLinear.z * seasonTint.z)
                property real uLeafDensity: seasonDensity
                property real uSnow: Math.max(seasonSnow, root.snowCover)
                property real uWet: root.wetness
                property real uTime: root.windTime
                property real uWind: root.windStrength * 0.35
                property real uOpacity: fade
                shadingMode: CustomMaterial.Shaded
                cullMode: Material.NoCulling
                vertexShader: "foliage_door.vert"
                fragmentShader: "foliage_door.frag"
            }
        }
    }
    Component {
        id: grassPart
        Model {
            property string itemId
            property int partIndex: 0
            property string kind
            property string partName: ""
            property real seasonDensity: 1.0
            property real seasonOpacity: 1.0
            property vector3d seasonTint: Qt.vector3d(1, 1, 1)
            property real seasonSnow: 0.0
            property color tint: "#ffffff"
            property vector3d tintLinear: Qt.vector3d(1, 1, 1)
            property bool retired: false   // set by destroyPart(); never a reason to hide
            property real fade: 1.0        // X-ray (L2.4)
            property bool groundDetail: false   // L4: relief on painted ground — never picked
            receivesShadows: true
            pickable: fade >= 1.0 && !groundDetail
            materials: fade < 1.0 ? [grassDoor] : [grassLook]
            CustomMaterial {
                id: grassLook
                property vector3d uTint: Qt.vector3d(tintLinear.x * seasonTint.x, tintLinear.y * seasonTint.y, tintLinear.z * seasonTint.z)
                property real uLeafDensity: seasonDensity
                property real uSnow: Math.max(seasonSnow, root.snowCover)
                property real uWet: root.wetness
                property real uTime: root.windTime
                property real uWind: root.windStrength
                shadingMode: CustomMaterial.Shaded
                cullMode: Material.NoCulling
                vertexShader: "grass.vert"
                fragmentShader: partName === "lawn_blades" ? "lawn.frag" : "foliage.frag"
            }
            CustomMaterial {   // the same blades as a screen door (X-ray, L2.4)
                id: grassDoor
                property vector3d uTint: Qt.vector3d(tintLinear.x * seasonTint.x, tintLinear.y * seasonTint.y, tintLinear.z * seasonTint.z)
                property real uLeafDensity: seasonDensity
                property real uSnow: Math.max(seasonSnow, root.snowCover)
                property real uWet: root.wetness
                property real uTime: root.windTime
                property real uWind: root.windStrength
                property real uOpacity: fade
                shadingMode: CustomMaterial.Shaded
                cullMode: Material.NoCulling
                vertexShader: "grass_door.vert"
                fragmentShader: "foliage_door.frag"
            }
        }
    }

    View3D {
        id: view
        anchors.fill: parent
        camera: root.topDown ? topCam : cam

        // the sky texture of the last buildSky(), or null: no sky was asked for
        property var skyTexture: null
        // L7: the atmosphere sky (made once, by the first buildAtmosphere) and whether
        // it is the sky now (buildAtmosphere: yes; buildSky, dropSky: no)
        property var atmosphere: null
        property bool atmosphereOn: false
        // a sky lights and backs the PERSPECTIVE view only. The painted sky is the light
        // probe under BOTH models and the background when no atmosphere is on (L7,
        // PF-E3D-17): paintedShown and atmosphereShown are both true under the atmosphere
        readonly property bool paintedShown: skyTexture !== null && !root.topDown
        readonly property bool atmosphereShown: atmosphereOn && atmosphere !== null && !root.topDown
        readonly property bool skyShown: paintedShown || atmosphereShown

        Component {
            id: skyTextureComponent
            Texture {}
        }
        Component {
            id: atmosphereComponent
            AtmosphereSky { skyExposure: root.probeExposure }
        }
        // the sky-view table (quick3d/cloud_volume.py: RGBA16F, 128 x 128), clamped at
        // its edges as the example's provider texture was
        Component {
            id: skyViewComponent
            Texture {
                tilingModeHorizontal: Texture.ClampToEdge
                tilingModeVertical: Texture.ClampToEdge
                magFilter: Texture.Linear
                minFilter: Texture.Linear
            }
        }
        // the cloud volume (quick3d/cloud_volume.py: RGBA16F, 64 cubed), tileable in
        // all three axes as the example's
        Component {
            id: cloudVolumeComponent
            Texture {
                tilingModeHorizontal: Texture.Repeat
                tilingModeVertical: Texture.Repeat
                tilingModeDepth: Texture.Repeat
                magFilter: Texture.Linear
                minFilter: Texture.Linear
            }
        }
        Component {
            id: skyDataComponent
            ProceduralSkyTextureData {
                textureQuality: ProceduralSkyTextureData.SkyTextureQualityLow
            }
        }

        // The top-down view is the TRUTH view: no tone mapping, no fog, no post effect,
        // no sky - a pixel is the surface's linear radiance (albedo x light) and a
        // probe can predict it, whatever the preset. The perspective view is the one
        // people look at: filmic, exposed and graded by the look.
        //
        // The numbers that are not properties are the L0 spike's, the same at every
        // preset (pinned against its scene file's values, frozen when L1.10 deleted it).
        environment: ExtendedSceneEnvironment {
            id: gardenEnvironment
            backgroundMode: view.atmosphereShown ? SceneEnvironment.SkyMaterial
                            : view.paintedShown ? SceneEnvironment.SkyBox : SceneEnvironment.Color
            clearColor: root.skyColor
            lightProbe: view.paintedShown ? view.skyTexture : null
            // Qt 6.12 (PF-E3D-16): when an EARLIER sky Texture is destroyed (buildSky's
            // deferred old.destroy()), its destroyed-watcher still fires and sets the probe
            // to null although the probe is the current sky - the sky drew the clear colour
            // after the first sun change. The binding is put back in the same signal, before
            // any frame can render (6.11: the watcher was gone with the switch)
            onLightProbeChanged: {
                if (lightProbe !== (view.paintedShown ? view.skyTexture : null))
                    lightProbe = Qt.binding(function() { return view.paintedShown ? view.skyTexture : null })
            }
            // L7: the atmosphere only backs the view (PF-E3D-17); the probe above lights it
            skyMaterial: view.atmosphereShown ? view.atmosphere : null
            probeExposure: root.probeExposure
            skyboxBlurAmount: 0.0
            tonemapMode: root.topDown ? SceneEnvironment.TonemapModeNone
                                      : SceneEnvironment.TonemapModeFilmic
            exposure: root.topDown ? 1.0 : root.exposure * root.photoExposure
            ditheringEnabled: !root.topDown
            aoEnabled: !root.topDown && root.ambientOcclusion && root.aoFade > 0
            // 0 wherever AO is off: Qt's setAoStrength turns AO on whenever the strength
            // is not 0, whatever aoEnabled says (3D review of L4's second owner pass: Low
            // drew SSAO once the fade had changed it)
            aoStrength: 55 * (!root.topDown && root.ambientOcclusion ? root.aoFade : 0)
            aoDistance: 14
            aoSoftness: 45
            aoSampleRate: root.aoSampleRate
            glowEnabled: !root.topDown && root.glow
            glowStrength: 1.05
            glowIntensity: 0.55
            glowBloom: 0.18
            glowHDRMinimumValue: 1.1
            glowQualityHigh: root.glowHighQuality
            fog: Fog {
                // blends the endless meadow into the sky's horizon, at EVERY preset:
                // without it low drew a one-row cliff where the meadow meets the sky
                enabled: !root.topDown && root.fog
                color: root.fogColor
                depthEnabled: true
                // a rain haze or a morning mist brings it nearer (L5: fogHaze)
                depthNear: root.fogNear * root.fogHaze
                depthFar: root.fogFar * root.fogHaze
                depthCurve: 1.4
                density: 1.0
            }
            // the truth view is always multisampled at 4x: its pixels do not depend on a preset
            antialiasingMode: (root.topDown || root.antialiasing === "msaa")
                              ? SceneEnvironment.MSAA : SceneEnvironment.NoAA
            antialiasingQuality: root.topDown ? SceneEnvironment.High
                                 : root.antialiasingQuality === "very_high" ? SceneEnvironment.VeryHigh
                                 : root.antialiasingQuality === "medium" ? SceneEnvironment.Medium
                                 : SceneEnvironment.High
            // without MSAA: FXAA (a post effect) and specular anti-aliasing instead
            fxaaEnabled: !root.topDown && root.antialiasing === "fxaa"
            specularAAEnabled: !root.topDown && root.antialiasing === "fxaa"
            // SSGI renders a black frame on Mesa llvmpipe: no preset turns it on
            ssgiEnabled: false
            ssrEnabled: !root.topDown && root.reflections
            // No sharpening ever - 0.08 overshot every thin lit/dark edge to near-black,
            // red-less pixels (1,500-3,100 isolated dark pixels per daytime frame at
            // 1280x720); 0.03 is nearly as bad. The render tier bounds the speckles.
            sharpnessAmount: 0.0
            colorAdjustmentsEnabled: !root.topDown
            // Under a grade these two live IN its table (core/scene3d/photo.py lut_strip): Qt
            // applies them right before the table, unclamped, and its table lookup is a
            // texelFetch that a colour below 0 reads from the NEIGHBOURING slice - the darkest
            // leaves came out red (R 0 became 57, 4181 pixels of a 720p frame)
            adjustmentSaturation: root.photoGraded ? 1.0 : root.saturation
            adjustmentContrast: root.photoGraded ? 1.0 : root.contrast
            // photo mode (L6.1): off unless a setting asks, and never in the truth view
            vignetteEnabled: !root.topDown && root.photoVignette > 0
            // Qt: colour x (u (1-u) v (1-v) x strength) ^ radius. A LOWER strength darkens the
            // middle of the picture too; the exponent is what reaches only into the corners
            vignetteStrength: 15
            vignetteRadius: root.photoVignette
            lutEnabled: !root.topDown && root.photoGraded
            depthOfFieldEnabled: !root.topDown && root.photoBlur > 0
            depthOfFieldFocusDistance: root.photoFocusDistance
            depthOfFieldFocusRange: root.photoFocusRange
            depthOfFieldBlurAmount: root.photoBlur
        }

        PerspectiveCamera {
            id: cam
            fieldOfView: root.camFov
            clipNear: 5
            // past all corners of the meadow (10 km half-side), from 600 m out
            // (camera.MAX_DISTANCE_CM): at the L0 spike's 800 m the cut showed against the
            // sky from about 400 m (3D review)
            clipFar: 1600000
        }
        OrthographicCamera {
            id: topCam
            position: Qt.vector3d(root.camTarget.x, 4000, root.camTarget.z)
            eulerRotation.x: -90   // looks down -Y with -Z (north) up the image, +X (east) right
            horizontalMagnification: root.topDownScale
            verticalMagnification: root.topDownScale
            clipNear: 1
            clipFar: 10000
        }

        // The key light: the sun - at night the look's moon. A DirectionalLight shines
        // down its local -Z; Python hands over the rotation that puts -Z onto the
        // light's travel (= -sun vector, core/solar). Its shadow settings are the
        // look's (the preset's map, cascades, filter and bias; the mood's darkness and
        // blur) - but no cascades in the orthographic truth view.
        DirectionalLight {
            id: sun
            visible: root.sunUp
            rotation: root.sunRotation
            color: root.sunColor
            brightness: root.sunBrightness
            ambientColor: Qt.rgba(0, 0, 0, 1)
            castsShadow: true
            shadowFactor: root.shadowFactor
            shadowMapQuality: root.shadowMapQuality === "ultra" ? Light.ShadowMapQualityUltra
                            : root.shadowMapQuality === "high" ? Light.ShadowMapQualityHigh
                            : Light.ShadowMapQualityVeryHigh
            csmNumSplits: root.topDown ? 0 : root.shadowCascades
            csmBlendRatio: 0.05
            softShadowQuality: root.softShadows === "pcf4" ? Light.PCF4
                             : root.softShadows === "pcf8" ? Light.PCF8
                             : root.softShadows === "pcf32" ? Light.PCF32 : Light.PCF16
            pcfFactor: root.pcfFactor
            shadowBias: root.shadowBias
            // as far as the fog begins (the spike's 9000 its floor): with the fog following
            // the camera, a framed plan beyond 90 m lay clear and shadowless (3D review).
            // The top-down truth view keeps the measured 9000.
            shadowMapFar: root.topDown ? 9000 : root.shadowFar
            lockShadowmapTexels: true
        }
        // The flat fill - ONLY where no sky texture lights the view (the truth view, a
        // host without a sky). No direct light of its own; separate from the key light
        // so that a frame without one is dim, not black. With a sky, the sky is the fill.
        DirectionalLight {
            brightness: 0
            ambientColor: view.skyShown ? Qt.rgba(0, 0, 0, 1) : root.fillColor
            castsShadow: false
        }

        // The endless meadow: a 20 x 20 km square around the plan, IN the plan's plane, the
        // plan cut out, in cells of at most 100 m — core/scene3d/meadow.py says why (3D
        // review of #388: one quad under the plan lost the depth test to it). Its ONE
        // geometry is the host's: loaded at start and whenever the plan's rectangle
        // changes, as the selection ring's (Quick3DHost._show_meadow).
        Model {
            id: meadow
            visible: geometry !== null
            pickable: false
            receivesShadows: true
            castsShadows: false
            materials: PrincipledMaterial {
                baseColor: root.meadowColor
                roughness: root.groundRoughness     // 1.0 dry; wet in the rain (L5)
                specularAmount: root.groundSpecular // 0.15 dry
            }
        }

        // the plan rectangle, bare: ground in the meadow's albedo. Drawn only while no
        // baked tiles lie on the plan (L1.5: the groundTile component above). The
        // MEADOW's material too (roughness 1.0, specular 0.15): at 0.92 / 0.2 its sheen
        // made the plan read as a darker or brighter rectangle under a grazing view
        // (-8.9 luma at golden hour; L1.4 fix round 1); the tiles keep these values.
        Model {
            source: "#Rectangle"
            position: Qt.vector3d(root.groundCenter.x, 0, root.groundCenter.z)
            eulerRotation.x: -90
            scale: Qt.vector3d(root.groundWidth / 100, root.groundDepth / 100, 1)
            receivesShadows: true
            castsShadows: false
            visible: root.groundVisible && !root.groundTiled
            materials: PrincipledMaterial {
                baseColor: root.meadowColor
                roughness: root.groundRoughness     // 1.0 dry; wet in the rain (L5)
                specularAmount: root.groundSpecular // 0.15 dry
            }
        }

        Node { id: groundTiles }
        Node { id: parts }

        // The selection ring (L1.8): unlit, casts and receives no shadow, cannot be
        // picked - a click on it meets what is behind it. Not a child of `parts`:
        // it is no item's part, and listParts() must not see it. Its width is the
        // shader's: uv.x band widths along the stored normal, uv.y band widths up,
        // one band width = ringWidthPx pixels at the vertex's depth (ring.vert).
        Model {
            id: selectionRing
            visible: root.selectionVisible && geometry !== null
            pickable: false
            castsShadows: false
            receivesShadows: false
            materials: CustomMaterial {
                property vector3d uColor: root.selectionColorLinear
                // centimetres per unit of depth (perspective) / centimetres flat (top-down)
                property real uPerDepth: root.topDown ? 0.0
                    : root.ringWidthPx * 2.0 * Math.tan(root.camFov * Math.PI / 360.0)
                      / Math.max(root.pictureHeight, 1.0)
                property real uFlat: root.topDown ? root.ringWidthPx / root.topDownScale : 0.0
                property real uDepthScale: root.ringDepthScale
                shadingMode: CustomMaterial.Unshaded
                cullMode: Material.NoCulling
                vertexShader: "ring.vert"
                fragmentShader: "ring.frag"
            }
        }

        // The analysis overlays (L2, #386): unlit vertex colour - the 2D maps' own
        // colours, in linear light - no shadows, never picked (a click on a drape meets
        // the ground or the item under it). Not children of `parts`: listParts() and
        // the sink's teardown never see them. overlay.frag divides by the exposure, so a
        // colour reads the same from noon to night; the shade's is a multiplier (1).
        Model {
            id: shadeOverlay
            visible: root.shadeVisible && geometry !== null
            pickable: false
            castsShadows: false
            receivesShadows: false
            materials: CustomMaterial {
                property real uExposure: 1.0
                property vector3d uDomeCenter: root.groundCenter
                property real uArcPerDepth: 0.0
                property real uArcFlat: 0.0
                shadingMode: CustomMaterial.Unshaded
                cullMode: Material.NoCulling
                depthDrawMode: Material.NeverDepthDraw
                // the 2D shadows MULTIPLY the frame under them (vertex colour = the
                // multiplier, drape.SHADE_MULTIPLIER): darker in every mood, never lighter
                // - over-blended, the unlit shadow colour went through night's exposure 2.4
                // and turned the night garden lighter (3D review of #386, PF-L3D-06)
                sourceBlend: CustomMaterial.DstColor
                destinationBlend: CustomMaterial.Zero
                sourceAlphaBlend: CustomMaterial.Zero
                destinationAlphaBlend: CustomMaterial.One
                vertexShader: "overlay.vert"
                fragmentShader: "overlay.frag"
            }
        }
        Model {
            id: drapeOverlay
            visible: root.drapeVisible && geometry !== null
            pickable: false
            castsShadows: false
            receivesShadows: false
            materials: CustomMaterial {
                shadingMode: CustomMaterial.Unshaded
                cullMode: Material.NoCulling
                // translucent like the canvas's overlays, and it writes no depth: a
                // drape above the ground must not hide what stands on it
                depthDrawMode: Material.NeverDepthDraw
                sourceBlend: CustomMaterial.SrcAlpha
                destinationBlend: CustomMaterial.OneMinusSrcAlpha
                // the frame's ALPHA is left as it is (1): blended with the colour factors it
                // became 1 - a(1 - a), and the view's texture let the window's white through -
                // measured: black at a = 0.5 read 64 grey levels too bright over the meadow
                sourceAlphaBlend: CustomMaterial.Zero
                destinationAlphaBlend: CustomMaterial.One
                property real uExposure: root.topDown ? 1.0 : root.exposure
                property vector3d uDomeCenter: root.groundCenter
                property real uArcPerDepth: 0.0
                property real uArcFlat: 0.0
                vertexShader: "overlay.vert"
                fragmentShader: "overlay.frag"
            }
        }
        Model {
            id: linesOverlay
            visible: root.linesVisible && geometry !== null
            pickable: false
            castsShadows: false
            receivesShadows: false
            materials: CustomMaterial {
                property real uExposure: root.topDown ? 1.0 : root.exposure
                property vector3d uDomeCenter: root.groundCenter
                property real uArcPerDepth: root.topDown ? 0.0
                    : 2.5 * 2.0 * Math.tan(root.camFov * Math.PI / 360.0)
                      / Math.max(root.pictureHeight, 1.0)
                property real uArcFlat: root.topDown ? 2.5 / root.topDownScale : 0.0
                shadingMode: CustomMaterial.Unshaded
                cullMode: Material.NoCulling
                depthDrawMode: Material.NeverDepthDraw
                sourceBlend: CustomMaterial.SrcAlpha
                destinationBlend: CustomMaterial.OneMinusSrcAlpha
                sourceAlphaBlend: CustomMaterial.Zero
                destinationAlphaBlend: CustomMaterial.One
                vertexShader: "overlay.vert"
                fragmentShader: "overlay.frag"
            }
        }

        // ---- the living garden (Phase 17 L5, #389, ADR-070) ----
        // Two Models for the life of the scene, like the overlays: Python loads each
        // one's geometry (core/scene3d/particles.py) and the look says what shows. No
        // weather change, no date and no time of day creates or destroys a Model. The
        // wind's clock moves both (windTime): reduced motion rests it at 0, and a
        // still frame is a photograph. Unlit, blended, no depth written, never picked,
        // no shadows - and never in the top-down truth view.
        Model {
            id: precipitation
            visible: root.precipKind > 0 && root.precipDensity > 0.0 && !root.topDown
                     && geometry !== null
            pickable: false
            castsShadows: false
            receivesShadows: false
            materials: CustomMaterial {
                property real uTime: root.windTime
                property real uKind: root.precipKind
                property real uDensity: root.precipDensity
                property vector3d uCenter: root.volumeCenter
                property real uSize: root.volumeSize
                property real uHeight: root.volumeHeight
                property vector3d uDrift: root.windDrift
                property vector3d uLight: root.particleLight
                property real uPerDepth: root.particlePerDepth
                shadingMode: CustomMaterial.Unshaded
                cullMode: Material.NoCulling
                depthDrawMode: Material.NeverDepthDraw
                sourceBlend: CustomMaterial.SrcAlpha
                destinationBlend: CustomMaterial.OneMinusSrcAlpha
                sourceAlphaBlend: CustomMaterial.Zero
                destinationAlphaBlend: CustomMaterial.One
                vertexShader: "precipitation.vert"
                fragmentShader: "precipitation.frag"
            }
        }
        Model {
            id: ambientLife
            visible: root.ambientVisible && !root.topDown && geometry !== null
            pickable: false
            castsShadows: false
            receivesShadows: false
            materials: CustomMaterial {
                property real uTime: root.windTime
                property vector3d uDrift: root.windDrift
                property vector3d uLight: root.particleLight
                property real uPerDepth: root.particlePerDepth
                // the life is switched off with the strip's switch; the bulbs are not life
                property real uLeaves: root.lifeEnabled ? root.leafLife : 0.0
                property real uButterflies: root.lifeEnabled ? root.butterflyLife : 0.0
                property real uFireflies: root.lifeEnabled ? root.fireflyLife : 0.0
                property real uLamps: root.lampGlow
                shadingMode: CustomMaterial.Unshaded
                cullMode: Material.NoCulling
                depthDrawMode: Material.NeverDepthDraw
                sourceBlend: CustomMaterial.SrcAlpha
                destinationBlend: CustomMaterial.OneMinusSrcAlpha
                sourceAlphaBlend: CustomMaterial.Zero
                destinationAlphaBlend: CustomMaterial.One
                vertexShader: "ambient.vert"
                fragmentShader: "ambient.frag"
            }
        }
        // The garden lights that LIGHT (L5.4): a fixed pool of lampSlots point lights,
        // made once when the scene loads (lampPool, below) - a light that comes and goes
        // changes every lit material's shader, so only the lamps the plan has are
        // visible, and only after dusk. Their places come from Python
        // (Quick3DHost.set_lamps): the nearest lamps to the camera's target. No shadows
        // (a point light's shadow is six maps). Not a Repeater3D: its slots are fixed.
        Component {
            id: lampLight
            PointLight {
                property int slot: 0
                readonly property var spot: slot < root.lamps.length ? root.lamps[slot] : null
                visible: spot !== null && root.lampGlow > 0.0 && !root.topDown
                position: spot ? Qt.vector3d(spot.x, spot.y, spot.z) : Qt.vector3d(0, 0, 0)
                color: root.lampColor
                brightness: spot ? spot.w * root.lampGlow * root.lampBrightness : 0.0
                castsShadow: false
                constantFade: root.lampNear
                linearFade: 0.0
                quadraticFade: root.lampFade
            }
        }
        Node {
            id: lampPool
            Component.onCompleted: {
                for (var i = 0; i < root.lampSlots; ++i)
                    lampLight.createObject(lampPool, {"slot": i})
            }
        }

        // Pre-warm screen-door shader pipelines (Issue #582): compile PSOs on
        // initial load so the first Cutaway / X-ray toggle does not freeze the GUI thread.
        // uOpacity: 0.0 discards all fragments, casting and receiving no shadows,
        // producing 0 visual pixels, while ensuring the GPU pipeline is compiled.
        Node {
            id: shaderWarmer
            position: root.groundCenter
            scale: Qt.vector3d(0.0001, 0.0001, 0.0001)

            Model {
                source: "#Rectangle"
                pickable: false
                castsShadows: false
                receivesShadows: false
                materials: CustomMaterial {
                    property vector3d uTint: Qt.vector3d(1, 1, 1)
                    property real uOpacity: 0.0
                    property real uRough: 0.78
                    property real uSpecular: 0.35
                    shadingMode: CustomMaterial.Shaded
                    cullMode: Material.NoCulling
                    vertexShader: "screen.vert"
                    fragmentShader: "screen.frag"
                }
            }
            Model {
                source: "#Rectangle"
                pickable: false
                castsShadows: false
                receivesShadows: false
                materials: CustomMaterial {
                    property vector3d uTint: Qt.vector3d(1, 1, 1)
                    property real uLeafDensity: 1.0
                    property real uSnow: 0.0
                    property real uWet: 0.0
                    property real uTime: 0.0
                    property real uWind: 0.0
                    property real uOpacity: 0.0
                    shadingMode: CustomMaterial.Shaded
                    cullMode: Material.NoCulling
                    vertexShader: "foliage_door.vert"
                    fragmentShader: "foliage_door.frag"
                }
            }
            Model {
                source: "#Rectangle"
                pickable: false
                castsShadows: false
                receivesShadows: false
                materials: CustomMaterial {
                    property vector3d uTint: Qt.vector3d(1, 1, 1)
                    property real uLeafDensity: 1.0
                    property real uSnow: 0.0
                    property real uWet: 0.0
                    property real uTime: 0.0
                    property real uWind: 0.0
                    property real uOpacity: 0.0
                    shadingMode: CustomMaterial.Shaded
                    cullMode: Material.NoCulling
                    vertexShader: "grass_door.vert"
                    fragmentShader: "foliage_door.frag"
                }
            }
            Model {
                source: "#Rectangle"
                pickable: false
                castsShadows: false
                receivesShadows: false
                materials: CustomMaterial {
                    property TextureInput uFill: TextureInput { texture: null }
                    property real uHasFill: 0.0
                    property vector3d uTint: Qt.vector3d(1, 1, 1)
                    property real uBody: 0.5
                    property real uReflect: 0.15
                    property real uRough: 0.02
                    property real uOpacity: 0.0
                    shadingMode: CustomMaterial.Shaded
                    vertexShader: "screen.vert"
                    fragmentShader: "water_door.frag"
                }
            }
        }
    }

    // the capture view (see "the capture view" above): under the view, which covers it
    View3D {
        id: captureView
        z: -1
        visible: root.captureWanted
        width: root.captureWidth / root.capturePixelRatio
        height: root.captureHeight / root.capturePixelRatio
        explicitTextureWidth: root.captureWidth
        explicitTextureHeight: root.captureHeight
        importScene: view.scene
        camera: view.camera
        environment: view.environment
    }
}
