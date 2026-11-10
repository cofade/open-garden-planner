// The baked ground (L1.5) with DETAIL NORMALS (Phase 17 L4.5, #388, ADR-065): the
// tile's own picture shades like relief - gravel, paving joints, lawn, the decking's
// boards - with no asset of its own. The normal tilts with the gradient of the
// texture's LUMINANCE (bright = raised), measured over one texel each way; nothing
// is loaded or generated for it.
//
// Everything else is the flat ground's look (the endless meadow's roughness 1.0 and
// specular 0.15, so the plan meets the meadow without a step) - the albedo through the
// engine's own sRGB polynomial (ogp-3d-renderer section 14: x(x(0.3053x + 0.6822) +
// 0.0125)), the same numbers PrincipledMaterial linearises a base colour map with.
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
//
// THE MEADOW'S GRASS (#798, ADR-048 addendum): ONE shader for every piece of ground -
// the baked tiles, the bare plan rectangle and the endless meadow around the plan - so
// the plan's edge is the same function on both sides. Where the tile is OPEN (its alpha:
// the bake leaves ground no item covers at alpha 0, with the meadow's colour in rgb) and
// on the meadow (uHasTile 0: no tile at all), the ground is the meadow's GRASS: the
// canvas's GRASS texture (resources/textures/grass.png, 1 texel = 1 cm, the canvas's own
// scale) as its linear colour over its own mean (uGrass: mean 1 per channel, RGBA16F, so
// every mip level keeps the mean), sampled twice in world space - as it lies and turned
// 37 degrees at 1.618 times the size, summed so that the variance stays and the 2.56 m
// repeat does not show - times a slow world variation (9 m and 41 m, a few per cent of
// brightness, a few degrees of hue; mean 1). Its mean is uMeadow's, so the far meadow
// keeps its colour, and in the truth view (uSurface 0) the meadow is the flat colour.
float groundLuma(vec3 c)
{
    return dot(c, vec3(0.2126, 0.7152, 0.0722));
}

vec3 groundLinear(vec3 c)
{
    return c * (c * (c * 0.305306011 + 0.682171111) + 0.012522878);
}

// A hash without sine (Dave Hoskins): the same on every graphics API, exact enough for
// the meadow's cells (at most about 2,300 of 9 m across its 20 km).
float meadowHash(vec2 p)
{
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

// Smooth value noise in -1 .. 1, mean 0, one cell per unit of p.
float meadowNoise(vec2 p)
{
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = meadowHash(i);
    float b = meadowHash(i + vec2(1.0, 0.0));
    float c = meadowHash(i + vec2(0.0, 1.0));
    float d = meadowHash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y) * 2.0 - 1.0;
}

// The grass's two samples at the ground point p (cm: x east, y south): the texture as it
// lies (one texel a centimetre) and turned 37 degrees at 1.618 times the size.
vec2 grassUvA(vec2 p)
{
    return p / 256.0;
}

vec2 grassUvB(vec2 p)
{
    return mat2(0.79864, 0.60181, -0.60181, 0.79864) * p / 414.2 + vec2(0.31, 0.57);
}

