"""Localized editable display of common edible-part terms; raw data stays portable."""

from PyQt6.QtCore import QCoreApplication


def _labels() -> dict[str, str]:
    return {
        "bulb": QCoreApplication.translate("EdibleParts", "Bulbs"),
        "flowers": QCoreApplication.translate("EdibleParts", "Flowers"),
        "fruit": QCoreApplication.translate("EdibleParts", "Fruit"),
        "leaves": QCoreApplication.translate("EdibleParts", "Leaves"),
        "pods": QCoreApplication.translate("EdibleParts", "Pods"),
        "roots": QCoreApplication.translate("EdibleParts", "Roots"),
        "seeds": QCoreApplication.translate("EdibleParts", "Seeds"),
        "stems": QCoreApplication.translate("EdibleParts", "Stems"),
        "tubers": QCoreApplication.translate("EdibleParts", "Tubers"),
    }


def display_edible_parts(parts: list[str]) -> str:
    """Translate known data terms; retain arbitrary user/provider descriptions."""
    labels = _labels()
    return ", ".join(labels.get(part.casefold(), part) for part in parts)


def parse_edible_parts(text: str, previous: list[str]) -> list[str]:
    """Keep exact stored values when unchanged, decode edited localized tokens."""
    if text.strip() == display_edible_parts(previous):
        return list(previous)
    canonical = {label.casefold(): code for code, label in _labels().items()}
    return [canonical.get(part.casefold(), part)
            for raw in text.split(",") if (part := raw.strip())]
