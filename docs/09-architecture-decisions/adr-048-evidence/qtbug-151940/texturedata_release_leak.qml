// Reproducer: QQuickWindow::releaseResources() leaks about half of the
// same-size QQuick3DTextureData textures (QSSGBufferManager::clear()).
//
// Run:   qml texturedata_release_leak.qml
// Args:  qml texturedata_release_leak.qml -- [--count=N] [--size=PX] [--cycles=N]
//                                            [--distinct-sizes] [--no-release]
//
// The scene shows N quads. Each quad has its own ProceduralTextureData. By
// default all textures have the same size and format. Nothing in the scene
// changes. Each cycle calls QQuickWindow::releaseResources() and then moves the
// camera a little, so that the next frame loads the textures again.
//
// Each cycle prints the number of textures registered with the render context
// (the rows of RenderStats.textureDetails) and RenderStats.imageDataSize.
// Expected: both values stay the same after each cycle.
// Actual (Qt 6.11.0, 6.12.0): both values grow by about N/2 textures per cycle.
// The textures that clear() skips stay registered until the QSSGRhiContext is
// destroyed.
//
// The window must be visible and presented (not minimized or covered, no locked
// screen, display not asleep). A cycle in which no frame was rendered prints
// "INVALID".

import QtQuick
import QtQuick3D
import QtQuick3D.Helpers // ProceduralTextureData

Window {
    id: win
    width: 640
    height: 640
    visible: true
    title: "releaseResources() texture leak"

    property int textureCount: intArg("--count=", 16)
    property int textureSize: intArg("--size=", 512)
    property int cycles: intArg("--cycles=", 10)
    property bool distinctSizes: hasArg("--distinct-sizes")
    property bool releaseEachCycle: !hasArg("--no-release")

    property int tick: 0
    property int cycle: 0
    property bool cyclePending: false
    property int baselineRows: -1
    property real baselineBytes: 0
    property int swaps: 0
    property int swapsAtRelease: 0

    onFrameSwapped: ++swaps

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

    function makePixels(w, h, index) {
        const buffer = new ArrayBuffer(w * h * 4)
        // One opaque colour per texture (little-endian RGBA8 -> 0xAABBGGRR).
        const r = (index * 53) % 256, g = (index * 97) % 256, b = (index * 151) % 256
        new Uint32Array(buffer).fill((0xff << 24 | b << 16 | g << 8 | r) >>> 0)
        return buffer
    }

    function registeredTextureRows() {
        // One table row per QRhiTexture in QSSGRhiContextPrivate::m_textures.
        const lines = view.renderStats.textureDetails.split("\n")
        let rows = 0
        for (const line of lines) {
            if (line.startsWith("| ") && !line.startsWith("| Name") && !line.startsWith("| ----"))
                ++rows
        }
        return rows
    }

    function report(label) {
        const rows = registeredTextureRows()
        const bytes = view.renderStats.imageDataSize
        console.log("LEAKTEST " + label
                    + " registeredTextures=" + rows
                    + " growthTextures=" + (rows - baselineRows)
                    + " imageDataSizeMiB=" + (bytes / 1048576).toFixed(2)
                    + " growthMiB=" + ((bytes - baselineBytes) / 1048576).toFixed(2)
                    + " framesRendered=" + swaps)
    }

    View3D {
        id: view
        anchors.fill: parent
        renderStats.extendedDataCollectionEnabled: true

        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.Color
            clearColor: "black"
        }

        PerspectiveCamera {
            id: camera
            z: 600
        }

        Repeater3D {
            model: win.textureCount
            delegate: Model {
                required property int index
                readonly property int columns: Math.ceil(Math.sqrt(win.textureCount))
                source: "#Rectangle"
                scale: Qt.vector3d(0.9 * 4 / columns, 0.9 * 4 / columns, 1)
                x: ((index % columns) - (columns - 1) / 2) * 400 / columns
                y: (Math.floor(index / columns) - (columns - 1) / 2) * 400 / columns
                materials: PrincipledMaterial {
                    lighting: PrincipledMaterial.NoLighting
                    baseColorMap: Texture {
                        textureData: ProceduralTextureData {
                            width: win.distinctSizes ? win.textureSize + index : win.textureSize
                            height: win.textureSize
                            format: TextureData.RGBA8
                            textureData: win.makePixels(width, height, index)
                        }
                    }
                }
            }
        }
    }

    Timer {
        interval: 250
        repeat: true
        running: true
        onTriggered: {
            ++win.tick
            if (win.baselineRows < 0) {
                // Wait until the first frames have uploaded every texture (at most 10 s).
                const uploaded = win.registeredTextureRows() >= win.textureCount && win.swaps >= 2
                if (win.tick < 4 || (!uploaded && win.tick < 40))
                    return
                if (!uploaded)
                    console.log("LEAKTEST INVALID: after 10 s only " + win.registeredTextureRows()
                                + " of " + win.textureCount + " textures are registered and "
                                + win.swaps + " frame(s) were rendered. Is the window visible?")
                win.baselineRows = win.registeredTextureRows()
                win.baselineBytes = view.renderStats.imageDataSize
                console.log("LEAKTEST config api=" + view.renderStats.graphicsApiName
                            + " textures=" + win.textureCount
                            + " size=" + win.textureSize
                            + " distinctSizes=" + win.distinctSizes
                            + " release=" + win.releaseEachCycle)
                win.report("baseline")
                return
            }
            if (!win.cyclePending) {
                win.swapsAtRelease = win.swaps
                if (win.releaseEachCycle)
                    win.releaseResources()
                camera.z = camera.z === 600 ? 600.5 : 600 // forces a new frame
                win.cyclePending = true
            } else {
                win.cyclePending = false
                ++win.cycle
                if (win.swaps === win.swapsAtRelease)
                    console.log("LEAKTEST INVALID: no frame was rendered in cycle " + win.cycle
                                + ", so its numbers do not show a reload. Is the window visible?")
                win.report("cycle=" + win.cycle)
                if (win.cycle >= win.cycles) {
                    console.log("LEAKTEST done")
                    Qt.quit()
                }
            }
        }
    }
}
