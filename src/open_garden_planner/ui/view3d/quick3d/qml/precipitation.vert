// Rain and snow (Phase 17 L5.2, #389, ADR-070): ONE buffer of quads with unit seeds
// (core/scene3d/particles.py precipitation_buffers), laid out here in a box around the
// camera's target - the WIND'S CLOCK moves them (uTime = windTime): at rest (0) every
// particle stands where its seed puts it, and nothing ticks while the clock is stopped.
//
//   VERTEX   the seed in the unit cube (x across, y the fall's phase, z along)
//   NORMAL   (phase, speed jitter, size jitter), each 0..1
//   COLOR    (tint jitter rgb, rank): a particle is drawn while rank < uDensity
//   UV0.x    the corner, 0..3
//
// WORLD-ANCHORED: the box's window slides with the camera, the particles do not - a
// particle's place is its seed plus its fall, wrapped into the window (mod), so an
// orbit never drags the rain along. Engine frame: x = East, y = up, z = -North.
VARYING vec4 vColor;
VARYING vec2 vUV;
VARYING float vFade;

void MAIN()
{
    bool snow = uKind > 1.5;
    vColor = vec4(COLOR.rgb, 1.0);
    if (COLOR.a >= uDensity || uKind < 0.5) {
        vFade = 0.0;
        vUV = vec2(0.0);
        POSITION = vec4(0.0, 0.0, 2.0, 1.0);    // beyond the far plane on every backend: clipped
        return;
    }
    float size = uSize;
    float height = uHeight;
    float fall = snow ? mix(80.0, 130.0, NORMAL.y) : mix(650.0, 900.0, NORMAL.y);   // cm/s
    vec2 drift = uDrift.xz * (snow ? 1.0 : 0.35);
    vec2 origin = uCenter.xz - 0.5 * size;
    vec2 driftDist = mod(drift * uTime, vec2(size));
    vec2 xz = origin + mod(VERTEX.xz * size + driftDist, vec2(size));
    float fallDist = mod(fall * uTime, height);
    float y = height - mod(VERTEX.y * height + fallDist, height);
    if (snow) {   // a flake sways as it falls (#689: wrap time to avoid float precision loss)
        float phase1 = mod(uTime * 1.3, 6.2831853);
        float phase2 = mod(uTime * 1.1, 6.2831853);
        xz += vec2(sin(phase1 + NORMAL.x * 6.2832), cos(phase2 + NORMAL.x * 5.0)) * 16.0;
    }
    vec3 center = vec3(xz.x, y, xz.y);
    // fade in at the box's sides and top, so its window never shows a line
    vec2 edge = min(xz - origin, origin + size - xz) / (0.12 * size);
    vFade = clamp(min(edge.x, edge.y), 0.0, 1.0) * clamp((height - y) / (0.15 * height), 0.0, 1.0);

    int corner = int(UV0.x + 0.5);
    vec2 c = corner == 0 ? vec2(-0.5, -0.5) : corner == 1 ? vec2(0.5, -0.5)
           : corner == 2 ? vec2(0.5, 0.5) : vec2(-0.5, 0.5);
    vUV = c + 0.5;
    vec3 toCamera = normalize(CAMERA_POSITION - center);
    float depth = max(dot(center - CAMERA_POSITION, CAMERA_DIRECTION), 1.0);
    float pixel = depth * uPerDepth;   // cm per pixel here
    vec3 along;
    vec3 across;
    float wide;
    float tall;
    if (snow) {   // a flake faces the camera
        across = normalize(cross(vec3(0.0, 1.0, 0.0), toCamera));
        along = cross(toCamera, across);
        wide = max(mix(1.4, 2.6, NORMAL.z), 2.6 * pixel);   // 1.6 px read as specks
        tall = wide;
    } else {      // a streak along its fall, turned to face the camera
        along = normalize(vec3(-drift.x, fall, -drift.y));
        across = normalize(cross(along, toCamera));
        wide = max(0.5, 1.3 * pixel);   // 0.9 px broke into dashes
        tall = max(mix(28.0, 52.0, NORMAL.z), 6.0 * pixel);
    }
    vec3 world = center + across * (c.x * wide) + along * (c.y * tall);
    POSITION = VIEWPROJECTION_MATRIX * vec4(world, 1.0);
}
