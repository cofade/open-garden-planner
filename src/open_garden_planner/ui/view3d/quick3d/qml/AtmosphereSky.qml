// Copyright (C) 2026 The Qt Company Ltd.
// SPDX-License-Identifier: BSD-3-Clause
//
// Open Garden Planner (Phase 17 L7, #391): the atmosphere sky - Qt's skymaterial
// example's AdvancedSky.qml (qtquick3d v6.12.0): Hillaire's atmosphere ("A Scalable
// and Production Ready Sky and Atmosphere Rendering Technique", 2020) with Schneider's
// ray-marched volumetric clouds. Provenance, the per-file licence check and the
// licence texts: PROVENANCE.md and LICENSE-qt-skymaterial.txt beside this file.
//
// What the app changed:
//  - the sun's direction (sunDirection, the example's "atmosphere coordinates") is
//    SET by Quick3DHost from the solar position (quick3d/look.py:
//    atmosphere_properties), never read from a light Node: at night the key light is
//    the look's moon, and the sky must keep the sun;
//  - the cloud noise volume is a Texture handed in at creation (Garden.qml: its data
//    is core/scene3d/cloud_noise.py, a port of the example's CloudNoiseTextureData);
//  - the painted-sky base, the haze band, the twilight weight, the gains, the clouds'
//    hue and the disc colour of atmosphere.frag (paintedTop .. sunDiscColor below), the
//    clouds' fade distance (cloudMaxDistanceKm), the silver lining faded with the cover
//    and the clouds' sunlight faded through civil twilight;
//  - the two LUTs are not rendered here: the sky-view table is computed on the CPU
//    once per sun (core/scene3d/atmosphere_lut.py) and handed in as texture data, so
//    the sky is complete in the FIRST frame (see skytextureBuffer).
//
// Like Garden.qml: NO user-visible strings, and every input is data from Python.
import QtQuick
import QtQuick3D

SkyMaterial {
    id: skyMaterial
    fragmentShader: "atmosphere.frag"
    // the example's sample count; one frame for the whole prefilter (iblRenderFrames 0):
    // the view renders on demand, and a probe must see the finished light in ONE frame
    iblSampleCount: 128
    iblRenderFrames: 0
    radianceMapSize: 512
    skyboxMode: SkyMaterial.Cubemap

    property int lutSize: 128
    property int lutSizeTransmit: 128

    // the atmosphere's composition (the example's values). Not read by atmosphere.frag's
    // MAIN(): the sky-view table that carries it is computed on the CPU, from
    // core/scene3d/atmosphere_lut.py's EARTH_ATMOSPHERE (turbidity 0.5 there)
    property real aerosolBaseDensity: 1.3681e20
    property real aerosolBackgroundDensity: 2e6
    property real aerosolHeightScale: 0.73
    property real aerosolBackgroundDividedByBaseDensity: aerosolBackgroundDensity / aerosolBaseDensity
    property real ozoneMeanMonthlyDobson: 347
    property real aerosolTurbidity: 1

    property vector4d aerosolAbsorptionCrossSection: Qt.vector4d(2.8722e-24, 4.6168e-24, 7.9706e-24, 1.3578e-23)
    property vector4d aerosolScatteringCrossSection: Qt.vector4d(1.5908e-22, 1.7711e-22, 2.0942e-22, 2.4033e-22)
    property vector4d groundAlbedo: Qt.vector4d(0.3, 0.3, 0.3, 0.3)

    property int aerosolType: 8
    property real eyeAltitude: 0.05
    // the clouds' sunlight (the example's)
    property real sunEnergy: 1.0
    property vector3d sunColor: Qt.vector3d(1, 1, 1)
    // the sun, in the example's atmosphere coordinates (x, y, z) = (-E, N, up) of the
    // engine frame: Quick3DHost sets it (the default is a sun at 60 degrees in the south)
    property vector3d sunDirection: Qt.vector3d(0, -0.5, 0.8660254)
    property real sunDiskInnerAngle: 1.5
    property real sunDiskOuterAngle: 10.0
    property real sunDiskFalloff: 0.05
    property real sunAlpha: 1.0

    // Volumetric clouds (the example's)
    property bool cloudsEnabled: false
    property real cloudCoverage: 0.4
    property real cloudDensityScale: 1.6
    property real cloudBottomKm: 3.3
    property real cloudTopKm: 4.9
    property real cloudScale: 6.0
    property vector2d cloudWindOffset: Qt.vector2d(0.0, 0.0)
    property real cloudTimeOffset: 0.0
    property real cloudExtinction: 0.7
    property real cloudPhaseG: 0.45
    property int cloudPrimarySteps: 64
    property int cloudLightSteps: 4
    // the example's 80 faded the clouds out between 2.4 and 4.7 degrees above the
    // horizon, where the clear sky's bright horizon then showed through the haze band
    // as a stripe; at 240 the fade lies between 0.8 and 1.6 degrees, inside the haze (L7)
    property real cloudMaxDistanceKm: 240.0

    // ---- the app's (atmosphere.frag) ----
    // the painted sky beneath, LINEAR rgb: ProceduralSkyTextureData's inputs
    property vector3d paintedTop: Qt.vector3d(0.38, 0.67, 0.88)
    property vector3d paintedHorizon: Qt.vector3d(0.67, 0.82, 0.96)
    property vector3d paintedGround: Qt.vector3d(0.05, 0.07, 0.03)
    property vector3d paintedSun: Qt.vector3d(1, 0.88, 0.72)          // the disc x its energy
    property real paintedSkyEnergy: 1.0
    property real paintedGroundEnergy: 1.0
    property real paintedGroundCurve: 0.1
    // 1 by day, 0 at night: how much of the atmosphere is painted over the base
    property real atmosphereWeight: 1.0
    // the band above the horizon through which the atmosphere fades in, degrees
    property real hazeDeg: 6.0
    // physical radiance -> the painted sky's units (the example drew x 0.1)
    property real atmosphereGain: 0.1
    // the clouds' scattered light -> the painted sky's units (atmosphere.frag), and how
    // much of the look's horizon hue they take
    property real cloudLightGain: 0.006
    property real cloudHueShare: 0.0
    // the atmosphere's disc: the look's sun colour, linear (x sunAlpha)
    property vector3d sunDiscColor: Qt.vector3d(1, 0.88, 0.72)

    // the pre-baked 3D Worley/Perlin noise of the cloud raymarch (set at creation)
    property Texture noiseVolume: null

    // the sky-view LUT (Buffer B) — computed on the CPU (core/scene3d/atmosphere_lut.py,
    // a port of the example's transmittance.frag and skytexture.frag) and handed in at
    // creation as texture DATA: a SkyMaterial compiles its shader only once every texture
    // it samples exists, and the example's QuadTextureProvider textures exist only after
    // their first render - so its first frame was white (measured, L7)
    property Texture skytextureBuffer: null
}
