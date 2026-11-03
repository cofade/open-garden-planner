// The baked ground (L1.5) with DETAIL NORMALS (Phase 17 L4.5, #388, ADR-065): the
// tile's own picture shades like relief - gravel, paving joints, lawn, the decking's
// boards - with no asset of its own. The normal tilts with the gradient of the
// texture's LUMINANCE (bright = raised), measured over one texel each way; nothing
// is loaded or generated for it.
//
// Everything else is the flat ground's look (Garden.qml's PrincipledMaterial: the
// endless meadow's roughness 1.0 and specular 0.15, so the plan meets the meadow
// without a step) - the albedo through the engine's own sRGB polynomial
// (ogp-3d-renderer section 14: x(x(0.3053x + 0.6822) + 0.0125)), the same numbers
// PrincipledMaterial linearises a base colour map with.
//
// ORIENTATION (measured, L4.5): a Texture's flipV is applied by PrincipledMaterial's
// own lookup and NOT to a TextureInput sampled here - read as UV0 the tiles came out
// mirrored north-south. So v is flipped here: texture row 0 is the tile's NORTH edge,
// and one texel north is -texel.y.
//
// The tile quad lies in the plan: world +X is east, world -Z north (frame.py). A height
// h(E, N) has the normal (-dh/dE, 1, +dh/dN). uDetail scales the tilt; the gradient
// is clamped, so a hard colour edge (a bed's outline, a path's border) reads as a
// bevel, not a cliff.
float groundLuma(vec3 c)
{
    return dot(c, vec3(0.2126, 0.7152, 0.0722));
}

vec3 groundLinear(vec3 c)
{
    return c * (c * (c * 0.305306011 + 0.682171111) + 0.012522878);
}

// THE WEATHER (Phase 17 L5, ADR-070): the meadow's own values, for every piece of
// ground at once - uGroundTint (the rain's darkening; a colour property, so through the
// same polynomial), uRough / uSpecular (1.0 / 0.15 dry), and snow mixed over it by
// uSnowCover towards weather.SNOW_LINEAR, as the meadow's albedo is mixed in Python.
// Dry and snowless (tint white, cover 0) this is the L4.5 shader exactly.
void MAIN()
{
    vec2 uv = vec2(UV0.x, 1.0 - UV0.y);
    vec3 albedo = groundLinear(texture(uBaseMap, uv).rgb) * groundLinear(uGroundTint);
    BASE_COLOR = vec4(mix(albedo, vec3(0.80, 0.84, 0.89), uSnowCover), 1.0);
    ROUGHNESS = uRough;
    METALNESS = 0.0;
    SPECULAR_AMOUNT = uSpecular;
    vec2 texel = 1.0 / vec2(textureSize(uBaseMap, 0));
    float east = groundLuma(texture(uBaseMap, uv + vec2(texel.x, 0.0)).rgb);
    float west = groundLuma(texture(uBaseMap, uv - vec2(texel.x, 0.0)).rgb);
    float north = groundLuma(texture(uBaseMap, uv - vec2(0.0, texel.y)).rgb);
    float south = groundLuma(texture(uBaseMap, uv + vec2(0.0, texel.y)).rgb);
    // snow fills the joints: the relief fades under it
    vec2 slope = clamp(vec2(east - west, north - south) * uDetail * (1.0 - 0.8 * uSnowCover),
                       vec2(-0.22), vec2(0.22));
    NORMAL = normalize(vec3(-slope.x, 1.0, slope.y));
}
