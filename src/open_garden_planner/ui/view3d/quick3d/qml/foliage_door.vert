// A COPY of foliage.vert for the screen-door material (L2.4, #386) with the depth-pass
// collapse added after POSITION (test_quick3d_qml pins it).
// Foliage wind (ported from the L0 spike): sway grows with the leaf's height in
// the crown (uv.x) and shifts phase per leaf (uv.y) and across the garden (world
// position). uTime is the scene's windTime: the look's animation policy runs it (L1.4).
VARYING vec4 vColor;
void MAIN()
{
    float w = UV0.x * UV0.x;
    float ph = UV0.y * 6.28318;
    vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    float gust = 0.6 + 0.4 * sin(uTime * 0.35 + wp.x * 0.002);
    // At rest (uTime 0) the vertex is EXACTLY the mesh's: the sway eases in over the
    // first two seconds. Without it a leaf with a wind weight sat up to uWind cm off
    // the mesh the CPU measures heights, spreads and picks with, even with no wind.
    // "At rest" means uTime == 0 and nothing else: a clock PAUSED at any other value
    // leaves every weighted vertex displaced. Whoever needs the mesh's own positions
    // (a truth probe, a measurement) sets the clock to 0 or the wind strength to 0.
    float rest = smoothstep(0.0, 2.0, uTime);
    VERTEX.x += sin(uTime * 1.9 + ph + wp.x * 0.011) * uWind * w * gust * rest;
    VERTEX.z += cos(uTime * 1.4 + ph + wp.z * 0.009) * uWind * 0.6 * w * gust * rest;
    vColor = COLOR;
    POSITION = MODELVIEWPROJECTION_MATRIX * vec4(VERTEX, 1.0);
    // the screen door's depth-pass collapse (screen.vert): no ghost in the AO depth
#if QSSG_ENABLE_DEPTH_PASS
    if (uOpacity < 1.0)
        POSITION = vec4(0.0);
#endif
}
