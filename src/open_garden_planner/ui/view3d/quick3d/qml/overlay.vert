// The analysis overlays (Phase 17 L2, #386): the drape of the 2D sun analysis and the
// sun path / compass / probe pin. The mesh is in the scene's own frame and its colour is
// the vertex colour, LINEAR, alpha included (core/scene3d/drape.py, sun_path.py).
//
// Follow-ups #578 and #576:
//  - Arcs (UV0.x > 0.5) have screen-constant width (~2.5 px) via uArcPerDepth.
//  - The near half of each arc (between camera and dome centre) fades smoothly to 25% opacity.
//  - Beads, sun ball and compass rose (UV0.x <= 0.5) remain 100% opaque.

VARYING vec4 vColor;

void MAIN()
{
    vec4 world = MODEL_MATRIX * vec4(VERTEX, 1.0);

    float alpha = 1.0;
    if (UV0.x > 0.5) {
        // Screen-constant arc width (#576)
        if (uArcPerDepth > 0.0 || uArcFlat > 0.0) {
            float depth = max(dot(world.xyz - CAMERA_POSITION, CAMERA_DIRECTION), 0.0);
            float targetRadius = 0.5 * (uArcFlat + depth * uArcPerDepth);
            if (UV0.y > 0.0 && targetRadius > 0.0) {
                float delta = targetRadius - UV0.y;
                vec3 outward = mat3(MODEL_MATRIX) * NORMAL;
                world.xyz += outward * delta;
            }
        }

        // Camera-relative near-half arc fade to 25% (#578)
        vec2 toVertex = world.xz - uDomeCenter.xz;
        vec2 toCamera = CAMERA_POSITION.xz - uDomeCenter.xz;
        float lenCam = length(toCamera);
        float lenVert = length(toVertex);
        if (lenCam > 1.0 && lenVert > 1.0) {
            float cosTheta = dot(toVertex, toCamera) / (lenVert * lenCam);
            if (cosTheta > 0.0) {
                alpha = mix(1.0, 0.25, cosTheta);
            }
        }
    }

    vColor = vec4(COLOR.rgb, COLOR.a * alpha);
    POSITION = VIEWPROJECTION_MATRIX * world;
}
