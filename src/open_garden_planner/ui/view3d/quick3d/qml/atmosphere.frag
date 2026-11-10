// Copyright (C) 2023 Fernando García Liñán
// Copyright (C) 2026 The Qt Company Ltd.
// SPDX-License-Identifier: MIT AND GPL-3.0-or-later
//
// Open Garden Planner (Phase 17 L7, #391): the atmosphere sky's SkyMaterial shader.
// Qt's skymaterial example (advancedsky.frag, qtquick3d v6.12.0; MIT) up to its MAIN(),
// with four marked changes in raymarchClouds(); MAIN() and the painted-sky base below
// the marked boundary are the app's (GPL-3.0-or-later). paintedSky() re-expresses the
// arithmetic of Qt's ProceduralSkyTextureData (GPL-3.0-only): see PROVENANCE.md.
// Provenance and licence texts: PROVENANCE.md and LICENSE-qt-skymaterial.txt beside this file.

//-----------------------------------------------------------------------------
// Constants

const float PI = 3.14159265358979323846;
const float INV_4PI = 0.25 / PI;
const float EARTH_RADIUS = 6371.0; // km

/*
 * Returns the distance between ro and the first intersection with the sphere
 * or -1.0 if there is no intersection. The sphere's origin is (0,0,0).
 * -1.0 is also returned if the ray is pointing away from the sphere.
 */
float raySphereIntersection(vec3 ro, vec3 rd, float radius)
{
    float b = dot(ro, rd);
    float c = dot(ro, ro) - radius*radius;
    if (c > 0.0 && b > 0.0) return -1.0;
    float d = b*b - c;
    if (d < 0.0) return -1.0;
    if (d > b*b) return (-b+sqrt(d));
    return (-b-sqrt(d));
}

//-----------------------------------------------------------------------------
// Volumetric clouds
// Density model: Schneider, "Real-time Volumetric Cloudscapes of Horizon
// Zero Dawn", GPU Pro 7 (2015).
// Lighting model: Wrenninge & Zafar, "Oz: The Great and Volumetric"
// (SIGGRAPH 2013 course on Production Volume Rendering).

float remap01(float v, float lo, float hi)
{
    return clamp((v - lo) / max(hi - lo, 1e-5), 0.0, 1.0);
}

float cloudDensityAt(vec3 pos, float heightFraction)
{
    // pos is in earth-centered coordinates (km).
    // Detail UVW — one full tile of the noise volume = cloudScale km. The XZ
    // offset shifts the camera column off (0,0,0) in noise space so a noise
    // valley at the origin doesn't empty the zenith view. cloudTimeOffset
    // animates the noise slowly through its 3D volume so clouds evolve.
    vec3 local = vec3(pos.x, pos.y - EARTH_RADIUS, pos.z);
    vec3 baseUvw = (local + vec3(cloudWindOffset.x + 73.5, 0.0, cloudWindOffset.y + 41.2))
                   / max(cloudScale, 1e-3);
    baseUvw.y += cloudTimeOffset;

    // Domain warp breaks the periodic repetition of the noise tile.
    vec3 warpSample = textureLod(noiseVolume, baseUvw * 0.35 + vec3(7.2, 1.1, 13.5), 0.0).gba;
    vec3 uvw = baseUvw + (warpSample - 0.5) * 0.35;

    // Coverage UVW at 5× larger period with independent offset.
    vec3 covUvw = uvw * 0.2 + vec3(1.7, 0.31, 2.3);
    float coverageR = textureLod(noiseVolume, covUvw, 0.0).r;

    float threshold = mix(0.85, 0.0, cloudCoverage);
    float baseShape = remap01(coverageR, threshold, threshold + 0.10);
    if (baseShape < 0.001)
        return 0.0;

    float bottomShape = smoothstep(0.0, 0.05, heightFraction);
    float topShape    = smoothstep(1.0, 0.4, heightFraction);
    float vshape = bottomShape * topShape;

    // Worley FBM channels carve cauliflower edges into the base shape.
    vec4 nDetail = textureLod(noiseVolume, uvw, 0.0);
    float erosion = nDetail.g * 0.5 + nDetail.b * 0.3 + nDetail.a * 0.2;
    float erodeStrength = mix(0.1, 0.5, smoothstep(1.0, 0.0, heightFraction));

    float density = baseShape * vshape - erosion * erodeStrength;
    density = clamp(density, 0.0, 1.0);

    return density * cloudDensityScale * 1.6;
}

