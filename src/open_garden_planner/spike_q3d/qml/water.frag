// The pond (spike, ADR-047 L0): the 2D water colour keeps its HUE in every mood —
// the sun and the sky set only its BRIGHTNESS (their luminance) — and the sky
// reflection is scaled by uReflect.
//
// Why not a PrincipledMaterial (measured on the bench board, golden hour): its
// image-based sky reflection turned the pond lavender (hue 284 vs the 2D 205.5);
// specularAmount, fresnelScale and fresnelPower do not reach that reflection,
// roughness 0.3 only got to 239 and blew the morning sun glint over the whole
// pond, and even a matte pond is tinted to 225 by the blue sky fill.
//
// qt_sampleDiffuse / qt_sampleGlossy are Qt Quick 3D's own probe samplers
// (orientation, RGBE decode and probe exposure included); re-check them after
// any Qt upgrade (the render tier renders this shader).
float waterLuma(vec3 c)
{
    return dot(c, vec3(0.2126, 0.7152, 0.0722));
}

void MAIN()
{
    BASE_COLOR = vec4(uWater, 1.0);   // linear
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
    // compiled without a light probe too (the orthographic probe views set none):
    // the samplers exist only when Qt includes its probe library
#if QSSG_ENABLE_LIGHT_PROBE
    DIFFUSE += BASE_COLOR.rgb * uBody * waterLuma(qt_sampleDiffuse(NORMAL).rgb) * AO_FACTOR;
    float ndv = clamp(dot(NORMAL, VIEW_VECTOR), 0.0, 1.0);
    float fresnel = 0.02 + 0.98 * pow(1.0 - ndv, 5.0);
    SPECULAR += uReflect * fresnel * qt_sampleGlossy(NORMAL, VIEW_VECTOR, ROUGHNESS).rgb;
#endif
}
