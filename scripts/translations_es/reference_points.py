"""Spanish translations for the reference-point object (#666, ADR-080)."""

from __future__ import annotations

TRANSLATIONS: dict[str, dict[str, str]] = {
    "Commands": {
        "Reference point": "Punto de referencia",
        "reference point": "punto de referencia",
    },
    "ReferencePoints": {
        " cm": " cm",
        " px": " px",
        "Attached to": "Vinculado a",
        "Attached to: {name}": "Vinculado a: {name}",
        "Choose a visible, unlocked layer to place a reference point.":
            "Elige una capa visible y desbloqueada para colocar un punto de referencia.",
        "Color": "Color",
        "Constant on screen": "Constante en pantalla",
        "Edit reference point…": "Editar punto de referencia…",
        "Fixed in plan (scales with zoom)": "Fijo en el plano (escala con el zoom)",
        "Independent point": "Punto independiente",
        "Keep on the parent outline": "Mantener en el contorno del elemento padre",
        "Name": "Nombre",
        "On outline of: {name}": "En el contorno de: {name}",
        "Place a survey stake or measurement datum":
            "Colocar una estaca de medición o un dato de referencia",
        "Reference point": "Punto de referencia",
        "Size mode": "Modo de tamaño",
        "Stroke width": "Grosor del trazo",
        "Symbol size": "Tamaño del símbolo",
        "Unlock the layer to edit this reference point.":
            "Desbloquea la capa para editar este punto de referencia.",
        "cm": "cm",
        "px": "px",
        "{name}\n{status}\nSymbol: {size} {unit}; stroke: {width} px":
            "{name}\n{status}\nSímbolo: {size} {unit}; trazo: {width} px",
    },
}
