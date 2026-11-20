"""French translations for the reference-point object (#666, ADR-080)."""

from __future__ import annotations

TRANSLATIONS: dict[str, dict[str, str]] = {
    "Commands": {
        "Reference point": "Point de référence",
        "reference point": "point de référence",
    },
    "MainToolbar": {
        "Reference point": "Point de référence",
        "Place a survey stake or measurement datum":
            "Placer un jalon ou un point de référence",
    },
    "ReferencePoints": {
        " cm": " cm",
        " px": " px",
        "Attached to": "Attaché à",
        "Attached to: {name}": "Attaché à : {name}",
        "Choose a visible, unlocked layer to place a reference point.":
            "Choisissez un calque visible et déverrouillé pour placer un point de référence.",
        "Color": "Couleur",
        "Constant on screen": "Constant à l’écran",
        "Edit reference point…": "Modifier le point de référence…",
        "Fixed in plan (scales with zoom)": "Fixe dans le plan (suit le zoom)",
        "Independent point": "Point indépendant",
        "Keep on the parent outline": "Rester sur le contour du parent",
        "Name": "Nom",
        "On outline of: {name}": "Sur le contour de : {name}",
        "Reference point": "Point de référence",
        "Size mode": "Mode de taille",
        "Stroke width": "Épaisseur du trait",
        "Symbol size": "Taille du symbole",
        "cm": "cm",
        "px": "px",
        "{name}\n{status}\nSymbol: {size} {unit}; stroke: {width} px":
            "{name}\n{status}\nSymbole : {size} {unit} ; trait : {width} px",
    },
}
