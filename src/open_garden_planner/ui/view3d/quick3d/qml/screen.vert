// The screen door's vertex stage (L2.4, #386): in the DEPTH pass a faded or cut part
// collapses to a point. That pass fills the depth texture ambient occlusion reads, and
// it does not run the fragment discard: a cut roof left a ghost of itself on lawn and
// sky, and every faded occluder its whole silhouette as AO, from the Medium preset up
// (3D review round 2). The shadow pass and the colour pass draw the part as it is - it
// keeps casting its shadow (PF-L3D-08). Used by the built parts' and the water's
// screen-door materials; foliage_door.vert and grass_door.vert add the same lines.
// The vertex colour goes to the fragment stage through vColor (#940, review 2): read as
// VAR_COLOR without it, the door drew a part darker and more saturated than its principled
// look (PF in ogp-3d-renderer 24) - a whole crown of blossom popped lighter the day its
// bloom reached 1 and it left the door.
VARYING vec4 vColor;

void MAIN()
{
    vColor = COLOR;
    // #940: a plant's flowers open and fade one by one. Every vertex of one flower
    // carries its phase in UV.y (plant_forge.accents.with_phase); while the plant's bloom
    // (uSeason) is below 1 a flower whose phase is not below it collapses - in EVERY pass,
    // so its shadow goes with it (the colour pass's dither left whole crowns shaded by
    // flowers barely there). uSeason 1: nothing collapses, whatever a part's uvs.
    if (uSeason < 1.0 && UV0.y >= uSeason)
        VERTEX = vec3(0.0);
#if QSSG_ENABLE_DEPTH_PASS
    if (uOpacity < 1.0)
        VERTEX = vec3(0.0);
#endif
}
