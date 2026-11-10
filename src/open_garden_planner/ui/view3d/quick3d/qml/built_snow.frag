// Snow on the built world (#687, ADR-070 decision 6 as amended): under the snow weather
// a built part's TOPS - a roof, a raised bed's soil, a deck, the trampoline's mat, a
// bench's seat - lie under the same snow as the ground. ONE shader for every vc part and
// every roof (no shader per part, ADR-060); Garden.qml swaps it in only while snow lies
// (root.builtSnow > 0), so every snowless frame is the principled look, bit for bit.
//
// The albedo is the principled look's: the vertex colour (linear) times the part's tint
// and, for a fill part, its picture - both through the engine's own sRGB polynomial
// (ogp-3d-renderer section 14: x(x(0.3053x + 0.6822) + 0.0125)), the numbers a
// PrincipledMaterial linearises its baseColor and baseColorMap with - so a part's sides
// keep their colour. Snow is mixed over it by uSnowCover (the look's built_snow: a smooth
// top lies white where the meadow's 0.75 still shows grass) times how much the surface
// faces up (a wall none, a 45-degree roof nearly all, a 60-degree one a third: snow
// slides off a steep pitch), towards weather.SNOW_LINEAR (pinned), with the snowy
// ground's roughness and specular: the snow on a roof is the snow on the meadow.
//
// The fill picture's Texture has flipV false (unlike a ground tile's), so UV0 is
// sampled as it is. The vertex colour comes through built_snow.vert (VAR_COLOR is not
// the principled look's colour: see there); how much a surface faces up is NORMAL.y, the
// world normal, as foliage.frag reads it.
VARYING vec4 vColor;

vec3 engineLinear(vec3 c)
{
    return c * (c * (c * 0.305306011 + 0.682171111) + 0.012522878);
}

void MAIN()
{
    vec3 albedo = vColor.rgb * engineLinear(uTintSrgb);
    if (uHasFill > 0.5)
        albedo *= engineLinear(texture(uFill, UV0).rgb);
    float lying = uSnowCover * smoothstep(0.35, 0.75, NORMAL.y);
    BASE_COLOR = vec4(mix(albedo, vec3(0.80, 0.84, 0.89), lying), 1.0);
    ROUGHNESS = mix(uRough, uSnowRough, lying);
    METALNESS = 0.0;
    SPECULAR_AMOUNT = mix(uSpecular, uSnowSpecular, lying);
}