// Open Garden Planner (L7, 3D review): how much of the deck's forward lobe a full cover
// diffuses away (gFwd below; the silver lining and the sun side of the ambient fade with
// the cover too)
const float CLOUD_DIFFUSION = 0.8;

vec3 raymarchClouds(vec3 ro, vec3 rd, vec3 sunDirWorld, vec3 sunRadiance,
                    vec3 skyZenithRGB, vec3 skyGroundRGB, vec3 skySunSideRGB,
                    out float transmittance)
{
    transmittance = 1.0;
    if (cloudCoverage <= 0.0 || cloudDensityScale <= 0.0)
        return vec3(0.0);
    if (rd.y <= 0.0)
        return vec3(0.0);

    float cloudBottomR = EARTH_RADIUS + cloudBottomKm;
    float cloudTopR = EARTH_RADIUS + cloudTopKm;
    float tStart = raySphereIntersection(ro, rd, cloudBottomR);
    float tEnd = raySphereIntersection(ro, rd, cloudTopR);
    if (tStart < 0.0 || tEnd < 0.0 || tEnd <= tStart)
        return vec3(0.0);
    tEnd = min(tEnd, tStart + cloudMaxDistanceKm);

    int steps = max(cloudPrimarySteps, 1);
    int lightSteps = max(cloudLightSteps, 1);
    float stepLen = (tEnd - tStart) / float(steps);
    float lStepLen = (cloudTopKm - cloudBottomKm) / float(lightSteps);

    // Two-octave Wrenninge multi-scattering approximation (see paper above).
    const int   MS_COUNT = 2;
    const float MS_A = 0.1;
    const float MS_B = 1.0;
    const float MS_C = 0.4;

    // Dual-lobe Henyey-Greenstein — backward lobe brightens front-lit clouds.
    const float gBack = -0.3;
    const float backLobeBlend = 0.2;

    float cosThetaView = dot(rd, sunDirWorld);
    vec3 scattering = vec3(0.0);

    for (int i = 0; i < steps; ++i) {
        float t = tStart + (float(i) + 0.5) * stepLen;
        vec3 pos = ro + rd * t;
        float h = length(pos) - EARTH_RADIUS;
        float hf = (h - cloudBottomKm) / max(cloudTopKm - cloudBottomKm, 1e-3);

        float distanceFade = 1.0 - smoothstep(0.5 * cloudMaxDistanceKm, cloudMaxDistanceKm, t);
        float density = cloudDensityAt(pos, hf) * distanceFade;

        if (density > 1e-4) {
            float ext = density * cloudExtinction;
            float stepT = exp(-ext * stepLen);

            float odSun = 0.0;
            for (int j = 0; j < lightSteps; ++j) {
                vec3 lpos = pos + sunDirWorld * lStepLen * (float(j) + 0.5);
                float lh = length(lpos) - EARTH_RADIUS;
                float lhf = (lh - cloudBottomKm) / max(cloudTopKm - cloudBottomKm, 1e-3);
                odSun += cloudDensityAt(lpos, lhf) * cloudExtinction * lStepLen;
            }

            vec3 msLight = vec3(0.0);
            float a = 1.0, b = 1.0, c = 1.0;
            for (int n = 0; n < MS_COUNT; ++n) {
                // a thick deck diffuses: its forward lobe fades with the cover (3D review
                // of L7 - at full strength an overcast was bright toward a low sun, and
                // with the gain that lit a cloudy sunset and a band round the horizon)
                float gFwd = c * cloudPhaseG * (1.0 - CLOUD_DIFFUSION * cloudCoverage);
                float gBk  = c * gBack;
                float ggF = gFwd * gFwd;
                float ggB = gBk * gBk;
                float denF = 1.0 + ggF - 2.0 * gFwd * cosThetaView;
                float denB = 1.0 + ggB - 2.0 * gBk * cosThetaView;
                float pFwd = INV_4PI * (1.0 - ggF) / (denF * sqrt(denF));
                float pBk  = INV_4PI * (1.0 - ggB) / (denB * sqrt(denB));
                float phaseN = mix(pFwd, pBk, backLobeBlend);
                float sunTN = exp(-odSun * a);
                msLight += b * phaseN * sunTN * sunRadiance;
                a *= MS_A; b *= MS_B; c *= MS_C;
            }

            // Powder brightening for dense interiors.
            float powderBoost = max(1.0, pow(density * 20.0, 0.5));
            msLight *= powderBoost;

            // Additive silver lining toward the sun.
            float silver = pow(clamp(cosThetaView, 0.0, 1.0), 4.0) * (1.0 - exp(-odSun * 2.0));
            // L7: an edge effect - faded with the weather's cover (3D review)
            msLight += silver * sunRadiance * (1.0 - cloudCoverage);

            vec3 ambient = mix(skyGroundRGB, skyZenithRGB, clamp(hf, 0.0, 1.0)) * 0.6;
            float sunFacing = clamp(cosThetaView * 0.5 + 0.5, 0.0, 1.0);
            // L7 (#719): the sun side of the ambient diffuses with the cover as the
            // forward lobe does - its sample is the clear sky's aerosol glow beside a low
            // sun, and a closed deck read 138 / 120 / 102 luma toward / across / away
            sunFacing = mix(sunFacing, 0.5, CLOUD_DIFFUSION * cloudCoverage);
            ambient += skySunSideRGB * sunFacing * 0.6;

            vec3 stepScatter = (msLight + ambient) * (1.0 - stepT);
            scattering += stepScatter * transmittance;
            transmittance *= stepT;

            if (transmittance < 0.01) {
                transmittance = 0.0;
                break;
            }
        }
    }

    return scattering;
}

