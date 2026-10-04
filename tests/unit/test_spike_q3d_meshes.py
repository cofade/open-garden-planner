"""Truth and budget gates for the spike's procedural meshes (ADR-047, plan §9).

The look may be stylised; the numbers may not lie. Every plant's bounding box
IS the data (height from the resolver, spread from the 2D canopy) because
``fit_to`` enforces it for all archetypes at once. Determinism uses a tolerance,
not a hash: numpy's SIMD trig differs across CPUs/builds (plan finding F9).
"""

from __future__ import annotations

import numpy as np
import pytest

from open_garden_planner.spike_q3d import meshes as M

PLANTS = [
    ("Apple Tree", "TREE", 420.0, 340.0),
    ("Birch", "TREE", 900.0, 280.0),
    ("Spruce", "TREE", 800.0, 240.0),
    ("Tomato", "PERENNIAL", 200.0, 90.0),
    ("Lettuce", "PERENNIAL", 30.0, 30.0),
    ("Cabbage", "PERENNIAL", 50.0, 90.0),
    ("Onion", "PERENNIAL", 60.0, 15.0),
    ("Chives", "PERENNIAL", 40.0, 30.0),
    ("Sunflower", "PERENNIAL", 300.0, 90.0),
    ("Lavender", "PERENNIAL", 90.0, 120.0),
    ("Hydrangea", "SHRUB", 150.0, 110.0),
    ("Unknown Plant", "SHRUB", 120.0, 100.0),
]


@pytest.mark.parametrize(("species", "ot", "height", "spread"), PLANTS)
def test_plant_bbox_is_the_data(species: str, ot: str, height: float, spread: float) -> None:
    mesh = M.plant_mesh(species, M.item_seed("fixed-" + species), height, spread, ot)
    lo, hi = mesh.bounds()
    assert lo[2] == pytest.approx(0.0, abs=0.5)          # stands on the ground
    assert hi[2] == pytest.approx(height, rel=0.03)      # height gate ±3 %
    span = max(hi[0] - lo[0], hi[1] - lo[1])
    assert span == pytest.approx(spread, rel=0.10)       # spread gate ±10 %
    assert not np.isnan(mesh.positions).any()
    assert not np.isnan(mesh.normals).any()


@pytest.mark.parametrize(("species", "ot", "height", "spread"), PLANTS[:4])
def test_triangle_budget(species: str, ot: str, height: float, spread: float) -> None:
    mesh = M.plant_mesh(species, 7, height, spread, ot)
    budget = 25_000 if ot == "TREE" else 6_000
    assert 0 < mesh.triangle_count <= budget


def test_same_seed_same_mesh_within_tolerance() -> None:
    a = M.plant_mesh("Apple Tree", 1234, 420.0, 340.0, "TREE")
    b = M.plant_mesh("Apple Tree", 1234, 420.0, 340.0, "TREE")
    assert a.vertex_count == b.vertex_count
    assert np.max(np.abs(a.positions - b.positions)) <= 1e-3


def test_different_seeds_are_not_clones() -> None:
    a = M.plant_mesh("Apple Tree", 1, 420.0, 340.0, "TREE")
    b = M.plant_mesh("Apple Tree", 2, 420.0, 340.0, "TREE")
    assert a.vertex_count != b.vertex_count or not np.allclose(a.positions, b.positions)


def test_item_seed_is_stable() -> None:
    assert M.item_seed("abc") == M.item_seed("abc")
    assert M.item_seed("abc") != M.item_seed("abd")


def test_gable_house_top_is_the_plans_ridge_height() -> None:
    """D4: a HOUSE's height IS its ridge height, so the mesh's top — the ridge cap — is it.

    The L0 board pinned 650 + 13 (slab + cap stacked ON the ridge height), which
    made every house 2.7 % and the 250 cm shed 4.8 % taller than the plan.
    """
    fp = [(0.0, 0.0), (900.0, 0.0), (900.0, 540.0), (0.0, 540.0)]
    mesh = M.gable_house(fp, ((0.0, 270.0), (900.0, 270.0)), 650.0)
    assert float(mesh.positions[:, 2].max()) == pytest.approx(650.0, abs=0.5)
    assert float(mesh.positions[:, 2].min()) == pytest.approx(0.0, abs=1e-3)
    # walls stop at the eave, well below the roof; the eave keeps ≥ 220 cm headroom
    wall_tops = mesh.positions[(np.abs(mesh.positions[:, 0] - 0.0) < 1e-3)
                               & (np.abs(mesh.positions[:, 1] - 0.0) < 1e-3), 2]
    assert 220.0 <= float(wall_tops.max()) < 650.0 - 100.0


