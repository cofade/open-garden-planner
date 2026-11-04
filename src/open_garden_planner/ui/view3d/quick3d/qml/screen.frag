// X-ray and Cutaway (L2.4, #386, ADR-063): a built part that fades (an occluder of
// the selection) or is cut (a roof while Cutaway is on) is drawn as a SCREEN DOOR -
// a 4 x 4 ordered dither keeps uOpacity of its pixels and discards the rest. The
// part stays in the opaque pass, so it still casts its shadow and sorts like a solid:
// a blended or hidden part drops out of the shadow map, and the faded tree's or the
// cut roof's shadow vanished from the ground (3D review of #386, PF-L3D-06).
// uOpacity 0 discards every pixel: a cut roof is not drawn and still shades the lawn.
// The rest is the vertex-coloured principled look of the part (Garden.qml).
float screenDoor2(vec2 a)
{
    a = floor(a);
    return fract(dot(a, vec2(0.5, a.y * 0.75)));
}

float screenDoor(vec2 a)
{
    return screenDoor2(0.5 * a) * 0.25 + screenDoor2(a);   // 0 .. 15/16, Bayer 4 x 4
}

void MAIN()
{
    if (screenDoor(FRAGCOORD.xy) >= uOpacity)
        discard;
    BASE_COLOR = vec4(VAR_COLOR.rgb * uTint, 1.0);
    ROUGHNESS = uRough;
    METALNESS = 0.0;
    SPECULAR_AMOUNT = uSpecular;
}