float ease(float x, float c)
{
    x = clamp(x, 0.0, 1.0);
    if (c > 0.0) {
        if (c < 1.0)
            return 1.0 - pow(1.0 - x, 1.0 / c);
        return pow(x, c);
    }
    if (c < 0.0) {
        if (x < 0.5)
            return pow(x * 2.0, -c) * 0.5;
        return (1.0 - pow(1.0 - (x - 0.5) * 2.0, -c)) * 0.5 + 0.5;
    }
    return 0.0;
}


vec2 sampleSphericalMap(vec3 v)
{
    // Linear azimuth/elevation
    float azimuth = atan(v.z, v.x);      // [-pi, pi]
    float theta   = asin(v.y);           // [-pi/2, pi/2]

    // Non-linear LUT warp: undo the warp applied during LUT generation
    float elevWarp = sqrt(abs(theta) / (PI * 0.5)) * sign(theta) * 0.5 + 0.5;

    // Map azimuth to [0,1]
    float azimuthUv = azimuth / (2.0 * PI) + 0.5;

    return vec2(azimuthUv, elevWarp);
}

//-----------------------------------------------------------------------------
// Open Garden Planner (Phase 17 L7, #391). Everything above this line is Qt's
// advancedsky.frag (MIT) but for four marked changes in raymarchClouds(); from here
// on is the app's (GPL-3.0-or-later; paintedSky(): see PROVENANCE.md).
//
// THE PAINTED SKY IS THE BASE. paintedSky() is Qt's ProceduralSkyTextureData,
// generateSkyTexture() (qtquick3d v6.12.0, src/helpers/proceduralskytexturedata.cpp),
// evaluated per direction instead of into an equirectangular texture: the sky the
// app drew through L1-L5, with the look's own colours (LINEAR, as vector3d uniforms:
// Qt's colour-property polynomial is not the sRGB curve). The atmosphere is painted
// OVER it, and only where it may be:
//
//  - at and below the horizon, and up through the haze band (hazeDeg), the painted
//    sky shows: the fog was calibrated on the painted horizon (fog = horizon x probe
//    exposure x 0.8), so the meadow meets this sky as it met the painted one, in
//    every direction - the atmosphere's horizon changes with the azimuth, the fog's
//    colour cannot;
//  - atmosphereWeight is 1 by day and falls to 0 through civil twilight (the look's
//    twilight fraction), so the night is the painted night exactly;
//  - atmosphereGain scales the physical radiance (W m^-2 sr^-1 after the spectral
//    conversion) into the painted sky's units, in place of the example's 0.1, and
//    cloudLightGain the clouds' scattered light (see the end of MAIN()).
//
// WHERE THE TWO SKIES MEET (#716, #719) - the order of operations in MAIN():
//  1. the painted sky in this direction, and the atmosphere's share of it
//     (atmosphereWeight x smoothstep(0, hazeDeg, elevation));
//  2. the clear sky: the sky-view table x its alpha, this sky's PROFILE
//     (atmosphere_lut.sky_profile) x atmosphereGain - every ring of it has the mean
//     brightness of the painted sky's gradient at its elevation (x one glow factor that
//     keeps the painted sky's light on the ground), so through the haze band two skies
//     of the same mean brightness mix and the sky never darkens toward the horizon;
//  3. the disc;
//  4. the clouds over it: their light x cloudLightGain, which for a deck carries its
//     ANCHOR (quick3d/look.py deck_anchor, measured): a closed deck reads the painted
//     sky's brightness 10 deg up, so the painted haze band below meets it without a
//     band at any sun;
//  5. mix(painted, atmosphere, share), then the skybox's exposure (skyExposed).
//
// The sun disc of the atmosphere is the look's sun colour (sunDiscColor, linear,
// times sunAlpha: 0 while the sun is down), drawn where the atmosphere shows; the
// clouds are lit by the example's sunColor x sunEnergy, faded through civil twilight
// (x atmosphereWeight in MAIN()).

