// Leaves and blades (ported from the L0 spike; shared by foliage.vert and
// grass.vert). albedo = vertex colour x the part's tint, both linear. uOpacity is 1,
// unless the part fades as an occluder of the selection (L2.4, X-ray): then it is a
// screen door - opaque pixels, so it keeps its shadow and needs no sorting (a blended
// crown lost its shadow and stacked its own leaves in no order: 3D review of #386).
VARYING vec4 vColor;
// The screen door of a faded part (L2.4): the same 4 x 4 ordered dither as screen.frag
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
    if (uOpacity < 1.0 && screenDoor(FRAGCOORD.xy) >= uOpacity)
        discard;
    BASE_COLOR = vec4(vColor.rgb * uTint, 1.0);
    ROUGHNESS = 0.82;
    METALNESS = 0.0;
    SPECULAR_AMOUNT = 0.25;
}

// Thin leaves and blades: light from BEHIND shines through (wrap + translucency).
// Front: Lambert. Back: 35 % of the light reaching the other face, still gated by
// the shadow map, so only leaves the sun actually reaches can glow.
void DIRECTIONAL_LIGHT()
{
    DIFFUSE += BASE_COLOR.rgb * LIGHT_COLOR * SHADOW_CONTRIB
             * (max(dot(NORMAL, TO_LIGHT_DIR), 0.0) + 0.35 * max(dot(-NORMAL, TO_LIGHT_DIR), 0.0));
}
