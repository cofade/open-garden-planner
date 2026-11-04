// Lawn blades have an upward-facing shading normal on both faces. Plant grasses
// retain foliage.frag: their leaf translucency is a different material contract.
VARYING vec4 vColor;
void MAIN()
{
    NORMAL = normalize(vec3(NORMAL.x, abs(NORMAL.y), NORMAL.z));
    BASE_COLOR = vec4(vColor.rgb * uTint, 1.0);
    BASE_COLOR.rgb = mix(BASE_COLOR.rgb, vec3(0.68, 0.71, 0.75), uSnow * max(NORMAL.y, 0.0));
    // L5 (ADR-070): wet leaves are darker and shine - the rain 1, a morning dew 0.6.
    // Not glossier than 0.6: at 0.38 a low sun left cream glints on the wet leaves in the
    // rain (1,005 px at a golden hour; 10 at 0.6 - 3D review of L5, round 3)
    BASE_COLOR.rgb *= 1.0 - 0.12 * uWet;
    ROUGHNESS = mix(0.82, 0.6, uWet);
    METALNESS = 0.0;
    SPECULAR_AMOUNT = mix(0.25, 0.6, uWet);
}

void DIRECTIONAL_LIGHT()
{
    DIFFUSE += BASE_COLOR.rgb * LIGHT_COLOR * SHADOW_CONTRIB
             * max(dot(NORMAL, TO_LIGHT_DIR), 0.0);
}

// L5: a garden light (a PointLight of the lamp pool) on the lawn's blades.
void POINT_LIGHT()
{
    DIFFUSE += BASE_COLOR.rgb * LIGHT_COLOR * LIGHT_ATTENUATION * SHADOW_CONTRIB
             * max(dot(NORMAL, TO_LIGHT_DIR), 0.0);
}
