// Photo mode's depth of field (#743, ADR-072 addendum): a picture-relative Gaussian blur,
// weighted by how far each pixel lies out of the sharp band. It replaces Qt's
// depthOfField*, which blurred a HALF-resolution copy with three taps 0.53 x amount pixels
// apart: about 2 px at any picture size, so a 4K save was much sharper than the pane that
// previewed it (gradient ratio 0.53 in the pane, 0.92 in the save), the taps read as copies
// above 1080p's amount, an in-focus edge's colour bled into the blurred wall behind it, and a
// blurred bar kept its hard edge against a sharp panel.
//
// What it does, per picture, at the picture's own size. Out of focus ("amount", 0 inside the
// band, 1 one band beyond its edge) splits what lies BEHIND the band from what lies IN FRONT
// of it into two layers, and each layer is blurred at two sizes: sigma (the full blur) and a
// third of it (what lies just outside the band; lerping a sharp pixel with the full blur drew
// sharp leaves inside a haze). Each blur takes a layer's linear colour PREMULTIPLIED by its
// weight, so averaging leaves out whatever is not in that layer - an in-focus leaf's colour
// never reaches the blurred roof behind it - and blurring premultiplied colour is exact
// separable Gaussian blur: rows, then columns, each with bilinear pairs of texels.
//
//  passes 1-8: a layer (behind or in front; weighted by the amount for the small blur, by its
//              strong part for the full one), then its rows blurred
//  pass 9:     the columns blurred and composed over the sharp scene; the layer in front also
//              spreads past its own edge (a blurred picket is soft against a sharp lawn)
//
// The Gaussian's sigma is blurShare x the picture's height in pixels: the same share of the
// picture in the pane and in a 4K save. The effect is only in the chain while the blur is
// drawn (Garden.qml's depthOfFieldActive): blur 0 is the view, not a level apart.
//
// It runs where the environment runs a user effect: on the scene's LINEAR colour, before
// exposure, tone mapping, glow, the grade and the vignette (measured: a constant 0.25 written
// here came out tone-mapped). So a blurred highlight still glows.
//
// No user-visible strings here (tests/unit/test_quick3d_qml.py).
import QtQuick
import QtQuick3D

