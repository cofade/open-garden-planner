// Reproducer: with glow on, an ExtendedSceneEnvironment whose chain has two effects
// ahead of its own scene (tonemapper) effect crashes the render thread on Direct3D 11.
//
// Run:   qml effect_chain_glow_crash.qml
// Args:  qml effect_chain_glow_crash.qml -- [--no-glow] [--no-ssr] [--no-dof] [--seconds=N]
//
// The scene is one cube on a plane. The environment enables screen-space reflections,
// depth of field and glow. Nothing else is set.
//
// Expected: the window shows the cube, and after N seconds (default 3) the file prints
//           "ALIVE" and quits.
// Actual (Qt 6.12.0, Windows 11, Direct3D 11, NVIDIA RTX 4070 and WARP not tested):
//           the process dies at the first frame with an access violation in d3d11.dll
//           (CContext::OMSetRenderTargets), no "ALIVE" line and no Qt warning.
//
// Each flag below removes one of the three; with any one removed the file prints ALIVE.
// Any two effects ahead of the scene effect break it, not only these two: two
// pass-through user Effects with glow gave a wrong picture (grey, the scene gone), and
// reflections plus one user Effect with glow crashed or gave a black picture.

import QtQuick
import QtQuick3D
import QtQuick3D.Helpers

Window {
    id: win
    width: 640
    height: 360
    visible: true
    title: "SSR + depth of field + glow"

    property bool glow: !hasArg("--no-glow")
    property bool reflections: !hasArg("--no-ssr")
    property bool depthOfField: !hasArg("--no-dof")
    property int seconds: intArg("--seconds=", 3)

    function hasArg(name) {
        return Qt.application.arguments.indexOf(name) >= 0
    }
    function intArg(prefix, fallback) {
        const args = Qt.application.arguments
        for (let i = 0; i < args.length; ++i) {
            if (args[i].startsWith(prefix))
                return parseInt(args[i].substring(prefix.length))
        }
        return fallback
    }

    View3D {
        anchors.fill: parent
        camera: camera

        environment: ExtendedSceneEnvironment {
            backgroundMode: SceneEnvironment.Color
            clearColor: "#808080"
            tonemapMode: SceneEnvironment.TonemapModeFilmic
            glowEnabled: win.glow
            ssrEnabled: win.reflections
            depthOfFieldEnabled: win.depthOfField
            depthOfFieldFocusDistance: 300
            depthOfFieldFocusRange: 50
            depthOfFieldBlurAmount: 4
        }

        PerspectiveCamera {
            id: camera
            position: Qt.vector3d(0, 40, 300)
        }
        DirectionalLight {
            eulerRotation.x: -45
        }
        Model {
            source: "#Cube"
            eulerRotation: Qt.vector3d(30, 30, 0)
            materials: PrincipledMaterial { baseColor: "red"; roughness: 0.1 }
        }
        Model {
            source: "#Rectangle"
            y: -60
            eulerRotation.x: -90
            scale: Qt.vector3d(5, 5, 1)
            materials: PrincipledMaterial { baseColor: "white"; roughness: 0.05 }
        }
    }

    Timer {
        interval: win.seconds * 1000
        running: true
        onTriggered: {
            console.log("ALIVE after " + win.seconds + " s: glow=" + win.glow + " ssr="
                        + win.reflections + " dof=" + win.depthOfField)
            Qt.quit()
        }
    }
}
