// The garden in Qt Quick 3D (Phase 17 L1.2, ADR-048). Ported from the L0 spike's
// GardenSpike.qml: what L1.2 keeps is its measured core — frame, light, shadows,
// materials, picking. Looks by sun elevation, the procedural sky, fog, presets and
// post effects are L1.4; the baked ground texture is L1.5.
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
    property color sunColor: "#fff1dc"
    property real sunBrightness: 1.9
    property color fillColor: "#778cab"     // flat fill: stands in for the sky's light until L1.4
    property real exposure: 0.85
    property color skyColor: "#cfe2f2"
    property color meadowColor: "#487f34"   // ONE albedo for the meadow and for bare plan ground
    property real windStrength: 2.5
    // the shaders' clock, in seconds; nothing animates it before L1.4. At 0 the wind is
    // at REST: every vertex is exactly where its mesh puts it (the shaders ease the sway
    // in over the first two seconds), so what is drawn is what the CPU measured.
    // ONLY at 0: a clock paused anywhere else leaves the sway in the frame. A truth
    // probe pins windTime to 0 (or windStrength to 0); "paused" is not "at rest".
    property real windTime: 0

    // ---- sun (Quick3DSink.set_sun): direction only, from core/solar ----
    property bool sunUp: false              // false until the first sun, and whenever it is down
    property quaternion sunRotation: Qt.quaternion(1, 0, 0, 0)   // rotates -Z onto the light's travel

    // ---- ground (Quick3DSink.set_ground) ----
    property bool groundVisible: false
    property vector3d groundCenter: Qt.vector3d(0, 0, 0)
    property real groundWidth: 1000         // along x (East), cm
    property real groundDepth: 1000         // along z (North), cm
    // true while baked tiles lie on the plan (quick3d/ground_tiles.py, L1.5): the bare
    // rectangle below is then not drawn — two coplanar surfaces would fight for the depth
    property bool groundTiled: false

    // ---- camera (Quick3DHost.set_shot) ----
    property bool topDown: false
    property vector3d camPos: Qt.vector3d(0, 1000, 2000)
    property vector3d camTarget: Qt.vector3d(0, 0, 0)
    property real camFov: 40
    property int camVersion: 0
    property real topDownScale: 0.5         // logical pixels per centimetre

    onCamVersionChanged: {
        cam.position = camPos
        cam.lookAt(camTarget)
    }

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
            out.push({
                "id": p.itemId, "part": p.partIndex, "kind": p.kind,
                "x": p.position.x, "y": p.position.y, "z": p.position.z,
                "yaw": p.eulerRotation.y,
                "r": p.tint.r, "g": p.tint.g, "b": p.tint.b,
                "casts": p.castsShadows, "geometry": p.geometry !== null,
                "visible": p.visible
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
        var r = view.pick(x, y)
        if (!r.objectHit)
            return {"hit": false}
        return {
            "hit": true, "id": r.objectHit.itemId || "",
            "part": r.objectHit.partIndex === undefined ? -1 : r.objectHit.partIndex,
            "x": r.scenePosition.x, "y": r.scenePosition.y, "z": r.scenePosition.z
        }
    }

    // ---- one Component per material kind: a Model with its OWN material instance ----
    // albedo = vertex colour x tint (linear) for every kind. `tint` is the sRGB colour
    // the principled materials take; `tintLinear` the same in linear light for the
    // custom shaders (computed in Python with the exact sRGB curve). `retired` marks a
    // Model that was destroyed and waits for its deferred delete: `visible` stays free
    // for a story that hides a Model on purpose.
    Component {
        id: vcPart
        Model {
            property string itemId
            property int partIndex: 0
            property string kind
            property color tint: "#ffffff"
            property vector3d tintLinear: Qt.vector3d(1, 1, 1)
            property bool retired: false   // set by destroyPart(); never a reason to hide
            receivesShadows: true
            pickable: true
            materials: PrincipledMaterial {
                vertexColorsEnabled: true
                baseColor: tint
                roughness: 0.78
                specularAmount: 0.35
            }
        }
    }
    Component {
        id: roofPart
        Model {
            property string itemId
            property int partIndex: 0
            property string kind
            property color tint: "#ffffff"
            property vector3d tintLinear: Qt.vector3d(1, 1, 1)
            property bool retired: false   // set by destroyPart(); never a reason to hide
            receivesShadows: true
            pickable: true
            // roof tiles and shingles (ogp-lush-cinematic 4: roughness 0.70-0.85)
            materials: PrincipledMaterial {
                vertexColorsEnabled: true
                baseColor: tint
                roughness: 0.80
                specularAmount: 0.15
            }
        }
    }
    Component {
        id: glassPart
        Model {
            property string itemId
            property int partIndex: 0
            property string kind
            property color tint: "#ffffff"
            property vector3d tintLinear: Qt.vector3d(1, 1, 1)
            property bool retired: false   // set by destroyPart(); never a reason to hide
            receivesShadows: true
            pickable: true
            materials: PrincipledMaterial {
                vertexColorsEnabled: true
                baseColor: tint
                roughness: 0.04
                metalness: 0.0
                specularAmount: 1.0
                opacity: 0.28
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
            property color tint: "#ffffff"
            property vector3d tintLinear: Qt.vector3d(1, 1, 1)
            property bool retired: false   // set by destroyPart(); never a reason to hide
            receivesShadows: true
            pickable: true
            // a custom shader keeps the water's hue in every mood; see water.frag for why
            // this is not a PrincipledMaterial (measured in the spike: lavender at golden hour)
            materials: CustomMaterial {
                property vector3d uTint: tintLinear
                property real uBody: 0.5      // = the principled diffuse's (1 - specularAmount)
                property real uReflect: 0.15
                // a crisp sun glint: 0.3 blew it over the pond, 0.05 still clipped ~23 %
                // of the visible pond at morning (spike, creator round 2)
                property real uRough: 0.02
                shadingMode: CustomMaterial.Shaded
                fragmentShader: "water.frag"
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
            materials: PrincipledMaterial {
                baseColorMap: Texture {
                    textureData: tileData
                    flipV: true
                    tilingModeHorizontal: Texture.ClampToEdge
                    tilingModeVertical: Texture.ClampToEdge
                    generateMipmaps: true
                    mipFilter: Texture.Linear
                }
                // the endless meadow's values (below): PrincipledMaterial scales the
                // sky's diffuse light by (1 - specularAmount), so any other pair puts a
                // luma step where a baked lawn meets the meadow at the plan's edge
                // (the L1.4 look review measured 2-8 luma for 0.92 / 0.2)
                roughness: 1.0
                specularAmount: 0.15
            }
        }
    }
    Component {
        id: foliagePart
        Model {
            property string itemId
            property int partIndex: 0
            property string kind
            property color tint: "#ffffff"
            property vector3d tintLinear: Qt.vector3d(1, 1, 1)
            property bool retired: false   // set by destroyPart(); never a reason to hide
            receivesShadows: true
            pickable: true
            materials: CustomMaterial {
                property vector3d uTint: tintLinear
                property real uTime: root.windTime
                property real uWind: root.windStrength * 0.35
                shadingMode: CustomMaterial.Shaded
                cullMode: Material.NoCulling
                vertexShader: "foliage.vert"
                fragmentShader: "foliage.frag"
            }
        }
    }
    Component {
        id: grassPart
        Model {
            property string itemId
            property int partIndex: 0
            property string kind
            property color tint: "#ffffff"
            property vector3d tintLinear: Qt.vector3d(1, 1, 1)
            property bool retired: false   // set by destroyPart(); never a reason to hide
            receivesShadows: true
            pickable: true
            materials: CustomMaterial {
                property vector3d uTint: tintLinear
                property real uTime: root.windTime
                property real uWind: root.windStrength
                shadingMode: CustomMaterial.Shaded
                cullMode: Material.NoCulling
                vertexShader: "grass.vert"
                fragmentShader: "foliage.frag"
            }
        }
    }

    View3D {
        id: view
        anchors.fill: parent
        camera: root.topDown ? topCam : cam

        // The top-down view is the TRUTH view: no tone mapping, so a pixel is the
        // surface's linear radiance (albedo x light) and a probe can predict it. The
        // perspective view is the one people look at: filmic, exposed by the look.
        //
        // ExtendedSceneEnvironment only for its `exposure` (the plain SceneEnvironment
        // has none): every effect it offers stays off until L1.4's presets. No
        // sharpening ever - 0.08 overshot thin lit edges into near-black dots (spike).
        environment: ExtendedSceneEnvironment {
            backgroundMode: SceneEnvironment.Color
            clearColor: root.skyColor
            tonemapMode: root.topDown ? SceneEnvironment.TonemapModeNone
                                      : SceneEnvironment.TonemapModeFilmic
            exposure: root.topDown ? 1.0 : root.exposure
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
            sharpnessAmount: 0.0
        }

        PerspectiveCamera {
            id: cam
            fieldOfView: root.camFov
            clipNear: 5
            clipFar: 80000
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

        // The sun. A DirectionalLight shines down its local -Z; Python hands over the
        // rotation that puts -Z onto the light's travel (= -sun vector, core/solar).
        // Shadow settings: the spike's High preset, the ones behind its shadow-IoU table
        // (ogp-3d-renderer 4) - but no cascades in the orthographic view, as there.
        DirectionalLight {
            id: sun
            visible: root.sunUp
            rotation: root.sunRotation
            color: root.sunColor
            brightness: root.sunBrightness
            ambientColor: Qt.rgba(0, 0, 0, 1)
            castsShadow: true
            shadowFactor: 82
            shadowMapQuality: Light.ShadowMapQualityVeryHigh
            csmNumSplits: root.topDown ? 0 : 2
            csmBlendRatio: 0.05
            softShadowQuality: Light.PCF16
            pcfFactor: 2.0
            shadowBias: 5
            shadowMapFar: 9000
            lockShadowmapTexels: true
        }
        // The fill: no direct light of its own, only the flat ambient term. Separate
        // from the sun so a night (sun switched off) is dim, not black.
        DirectionalLight {
            brightness: 0
            ambientColor: root.fillColor
            castsShadow: false
        }

        // endless meadow (4 x 4 km, past the 800 m far plane), 1 cm under the plan
        Model {
            source: "#Rectangle"
            position: Qt.vector3d(root.groundCenter.x, -1.0, root.groundCenter.z)
            eulerRotation.x: -90
            scale: Qt.vector3d(4000, 4000, 1)
            receivesShadows: true
            castsShadows: false
            materials: PrincipledMaterial {
                baseColor: root.meadowColor
                roughness: 1.0
                specularAmount: 0.15
            }
        }

        // the plan rectangle, bare: ground in the meadow's albedo. Drawn only while no
        // baked tiles lie on the plan (L1.5: the groundTile component above).
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
                roughness: 0.92
                specularAmount: 0.2
            }
        }

        Node { id: groundTiles }
        Node { id: parts }
    }
}