const float PAINTED_SKY_CURVE = 0.09;    // ProceduralSkyTextureData's default skyCurve
const float PAINTED_SUN_MIN_DEG = 1.0;   // ... sunAngleMin
const float PAINTED_SUN_MAX_DEG = 100.0; // ... sunAngleMax
const float PAINTED_SUN_CURVE = 0.05;    // ... sunCurve

vec3 paintedSky(vec3 dir, vec3 sunDir)
{
    float vAngle = acos(clamp(dir.y, -1.0, 1.0));
    if (dir.y < 0.0) {
        float c = (vAngle - PI * 0.5) / (PI * 0.5);
        return mix(paintedHorizon, paintedGround, ease(c, paintedGroundCurve)) * paintedGroundEnergy;
    }
    float c = vAngle / (PI * 0.5);
    vec3 color = mix(paintedHorizon, paintedTop, ease(1.0 - c, PAINTED_SKY_CURVE)) * paintedSkyEnergy;
    float sunAngle = degrees(acos(clamp(dot(sunDir, dir), -1.0, 1.0)));
    if (sunAngle < PAINTED_SUN_MIN_DEG)
        return paintedSun;
    if (sunAngle < PAINTED_SUN_MAX_DEG) {
        float c2 = ease((sunAngle - PAINTED_SUN_MIN_DEG) / (PAINTED_SUN_MAX_DEG - PAINTED_SUN_MIN_DEG),
                        PAINTED_SUN_CURVE);
        return mix(paintedSun, color, c2);
    }
    return color;
}

// The exposure the painted sky's skybox pass applies (Qt's skybox.frag: qt_exposure, compiled
// in by QSSG_FORCE_IBL_EXPOSURE). Qt's screen-space sky path has no such variant under the
// post effects' tonemap, so it passes FRAGCOLOR straight through: without this the
// atmosphere read 1.8x too bright by day and 2.9x at night (3D review of PF-E3D-17's fix).
vec3 skyExposed(vec3 radiance)
{
    return vec3(1.0) - exp(-radiance * skyExposure);
}

