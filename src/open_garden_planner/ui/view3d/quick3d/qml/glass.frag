// A window pane (#992). The pane's sky reflection (IBL) keeps the measured 0.70
// roughness floor against Ultra SSR flicker (#883) through IBL_PROBE(); Qt's
// SCREEN-SPACE reflection pass reads ROUGHNESS, so MAIN() sets it to uSsrRough (0.38
// while the view draws SSR, 0.70 otherwise). Metalness stays 0 so windows never turn
// into chrome mirrors.
VARYING vec4 vColor;

vec3 engineLinear(vec3 c)
{
    return c * (c * (c * 0.305306011 + 0.682171111) + 0.012522878);
}

void MAIN()
{
    BASE_COLOR = vec4(vColor.rgb * engineLinear(uTintSrgb) * uAlbedo, 1.0);
    ROUGHNESS = uSsrRough;
    METALNESS = 0.0;
    SPECULAR_AMOUNT = uSpecular;
}

void IBL_PROBE()
{
#if QSSG_ENABLE_LIGHT_PROBE || defined(SAMPLE_PROBE_GLSLLIB)
    float f0 = 0.08 * SPECULAR_AMOUNT;
    DIFFUSE += BASE_COLOR.rgb * (1.0 - f0) * qt_sampleDiffuse(NORMAL).rgb * AO_FACTOR;
    float ndv = clamp(dot(NORMAL, VIEW_VECTOR), 0.0, 1.0);
    float fresnel = f0 + (1.0 - f0) * pow(1.0 - ndv, 5.0);
    SPECULAR += fresnel * qt_sampleGlossy(NORMAL, VIEW_VECTOR, uRough).rgb * AO_FACTOR;
#endif
}
