"""Generate plant species SVG illustrations for the garden planner.

Produces top-down view SVGs matching the established illustration style:
- viewBox 0 0 100 100
- Radial gradient foliage base
- Layered ellipse leaf clusters
- Characteristic fruit/flower features
- Consistent color palette

Usage:
    python scripts/generate_plant_svgs.py
"""

import math
import random
from pathlib import Path

OUTPUT_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "open_garden_planner"
    / "resources"
    / "plants"
    / "species"
)

# ---------------------------------------------------------------------------
# Foliage blob path generation
# ---------------------------------------------------------------------------

def _generate_blob_path(seed: int, cx: float = 50, cy: float = 50,
                        radius: float = 32, n_points: int = 8) -> str:
    """Generate an irregular closed blob path using cubic beziers.

    Returns SVG path data string (M ... C ... Z).
    """
    rng = random.Random(seed)
    angles = sorted([i * (2 * math.pi / n_points) + rng.uniform(-0.2, 0.2)
                     for i in range(n_points)])
    points = []
    for a in angles:
        r = radius + rng.uniform(-8, 6)
        points.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    # Build cubic bezier path
    n = len(points)
    d = f"M{points[0][0]:.0f} {points[0][1]:.0f} "
    for i in range(n):
        p0 = points[i]
        p1 = points[(i + 1) % n]
        # Control points at ~1/3 and ~2/3 with slight randomness
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        cp1x = p0[0] + dx * 0.33 + rng.uniform(-4, 4)
        cp1y = p0[1] + dy * 0.33 + rng.uniform(-4, 4)
        cp2x = p0[0] + dx * 0.66 + rng.uniform(-4, 4)
        cp2y = p0[1] + dy * 0.66 + rng.uniform(-4, 4)
        d += f"C{cp1x:.0f} {cp1y:.0f} {cp2x:.0f} {cp2y:.0f} {p1[0]:.0f} {p1[1]:.0f} "
    d += "Z"
    return d


def _generate_leaf_clusters(seed: int, n: int = 5,
                            cx: float = 50, cy: float = 50,
                            spread: float = 18) -> list[dict]:
    """Generate leaf cluster ellipses around center."""
    rng = random.Random(seed)
    clusters = []
    for i in range(n):
        angle = (i / n) * 2 * math.pi + rng.uniform(-0.4, 0.4)
        dist = rng.uniform(8, spread)
        x = cx + dist * math.cos(angle)
        y = cy + dist * math.sin(angle)
        rx = rng.randint(8, 14)
        ry = rng.randint(6, 11)
        opacity = round(rng.uniform(0.4, 0.6), 2)
        clusters.append({"cx": x, "cy": y, "rx": rx, "ry": ry, "opacity": opacity})
    return clusters


# ---------------------------------------------------------------------------
# SVG builder
# ---------------------------------------------------------------------------

def build_plant_svg(spec: dict) -> str:
    """Build an SVG string from a plant specification dict."""
    name = spec["name"]
    grad = spec.get("gradient", ("#508c2e", "#407824", "#30641c"))
    leaf_fill = spec.get("leaf_fill", "#58942e")
    leaf_alt = spec.get("leaf_alt", "#508c28")
    blob_seed = spec.get("seed", hash(name) & 0xFFFF)
    leaf_count = spec.get("leaf_count", 5)
    features = spec.get("features", [])
    leaf_spread = spec.get("leaf_spread", 18)
    foliage_radius = spec.get("foliage_radius", 32)

    grad_id = f"{name}_base"
    blob_path = _generate_blob_path(blob_seed, radius=foliage_radius)
    clusters = _generate_leaf_clusters(blob_seed + 1, leaf_count, spread=leaf_spread)

    lines = []
    lines.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">')
    lines.append(f'  <!-- {spec.get("comment", name)} - top-down view -->')
    lines.append('  <defs>')
    lines.append(f'    <radialGradient id="{grad_id}" cx="50%" cy="50%" r="55%">')
    lines.append(f'      <stop offset="0%" stop-color="{grad[0]}"/>')
    lines.append(f'      <stop offset="70%" stop-color="{grad[1]}"/>')
    lines.append(f'      <stop offset="100%" stop-color="{grad[2]}"/>')
    lines.append('    </radialGradient>')
    lines.append('  </defs>')

    # Foliage base
    lines.append(f'  <path d="{blob_path}" fill="url(#{grad_id})" opacity="0.8"/>')

    # Leaf clusters
    for i, cl in enumerate(clusters):
        fill = leaf_fill if i % 2 == 0 else leaf_alt
        lines.append(
            f'  <ellipse cx="{cl["cx"]:.0f}" cy="{cl["cy"]:.0f}" '
            f'rx="{cl["rx"]}" ry="{cl["ry"]}" '
            f'fill="{fill}" opacity="{cl["opacity"]}"/>'
        )

    # Features (fruits, flowers, etc.)
    for feat in features:
        ft = feat["type"]
        if ft == "circle":
            lines.append(
                f'  <circle cx="{feat["cx"]}" cy="{feat["cy"]}" '
                f'r="{feat["r"]}" fill="{feat["fill"]}" '
                f'opacity="{feat.get("opacity", 0.8)}"/>'
            )
            # Add highlight
            if feat.get("highlight"):
                lines.append(
                    f'  <circle cx="{feat["cx"] - 1}" cy="{feat["cy"] - 1}" '
                    f'r="{feat["r"] * 0.4:.1f}" fill="{feat["highlight"]}" '
                    f'opacity="{feat.get("h_opacity", 0.45)}"/>'
                )
        elif ft == "ellipse":
            transform = f' transform="{feat["transform"]}"' if "transform" in feat else ""
            lines.append(
                f'  <ellipse cx="{feat["cx"]}" cy="{feat["cy"]}" '
                f'rx="{feat["rx"]}" ry="{feat["ry"]}" '
                f'fill="{feat["fill"]}" opacity="{feat.get("opacity", 0.7)}"{transform}/>'
            )
        elif ft == "petal_ring":
            # Ring of petals around center
            n_petals = feat.get("count", 8)
            petal_rx = feat.get("rx", 6)
            petal_ry = feat.get("ry", 14)
            ring_r = feat.get("ring_r", 20)
            color = feat["fill"]
            alt_color = feat.get("alt_fill", color)
            for p in range(n_petals):
                angle = (p / n_petals) * 360
                rad = math.radians(angle)
                px = 50 + ring_r * math.cos(rad)
                py = 50 + ring_r * math.sin(rad)
                fc = color if p % 2 == 0 else alt_color
                op = round(0.75 - p * 0.02, 2)
                lines.append(
                    f'  <ellipse cx="{px:.0f}" cy="{py:.0f}" '
                    f'rx="{petal_rx}" ry="{petal_ry}" '
                    f'fill="{fc}" opacity="{max(0.5, op)}" '
                    f'transform="rotate({angle:.0f} {px:.0f} {py:.0f})"/>'
                )
            # Center disc
            if "center_fill" in feat:
                cr = feat.get("center_r", 8)
                lines.append(
                    f'  <circle cx="50" cy="50" r="{cr}" '
                    f'fill="{feat["center_fill"]}" opacity="0.9"/>'
                )

    # Vein hints
    if spec.get("veins", True):
        rng = random.Random(blob_seed + 99)
        for _ in range(2):
            x1 = 50 + rng.randint(-15, 15)
            y1 = 50 + rng.randint(-15, 15)
            x2 = x1 + rng.randint(-20, 20)
            y2 = y1 + rng.randint(-20, 20)
            lines.append(
                f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                f'stroke="{grad[2]}" stroke-width="0.8" opacity="0.3"/>'
            )

    lines.append('</svg>')
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# Species definitions
# ---------------------------------------------------------------------------

