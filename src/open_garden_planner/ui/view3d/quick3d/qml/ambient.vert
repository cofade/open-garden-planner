// The garden's life (Phase 17 L5.2, #389, ADR-070): falling leaves, butterflies at the
// plants in flower, fireflies on summer evenings - and (L5.4) the glow of the garden
// lights' bulbs. ONE buffer (core/scene3d/particles.py ambient_buffers), moved here by
// the WIND'S CLOCK (uTime = windTime): at rest (0) everything stands where its seed
// puts it, and nothing ticks while the clock is stopped.
//
//   VERTEX   the emitter's centre at its crown's top (engine frame; a bulb: the bulb)
//   NORMAL   (phase 0..1, speed 0..1, the emitter's radius cm; a bulb: its glow's size)
//   COLOR    (linear rgb, the kind's code: int(a * 4) = 0 leaf, 1 butterfly,
//            2 firefly, 3 bulb)
//   UV0      (the corner - 0..3, a butterfly's 0..7 -, the soil's height: engine y)
//
// WHICH plants have life is the plan's (the buffer); WHEN it shows is the look's
// (uLeaves, uButterflies, uFireflies, uLamps): a kind at 0 is collapsed to nothing.
VARYING vec4 vColor;
VARYING vec2 vUV;
VARYING float vKind;
VARYING float vGlow;

vec2 cornerOf(int corner)
{
    return corner == 0 ? vec2(-0.5, -0.5) : corner == 1 ? vec2(0.5, -0.5)
         : corner == 2 ? vec2(0.5, 0.5) : vec2(-0.5, 0.5);
}

void MAIN()
{
    int kind = int(COLOR.a * 4.0);
    float life = kind == 0 ? uLeaves : kind == 1 ? uButterflies : kind == 2 ? uFireflies : uLamps;
    vKind = float(kind);
    vColor = vec4(COLOR.rgb, 1.0);
    vGlow = 0.0;
    if (life <= 0.001) {
        vUV = vec2(0.0);
        POSITION = vec4(0.0, 0.0, 2.0, 1.0);    // beyond the far plane on every backend: clipped
        return;
    }
    float phase = NORMAL.x;
    float speed = NORMAL.y;
    float radius = NORMAL.z;
    float ground = UV0.y;
    int corner = int(UV0.x + 0.5);
    float t = uTime;
    vec3 top = VERTEX;
    vec3 world;
    if (kind == 1) {
        // a butterfly: two wings hinged on its body, circling over the flowers
        float orbit = radius * 0.8 + 25.0;
        float turn = mix(0.35, 0.7, speed) * (fract(phase * 5.0) > 0.5 ? 1.0 : -1.0);
        float a = t * turn + phase * 6.2832;
        float wander = sin(t * 0.37 + phase * 9.0);
        vec3 body = top + vec3(cos(a) * orbit * (0.75 + 0.25 * wander),
                               18.0 + 22.0 * sin(t * 0.9 + phase * 17.0),
                               sin(a) * orbit);
        vec3 heading = normalize(vec3(-sin(a) * turn, 0.0, cos(a) * turn));
        vec3 lateral = normalize(cross(vec3(0.0, 1.0, 0.0), heading));
        // at rest the wings are open; running, they beat
        float beat = uTime > 0.0 ? sin(t * 15.0 + phase * 30.0) : 0.0;
        float flap = 0.25 + 0.95 * beat;
        float side = corner < 4 ? -1.0 : 1.0;
        int c = corner - (corner < 4 ? 0 : 4);
        vec2 q = c == 0 ? vec2(-0.5, 0.0) : c == 1 ? vec2(0.5, 0.0)
               : c == 2 ? vec2(0.5, 1.0) : vec2(-0.5, 1.0);
        float size = mix(5.0, 7.5, speed);
        float depth = max(dot(body - CAMERA_POSITION, CAMERA_DIRECTION), 1.0);
        size = max(size, 2.0 * depth * uPerDepth);
        vec3 outward = lateral * side * cos(flap) + vec3(0.0, 1.0, 0.0) * sin(flap);
        world = body + heading * (q.x * size * 0.8) + outward * (q.y * size);
        vUV = vec2(q.x + 0.5, q.y);
    } else {
        vec3 center;
        vec3 across;
        vec3 along;
        float size;
        vec2 c = cornerOf(corner);
        if (kind == 0) {
            // a leaf: from the crown to the soil, tumbling, carried by the wind
            float drop = max(top.y - ground, 30.0);
            float fall = mix(55.0, 85.0, speed);
            float cycle = drop / fall;
            float s = mod(phase * cycle + t, cycle) / cycle;
            float angle = phase * 43.98;
            float reach = radius * 0.9 * sqrt(fract(phase * 13.7));
            vec2 start = top.xz + vec2(cos(angle), sin(angle)) * reach;
            vec2 xz = start + uDrift.xz * (0.6 * s * cycle)
                    + vec2(sin(t * 2.1 + phase * 40.0), cos(t * 1.7 + phase * 31.0)) * (14.0 * s);
            center = vec3(xz.x, mix(top.y - 0.2 * drop * fract(phase * 7.0), ground + 1.5, s), xz.y);
            float spin = t * mix(2.0, 4.0, speed) + phase * 20.0;
            across = normalize(vec3(cos(spin), 0.35 * sin(spin * 0.7), sin(spin)));
            along = normalize(cross(across, vec3(0.3 * sin(spin * 1.3), 1.0, 0.3 * cos(spin))));
            size = mix(7.0, 11.0, speed);
        } else {
            vec3 toCamera;
            if (kind == 2) {
                // a firefly: drifting low among the plants, blinking
                float wide = radius * 0.9 + 40.0;
                float lift = mix(25.0, max(top.y - ground, 60.0) * 0.9, fract(phase * 3.7));
                center = vec3(top.x + sin(t * mix(0.15, 0.3, speed) + phase * 40.0) * wide,
                              ground + lift + sin(t * 0.6 + phase * 8.0) * 15.0,
                              top.z + cos(t * mix(0.12, 0.25, speed) + phase * 23.0) * wide);
                vGlow = pow(max(sin(t * mix(1.2, 2.0, speed) + phase * 50.0), 0.0), 4.0);
                if (uTime == 0.0)
                    vGlow = fract(phase * 7.3) > 0.55 ? 1.0 : 0.0;   // a photograph: some lit
                size = 3.0;
            } else {
                // a bulb of a garden light: where it hangs, glowing
                center = top;
                vGlow = 1.0;
                size = radius;
            }
            toCamera = normalize(CAMERA_POSITION - center);
            across = normalize(cross(vec3(0.0, 1.0, 0.0), toCamera));
            along = cross(toCamera, across);
        }
        float depth = max(dot(center - CAMERA_POSITION, CAMERA_DIRECTION), 1.0);
        size = max(size, (kind == 0 ? 3.0 : 2.5) * depth * uPerDepth);
        world = center + across * (c.x * size) + along * (c.y * size);
        vUV = c + 0.5;
    }
    vGlow *= life;
    vColor.a = life;
    POSITION = VIEWPROJECTION_MATRIX * vec4(world, 1.0);
}
