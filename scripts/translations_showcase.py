"""Targets for the 3D showcase follow-up package (#941-#966).

German, Spanish and French targets for the three new user-visible strings:
a board fence style, the moss fill pattern, and the camera tour's part-turn tooltip.
"""

from __future__ import annotations

BOARD_DE = "Bretterzaun"
MOSS_DE = "Moos"
TURN_DE = (
    "Wie viel einer Runde der Drohnenflug zurücklegt. Weniger als eine volle Runde "
    "hält einen Garten mit einem Haus auf einer Seite auf seiner Gartenseite."
)

DE = {
    "PathFenceStyle": {"Board Fence": BOARD_DE},
    "PropertiesPanel": {"Moss": MOSS_DE},
    "TourDialog": {
        "How much of a turn the drone makes. Less than a full turn keeps a garden "
        "with a house on one side on its garden side.": TURN_DE,
    },
}

ES = {
    "PathFenceStyle": {"Board Fence": "Valla de tablas"},
    "PropertiesPanel": {"Moss": "Musgo"},
    "TourDialog": {
        "How much of a turn the drone makes. Less than a full turn keeps a garden "
        "with a house on one side on its garden side.": (
            "Cuánto gira el dron. Menos de una vuelta completa mantiene un jardín "
            "con una casa en un lado del lado del jardín."
        ),
    },
}

FR = {
    "PathFenceStyle": {"Board Fence": "Clôture à planches"},
    "PropertiesPanel": {"Moss": "Mousse"},
    "TourDialog": {
        "How much of a turn the drone makes. Less than a full turn keeps a garden "
        "with a house on one side on its garden side.": (
            "La part de tour effectuée par le drone. Moins d’un tour complet garde "
            "un jardin avec une maison d’un côté du côté du jardin."
        ),
    },
}