# Helper for fruit circles
def _fruits(positions: list[tuple], fill: str, highlight: str = "",
            r: float = 4.5) -> list[dict]:
    feats = []
    for cx, cy in positions:
        feat: dict = {"type": "circle", "cx": cx, "cy": cy, "r": r, "fill": fill}
        if highlight:
            feat["highlight"] = highlight
        feats.append(feat)
    return feats


def _flower_spikes(positions: list[tuple], fill: str, tip_fill: str = "") -> list[dict]:
    feats = []
    for cx, cy, rot in positions:
        transform = f"rotate({rot} {cx} {cy})" if rot else ""
        feat: dict = {
            "type": "ellipse", "cx": cx, "cy": cy, "rx": 2.5, "ry": 7,
            "fill": fill, "opacity": 0.75,
        }
        if transform:
            feat["transform"] = transform
        feats.append(feat)
        if tip_fill:
            tf: dict = {
                "type": "ellipse", "cx": cx, "cy": cy - 4, "rx": 1.5, "ry": 2.5,
                "fill": tip_fill, "opacity": 0.55,
            }
            if transform:
                tf["transform"] = transform
            feats.append(tf)
    return feats


SPECIES: list[dict] = [
    # =========== VEGETABLES (30) ===========
    {"name": "pepper", "comment": "Bell pepper plant with colorful fruits",
     "gradient": ("#4a8828", "#3c7420", "#2e6018"),
     "features": _fruits([(38, 40), (62, 45), (48, 62), (30, 55)], "#e04030", "#f06050")
     + _fruits([(68, 60)], "#f0c020", "#f8d848", r=4)},

    {"name": "eggplant", "comment": "Eggplant with purple fruits",
     "gradient": ("#4a8828", "#3c7420", "#2e6018"),
     "features": [
         {"type": "ellipse", "cx": 40, "cy": 42, "rx": 6, "ry": 9, "fill": "#4a2068", "opacity": 0.85},
         {"type": "ellipse", "cx": 62, "cy": 55, "rx": 5, "ry": 8, "fill": "#522878", "opacity": 0.8},
         {"type": "ellipse", "cx": 48, "cy": 65, "rx": 5, "ry": 7, "fill": "#4a2068", "opacity": 0.75},
     ]},

    {"name": "zucchini", "comment": "Zucchini plant with large leaves and fruits",
     "gradient": ("#508c2e", "#407824", "#306018"), "foliage_radius": 35,
     "features": [
         {"type": "ellipse", "cx": 38, "cy": 55, "rx": 5, "ry": 12, "fill": "#3a7828", "opacity": 0.8,
          "transform": "rotate(-30 38 55)"},
         {"type": "ellipse", "cx": 62, "cy": 48, "rx": 4, "ry": 10, "fill": "#3a7828", "opacity": 0.75,
          "transform": "rotate(20 62 48)"},
     ] + _fruits([(44, 35)], "#f0c820", "#f8d848", r=4)},

    {"name": "cucumber", "comment": "Cucumber vine with small fruits",
     "gradient": ("#508c2e", "#407824", "#306018"),
     "features": [
         {"type": "ellipse", "cx": 40, "cy": 42, "rx": 4, "ry": 9, "fill": "#3c8030", "opacity": 0.8,
          "transform": "rotate(-20 40 42)"},
         {"type": "ellipse", "cx": 58, "cy": 56, "rx": 3.5, "ry": 8, "fill": "#448828", "opacity": 0.75,
          "transform": "rotate(15 58 56)"},
     ]},

    {"name": "pumpkin", "comment": "Pumpkin plant with sprawling vines",
     "gradient": ("#4a8428", "#3c7020", "#2e5c18"), "foliage_radius": 35,
     "features": _fruits([(50, 50), (35, 60)], "#e8882 0", "#f0a040", r=7)},

    {"name": "squash", "comment": "Squash plant with large leaves",
     "gradient": ("#4a8828", "#3c7420", "#2e6018"), "foliage_radius": 34,
     "features": _fruits([(48, 52)], "#e8a830", "#f0c050", r=6)
     + _fruits([(62, 58)], "#d89020", "#e0a838", r=5)},

    {"name": "bean", "comment": "Bean plant with climbing tendrils",
     "gradient": ("#58a030", "#488c28", "#387820"), "leaf_count": 6,
     "features": [
         {"type": "ellipse", "cx": 42, "cy": 44, "rx": 2, "ry": 6, "fill": "#408028", "opacity": 0.7,
          "transform": "rotate(-10 42 44)"},
         {"type": "ellipse", "cx": 58, "cy": 52, "rx": 2, "ry": 6, "fill": "#408028", "opacity": 0.65,
          "transform": "rotate(15 58 52)"},
     ]},

    {"name": "pea", "comment": "Pea plant with tendrils and pods",
     "gradient": ("#60a838", "#509428", "#408020"), "leaf_count": 6,
     "features": [
         {"type": "ellipse", "cx": 40, "cy": 42, "rx": 2.5, "ry": 5, "fill": "#78b848", "opacity": 0.7},
         {"type": "ellipse", "cx": 56, "cy": 55, "rx": 2, "ry": 5, "fill": "#78b848", "opacity": 0.65},
     ]},

    {"name": "corn", "comment": "Corn stalk from above - star pattern",
     "gradient": ("#58a030", "#488c28", "#387820"), "leaf_count": 4,
     "leaf_spread": 22, "foliage_radius": 28,
     "features": [
         {"type": "ellipse", "cx": 50, "cy": 20, "rx": 5, "ry": 22, "fill": "#58a830", "opacity": 0.65},
         {"type": "ellipse", "cx": 50, "cy": 80, "rx": 5, "ry": 22, "fill": "#58a830", "opacity": 0.6},
         {"type": "ellipse", "cx": 20, "cy": 50, "rx": 22, "ry": 5, "fill": "#58a830", "opacity": 0.65},
         {"type": "ellipse", "cx": 80, "cy": 50, "rx": 22, "ry": 5, "fill": "#58a830", "opacity": 0.6},
         {"type": "circle", "cx": 50, "cy": 50, "r": 5, "fill": "#c8a830", "opacity": 0.6},
     ], "veins": False},

    {"name": "carrot", "comment": "Carrot foliage from above",
     "gradient": ("#58a830", "#489428", "#388020"), "leaf_count": 6,
     "leaf_fill": "#60b038", "leaf_alt": "#58a830",
     "features": [
         {"type": "circle", "cx": 50, "cy": 50, "r": 5, "fill": "#e08030", "opacity": 0.6},
     ]},

    {"name": "radish", "comment": "Radish plant with round leaves",
     "gradient": ("#58a830", "#489428", "#388020"), "leaf_count": 5, "foliage_radius": 26,
     "features": [
         {"type": "circle", "cx": 50, "cy": 50, "r": 6, "fill": "#d83848", "opacity": 0.5},
     ]},

    {"name": "beet", "comment": "Beetroot with dark red-green foliage",
     "gradient": ("#4a7830", "#3c6428", "#2e5020"),
     "leaf_fill": "#5a3838", "leaf_alt": "#4a7030",
     "features": [
         {"type": "circle", "cx": 50, "cy": 50, "r": 6, "fill": "#881838", "opacity": 0.5},
     ]},

    {"name": "turnip", "comment": "Turnip with broad leaves",
     "gradient": ("#58a030", "#488c28", "#387820"), "leaf_count": 5,
     "features": [
         {"type": "circle", "cx": 50, "cy": 52, "r": 6, "fill": "#d8c8e0", "opacity": 0.5},
     ]},

    {"name": "potato", "comment": "Potato plant with dense foliage",
     "gradient": ("#508c2e", "#407824", "#306018"), "leaf_count": 6,
     "features": _fruits([(45, 42), (58, 55)], "#f0f0e0", "#ffffff", r=2)},

    {"name": "onion", "comment": "Onion plant with tubular leaves",
     "gradient": ("#58a830", "#489428", "#388020"), "leaf_count": 4,
     "leaf_spread": 12, "foliage_radius": 24,
     "features": [
         {"type": "ellipse", "cx": 50, "cy": 28, "rx": 3, "ry": 16, "fill": "#68b840", "opacity": 0.65},
         {"type": "ellipse", "cx": 42, "cy": 34, "rx": 3, "ry": 14, "fill": "#60b038", "opacity": 0.6,
          "transform": "rotate(-15 42 34)"},
         {"type": "ellipse", "cx": 58, "cy": 32, "rx": 3, "ry": 14, "fill": "#68b840", "opacity": 0.55,
          "transform": "rotate(15 58 32)"},
     ]},

    {"name": "garlic", "comment": "Garlic plant with narrow upright leaves",
     "gradient": ("#68a848", "#589438", "#488028"), "leaf_count": 4,
     "leaf_spread": 10, "foliage_radius": 22,
     "features": [
         {"type": "ellipse", "cx": 50, "cy": 26, "rx": 2.5, "ry": 18, "fill": "#70b848", "opacity": 0.6},
         {"type": "ellipse", "cx": 44, "cy": 30, "rx": 2.5, "ry": 16, "fill": "#68b040", "opacity": 0.55,
          "transform": "rotate(-12 44 30)"},
     ]},

    {"name": "leek", "comment": "Leek plant - upright fan of leaves",
     "gradient": ("#58a038", "#489028", "#387c20"), "leaf_count": 4,
     "leaf_spread": 10, "foliage_radius": 24,
     "features": [
         {"type": "ellipse", "cx": 50, "cy": 24, "rx": 4, "ry": 20, "fill": "#68b040", "opacity": 0.65},
         {"type": "ellipse", "cx": 56, "cy": 28, "rx": 3.5, "ry": 18, "fill": "#60a838", "opacity": 0.6,
          "transform": "rotate(10 56 28)"},
     ]},

    {"name": "celery", "comment": "Celery - upright stalks from above",
     "gradient": ("#68b840", "#58a430", "#489028"), "leaf_count": 5,
     "leaf_spread": 14, "foliage_radius": 26,
     "features": [
         {"type": "circle", "cx": 50, "cy": 50, "r": 6, "fill": "#b8d888", "opacity": 0.5},
     ]},

    {"name": "broccoli", "comment": "Broccoli with dense floret head",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 5,
     "foliage_radius": 34,
     "features": [
         {"type": "circle", "cx": 50, "cy": 48, "r": 14, "fill": "#388028", "opacity": 0.7},
         {"type": "circle", "cx": 44, "cy": 44, "r": 5, "fill": "#489838", "opacity": 0.5},
         {"type": "circle", "cx": 56, "cy": 44, "r": 5, "fill": "#409030", "opacity": 0.45},
         {"type": "circle", "cx": 50, "cy": 52, "r": 5, "fill": "#489838", "opacity": 0.45},
     ]},

    {"name": "cauliflower", "comment": "Cauliflower with white head",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 5,
     "foliage_radius": 34,
     "features": [
         {"type": "circle", "cx": 50, "cy": 48, "r": 14, "fill": "#f0ece0", "opacity": 0.85},
         {"type": "circle", "cx": 44, "cy": 44, "r": 5, "fill": "#f8f4e8", "opacity": 0.5},
         {"type": "circle", "cx": 56, "cy": 46, "r": 5, "fill": "#e8e4d8", "opacity": 0.45},
     ]},

    {"name": "cabbage", "comment": "Cabbage - tight leaf rosette",
     "gradient": ("#488c2e", "#3a7824", "#2c641c"), "leaf_count": 6,
     "foliage_radius": 34,
     "features": [
         {"type": "circle", "cx": 50, "cy": 50, "r": 16, "fill": "#78c058", "opacity": 0.6},
         {"type": "circle", "cx": 50, "cy": 50, "r": 10, "fill": "#a0d880", "opacity": 0.5},
         {"type": "circle", "cx": 50, "cy": 50, "r": 5, "fill": "#c8e8a8", "opacity": 0.4},
     ]},

    {"name": "kale", "comment": "Curly kale leaves",
     "gradient": ("#2a6828", "#1c5420", "#104018"), "leaf_count": 6,
     "leaf_fill": "#387838", "leaf_alt": "#2a6828",
     "foliage_radius": 33},

    {"name": "spinach", "comment": "Spinach - flat leaf rosette",
     "gradient": ("#408830", "#308028", "#206820"), "leaf_count": 6,
     "leaf_fill": "#48a038", "leaf_alt": "#409830",
     "foliage_radius": 30},

    {"name": "lettuce", "comment": "Lettuce - light green rosette",
     "gradient": ("#78c448", "#68b438", "#58a028"), "leaf_count": 6,
     "foliage_radius": 32,
     "features": [
         {"type": "circle", "cx": 50, "cy": 50, "r": 12, "fill": "#98d868", "opacity": 0.5},
         {"type": "circle", "cx": 50, "cy": 50, "r": 6, "fill": "#b8e888", "opacity": 0.4},
     ]},

    {"name": "arugula", "comment": "Arugula with narrow jagged leaves",
     "gradient": ("#509830", "#408828", "#307820"), "leaf_count": 6,
     "leaf_spread": 16, "foliage_radius": 28},

    {"name": "chard", "comment": "Swiss chard with colorful stems",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 5,
     "features": [
         {"type": "ellipse", "cx": 50, "cy": 45, "rx": 2, "ry": 12, "fill": "#e04040", "opacity": 0.6},
         {"type": "ellipse", "cx": 40, "cy": 48, "rx": 2, "ry": 10, "fill": "#e8a020", "opacity": 0.55,
          "transform": "rotate(-15 40 48)"},
         {"type": "ellipse", "cx": 60, "cy": 46, "rx": 2, "ry": 10, "fill": "#f0d020", "opacity": 0.55,
          "transform": "rotate(15 60 46)"},
     ]},

    {"name": "artichoke", "comment": "Artichoke with spiky silvery leaves",
     "gradient": ("#688c58", "#587848", "#486438"), "leaf_count": 5,
     "leaf_fill": "#789c68", "leaf_alt": "#688c58",
     "foliage_radius": 34,
     "features": [
         {"type": "circle", "cx": 50, "cy": 48, "r": 10, "fill": "#789068", "opacity": 0.6},
     ]},

    {"name": "asparagus", "comment": "Asparagus fern from above",
     "gradient": ("#58a838", "#489428", "#388020"), "leaf_count": 6,
     "leaf_spread": 20, "foliage_radius": 28,
     "leaf_fill": "#68b848", "leaf_alt": "#58a838"},

    {"name": "rhubarb", "comment": "Rhubarb with large leaves and red stems",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 4,
     "foliage_radius": 36, "leaf_spread": 20,
     "features": [
         {"type": "ellipse", "cx": 50, "cy": 50, "rx": 2.5, "ry": 20, "fill": "#c03040", "opacity": 0.6},
         {"type": "ellipse", "cx": 38, "cy": 50, "rx": 2.5, "ry": 18, "fill": "#c83848", "opacity": 0.55,
          "transform": "rotate(-25 38 50)"},
         {"type": "ellipse", "cx": 62, "cy": 50, "rx": 2.5, "ry": 18, "fill": "#c03040", "opacity": 0.55,
          "transform": "rotate(25 62 50)"},
     ]},

    {"name": "okra", "comment": "Okra plant with large lobed leaves",
     "gradient": ("#4a8828", "#3c7420", "#2e6018"), "leaf_count": 5,
     "foliage_radius": 32,
     "features": _fruits([(48, 40), (58, 55)], "#68a838", "#80c048", r=3)},

    # =========== HERBS (20) ===========
    {"name": "basil", "comment": "Sweet basil with broad aromatic leaves",
     "gradient": ("#50a030", "#409028", "#308020"), "leaf_count": 5,
     "leaf_fill": "#58b038", "leaf_alt": "#48a030", "foliage_radius": 28},

    {"name": "rosemary", "comment": "Rosemary with needle-like leaves",
     "gradient": ("#587858", "#486848", "#385838"), "leaf_count": 5,
     "leaf_fill": "#688868", "leaf_alt": "#587858", "foliage_radius": 26,
     "features": _fruits([(40, 38), (58, 42), (48, 58)], "#a8a0d8", r=2)},

    {"name": "thyme", "comment": "Thyme - tiny-leaved aromatic",
     "gradient": ("#608848", "#508038", "#407028"), "leaf_count": 6,
     "leaf_fill": "#709850", "leaf_alt": "#608848", "foliage_radius": 24},

    {"name": "sage", "comment": "Sage with silvery-green textured leaves",
     "gradient": ("#709880", "#608870", "#507860"), "leaf_count": 5,
     "leaf_fill": "#80a890", "leaf_alt": "#709880", "foliage_radius": 28},

    {"name": "mint", "comment": "Mint with spreading fresh green leaves",
     "gradient": ("#48b838", "#38a828", "#289820"), "leaf_count": 6,
     "leaf_fill": "#58c848", "leaf_alt": "#48b838", "foliage_radius": 30},

    {"name": "parsley", "comment": "Parsley with curly bright green leaves",
     "gradient": ("#48a830", "#389828", "#288820"), "leaf_count": 6,
     "leaf_fill": "#58b838", "leaf_alt": "#48a830", "foliage_radius": 26},

    {"name": "cilantro", "comment": "Cilantro with flat delicate leaves",
     "gradient": ("#58a838", "#489428", "#388020"), "leaf_count": 6,
     "leaf_fill": "#68b848", "leaf_alt": "#58a838", "foliage_radius": 26},

    {"name": "dill", "comment": "Dill with feathery fronds",
     "gradient": ("#58a838", "#489428", "#388020"), "leaf_count": 5,
     "leaf_fill": "#70c050", "leaf_alt": "#60b040", "foliage_radius": 28,
     "features": [
         {"type": "circle", "cx": 50, "cy": 38, "r": 8, "fill": "#c8c830", "opacity": 0.4},
     ]},

    {"name": "chives", "comment": "Chives - thin tubular leaves with purple flowers",
     "gradient": ("#48a830", "#389828", "#288820"), "leaf_count": 4,
     "leaf_spread": 10, "foliage_radius": 22,
     "features": [
         {"type": "ellipse", "cx": 50, "cy": 26, "rx": 2, "ry": 18, "fill": "#58b838", "opacity": 0.65},
         {"type": "ellipse", "cx": 44, "cy": 30, "rx": 2, "ry": 16, "fill": "#50b030", "opacity": 0.6,
          "transform": "rotate(-8 44 30)"},
         {"type": "ellipse", "cx": 56, "cy": 28, "rx": 2, "ry": 16, "fill": "#58b838", "opacity": 0.6,
          "transform": "rotate(8 56 28)"},
     ] + _fruits([(50, 30), (44, 34)], "#c080d0", r=3)},

    {"name": "oregano", "comment": "Oregano with small rounded leaves",
     "gradient": ("#588838", "#488028", "#387020"), "leaf_count": 6,
     "leaf_fill": "#689848", "leaf_alt": "#588838", "foliage_radius": 26},

    {"name": "tarragon", "comment": "Tarragon with narrow aromatic leaves",
     "gradient": ("#608840", "#508030", "#407028"), "leaf_count": 5,
     "leaf_fill": "#709848", "leaf_alt": "#608840", "foliage_radius": 26},

    {"name": "lemongrass", "comment": "Lemongrass with tall grass-like leaves",
     "gradient": ("#78b848", "#68a838", "#589828"), "leaf_count": 4,
     "leaf_spread": 14, "foliage_radius": 26,
     "features": [
         {"type": "ellipse", "cx": 50, "cy": 22, "rx": 4, "ry": 22, "fill": "#80c050", "opacity": 0.6},
         {"type": "ellipse", "cx": 42, "cy": 26, "rx": 3.5, "ry": 20, "fill": "#78b848", "opacity": 0.55,
          "transform": "rotate(-12 42 26)"},
         {"type": "ellipse", "cx": 58, "cy": 24, "rx": 3.5, "ry": 20, "fill": "#80c050", "opacity": 0.55,
          "transform": "rotate(12 58 24)"},
     ]},

    {"name": "chamomile", "comment": "Chamomile with daisy-like flowers",
     "gradient": ("#58a038", "#489028", "#388020"), "leaf_count": 5,
     "foliage_radius": 28,
     "features": _fruits([(42, 36), (58, 40), (35, 55), (55, 60), (48, 45)],
                         "#f8f0d0", "#ffffff", r=4)
     + _fruits([(42, 36), (58, 40), (35, 55), (55, 60), (48, 45)],
               "#e8c828", r=2)},

    {"name": "fennel", "comment": "Fennel with feathery fronds and bulb",
     "gradient": ("#58a838", "#489428", "#388020"), "leaf_count": 5,
     "leaf_fill": "#70c050", "leaf_alt": "#60b040", "foliage_radius": 30,
     "features": [
         {"type": "circle", "cx": 50, "cy": 55, "r": 8, "fill": "#c8d8a8", "opacity": 0.5},
     ]},

    {"name": "marjoram", "comment": "Sweet marjoram with small grey-green leaves",
     "gradient": ("#608850", "#508040", "#407030"), "leaf_count": 6,
     "leaf_fill": "#709860", "leaf_alt": "#608850", "foliage_radius": 24},

    {"name": "bay_laurel", "comment": "Bay laurel with glossy dark leaves",
     "gradient": ("#3a6828", "#2c5820", "#1e4818"), "leaf_count": 5,
     "leaf_fill": "#4a7838", "leaf_alt": "#3a6828", "foliage_radius": 30},

    {"name": "stevia", "comment": "Stevia with serrated bright leaves",
     "gradient": ("#58b038", "#48a028", "#389020"), "leaf_count": 5,
     "leaf_fill": "#68c048", "leaf_alt": "#58b038", "foliage_radius": 24},

    {"name": "sorrel", "comment": "Sorrel with arrow-shaped leaves",
     "gradient": ("#508830", "#408028", "#307020"), "leaf_count": 5,
     "leaf_fill": "#609838", "leaf_alt": "#508830", "foliage_radius": 28},

    {"name": "borage", "comment": "Borage with star-shaped blue flowers",
     "gradient": ("#4a8028", "#3c7020", "#2e6018"), "leaf_count": 5,
     "foliage_radius": 30,
     "features": _fruits([(40, 35), (60, 38), (45, 55), (58, 58), (50, 42)],
                         "#5878d0", "#8098e0", r=3.5)},

    {"name": "lovage", "comment": "Lovage with large celery-like leaves",
     "gradient": ("#488828", "#3c7820", "#2e6818"), "leaf_count": 5,
     "leaf_fill": "#589838", "leaf_alt": "#488828", "foliage_radius": 32},

    # =========== FLOWERS (20) ===========
    {"name": "tulip", "comment": "Tulip - cup-shaped flower from above",
     "gradient": ("#488c28", "#3a7820", "#2c6418"), "leaf_count": 3,
     "leaf_spread": 20, "foliage_radius": 28,
     "features": [
         {"type": "ellipse", "cx": 50, "cy": 42, "rx": 10, "ry": 12, "fill": "#e83060", "opacity": 0.85},
         {"type": "ellipse", "cx": 50, "cy": 42, "rx": 7, "ry": 9, "fill": "#f04878", "opacity": 0.7},
         {"type": "ellipse", "cx": 50, "cy": 42, "rx": 4, "ry": 5, "fill": "#f86890", "opacity": 0.55},
     ]},

    {"name": "daffodil", "comment": "Daffodil with trumpet center",
     "gradient": ("#488c28", "#3a7820", "#2c6418"), "leaf_count": 3,
     "leaf_spread": 18, "foliage_radius": 26,
     "features": [
         {"type": "petal_ring", "count": 6, "rx": 6, "ry": 14, "ring_r": 16,
          "fill": "#f8e028", "alt_fill": "#f0d820", "center_fill": "#e8a018", "center_r": 7},
     ]},

    {"name": "dahlia", "comment": "Dahlia with dense petal layers",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 4,
     "foliage_radius": 30,
     "features": [
         {"type": "petal_ring", "count": 12, "rx": 4, "ry": 12, "ring_r": 18,
          "fill": "#d83060", "alt_fill": "#e04070", "center_fill": "#c82050", "center_r": 6},
     ]},

    {"name": "peony", "comment": "Peony with fluffy layered petals",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 4,
     "foliage_radius": 32,
     "features": [
         {"type": "circle", "cx": 50, "cy": 46, "r": 18, "fill": "#f0a0b8", "opacity": 0.8},
         {"type": "circle", "cx": 50, "cy": 46, "r": 14, "fill": "#f0b0c8", "opacity": 0.7},
         {"type": "circle", "cx": 50, "cy": 46, "r": 10, "fill": "#f8c0d0", "opacity": 0.6},
         {"type": "circle", "cx": 50, "cy": 46, "r": 6, "fill": "#f8d0d8", "opacity": 0.5},
     ]},

    {"name": "iris", "comment": "Iris with sword-like leaves and flower",
     "gradient": ("#4a7838", "#3c6830", "#2e5828"), "leaf_count": 3,
     "leaf_spread": 16, "foliage_radius": 28,
     "features": [
         {"type": "ellipse", "cx": 50, "cy": 38, "rx": 10, "ry": 14, "fill": "#6848a0", "opacity": 0.8},
         {"type": "ellipse", "cx": 50, "cy": 38, "rx": 6, "ry": 8, "fill": "#8068b8", "opacity": 0.6},
         {"type": "circle", "cx": 50, "cy": 38, "r": 3, "fill": "#f0d830", "opacity": 0.6},
     ]},

    {"name": "lily", "comment": "Lily with star-shaped petals",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 4,
     "foliage_radius": 30,
     "features": [
         {"type": "petal_ring", "count": 6, "rx": 5, "ry": 16, "ring_r": 16,
          "fill": "#f8f0e0", "alt_fill": "#f0e8d8", "center_fill": "#e8c030", "center_r": 5},
     ]},

    {"name": "marigold", "comment": "Marigold with dense orange petals",
     "gradient": ("#4a8828", "#3c7420", "#2e6018"), "leaf_count": 5,
     "foliage_radius": 30,
     "features": [
         {"type": "petal_ring", "count": 10, "rx": 4, "ry": 10, "ring_r": 14,
          "fill": "#f0a020", "alt_fill": "#e89018", "center_fill": "#c87010", "center_r": 5},
     ]},

    {"name": "zinnia", "comment": "Zinnia with bold colorful petals",
     "gradient": ("#488c28", "#3a7820", "#2c6418"), "leaf_count": 4,
     "foliage_radius": 28,
     "features": [
         {"type": "petal_ring", "count": 10, "rx": 5, "ry": 12, "ring_r": 16,
          "fill": "#e84060", "alt_fill": "#f05070", "center_fill": "#c83050", "center_r": 5},
     ]},

    {"name": "cosmos", "comment": "Cosmos with delicate petals",
     "gradient": ("#58a038", "#489028", "#388020"), "leaf_count": 5,
     "foliage_radius": 26,
     "features": [
         {"type": "petal_ring", "count": 8, "rx": 5, "ry": 14, "ring_r": 18,
          "fill": "#f0a0c0", "alt_fill": "#f8b0d0", "center_fill": "#e8c030", "center_r": 5},
     ]},

    {"name": "aster", "comment": "Aster with many narrow petals",
     "gradient": ("#488c28", "#3a7820", "#2c6418"), "leaf_count": 5,
     "foliage_radius": 28,
     "features": [
         {"type": "petal_ring", "count": 12, "rx": 3, "ry": 12, "ring_r": 16,
          "fill": "#9868c8", "alt_fill": "#a878d0", "center_fill": "#e8c830", "center_r": 5},
     ]},

    {"name": "chrysanthemum", "comment": "Chrysanthemum with dense layered petals",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 4,
     "foliage_radius": 30,
     "features": [
         {"type": "petal_ring", "count": 14, "rx": 3, "ry": 10, "ring_r": 16,
          "fill": "#e8c030", "alt_fill": "#f0c838", "center_fill": "#c8a020", "center_r": 5},
     ]},

    {"name": "geranium", "comment": "Geranium with round leaf clusters and flowers",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 5,
     "foliage_radius": 30,
     "features": _fruits([(42, 34), (58, 38), (36, 52), (56, 56), (48, 42)],
                         "#e84060", "#f06878", r=4)},

    {"name": "petunia", "comment": "Petunia with trumpet-shaped flowers",
     "gradient": ("#488c28", "#3a7820", "#2c6418"), "leaf_count": 5,
     "foliage_radius": 28,
     "features": _fruits([(40, 36), (60, 40), (48, 56), (35, 52), (62, 55)],
                         "#a848c0", "#c068d8", r=5)},

    {"name": "pansy", "comment": "Pansy with face-like blooms",
     "gradient": ("#488c28", "#3a7820", "#2c6418"), "leaf_count": 5,
     "foliage_radius": 26,
     "features": [
         {"type": "circle", "cx": 42, "cy": 38, "r": 7, "fill": "#5828a0", "opacity": 0.8},
         {"type": "circle", "cx": 42, "cy": 38, "r": 4, "fill": "#f0d030", "opacity": 0.6},
         {"type": "circle", "cx": 58, "cy": 42, "r": 6, "fill": "#6838b0", "opacity": 0.75},
         {"type": "circle", "cx": 58, "cy": 42, "r": 3, "fill": "#f0d030", "opacity": 0.55},
     ]},

    {"name": "hydrangea", "comment": "Hydrangea with large flower clusters",
     "gradient": ("#3a6828", "#2c5820", "#1e4818"), "leaf_count": 4,
     "foliage_radius": 34,
     "features": [
         {"type": "circle", "cx": 48, "cy": 44, "r": 16, "fill": "#8898d8", "opacity": 0.7},
     ] + _fruits([(42, 38), (54, 40), (46, 48), (56, 50), (44, 52), (52, 44),
                  (48, 36), (40, 46), (58, 46)],
                 "#98a8e0", "#b0b8e8", r=3)},

    {"name": "clematis", "comment": "Clematis vine with star-shaped flowers",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 5,
     "foliage_radius": 30,
     "features": [
         {"type": "petal_ring", "count": 6, "rx": 5, "ry": 14, "ring_r": 16,
          "fill": "#8858b8", "alt_fill": "#9868c8", "center_fill": "#f0e8c0", "center_r": 4},
     ]},

    {"name": "wisteria", "comment": "Wisteria with cascading flower clusters",
     "gradient": ("#3a6828", "#2c5820", "#1e4818"), "leaf_count": 5,
     "foliage_radius": 32,
     "features": _flower_spikes(
         [(35, 35, -20), (50, 30, 0), (65, 35, 20), (30, 55, -30), (70, 55, 30)],
         "#9870c0", "#b890d8")},

    {"name": "jasmine", "comment": "Jasmine with small white star flowers",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 5,
     "foliage_radius": 28,
     "features": _fruits([(38, 34), (58, 38), (44, 52), (62, 54), (50, 42)],
                         "#f8f8f0", "#ffffff", r=3.5)},

    {"name": "hibiscus", "comment": "Hibiscus with large tropical flowers",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 4,
     "foliage_radius": 32,
     "features": [
         {"type": "petal_ring", "count": 5, "rx": 7, "ry": 16, "ring_r": 16,
          "fill": "#e84050", "alt_fill": "#f05060", "center_fill": "#f0d030", "center_r": 5},
     ]},

    {"name": "crocus", "comment": "Crocus with cup-shaped spring flowers",
     "gradient": ("#488c28", "#3a7820", "#2c6418"), "leaf_count": 3,
     "leaf_spread": 14, "foliage_radius": 24,
     "features": [
         {"type": "ellipse", "cx": 50, "cy": 40, "rx": 8, "ry": 12, "fill": "#8858b8", "opacity": 0.8},
         {"type": "ellipse", "cx": 50, "cy": 40, "rx": 5, "ry": 8, "fill": "#9868c8", "opacity": 0.6},
         {"type": "circle", "cx": 50, "cy": 40, "r": 2, "fill": "#f0c830", "opacity": 0.7},
     ]},

    # =========== TREES (15) ===========
    {"name": "pear_tree", "comment": "Pear tree canopy from above",
     "gradient": ("#3a7028", "#2c5c20", "#1e4818"), "leaf_count": 6,
     "foliage_radius": 36,
     "features": _fruits([(42, 38), (60, 44), (48, 58), (36, 52)],
                         "#a8c830", "#c0d848", r=4)},

    {"name": "plum_tree", "comment": "Plum tree with purple fruits",
     "gradient": ("#3a6828", "#2c5820", "#1e4818"), "leaf_count": 6,
     "foliage_radius": 36,
     "features": _fruits([(40, 36), (58, 42), (46, 56), (62, 58), (34, 50)],
                         "#6828a0", "#8040b8", r=4)},

    {"name": "peach_tree", "comment": "Peach tree with fuzzy fruits",
     "gradient": ("#3a7028", "#2c5c20", "#1e4818"), "leaf_count": 6,
     "foliage_radius": 36,
     "features": _fruits([(42, 36), (60, 42), (48, 58), (35, 50)],
                         "#f0a068", "#f8b880", r=4.5)},

    {"name": "fig_tree", "comment": "Fig tree with large lobed leaves",
     "gradient": ("#3a6828", "#2c5820", "#1e4818"), "leaf_count": 5,
     "foliage_radius": 36, "leaf_spread": 20,
     "features": _fruits([(44, 40), (58, 52), (38, 56)],
                         "#584028", "#685038", r=4)},

    {"name": "olive_tree", "comment": "Olive tree with silvery-green foliage",
     "gradient": ("#687848", "#587038", "#486030"), "leaf_count": 6,
     "leaf_fill": "#788858", "leaf_alt": "#687848",
     "foliage_radius": 34,
     "features": _fruits([(42, 38), (56, 44), (48, 56), (62, 52)],
                         "#506030", "#607040", r=3)},

    {"name": "lemon_tree", "comment": "Lemon tree with bright yellow fruits",
     "gradient": ("#3a7028", "#2c5c20", "#1e4818"), "leaf_count": 6,
     "foliage_radius": 35,
     "features": _fruits([(40, 36), (60, 42), (48, 58), (34, 52), (56, 56)],
                         "#f0d830", "#f8e050", r=4)},

    {"name": "orange_tree", "comment": "Orange tree with citrus fruits",
     "gradient": ("#2e6420", "#205818", "#184c12"), "leaf_count": 6,
     "foliage_radius": 36,
     "features": _fruits([(42, 36), (60, 40), (48, 58), (36, 52), (58, 56)],
                         "#f09020", "#f8a838", r=4.5)},

    {"name": "walnut_tree", "comment": "Walnut tree with compound leaves",
     "gradient": ("#3a6828", "#2c5820", "#1e4818"), "leaf_count": 6,
     "foliage_radius": 38, "leaf_spread": 22},

    {"name": "oak", "comment": "Oak tree with broad dense canopy",
     "gradient": ("#2e5c20", "#205018", "#184412"), "leaf_count": 6,
     "foliage_radius": 38, "leaf_spread": 22,
     "leaf_fill": "#3e6c30", "leaf_alt": "#2e5c20"},

    {"name": "maple", "comment": "Maple tree with dense spreading canopy",
     "gradient": ("#3a7028", "#2c5c20", "#1e4818"), "leaf_count": 6,
     "foliage_radius": 36, "leaf_spread": 20},

    {"name": "birch", "comment": "Birch tree with light airy canopy",
     "gradient": ("#58a038", "#489028", "#388020"), "leaf_count": 6,
     "foliage_radius": 30, "leaf_spread": 18,
     "leaf_fill": "#68b048", "leaf_alt": "#58a038",
     "features": [
         {"type": "circle", "cx": 50, "cy": 50, "r": 4, "fill": "#e8e0d0", "opacity": 0.5},
     ]},

    {"name": "willow", "comment": "Willow tree with drooping canopy",
     "gradient": ("#58a038", "#489028", "#388020"), "leaf_count": 6,
     "foliage_radius": 38, "leaf_spread": 24,
     "leaf_fill": "#68b048", "leaf_alt": "#58a038"},

    {"name": "magnolia", "comment": "Magnolia with large glossy leaves and flowers",
     "gradient": ("#2e5c20", "#205018", "#184412"), "leaf_count": 5,
     "foliage_radius": 34,
     "features": [
         {"type": "circle", "cx": 48, "cy": 42, "r": 10, "fill": "#f8e8f0", "opacity": 0.8},
         {"type": "circle", "cx": 48, "cy": 42, "r": 6, "fill": "#f0d8e8", "opacity": 0.6},
     ]},

    {"name": "pine", "comment": "Pine tree with radiating needle clusters",
     "gradient": ("#2a5c30", "#1c4c24", "#103c18"), "leaf_count": 5,
     "foliage_radius": 34, "leaf_spread": 20,
     "leaf_fill": "#3a6c40", "leaf_alt": "#2a5c30",
     "features": [
         {"type": "circle", "cx": 50, "cy": 50, "r": 4, "fill": "#4a3520", "opacity": 0.5},
     ]},

    {"name": "spruce", "comment": "Spruce tree - star shaped from above",
     "gradient": ("#1e4c24", "#143c1c", "#0c2c14"), "leaf_count": 5,
     "foliage_radius": 34, "leaf_spread": 20,
     "leaf_fill": "#2e5c34", "leaf_alt": "#1e4c24",
     "features": [
         {"type": "circle", "cx": 50, "cy": 50, "r": 4, "fill": "#4a3520", "opacity": 0.5},
     ]},

    # =========== SHRUBS (15) ===========
    {"name": "blueberry", "comment": "Blueberry bush with small blue fruits",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 6,
     "foliage_radius": 30,
     "features": _fruits([(38, 38), (55, 36), (62, 48), (42, 56), (56, 58), (48, 44)],
                         "#384880", "#485898", r=3)},

    {"name": "raspberry", "comment": "Raspberry with red aggregate fruits",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 5,
     "foliage_radius": 30,
     "features": _fruits([(40, 38), (58, 42), (46, 56), (62, 54), (34, 52)],
                         "#c82838", "#d84050", r=3.5)},

    {"name": "blackberry", "comment": "Blackberry with dark fruits",
     "gradient": ("#3a7028", "#2c5c20", "#205018"), "leaf_count": 5,
     "foliage_radius": 32,
     "features": _fruits([(40, 36), (58, 42), (46, 56), (62, 56), (34, 50)],
                         "#282028", "#383038", r=3.5)},

    {"name": "gooseberry", "comment": "Gooseberry bush with translucent fruits",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 5,
     "foliage_radius": 28,
     "features": _fruits([(40, 38), (58, 42), (46, 56), (34, 50)],
                         "#a8c848", "#c0d860", r=3.5)},

    {"name": "currant", "comment": "Currant bush with small clustered fruits",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 5,
     "foliage_radius": 30,
     "features": _fruits([(38, 38), (42, 42), (40, 46), (56, 40), (60, 44), (58, 48)],
                         "#c02030", "#d83848", r=2.5)},

    {"name": "holly", "comment": "Holly with spiky dark leaves and red berries",
     "gradient": ("#1e4818", "#143c12", "#0c300c"), "leaf_count": 6,
     "leaf_fill": "#2e5828", "leaf_alt": "#1e4818",
     "foliage_radius": 30,
     "features": _fruits([(42, 40), (56, 44), (48, 56), (38, 52)],
                         "#d82020", "#e84040", r=2.5)},

    {"name": "privet", "comment": "Privet hedge shrub",
     "gradient": ("#3a6828", "#2c5820", "#1e4818"), "leaf_count": 6,
     "leaf_fill": "#4a7838", "leaf_alt": "#3a6828",
     "foliage_radius": 32},

    {"name": "juniper", "comment": "Juniper with scale-like foliage",
     "gradient": ("#2a5c30", "#1c4c24", "#103c18"), "leaf_count": 6,
     "leaf_fill": "#3a6c40", "leaf_alt": "#2a5c30",
     "foliage_radius": 30,
     "features": _fruits([(44, 42), (56, 48), (48, 56)],
                         "#384870", "#485878", r=2.5)},

    {"name": "forsythia", "comment": "Forsythia with bright yellow spring flowers",
     "gradient": ("#4a7828", "#3c6820", "#2e5818"), "leaf_count": 5,
     "foliage_radius": 30,
     "features": _fruits([(36, 34), (54, 32), (66, 42), (40, 52), (58, 56),
                          (28, 44), (68, 54), (48, 40)],
                         "#f0d020", "#f8e040", r=3)},

    {"name": "lilac", "comment": "Lilac with fragrant flower clusters",
     "gradient": ("#3a6828", "#2c5820", "#1e4818"), "leaf_count": 5,
     "foliage_radius": 32,
     "features": _flower_spikes(
         [(38, 32, -15), (52, 28, 0), (64, 34, 15), (42, 50, -10), (60, 52, 10)],
         "#b880d0", "#c898d8")},

    {"name": "viburnum", "comment": "Viburnum with flat-topped flower clusters",
     "gradient": ("#3a6828", "#2c5820", "#1e4818"), "leaf_count": 5,
     "foliage_radius": 32,
     "features": [
         {"type": "circle", "cx": 44, "cy": 38, "r": 8, "fill": "#f0e8e0", "opacity": 0.7},
         {"type": "circle", "cx": 58, "cy": 42, "r": 7, "fill": "#f0e8e0", "opacity": 0.65},
     ]},

    {"name": "barberry", "comment": "Barberry with dark red-purple foliage",
     "gradient": ("#6a2828", "#5a2020", "#4a1818"), "leaf_count": 6,
     "leaf_fill": "#7a3838", "leaf_alt": "#6a2828",
     "foliage_radius": 28,
     "features": _fruits([(42, 42), (56, 48), (48, 56)],
                         "#d82020", r=2)},

    {"name": "camellia", "comment": "Camellia with glossy leaves and showy flowers",
     "gradient": ("#2e5820", "#204c18", "#184012"), "leaf_count": 5,
     "foliage_radius": 32,
     "features": [
         {"type": "circle", "cx": 46, "cy": 42, "r": 10, "fill": "#e84060", "opacity": 0.8},
         {"type": "circle", "cx": 46, "cy": 42, "r": 7, "fill": "#f05878", "opacity": 0.65},
         {"type": "circle", "cx": 46, "cy": 42, "r": 4, "fill": "#f87890", "opacity": 0.5},
     ]},

    {"name": "spirea", "comment": "Spirea with arching branches and flower clusters",
     "gradient": ("#3a7828", "#2c6420", "#205018"), "leaf_count": 6,
     "foliage_radius": 30,
     "features": _fruits([(38, 34), (54, 32), (64, 42), (42, 52), (58, 54)],
                         "#f0d0d8", "#f8e0e8", r=3.5)},

    {"name": "elderberry", "comment": "Elderberry with compound leaves and berry clusters",
     "gradient": ("#3a6828", "#2c5820", "#1e4818"), "leaf_count": 5,
     "foliage_radius": 34,
     "features": _fruits([(40, 36), (42, 40), (44, 38), (56, 42), (58, 46), (54, 44),
                          (46, 56), (50, 58), (48, 54)],
                         "#201028", "#302038", r=2)},
]


def main() -> None:
    """Generate all plant species SVGs."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for spec in SPECIES:
        name = spec["name"]
        svg_content = build_plant_svg(spec)
        output_path = OUTPUT_DIR / f"{name}.svg"
        output_path.write_text(svg_content, encoding="utf-8")
        print(f"  Generated {name}.svg ({len(svg_content)} bytes)")

    print(f"\n{len(SPECIES)} plant SVGs generated in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
