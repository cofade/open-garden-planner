// A built part that shows its surface's detail picture (#801): a roof's tiles, a wall's
// plaster, courses or boards - the canvas's own pictures (resources/textures), laid by
// built_detail.vert. Everything else is the part's principled look: its vertex colour
// times its tint (through the engine's sRGB polynomial, as PrincipledMaterial linearises
// a baseColor), its surface's roughness and specular (core/scene3d/materials.SURFACES,
// written by the host per part: #803).
//
// THE PICTURE (core/scene3d/surface_detail.detail_texels): R = the albedo multiplier x
// 0.4 (linear; its mean over the picture is 1, so the part's mean colour is its colour,
// and the mipmaps take a far roof to exactly that flat mean - no moire); G, B = the
// height's slope along u and v, 0.5 + slope (bright = raised, as the ground's detail).
// Mipmaps average the slope towards 0, and uDetailFade takes the normal to flat by
// distance on top: a far wall shades as a plane.
//
// THE FRAME: the cotangent frame of the picture's coordinates in screen space (dFdx /
// dFdy of the world position and of vDetailUV), so a roof's mirrored half and a hip's
// faces need no tangent in the mesh.
//
// THE WEATHER, as the ground's (ground.frag): the rain darkens by the ground's own tint
// and shifts roughness and specular by the ground's own shift; snow lies on what faces up
// by the living garden's rule (uSnowCover = its builtSnow, built_snow.frag's smoothstep and
// colour weather.SNOW_LINEAR, its joints filled: the relief fades under it).
VARYING vec4 vColor;
VARYING vec2 vDetailUV;

vec3 engineLinear(vec3 c)
{
    return c * (c * (c * 0.305306011 + 0.682171111) + 0.012522878);
}

void MAIN()
{
    vec4 detail = texture(uDetailMap, vDetailUV);
    vec3 albedo = vColor.rgb * engineLinear(uTintSrgb) * mix(1.0, detail.r * 2.5, uDetailContrast);
    albedo *= engineLinear(uWetTint);
    vec3 n = normalize(NORMAL);
    float lying = uSnowCover * smoothstep(0.35, 0.75, n.y);

    // the detail normal, faded by distance and under snow
    float dist = length(VAR_WORLD_POSITION - CAMERA_POSITION);
    float strength = uDetailNormal * (1.0 - smoothstep(0.4 * uDetailFade, uDetailFade, dist))
                   * (1.0 - 0.8 * lying);
    vec2 slope = clamp((detail.gb - vec2(0.5)) * strength, vec2(-0.6), vec2(0.6));
    vec3 dp1 = dFdx(VAR_WORLD_POSITION);
    vec3 dp2 = dFdy(VAR_WORLD_POSITION);
    vec2 duv1 = dFdx(vDetailUV);
    vec2 duv2 = dFdy(vDetailUV);
    vec3 dp2perp = cross(dp2, n);
    vec3 dp1perp = cross(n, dp1);
    vec3 t = dp2perp * duv1.x + dp1perp * duv2.x;
    vec3 b = dp2perp * duv1.y + dp1perp * duv2.y;
    float scale = inversesqrt(max(max(dot(t, t), dot(b, b)), 1e-20));
    vec3 bent = n - slope.x * t * scale - slope.y * b * scale;

    BASE_COLOR = vec4(mix(albedo, vec3(0.80, 0.84, 0.89), lying), 1.0);
    NORMAL = normalize(bent);
    METALNESS = 0.0;
    ROUGHNESS = mix(clamp(uRough + uWetRough, 0.04, 1.0), uSnowRough, lying);
    SPECULAR_AMOUNT = mix(clamp(uSpecular + uWetSpecular, 0.0, 1.0), uSnowSpecular, lying);
}
