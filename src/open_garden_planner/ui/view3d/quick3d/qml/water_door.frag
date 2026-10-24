// Water (ported from the L0 spike, ADR-048): the water colour keeps its HUE in
// every mood - the sun and the sky set only its BRIGHTNESS (their luminance) -
// and the sky reflection is scaled by uReflect.
//
// albedo = vertex colour x the part's tint, both linear (the spike read one colour
// for every pond from a uniform; here the mesh carries it, like every other kind).
//
// Why not a PrincipledMaterial (measured on the spike's bench board, golden hour):
// its image-based sky reflection turned the pond lavender (hue 284 vs the 2D
// 205.5); specularAmount, fresnelScale and fresnelPower do not reach that
// reflection, roughness 0.3 only got to 239 and blew the morning sun glint over the
// whole pond, and even a matte pond is tinted to 225 by the blue sky fill.
//
// qt_sampleDiffuse / qt_sampleGlossy are Qt Quick 3D's own probe samplers
// (orientation, RGBE decode and probe exposure included); re-check them after any
// Qt upgrade. This shader ships ONLY with the Qt-message check of the render tier
// active: a shader that does not compile is a warning, and the frame still renders.
float waterLuma(vec3 c)
{
    return dot(c, vec3(0.2126, 0.7152, 0.0722));
}

// The screen door of a faded part (L2.4, #386): the same 4 x 4 ordered dither as
// screen.frag. A COPY of water.frag with this block and the discard in MAIN added
// (test_quick3d_qml pins it): the look shader carries no discard, so nothing changes
// while no part fades.
float screenDoor2(vec2 a)
{
    a = floor(a);
    return fract(dot(a, vec2(0.5, a.y * 0.75)));
}

float screenDoor(vec2 a)
{
    return screenDoor2(0.5 * a) * 0.25 + screenDoor2(a);
}

void MAIN()
{
    if (screenDoor(FRAGCOORD.xy) >= uOpacity)
        discard;
    BASE_COLOR = vec4(VAR_COLOR.rgb * uTint, 1.0);   // linear
    ROUGHNESS = uRough;
    METALNESS = 0.0;
    SPECULAR_AMOUNT = 0.5;
}

void DIRECTIONAL_LIGHT()
{
    DIFFUSE += BASE_COLOR.rgb * uBody * waterLuma(LIGHT_COLOR) * SHADOW_CONTRIB
             * max(dot(NORMAL, TO_LIGHT_DIR), 0.0);
}

void IBL_PROBE()
{
    // compiled without a light probe too (L1.2 sets none; L1.4 adds the sky): the
    // samplers exist only when Qt includes its probe library
#if QSSG_ENABLE_LIGHT_PROBE
    DIFFUSE += BASE_COLOR.rgb * uBody * waterLuma(qt_sampleDiffuse(NORMAL).rgb) * AO_FACTOR;
    float ndv = clamp(dot(NORMAL, VIEW_VECTOR), 0.0, 1.0);
    float fresnel = 0.02 + 0.98 * pow(1.0 - ndv, 5.0);
    SPECULAR += uReflect * fresnel * qt_sampleGlossy(NORMAL, VIEW_VECTOR, ROUGHNESS).rgb;
#endif
}
