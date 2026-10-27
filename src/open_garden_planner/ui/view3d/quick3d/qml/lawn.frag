// Lawn blades have an upward-facing shading normal on both faces. Plant grasses
// retain foliage.frag: their leaf translucency is a different material contract.
VARYING vec4 vColor;
void MAIN()
{
    NORMAL = normalize(vec3(NORMAL.x, abs(NORMAL.y), NORMAL.z));
    BASE_COLOR = vec4(vColor.rgb * uTint, 1.0);
    BASE_COLOR.rgb = mix(BASE_COLOR.rgb, vec3(0.68, 0.71, 0.75), uSnow * max(NORMAL.y, 0.0));
    ROUGHNESS = 0.82;
    METALNESS = 0.0;
    SPECULAR_AMOUNT = 0.25;
}

void DIRECTIONAL_LIGHT()
{
    DIFFUSE += BASE_COLOR.rgb * LIGHT_COLOR * SHADOW_CONTRIB
             * max(dot(NORMAL, TO_LIGHT_DIR), 0.0);
}
