// The vertex stage of a swaying plant's wood and fruit (#800): while the wind's clock runs,
// Garden.qml draws a plant's built parts (its trunk, branches, fruit, flowers) through this
// and built_snow.frag - the principled look to the level when no snow lies (built_snow.vert
// says why the colour goes through COLOR) - so they sway with the leaves by the SAME
// function: a twig and its leaves move together. Wood does not flutter. At rest (the
// clock at 0) Garden.qml keeps the principled look and nothing here runs.
VARYING vec4 vColor;

// ---- the plant's sway (#800) ----------------------------------------------------------
// The SAME block in foliage.vert, foliage_door.vert and plant_sway.vert (pinned by
// tests/unit/test_quick3d_qml.py), and stated in numpy by core/scene3d/wind.py
// (sway_offsets; tests/unit/test_scene3d_wind.py). Engine frame, item-local cm.
//   uSwayFrame: the plant's height and canopy radius (cm, from its own meshes - the data's)
//               and its phase 0..1 (from its item id); height 0: the part does not sway
//   uWindSway:  downwind (engine frame) times the wind's strength over a clear day's; 0: calm
// Every frequency is a whole number of cycles an hour: the clock wraps 3602 -> 2 s seamlessly.
float swayHourly(float hz)
{
    return 6.2831853 * floor(hz * 3600.0 + 0.5) / 3600.0;
}

vec3 plantSway(vec3 v, vec3 n, float leafPhase, float leaf)
{
    float wind = length(uWindSway);
    if (uSwayFrame.x <= 0.0 || wind <= 0.0)
        return vec3(0.0);
    float h = uSwayFrame.x;
    float r = max(uSwayFrame.y, 1.0);
    float seed = 6.2831853 * uSwayFrame.z;
    float t = uTime;
    vec3 origin = MODEL_MATRIX[3].xyz;
    vec3 down = uWindSway / wind;
    vec3 across = vec3(-down.z, 0.0, down.x);
    // a taller plant swings slower: 1.2 Hz at 1 m over the root of its height in m, each
    // plant within 10 % of that by its phase - two alike drift in and out of step
    float hz = clamp(1.2 * inversesqrt(max(h, 1.0) / 100.0), 0.25, 2.5) * (0.9 + 0.2 * uSwayFrame.z);
    // the gust swells and eases the whole plant, travelling downwind across the garden
    float gust = 0.65 + 0.35 * sin(swayHourly(0.07) * t - 0.0021 * dot(origin.xz, down.xz) + seed);
    float y = clamp(v.y / h, 0.0, 1.0);
    // the whole plant, a cantilever: leans downwind and swings about it, a figure of eight
    vec3 body = (y * y) * (down * (0.35 + sin(swayHourly(hz) * t + seed))
                           + across * (0.4 * sin(swayHourly(0.71 * hz) * t + seed + 1.7)));
    vec3 offset = body * mat3(MODEL_MATRIX);   // the garden's axes -> the model's own
    // branches: the further out and up, the more - a smooth field, so a twig and its
    // leaves move together
    float reach = clamp(length(v.xz) / r, 0.0, 1.0) * y;
    offset += 0.45 * reach * vec3(sin(swayHourly(1.9 * hz) * t + 3.1 * v.x / r + 1.3 * v.y / h + seed),
                                  0.35 * sin(swayHourly(2.15 * hz) * t + 2.3 * v.z / r + seed),
                                  sin(swayHourly(1.65 * hz) * t + 2.7 * v.z / r + 0.9 * v.y / h + seed));
    // a leaf flutters along its normal, faster, each at its own phase (never near a
    // frame rate's Nyquist: at most 5.1 Hz, six frames a cycle at 30 fps)
    float flutterHz = max(2.0, 1.6 * hz) * (0.85 + 0.3 * fract(leafPhase * 7.31));
    offset += leaf * 0.25 * y * sin(swayHourly(flutterHz) * t + 6.2831853 * leafPhase * 13.0) * n;
    // the amplitude: 0.5 % of the plant's height at its top, under a clear day's wind
    return 0.005 * h * wind * gust * offset;
}
// ---- end of the plant's sway ----------------------------------------------------------

void MAIN()
{
    float rest = smoothstep(0.0, 2.0, uTime);
    VERTEX += plantSway(VERTEX, vec3(0.0), 0.0, 0.0) * rest;
    vColor = COLOR;
}
