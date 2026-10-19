// The selection ring (L1.8, ADR-065): a band of constant width ON SCREEN.
//
// The mesh (core/scene3d/selection.py) holds every outline point three times at the
// SAME position. What tells them apart is here:
//   NORMAL  the level direction away from the solid (the corner's mitre), unit length
//   UV0.x   band widths to move along it   (0 = the outline itself)
//   UV0.y   band widths to move up         (the ribbon standing on the outer edge)
// One band width is uFlat centimetres in the orthographic truth view and
// depth x uPerDepth centimetres in the perspective view - the same number of pixels
// near and far, so the ring is a hair neither when the whole garden is framed nor a
// plank in walk mode.
//
// uDepthScale < 1 pulls the ring towards the NEAR PLANE in depth only (its place on
// the screen is untouched): at 0.01 its depth is a hundredth of what it was. Where the
// near plane is in clip space depends on the backend - z = 0 (Direct3D, Vulkan, Metal)
// or z = -w (OpenGL) - and NEAR_CLIP_VALUE says which. Plainly scaling z is right only
// for the first: on OpenGL it moves the ring to the MIDDLE of the depth range, which
// in the orthographic truth view is behind the ground (measured: 0 ring pixels in
// every top-down frame, 1,548 with this line).
void MAIN()
{
    vec4 world = MODEL_MATRIX * vec4(VERTEX, 1.0);
    float depth = max(dot(world.xyz - CAMERA_POSITION, CAMERA_DIRECTION), 0.0);
    float width = uFlat + depth * uPerDepth;
    vec3 outward = mat3(MODEL_MATRIX) * NORMAL;
    world.xyz += outward * (UV0.x * width);
    world.y += UV0.y * width;
    POSITION = VIEWPROJECTION_MATRIX * world;
    POSITION.z = mix(NEAR_CLIP_VALUE * POSITION.w, POSITION.z, uDepthScale);
}