void MAIN()
{
    vec3 direction = normalize(qt_eyeDir);
    vec3 sunDirWorld = normalize(vec3(-sunDirection.x, sunDirection.z, -sunDirection.y));
    vec3 painted = paintedSky(direction, sunDirWorld);

    float elevation = asin(clamp(direction.y, -1.0, 1.0));
    float share = atmosphereWeight * smoothstep(0.0, radians(max(hazeDeg, 0.01)), elevation);
    if (share <= 0.0) {
        FRAGCOLOR = vec4(skyExposed(painted), 1.0);
        return;
    }

    // the clear sky: the table's rgb, times its alpha - this sky's profile (#716,
    // atmosphere_lut.sky_profile), which gives every ring above the horizon the painted
    // gradient's mean brightness: one gain alone left a cream low band 1.4-1.8x the
    // painted sky over a horizon that darkened toward 0.5 deg, and a zenith at 0.5-0.8x
    vec2 uv = sampleSphericalMap(direction);
    vec4 skyView = texture(skytextureBuffer, uv);
    vec3 col = skyView.rgb * skyView.a;

    vec3 sunCol = vec3(0.0);
    if (direction.y > 0.0) {
        float sunDot = clamp(dot(sunDirWorld, direction), -1.0, 1.0);
        float sunAngle = degrees(acos(sunDot));
        if (sunAngle < sunDiskInnerAngle) {
            sunCol = sunDiscColor * sunAlpha;
        } else if (sunAngle < sunDiskOuterAngle) {
            // the glow round the core in the painted disc's own colour and energy: the core's
            // x4 (sunDiscColor) clipped a sunset disc and its glow to white (3D review of L7)
            float t = (sunAngle - sunDiskInnerAngle) / (sunDiskOuterAngle - sunDiskInnerAngle);
            t = ease(t, sunDiskFalloff);
            sunCol = paintedSun * sunAlpha * (1.0 - t);
        }
    }

    // Volumetric clouds, as in the example (cloudDensityAt / raymarchClouds above).
    float cloudT = 1.0;
    vec3 cloudScatter = vec3(0.0);
    if (cloudsEnabled) {
        const float SUN_RADIANCE_SCALE = 100.0;
        vec3 sunTint = sunColor.rgb * sunEnergy;
        float sunCosZenith = max(sunDirWorld.y, 0.0);
        float slant = 1.0 / max(sunCosZenith + 0.025, 0.025);
        vec3 sunAtten = exp(-slant * vec3(0.05, 0.15, 0.40));
        // the deck loses the sun through civil twilight as the look does (atmosphereWeight
        // = 1 - twilight; 1 by day): the example clamps the slant at the horizon, so its
        // deck kept the horizon sun's light down to -6 deg and glowed (3D review of L7)
        vec3 sunRadianceLinear = sunTint * sunAtten * SUN_RADIANCE_SCALE * atmosphereWeight;

        vec3 skyZenithRGB = texture(skytextureBuffer, sampleSphericalMap(vec3(0.0, 1.0, 0.0))).rgb;
        vec3 skyGroundRGB = texture(skytextureBuffer, sampleSphericalMap(normalize(vec3(0.0, -0.25, 0.0)))).rgb;
        vec3 sunSideDir = normalize(sunDirWorld + vec3(0.0, 0.1, 0.0));
        vec3 skySunSideRGB = texture(skytextureBuffer, sampleSphericalMap(sunSideDir)).rgb;

        vec3 ro = vec3(0.0, EARTH_RADIUS + eyeAltitude, 0.0);
        cloudScatter = raymarchClouds(ro, direction, sunDirWorld, sunRadianceLinear,
                                      skyZenithRGB, skyGroundRGB, skySunSideRGB, cloudT);
        // The deck takes the hue of the look's horizon - under a weather, the weather's
        // own grey - keeping its own light, as far as cloudHueShare says (quick3d/look.py
        // cloud_hue_share: its own colour stays only where the cloud is thin and the deck
        // open): the example lights its clouds with an analytic sun reddening alone, and a
        // full overcast read beige to mustard (L7), a Snow deck pink at a low sun (#719)
        const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);
        float hueLuma = max(dot(paintedHorizon, LUMA), 1e-5);
        vec3 tinted = paintedHorizon * (dot(cloudScatter, LUMA) / hueLuma);
        cloudScatter = mix(cloudScatter, tinted, cloudHueShare);
    }

    // the atmosphere in the painted sky's units; the disc is already in them. The clouds
    // take the same gain times ATMOSPHERE_CLOUD_GAIN (cloudLightGain, quick3d/look.py
    // cloud_light_gain): the example's scale saturates a full cover to white; a deck takes
    // its anchor on top there (#719)
    vec3 atmosphere = max(col * cloudT * atmosphereGain + cloudScatter * cloudLightGain, vec3(0.0))
                      + sunCol * cloudT;
    FRAGCOLOR = vec4(skyExposed(mix(painted, atmosphere, share)), 1.0);
}