def test_grass_stays_inside_lawn_and_out_of_the_pond() -> None:
    lawn = [(0.0, 0.0), (400.0, 0.0), (400.0, 300.0), (0.0, 300.0)]
    pond = [(150.0, 100.0), (250.0, 100.0), (250.0, 200.0), (150.0, 200.0)]
    mesh = M.grass(lawn, 3, 400.0, exclude=[pond])
    roots = mesh.positions[::5]  # first vertex of each blade = its root
    assert roots[:, 0].min() >= -2.0 and roots[:, 0].max() <= 402.0
    in_pond = (roots[:, 0] > 152) & (roots[:, 0] < 248) & (roots[:, 1] > 102) & (roots[:, 1] < 198)
    assert not in_pond.any()
    assert mesh.uv[:, 0].min() == 0.0 and mesh.uv[:, 0].max() == 1.0  # wind weight base→tip


def test_concat_offsets_indices() -> None:
    a = M.box(0, 0, 0, 10, 10, 10, "#ffffff")
    b = M.box(50, 0, 0, 10, 10, 10, "#ffffff")
    both = M.MeshData.concat([a, b])
    assert both.vertex_count == a.vertex_count + b.vertex_count
    assert int(both.indices.max()) == both.vertex_count - 1


# ── the flat-normal gate (L0 review P0: the roof slabs stored the OTHER slope's normal) ──
#
# A flat face's stored vertex normal must equal its winding normal (dot ≥ 0.99),
# or the sun lights the wrong face. "Flat face" = a triangle whose three stored
# vertex normals are identical — how every flat builder emits them (``prism`` /
# ``box`` walls and caps, gable triangles, roof slabs, glass panes).
#
# Covered builders: every builder that emits flat faces — FLAT (only flat faces:
# prism, box, raised_bed, round_thing, table, chair, bench, stone_wall, pergola,
# polyline posts/pickets, water_surface, ground_quad) and MIXED (flat faces plus
# smooth tubes/cylinders/spheres: gable_house + its cylinder ridge cap,
# greenhouse frame + glass, trampoline, bird_bath, bbq_grill). Smooth triangles
# (vertex normals differ across the triangle) are exempt from the 0.99 rule —
# their normals are interpolated on purpose — but must still face outward.
#
# Exempt entirely: ``leaves`` / ``flowers`` / ``grass`` and every plant
# archetype built on them, and ``hedge``'s leaf shell (its core IS ``prism``,
# covered here). They are thin double-sided cards (cullMode NoCulling) whose
# normals are BENT by design — spherized toward the crown centre, tilted
# toward the sky — so shading reads as one soft volume, not as facets.

L_FP = [(0.0, 0.0), (300.0, 0.0), (300.0, 100.0), (120.0, 100.0), (120.0, 250.0), (0.0, 250.0)]
RECT = [(0.0, 0.0), (300.0, 0.0), (300.0, 200.0), (0.0, 200.0)]


def _rotated_house(angle_deg: float) -> M.MeshData:
    a = np.radians(angle_deg)
    rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    corners = [rot @ np.array(c) + [500.0, 400.0] for c in
               ((-450.0, -270.0), (450.0, -270.0), (450.0, 270.0), (-450.0, 270.0))]
    ends = [rot @ np.array(c) + [500.0, 400.0] for c in ((-450.0, 0.0), (450.0, 0.0))]
    fp = [(float(x), float(y)) for x, y in corners]
    return M.gable_house(fp, ((float(ends[0][0]), float(ends[0][1])),
                              (float(ends[1][0]), float(ends[1][1]))), 520.0)


