// The photo blur's bench (#743) — a test fixture, not shipped. Driven by
// view3d_capture_driver.py's ``blur_bench`` scenario. It uses the PRODUCT's PhotoBlur.qml on a
// scene whose answers are known: unlit flat panels, so a colour is exactly its material's.
//
// The camera sits at the origin and looks down -Z (vertical field of view 40 degrees); the
// band is 900..1100 cm around a focus of 1000 cm.
//  - a far wall (2500 cm), dark grey: fully out of focus
//  - a thin white line on that wall: the blur of a 2 cm line, one smooth hump or copies
//  - a white bar in focus (1000 cm) in front of the wall: does its colour reach the wall?
//  - a light panel in focus with a dark bar near the camera (400 cm) in front of it: is the
//    blurred bar's edge soft against the sharp panel, and does the panel light the bar's rim?
import QtQuick
import QtQuick3D
import QtQuick3D.Helpers
import "../../src/open_garden_planner/ui/view3d/quick3d/qml"

Item {
    id: bench
    width: 640
    height: 360
    property int pictureWidth: 640
    property int pictureHeight: 360
    property bool blurOn: false

    View3D {
        objectName: "bench"
        width: bench.pictureWidth
        height: bench.pictureHeight
        explicitTextureWidth: bench.pictureWidth
        explicitTextureHeight: bench.pictureHeight
        camera: camera

        environment: ExtendedSceneEnvironment {
            backgroundMode: SceneEnvironment.Color
            clearColor: "black"
            tonemapMode: SceneEnvironment.TonemapModeLinear
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
            effects: bench.blurOn ? [blur] : []
        }
        PhotoBlur {
            id: blur
            focusDistance: 1000
            focusRange: 200
            blurShare: 0.006
        }
        PerspectiveCamera {
            id: camera
            fieldOfView: 40
            clipNear: 5
            clipFar: 1600000
        }
        Model {
            source: "#Rectangle"
            z: -2500
            scale: Qt.vector3d(40, 25, 1)
            materials: PrincipledMaterial { lighting: PrincipledMaterial.NoLighting; baseColor: "#404040" }
        }
        Model {
            source: "#Rectangle"
            x: 600
            z: -2499
            scale: Qt.vector3d(0.02, 6, 1)
            materials: PrincipledMaterial { lighting: PrincipledMaterial.NoLighting; baseColor: "white" }
        }
        Model {
            source: "#Rectangle"
            x: -150
            z: -1000
            scale: Qt.vector3d(0.6, 4, 1)
            materials: PrincipledMaterial { lighting: PrincipledMaterial.NoLighting; baseColor: "white" }
        }
        Model {
            source: "#Rectangle"
            x: 120
            y: -150
            z: -1000
            scale: Qt.vector3d(3, 1.6, 1)
            materials: PrincipledMaterial { lighting: PrincipledMaterial.NoLighting; baseColor: "#c0c0c0" }
        }
        Model {
            source: "#Rectangle"
            x: 40
            y: -60
            z: -400
            scale: Qt.vector3d(0.12, 0.8, 1)
            materials: PrincipledMaterial { lighting: PrincipledMaterial.NoLighting; baseColor: "#101010" }
        }
    }
}
