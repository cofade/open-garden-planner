"""Translated presentation of language-independent sun exposure records."""

from datetime import date

from PyQt6.QtCore import QT_TR_NOOP, QCoreApplication, QLocale

from open_garden_planner.models.plant_data import SunRequirement


def sun_requirement_label(required: str) -> str:
    labels = {
        "full_sun": QT_TR_NOOP("full sun"), "partial_sun": QT_TR_NOOP("partial sun"),
        "partial_shade": QT_TR_NOOP("partial shade"), "full_shade": QT_TR_NOOP("full shade"),
        "unknown": QT_TR_NOOP("unspecified sun requirement"),
    }
    return QCoreApplication.translate("SunExposure", labels.get(required, labels["unknown"]))


def unavailable_message(reason: str) -> str:
    labels = {
        "absent": QT_TR_NOOP("Compute sun hours to enable sun diagnostics."),
        "computing": QT_TR_NOOP("Computing sun hours…"),
        "stale": QT_TR_NOOP("Not evaluated — recompute sun hours."),
        "no_location": QT_TR_NOOP("Not evaluated — set garden location."),
        "out_of_grid": QT_TR_NOOP("Not evaluated — plant is outside the sun grid."),
        "hidden": QT_TR_NOOP("Not evaluated — plant is on a hidden layer."),
        "cancelled": QT_TR_NOOP("Not evaluated — computation cancelled."),
        "invalid": QT_TR_NOOP("Not evaluated — exposure data unavailable."),
    }
    return QCoreApplication.translate("SunExposure", labels.get(reason, labels["absent"]))


def exposure_hours_text(hours: float, reference_date: date) -> str:
    return QCoreApplication.translate("SunExposure", "{hours} h on {date}").format(
        hours=QLocale().toString(hours, "f", 1), date=reference_date.isoformat())


def mismatch_message(name: str, required: SunRequirement, hours: float, reference_date: date, direction: str) -> str:
    description = QCoreApplication.translate("SunExposure", "too little sun") if direction == "too_little" else QCoreApplication.translate("SunExposure", "too much sun")
    message = QCoreApplication.translate(
        "SunExposure", "{name} needs {required}, but receives ~{hours} h direct sun on {date} ({direction})."
    ).format(name=name, required=sun_requirement_label(required.value), hours=QLocale().toString(hours, "f", 1),
             date=reference_date.isoformat(), direction=description)
    return message + "\n" + QCoreApplication.translate(
        "SunExposure", "Estimated at ground level, excluding this plant's own shadow; leaf height and canopy translucency are not modelled.")