FLAT_BUILDERS = {
    "prism_concave": lambda: M.prism(L_FP, 120.0, 0.0, "#808080", "#909090"),
    "prism_clockwise_raised": lambda: M.prism(L_FP[::-1], 80.0, 15.0, "#808080"),
    "box_rotated": lambda: M.box(50.0, 60.0, 0.0, 80.0, 40.0, 100.0, "#808080", 33.0),
    "raised_bed": lambda: M.raised_bed(RECT, 40.0),
    "round_thing": lambda: M.round_thing(0.0, 0.0, 30.0, 30.0, "#c46a3c", "#4a3222"),
    "table": lambda: M.table(0.0, 0.0, 160.0, 90.0, 75.0),
    "chair": lambda: M.chair(0.0, 0.0, 37.0, 85.0),
    "bench": lambda: M.bench(0.0, 0.0, 150.0, 50.0, 85.0),
    "stone_wall": lambda: M.stone_wall([(0.0, 0.0), (400.0, 0.0), (400.0, 300.0)], 200.0),
    "pergola": lambda: M.pergola(RECT, 250.0),
    "fence": lambda: M.polyline_posts_and_pickets([(0.0, 0.0), (500.0, 0.0), (500.0, 380.0)],
                                                  120.0),
    "water_surface": lambda: M.water_surface(L_FP, 2.0),
    "ground_quad": lambda: M.ground_quad(0.0, 0.0, 100.0, 100.0),
}
MIXED_BUILDERS = {
    "gable_house": lambda: M.gable_house([(0.0, 0.0), (900.0, 0.0), (900.0, 540.0), (0.0, 540.0)],
                                         ((0.0, 270.0), (900.0, 270.0)), 450.0),
    "gable_house_rotated_30": lambda: _rotated_house(30.0),
    "gable_house_rotated_200": lambda: _rotated_house(200.0),
    "gable_shed_ridge_north_south": lambda: M.gable_house(
        [(0.0, 0.0), (240.0, 0.0), (240.0, 300.0), (0.0, 300.0)], ((120.0, 0.0), (120.0, 300.0)),
        250.0, wall="#9c7a54", roof="#78695a", pitch_deg=25.0, overhang=20.0),
    "greenhouse_frame": lambda: M.greenhouse(RECT, 220.0)[0],
    "greenhouse_glass": lambda: M.greenhouse(RECT, 220.0)[1],
    "trampoline": lambda: M.trampoline(0.0, 0.0, 140.0, 90.0),
    "bird_bath": lambda: M.bird_bath(0.0, 0.0, 25.0, 90.0),
}
SMOOTH_ONLY = {
    "bbq_grill": lambda: M.bbq_grill(0.0, 0.0, 30.0, 90.0),
    "cylinder": lambda: M.cylinder((0.0, 0.0, 0.0), (40.0, 10.0, 100.0), 8.0, 5.0, "#808080"),
}


_winding_vs_stored = M.normal_vs_winding


@pytest.mark.parametrize("name", sorted(FLAT_BUILDERS))
def test_flat_builder_normals_match_their_winding(name: str) -> None:
    dots, flat = _winding_vs_stored(FLAT_BUILDERS[name]())
    assert len(dots) > 0
    assert flat.all(), f"{name}: {int((~flat).sum())} triangles are not flat-shaded"
    assert dots.min() >= 0.99, f"{name}: worst normal·winding {dots.min():.3f}"


@pytest.mark.parametrize("name", sorted(MIXED_BUILDERS))
def test_mixed_builder_flat_faces_match_and_smooth_parts_face_out(name: str) -> None:
    dots, flat = _winding_vs_stored(MIXED_BUILDERS[name]())
    assert flat.any(), f"{name}: no flat faces found — the gate would be vacuous"
    assert dots[flat].min() >= 0.99, f"{name}: worst flat normal·winding {dots[flat].min():.3f}"
    if (~flat).any():
        assert dots[~flat].min() > 0.5, f"{name}: a smooth triangle faces inward"


@pytest.mark.parametrize("name", sorted(SMOOTH_ONLY))
def test_smooth_parts_face_outward(name: str) -> None:
    dots, _flat = _winding_vs_stored(SMOOTH_ONLY[name]())
    assert dots.min() > 0.5, f"{name}: a smooth triangle faces inward ({dots.min():.3f})"


def test_roof_slopes_store_their_own_normal_not_the_other_one() -> None:
    """The exact L0 defect, pinned: each slab's normal tilts AWAY from the ridge."""
    mesh = M.gable_house([(0.0, 0.0), (900.0, 0.0), (900.0, 540.0), (0.0, 540.0)],
                         ((0.0, 270.0), (900.0, 270.0)), 450.0)
    tri = mesh.indices.reshape(-1, 3)
    cent = mesh.positions[tri].mean(axis=1)
    nv = mesh.normals[tri]
    n = nv[:, 0]
    flat = np.abs(nv - nv[:, :1]).max(axis=(1, 2)) < 1e-6  # not the hexagonal ridge cap
    slab_top = flat & (n[:, 2] > 0.5) & (n[:, 2] < 0.99) & (cent[:, 2] > 250.0)
    south = slab_top & (cent[:, 1] < 270.0)
    north = slab_top & (cent[:, 1] > 270.0)
    assert south.any() and north.any()
    assert (n[south, 1] < -0.3).all()  # the south slope faces south (−N)
    assert (n[north, 1] > 0.3).all()   # the north slope faces north (+N)


# ── the height gate for built objects (L0 review P0: +2.7 % … +15.6 % overshoots) ──