// The grass at p: its colour over the meadow's (mean 1 per channel) and, with uDetail,
// the slope of its relief (east, north) as the tiles' detail normals read it.
vec3 meadowGrass(vec2 p, out vec2 slope)
{
    vec2 uvA = grassUvA(p);
    vec2 uvB = grassUvB(p);
    vec3 a = texture(uGrass, uvA).rgb;
    vec3 b = texture(uGrass, uvB).rgb;
    // the two summed around their mean: the variance of one, the repeat of neither
    vec3 grass = 1.0 + (a + b - 2.0) * 0.70711;
    slope = vec2(0.0);
    if (uDetail > 0.0) {
        // one centimetre east and one north (p.y grows to the south), forward
        // differences of the relief's luminance - the tiles' central differences of
        // their codes, at the scale of a linear ratio (uGrassRelief)
        float east = groundLuma(texture(uGrass, grassUvA(p + vec2(1.0, 0.0))).rgb
                                + texture(uGrass, grassUvB(p + vec2(1.0, 0.0))).rgb);
        float north = groundLuma(texture(uGrass, grassUvA(p - vec2(0.0, 1.0))).rgb
                                 + texture(uGrass, grassUvB(p - vec2(0.0, 1.0))).rgb);
        float sum = groundLuma(a + b);
        slope = vec2(east - sum, north - sum) * 0.70711 * uGrassRelief * uDetail;
    }
    if (uSurface > 1.5) {
        // the variation: brightness at 3.1 m (in place of the texture's own mottle, which
        // repeats and is taken out of uGrass), 9 m and 41 m; hue at 17 m (drier, warmer
        // patches and lusher, cooler ones); each of mean 1, each octave turned its own way
        // so that no cell grid lines up with another or with the plan
        float bright = 1.0
                     + uMeadowVariation.x * meadowNoise(mat2(0.87462, 0.48481, -0.48481, 0.87462) * p / 310.0)
                     + uMeadowVariation.y * meadowNoise(mat2(0.95630, -0.29237, 0.29237, 0.95630) * p / 900.0
                                                        + vec2(5.3, 11.7))
                     + uMeadowVariation.z * meadowNoise(p / 4100.0 + vec2(17.3, 5.1));
        float hue = uMeadowVariation.w * meadowNoise(mat2(0.60182, 0.79864, -0.79864, 0.60182) * p / 1700.0
                                                     + vec2(3.7, 41.9));
        grass *= bright * vec3(1.0 + 1.6 * hue, 1.0, 1.0 - 2.4 * hue);
    }
    return grass;
}

// THE WEATHER (Phase 17 L5, ADR-070): the meadow's own values, for every piece of
// ground at once - uGroundTint (the rain's darkening; a colour property, so through the
// same polynomial), uRough / uSpecular (1.0 / 0.15 dry), and snow mixed over it by
// uSnowCover towards weather.SNOW_LINEAR. Dry and snowless (tint white, cover 0) and
// with the flat surface (uSurface 0) this is the L4.5 shader exactly.
void MAIN()
{
    vec2 uv = vec2(UV0.x, 1.0 - UV0.y);
    vec4 tile = uHasTile > 0.5 ? texture(uBaseMap, uv) : vec4(uMeadow, 0.0);
    vec3 albedo = groundLinear(tile.rgb);
    vec2 slope = vec2(0.0);
    if (uHasTile > 0.5 && uDetail > 0.0) {
        vec2 texel = 1.0 / vec2(textureSize(uBaseMap, 0));
        float east = groundLuma(texture(uBaseMap, uv + vec2(texel.x, 0.0)).rgb);
        float west = groundLuma(texture(uBaseMap, uv - vec2(texel.x, 0.0)).rgb);
        float north = groundLuma(texture(uBaseMap, uv - vec2(0.0, texel.y)).rgb);
        float south = groundLuma(texture(uBaseMap, uv + vec2(0.0, texel.y)).rgb);
        slope = vec2(east - west, north - south) * uDetail;
    }
    if (uSurface > 0.5) {
        // what of this point is open meadow: all of the meadow, and on the plan the
        // ground no item covers - if the plan's open ground takes the grass (uGrassShare)
        float open = (1.0 - tile.a) * uGrassShare;
        vec2 grassSlope;
        vec3 grass = meadowGrass(VAR_WORLD_POSITION.xz, grassSlope);
        albedo += open * groundLinear(uMeadow) * (grass - 1.0);
        slope += open * grassSlope;
    }
    albedo *= groundLinear(uGroundTint);
    BASE_COLOR = vec4(mix(albedo, vec3(0.80, 0.84, 0.89), uSnowCover), 1.0);
    ROUGHNESS = uRough;
    METALNESS = 0.0;
    SPECULAR_AMOUNT = uSpecular;
    // snow fills the joints: the relief fades under it
    slope = clamp(slope * (1.0 - 0.8 * uSnowCover), vec2(-0.22), vec2(0.22));
    NORMAL = normalize(vec3(-slope.x, 1.0, slope.y));
}
