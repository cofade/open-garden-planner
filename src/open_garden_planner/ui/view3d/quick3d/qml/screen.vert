// The screen door's vertex stage (L2.4, #386): in the DEPTH pass a faded or cut part
// collapses to a point. That pass fills the depth texture ambient occlusion reads, and
// it does not run the fragment discard: a cut roof left a ghost of itself on lawn and
// sky, and every faded occluder its whole silhouette as AO, from the Medium preset up
// (3D review round 2). The shadow pass and the colour pass draw the part as it is - it
// keeps casting its shadow (PF-L3D-08). Used by the built parts' and the water's
// screen-door materials; foliage_door.vert and grass_door.vert add the same lines.
void MAIN()
{
#if QSSG_ENABLE_DEPTH_PASS
    if (uOpacity < 1.0)
        VERTEX = vec3(0.0);
#endif
}