HEIGHT_BUILDERS = {
    "prism": (lambda h: M.prism(L_FP, h, 0.0, "#808080"), 137.0),
    "raised_bed": (lambda h: M.raised_bed(RECT, h), 40.0),
    "round_thing": (lambda h: M.round_thing(0.0, 0.0, 30.0, h, "#c46a3c"), 30.0),
    "table": (lambda h: M.table(0.0, 0.0, 160.0, 90.0, h), 75.0),
    "chair": (lambda h: M.chair(0.0, 0.0, 15.0, h), 85.0),
    "chair_tall": (lambda h: M.chair(0.0, 0.0, 15.0, h), 110.0),
    "bench": (lambda h: M.bench(0.0, 0.0, 150.0, 50.0, h), 85.0),
    "stone_wall": (lambda h: M.stone_wall([(0.0, 0.0), (400.0, 0.0)], h), 200.0),
    "pergola": (lambda h: M.pergola(RECT, h), 250.0),
    "fence": (lambda h: M.polyline_posts_and_pickets([(0.0, 0.0), (500.0, 0.0)], h), 120.0),
    "hedge": (lambda h: M.hedge(RECT, h, 11), 150.0),
    "greenhouse": (lambda h: M.MeshData.concat(M.greenhouse(RECT, h)), 220.0),
    "gable_house": (lambda h: M.gable_house(RECT, ((0.0, 100.0), (300.0, 100.0)), h), 450.0),
    "gable_shed": (lambda h: M.gable_house(RECT, ((0.0, 100.0), (300.0, 100.0)), h,
                                           pitch_deg=25.0, overhang=20.0), 250.0),
    "trampoline": (lambda h: M.trampoline(0.0, 0.0, 140.0, h), 90.0),
    "bbq_grill": (lambda h: M.bbq_grill(0.0, 0.0, 30.0, h), 90.0),
    "bird_bath": (lambda h: M.bird_bath(0.0, 0.0, 25.0, h), 90.0),
}


@pytest.mark.parametrize("name", sorted(HEIGHT_BUILDERS))
def test_built_object_top_is_its_height(name: str) -> None:
    """Each builder honours its height by construction, so ``fit_height`` never distorts."""
    build, h = HEIGHT_BUILDERS[name]
    mesh = build(h)
    assert float(mesh.positions[:, 2].max()) == pytest.approx(h, rel=0.01)
    assert float(mesh.positions[:, 2].min()) >= -1.0  # nothing sinks into the ground
    assert not np.isnan(mesh.positions).any() and not np.isnan(mesh.normals).any()


@pytest.mark.parametrize(("build", "r"), [(M.bird_bath, 25.0), (M.bbq_grill, 30.0)])
def test_round_props_stay_inside_their_footprint(build, r: float) -> None:
    """The bird bath's basin was 1.6× the item radius — wider than the plan's circle."""
    mesh = build(0.0, 0.0, r, 90.0)
    assert float(np.hypot(mesh.positions[:, 0], mesh.positions[:, 1]).max()) <= r * 1.001


def test_fit_height_scales_about_the_ground_and_keeps_flat_normals() -> None:
    mesh = M.gable_house(RECT, ((0.0, 100.0), (300.0, 100.0)), 450.0)
    fitted = M.fit_height(mesh, 300.0)
    assert float(fitted.positions[:, 2].max()) == pytest.approx(300.0, abs=1e-3)
    assert float(fitted.positions[:, 2].min()) == pytest.approx(0.0, abs=1e-3)
    np.testing.assert_allclose(fitted.positions[:, :2], mesh.positions[:, :2])
    np.testing.assert_allclose(np.linalg.norm(fitted.normals, axis=1), 1.0, atol=1e-5)
    dots, flat = _winding_vs_stored(fitted)
    assert dots[flat].min() >= 0.99  # inverse-transpose normals still match the winding


def test_fit_height_shares_one_scale_across_an_items_meshes() -> None:
    frame, glass = M.greenhouse(RECT, 220.0)
    top = max(float(frame.positions[:, 2].max()), float(glass.positions[:, 2].max()))
    f2, g2 = (M.fit_height(m, 180.0, top=top) for m in (frame, glass))
    assert max(float(f2.positions[:, 2].max()), float(g2.positions[:, 2].max())) == \
        pytest.approx(180.0, abs=1e-3)
    s = 180.0 / top
    np.testing.assert_allclose(g2.positions[:, 2], glass.positions[:, 2] * s, rtol=1e-5)


# ── look fixes pinned (L0 review P1) ──