Effect {
    id: photoBlur

    // cm along the view's axis, from the camera to the focused point (photo.focus_distance_cm)
    property real focusDistance: 600.0
    // cm that stay sharp around it, half in front and half behind (photo.focus_range_cm)
    property real focusRange: 100.0
    // the full Gaussian's sigma as a share of the picture's height (photo.blur_sigma_share)
    property real blurShare: 0.0
    // set per pass by SetUniformValue: which layer (+1 behind the band, -1 in front of it),
    // weighted for which blur (0 the small one, 1 the full one), and the rows' sigma scale
    property real layerSign: 1.0
    property real layerStrong: 0.0
    property real sigmaScale: 1.0

    readonly property TextureInput sceneSampler: TextureInput { texture: Texture {} }
    readonly property TextureInput farSmallSampler: TextureInput { texture: Texture {} }
    readonly property TextureInput nearSmallSampler: TextureInput { texture: Texture {} }
    readonly property TextureInput nearFullSampler: TextureInput { texture: Texture {} }

    Shader {
        id: layerShader
        stage: Shader.Fragment
        shader: Qt.resolvedUrl("photoblur_layer.frag")
    }
    Shader {
        id: rowsShader
        stage: Shader.Fragment
        shader: Qt.resolvedUrl("photoblur_rows.frag")
    }
    Shader {
        id: composeShader
        stage: Shader.Fragment
        shader: Qt.resolvedUrl("photoblur_compose.frag")
    }

    // half floats for HDR colour; bilinear so that one tap reads a pair of texels. The layer
    // buffer is written four times, each time after the pass before has read it
    Buffer {
        id: layerBuffer
        name: "photoBlurLayer"
        format: Buffer.RGBA16F
        textureFilterOperation: Buffer.Linear
        textureCoordOperation: Buffer.ClampToEdge
        bufferFlags: Buffer.None
        sizeMultiplier: 1.0
    }
    Buffer {
        id: farSmallBuffer
        name: "photoBlurFarSmall"
        format: Buffer.RGBA16F
        textureFilterOperation: Buffer.Linear
        textureCoordOperation: Buffer.ClampToEdge
        bufferFlags: Buffer.None
        sizeMultiplier: 1.0
    }
    Buffer {
        id: farFullBuffer
        name: "photoBlurFarFull"
        format: Buffer.RGBA16F
        textureFilterOperation: Buffer.Linear
        textureCoordOperation: Buffer.ClampToEdge
        bufferFlags: Buffer.None
        sizeMultiplier: 1.0
    }
    Buffer {
        id: nearSmallBuffer
        name: "photoBlurNearSmall"
        format: Buffer.RGBA16F
        textureFilterOperation: Buffer.Linear
        textureCoordOperation: Buffer.ClampToEdge
        bufferFlags: Buffer.None
        sizeMultiplier: 1.0
    }
    Buffer {
        id: nearFullBuffer
        name: "photoBlurNearFull"
        format: Buffer.RGBA16F
        textureFilterOperation: Buffer.Linear
        textureCoordOperation: Buffer.ClampToEdge
        bufferFlags: Buffer.None
        sizeMultiplier: 1.0
    }

    passes: [
        Pass {
            shaders: [ layerShader ]
            output: layerBuffer
            commands: [
                SetUniformValue { target: "layerSign"; value: 1.0 },
                SetUniformValue { target: "layerStrong"; value: 0.0 },
                BufferInput { sampler: "sceneSampler" }
            ]
        },
        Pass {
            shaders: [ rowsShader ]
            output: farSmallBuffer
            commands: [
                SetUniformValue { target: "sigmaScale"; value: 0.3333333 },
                BufferInput { buffer: layerBuffer }
            ]
        },
        Pass {
            shaders: [ layerShader ]
            output: layerBuffer
            commands: [
                SetUniformValue { target: "layerSign"; value: 1.0 },
                SetUniformValue { target: "layerStrong"; value: 1.0 },
                BufferInput { sampler: "sceneSampler" }
            ]
        },
        Pass {
            shaders: [ rowsShader ]
            output: farFullBuffer
            commands: [
                SetUniformValue { target: "sigmaScale"; value: 1.0 },
                BufferInput { buffer: layerBuffer }
            ]
        },
        Pass {
            shaders: [ layerShader ]
            output: layerBuffer
            commands: [
                SetUniformValue { target: "layerSign"; value: -1.0 },
                SetUniformValue { target: "layerStrong"; value: 0.0 },
                BufferInput { sampler: "sceneSampler" }
            ]
        },
        Pass {
            shaders: [ rowsShader ]
            output: nearSmallBuffer
            commands: [
                SetUniformValue { target: "sigmaScale"; value: 0.3333333 },
                BufferInput { buffer: layerBuffer }
            ]
        },
        Pass {
            shaders: [ layerShader ]
            output: layerBuffer
            commands: [
                SetUniformValue { target: "layerSign"; value: -1.0 },
                SetUniformValue { target: "layerStrong"; value: 1.0 },
                BufferInput { sampler: "sceneSampler" }
            ]
        },
        Pass {
            shaders: [ rowsShader ]
            output: nearFullBuffer
            commands: [
                SetUniformValue { target: "sigmaScale"; value: 1.0 },
                BufferInput { buffer: layerBuffer }
            ]
        },
        Pass {
            shaders: [ composeShader ]
            commands: [
                BufferInput { buffer: farFullBuffer },
                BufferInput { buffer: farSmallBuffer; sampler: "farSmallSampler" },
                BufferInput { buffer: nearSmallBuffer; sampler: "nearSmallSampler" },
                BufferInput { buffer: nearFullBuffer; sampler: "nearFullSampler" },
                BufferInput { sampler: "sceneSampler" }
            ]
        }
    ]
}
