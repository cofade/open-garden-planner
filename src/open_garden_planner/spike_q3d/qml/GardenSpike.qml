// Qt Quick 3D spike scene (ADR-047, Phase 17 L0) — evidence tooling, no UI strings.
// Python drives everything through root properties; the scene is in the ENGINE
// frame (x = East, y = up, z = -North, centimetres) — the mapping happens once
// in quick.py, never here.
import QtQuick
import QtQuick3D
import QtQuick3D.Helpers

Item {
    id: root
    width: 1280
    height: 720

    // ---- inputs set from Python ----
    property var sceneModels: []
    property var groundTexture: null
    property vector3d groundCenter: Qt.vector3d(0, 0, 0)
    property real groundWidth: 1000
    property real groundDepth: 1000
    property string preset: "high"          // low | medium | high | ultra
    property bool night: false
    property real sunElevation: 45          // degrees above horizon
    property real skyLongitude: 0           // ProceduralSkyTextureData convention
    property vector3d sunTravel: Qt.vector3d(0, -1, 0)   // direction light travels
    property quaternion sunRotation: Qt.quaternion(1, 0, 0, 0)  // rotates -Z onto sunTravel
    property color sunColor: "#fff1dc"
    property real sunBrightness: 1.6
    property real probeExposure: 0.9
    property real exposure: 1.0
    property vector3d camPos: Qt.vector3d(0, 1000, 2000)
    property vector3d camTarget: Qt.vector3d(0, 0, 0)
    property real camFov: 40
    property int camVersion: 0
    property int sunVersion: 0
    property bool animate: false
    property real windTime: 0
    property real windStrength: 2.5
    property bool orthoTopDown: false
    property real orthoMagnification: 0.5
    property color clearColor: "#ffffff"
    property color skyTop: "#3d77c7"
    property color skyHorizon: "#c6dcef"
    property color sunDiscColor: "#ffe6c0"
    property color fogColor: "#c9d8e6"
    property color meadowColor: "#487f34"   // set once from runner.MEADOW_ALBEDO (= the bake)
    // linear water albedo, set once from meshes.WATER_ALBEDO (water.png's linear mean)
    property vector3d waterColor: Qt.vector3d(0.0742, 0.2874, 0.5583)
    property bool allowSsgi: false   // SSGI renders black on Mesa llvmpipe (ADR-047 evidence) — opt-in
    property bool allowSsr: true

    onSunVersionChanged: view.rebuildSky()
    onCamVersionChanged: {
        cam.position = camPos
        cam.lookAt(camTarget)
    }

    NumberAnimation on windTime {
        from: 0; to: 3600; duration: 3600000; loops: Animation.Infinite
        running: root.animate
    }

    function projectToView(x, y, z) {
        var p = view.mapFrom3DScene(Qt.vector3d(x, y, z))
        return {"x": p.x, "y": p.y}
    }

    function pickAt(x, y) {
        var r = view.pick(x, y)
        if (!r.objectHit)
            return {"hit": false}
        return {"hit": true, "id": r.objectHit.itemId || "", "x": r.scenePosition.x,
                "y": r.scenePosition.y, "z": r.scenePosition.z}
    }

    View3D {
        id: view
        anchors.fill: parent
        camera: root.orthoTopDown ? topCam : cam

        environment: ExtendedSceneEnvironment {
            id: env
            backgroundMode: root.orthoTopDown ? SceneEnvironment.Color : SceneEnvironment.SkyBox
            clearColor: root.clearColor
            lightProbe: root.orthoTopDown ? null : view.skyTexture
            probeExposure: root.probeExposure
            skyboxBlurAmount: 0.0
            tonemapMode: root.orthoTopDown ? SceneEnvironment.TonemapModeNone
                                            : SceneEnvironment.TonemapModeFilmic
            exposure: root.exposure
            ditheringEnabled: true
            aoEnabled: !root.orthoTopDown && root.preset !== "low"
            aoStrength: 55
            aoDistance: 14
            aoSoftness: 45
            aoSampleRate: root.preset === "ultra" ? 4 : (root.preset === "high" ? 3 : 2)
            glowEnabled: !root.orthoTopDown && root.preset !== "low"
            glowStrength: 1.05
            glowIntensity: 0.55
            glowBloom: 0.18
            glowHDRMinimumValue: 1.1
            glowQualityHigh: root.preset === "ultra"
            fog: Fog {
                // blends the endless meadow into the sky's horizon: the colour is the
                // per-mood fogColor (sky horizon x probe exposure x 0.8, runner.look_for)
                enabled: !root.orthoTopDown && root.preset !== "low"
                color: root.fogColor
                depthEnabled: true
                depthNear: 2600
                depthFar: 16000
                depthCurve: 1.4
                density: 1.0
            }
            antialiasingMode: root.preset === "low" ? SceneEnvironment.NoAA : SceneEnvironment.MSAA
            // low has no MSAA: FXAA (post) + specular AA instead; FXAA stays off in the
            // orthographic probe views so the IoU / orientation probes measure raw pixels
            fxaaEnabled: root.preset === "low" && !root.orthoTopDown
            specularAAEnabled: root.preset === "low"
            antialiasingQuality: root.preset === "ultra" ? SceneEnvironment.VeryHigh
                                                          : SceneEnvironment.High
            ssgiEnabled: root.preset === "ultra" && root.allowSsgi
            ssrEnabled: root.preset === "ultra" && root.allowSsr
            sharpnessAmount: 0.08
            colorAdjustmentsEnabled: true
            adjustmentSaturation: root.night ? 0.85 : 1.06
            adjustmentContrast: 1.04
        }

        // The environment pre-filters its light probe once per Texture OBJECT and
        // does not notice later textureData updates (measured by the spike's sky
        // probe) — so every sun change builds a fresh sky Texture.
        Component {
            id: skyComponent
            Texture {
                textureData: ProceduralSkyTextureData {
                    sunLatitude: root.sunElevation
                    sunLongitude: root.skyLongitude
                    skyTopColor: root.skyTop
                    skyHorizonColor: root.skyHorizon
                    groundBottomColor: root.night ? "#0a0f14" : "#3c4d2e"
                    // the background below the horizon is drawn x probeExposure like the sky
                    // above it, so it meets the fogged meadow without a dark line
                    groundHorizonColor: root.skyHorizon
                    sunColor: root.sunDiscColor
                    skyEnergy: root.night ? 0.25 : 1.0
                    groundEnergy: root.night ? 0.15 : 0.9
                    sunEnergy: root.night ? 0.0 : 1.0
                    textureQuality: ProceduralSkyTextureData.SkyTextureQualityHigh
                }
            }
        }
        property var skyTexture: null
        function rebuildSky() {
            var old = skyTexture
            skyTexture = skyComponent.createObject(view.scene)
            if (old)
                old.destroy()
        }
        Component.onCompleted: rebuildSky()

        PerspectiveCamera {
            id: cam
            fieldOfView: root.camFov
            clipNear: 5
            clipFar: 80000
        }
        OrthographicCamera {
            id: topCam
            position: Qt.vector3d(root.camTarget.x, 4000, root.camTarget.z)
            eulerRotation.x: -90
            horizontalMagnification: root.orthoMagnification
            verticalMagnification: root.orthoMagnification
            clipNear: 1
            clipFar: 10000
        }

        DirectionalLight {
            id: sun
            rotation: root.sunRotation
            color: root.sunColor
            brightness: root.sunBrightness
            ambientColor: Qt.rgba(0, 0, 0, 1)
            castsShadow: true
            shadowFactor: root.night ? 40 : 82
            // low: High + one cascade — Medium without cascades stair-stepped and
            // acned the roof (morning_low, L0 review)
            shadowMapQuality: root.preset === "low" ? Light.ShadowMapQualityHigh
                            : root.preset === "medium" ? Light.ShadowMapQualityHigh
                            : root.preset === "high" ? Light.ShadowMapQualityVeryHigh
                            : Light.ShadowMapQualityUltra
            csmNumSplits: root.orthoTopDown ? 0 : (root.preset === "low" ? 1
                          : root.preset === "medium" ? 1 : (root.preset === "high" ? 2 : 3))
            csmBlendRatio: 0.05
            softShadowQuality: root.preset === "low" ? Light.PCF4
                             : root.preset === "medium" ? Light.PCF8
                             : root.preset === "high" ? Light.PCF16 : Light.PCF32
            pcfFactor: 2.0
            // 1024-texel maps (low, medium) showed acne and a staircase on a sun-grazed roof
            // at bias 5 (morning: 33-40 % of the slope darker than high); 15 measured clean,
            // IoU gate unchanged (low 0.963/0.968/0.937, medium 0.967/0.973/0.937)
            shadowBias: (root.preset === "low" || root.preset === "medium") ? 15 : 5
            shadowMapFar: 9000
            lockShadowmapTexels: true
        }

        // endless meadow (4 x 4 km, past the 800 m far plane) so the horizon never shows the
        // sky's ground hemisphere; same albedo as the baked plan ground
        Model {
            source: "#Rectangle"
            position: Qt.vector3d(root.groundCenter.x, -1.0, root.groundCenter.z)
            eulerRotation.x: -90
            scale: Qt.vector3d(4000, 4000, 1)
            receivesShadows: true
            castsShadows: false
            visible: !root.orthoTopDown
            materials: PrincipledMaterial {
                baseColor: root.meadowColor
                roughness: 1.0
                specularAmount: 0.15
            }
        }

        // the plan's flat surfaces (lawn, terrace, paths, beds) baked from the 2D renderer
        Model {
            id: ground
            source: "#Rectangle"
            position: Qt.vector3d(root.groundCenter.x, 0, root.groundCenter.z)
            eulerRotation.x: -90
            scale: Qt.vector3d(root.groundWidth / 100, root.groundDepth / 100, 1)
            receivesShadows: true
            castsShadows: false
            visible: root.groundTexture !== null
            materials: PrincipledMaterial {
                baseColorMap: Texture {
                    textureData: root.groundTexture ? root.groundTexture : null
                    flipV: true   // texture rows are north-up; pinned by the orientation probe
                    generateMipmaps: true
                    mipFilter: Texture.Linear
                }
                roughness: 0.92
                specularAmount: 0.2
            }
        }

        PrincipledMaterial { id: vcMat; vertexColorsEnabled: true; roughness: 0.78; specularAmount: 0.35 }
        PrincipledMaterial {
            id: whiteMat
            baseColor: "#ffffff"; roughness: 1.0; specularAmount: 0.0
            lighting: PrincipledMaterial.FragmentLighting
        }
        PrincipledMaterial {
            id: glassMat
            baseColor: "#dcf0f7"; roughness: 0.04; metalness: 0.0; specularAmount: 1.0
            opacity: 0.28; alphaMode: PrincipledMaterial.Blend; cullMode: Material.NoCulling
            depthDrawMode: Material.NeverDepthDraw
        }
        CustomMaterial {
            // the pond keeps the 2D water hue in every mood; see water.frag for why
            // this is not a PrincipledMaterial (measured: lavender at golden hour)
            id: waterMat
            property vector3d uWater: root.waterColor
            property real uBody: 0.5      // = the principled IBL diffuse's (1 - specularAmount)
            property real uReflect: 0.15  // bench board: golden hour 212.7 deg, noon 197.3 (2D 205.5)
            property real uRough: 0.05    // a crisp sun glint (0.3 blew it over the pond)
            shadingMode: CustomMaterial.Shaded
            fragmentShader: "water.frag"
        }
        CustomMaterial {
            id: foliageMat
            property real uTime: root.windTime
            property real uWind: root.windStrength * 0.35
            shadingMode: CustomMaterial.Shaded
            cullMode: Material.NoCulling
            vertexShader: "foliage.vert"
            fragmentShader: "foliage.frag"
        }
        CustomMaterial {
            id: grassMat
            property real uTime: root.windTime
            property real uWind: root.windStrength
            shadingMode: CustomMaterial.Shaded
            cullMode: Material.NoCulling
            vertexShader: "grass.vert"
            fragmentShader: "foliage.frag"
        }

        Repeater3D {
            model: root.sceneModels
            delegate: Model {
                property string itemId: modelData.itemId
                geometry: modelData.geometry
                castsShadows: modelData.castsShadows
                receivesShadows: true
                pickable: true
                materials: [modelData.kind === "foliage" ? foliageMat
                          : modelData.kind === "grass" ? grassMat
                          : modelData.kind === "glass" ? glassMat
                          : modelData.kind === "water" ? waterMat
                          : modelData.kind === "white" ? whiteMat
                          : vcMat]
            }
        }
    }
}