def test_flower_heads_sit_on_their_blade_tips() -> None:
    """Lily/iris/tulip heads floated 2 % above and 10 % inside their blade tips."""
    seed = M.item_seed("lily-test")
    with_heads = M.blades(seed, 100.0, 60.0, "crisp", ("flower", "orange"))
    n_blade_verts = M.blades(seed, 100.0, 60.0, "crisp", ("", "")).vertex_count
    blade_tips = with_heads.positions[:n_blade_verts].reshape(-1, 10, 3)[:, -2:].mean(axis=1)
    heads = with_heads.positions[n_blade_verts:]
    sphere_v = len(M._SPHERE_V)
    k = len(heads) // (sphere_v + 6 * 4)  # per head: one disk sphere + six 4-vertex petals
    assert k >= 1 and len(heads) == k * (sphere_v + 24)
    disks = heads[: k * sphere_v].reshape(k, sphere_v, 3).mean(axis=1)  # = disk centres
    radius = float(np.clip(60.0 * 0.18, 3.0, 7.0))
    lifted = blade_tips + np.array([0.0, 0.0, radius * 0.15], np.float32)  # disk sits on the head
    gap = np.linalg.norm(disks[:, None, :] - lifted[None, :, :], axis=2).min(axis=1)
    assert float(gap.max()) < 0.05


def test_trunk_is_one_bark_shade_not_bands() -> None:
    """Per-segment bark jitter (0.80–1.15) banded trunks like a ladder; now one shade per branch."""
    mesh = M.space_colonization_tree(42, 600.0, 300.0, "fresh")
    sides = 7
    # the wood mesh comes first in the concat, and its first segments are the trunk chain
    seg_cols = mesh.colors[: 2 * sides * 8].reshape(8, 2 * sides, 4)[:, 0, :3]
    assert np.ptp(seg_cols, axis=0).max() < 1e-6


def test_limbs_are_seamless_at_every_joint() -> None:
    """The other half of the banding: each segment ended at 0.92 × its radius in its OWN frame.

    A continuation segment's bottom ring must BE the ring its parent segment
    ended with — same vertices, same normals — or every joint shows a ledge
    (8.5 % on HEAD) and a shading step.
    """
    mesh = M.space_colonization_tree(42, 600.0, 300.0, "fresh")
    sides = 7
    pos = mesh.positions[: 2 * sides * 9].reshape(9, 2, sides, 3)  # 9 trunk segments
    nrm = mesh.normals[: 2 * sides * 9].reshape(9, 2, sides, 3)
    np.testing.assert_allclose(pos[1:, 0], pos[:-1, 1], atol=1e-3)
    np.testing.assert_allclose(nrm[1:, 0], nrm[:-1, 1], atol=1e-5)


def _bending_limb() -> tuple[np.ndarray, ...]:
    """A limb bending from vertical to horizontal (through the old |t_z| = 0.9 helper
    switch) in 12 segments, plus one side branch off node 4."""
    pts, par = [[0.0, 0.0, 0.0]], [-1]
    for k in range(1, 13):
        a = np.radians(90.0 - 7.5 * k)
        pts.append(list(np.asarray(pts[-1]) + 10.0 * np.array([np.cos(a) * 0.6, np.cos(a) * 0.8,
                                                              np.sin(a)])))
        par.append(k - 1)
    pts.append(list(np.asarray(pts[4]) + [10.0, -5.0, 4.0]))
    par.append(4)
    n = len(pts)
    radius = np.linspace(3.0, 1.0, n)
    radius[-1] = 0.8
    is_cont = np.ones(n, bool)
    is_cont[[0, n - 1]] = False
    return np.asarray(pts), np.asarray(par), radius, is_cont


def test_limb_tubes_neither_twist_nor_turn_inside_out() -> None:
    """Parallel-transported ring frames: each ring vertex turns only by the limb's bend."""
    pts, par, radius, is_cont = _bending_limb()
    mesh = M.limb_tubes(pts, par, radius, is_cont, np.ones((len(pts) - 1, 4), np.float32))
    rings = mesh.normals.reshape(-1, 2, 7, 3)
    turn = (rings[:, 0] * rings[:, 1]).sum(axis=2)
    assert float(turn.min()) > np.cos(np.radians(10.0))  # 7.5° bend per segment, no twist
    dots, _flat = M.normal_vs_winding(mesh)
    assert float(dots.min()) > 0.9  # every face faces out
    seg = mesh.positions.reshape(-1, 2, 7, 3)
    np.testing.assert_allclose(seg[1:12, 0], seg[0:11, 1], atol=1e-4)  # shared joint rings
