"""German, Spanish, French and Russian targets for #986 (tabbed Preferences) and #907 (per-quantity units).

German, Spanish and French are merged automatically by ``scripts/fill_translations.py``
(which invokes the Spanish and French populators). Russian has no fill script and is
maintained directly in ``open_garden_planner_ru.ts``; its targets are kept alongside the
other locales here as the canonical record.
"""

from __future__ import annotations

_CANADA_TOOLTIP_EN = (
    "Canada (mixed) is provisional: lengths and areas in feet and inches, "
    "weather and harvest in metric units. Change any row to make it Custom."
)

DE: dict[str, dict[str, str]] = {
    "HarvestUnits": {
        "lb": "lb",
        "oz": "oz",
    },
    "PlantDatabasePanel": {
        "Opt. temp: {temp}": "Opt. Temp.: {temp}",
    },
    "PreferencesDialog": {
        "Area:": "Fläche:",
        "Canada (mixed)": "Kanada (gemischt)",
        _CANADA_TOOLTIP_EN: (
            "Kanada (gemischt) ist vorläufig: Längen und Flächen in Fuß und Zoll, "
            "Wetter und Ernte in metrischen Einheiten. Ändern Sie eine Zeile, um sie "
            "benutzerdefiniert zu machen."
        ),
        "Custom": "Benutzerdefiniert",
        "General": "Allgemein",
        "Harvest mass:": "Erntemasse:",
        "Imperial (US)": "Imperial (US)",
        "Length:": "Länge:",
        "Metric": "Metrisch",
        "Online services": "Onlinedienste",
        "Orange warning threshold:": "Warnschwelle orange:",
        "Precipitation:": "Niederschlag:",
        "Preset:": "Voreinstellung:",
        "Red alert threshold:": "Alarmschwelle rot:",
        "Temperature:": "Temperatur:",
        "The system used for lengths and the canvas.": (
            "Das System für Längen und die Zeichenfläche."
        ),
        "Volume:": "Volumen:",
    },
    "SeedPacketEditDialog": {
        "Temp. range:": "Temperaturbereich:",
    },
    "Tasks": {
        "Frost {temp}": "Frost {temp}",
    },
    "WeatherWidget": {
        "Max °F": "Max. °F",
        "Min °F": "Min. °F",
        "Rain in": "Regen (in)",
    },
    "_DetailPanel": {
        "Min. germ. temp: {temp}": "Min. Keimtemperatur: {temp}",
    },
}

ES: dict[str, dict[str, str]] = {
    "HarvestUnits": {
        "lb": "lb",
        "oz": "oz",
    },
    "PlantDatabasePanel": {
        "Opt. temp: {temp}": "Temp. ópt.: {temp}",
    },
    "PreferencesDialog": {
        "Area:": "Área:",
        "Canada (mixed)": "Canadá (mixto)",
        _CANADA_TOOLTIP_EN: (
            "Canadá (mixto) es provisional: longitudes y áreas en pies y pulgadas, "
            "clima y cosecha en unidades métricas. Cambie cualquier fila para hacerlo "
            "Personalizado."
        ),
        "Custom": "Personalizado",
        "General": "General",
        "Harvest mass:": "Masa de cosecha:",
        "Imperial (US)": "Imperial (EE. UU.)",
        "Length:": "Longitud:",
        "Metric": "Métrico",
        "Online services": "Servicios en línea",
        "Orange warning threshold:": "Umbral de aviso naranja:",
        "Precipitation:": "Precipitación:",
        "Preset:": "Preajuste:",
        "Red alert threshold:": "Umbral de alerta rojo:",
        "Temperature:": "Temperatura:",
        "The system used for lengths and the canvas.": (
            "El sistema usado para longitudes y el lienzo."
        ),
        "Volume:": "Volumen:",
    },
    "SeedPacketEditDialog": {
        "Temp. range:": "Rango de temperatura:",
    },
    "Tasks": {
        "Frost {temp}": "Helada {temp}",
    },
    "WeatherWidget": {
        "Max °F": "Máx. °F",
        "Min °F": "Mín. °F",
        "Rain in": "Lluvia (in)",
    },
    "_DetailPanel": {
        "Min. germ. temp: {temp}": "Temp. mín. de germinación: {temp}",
    },
}

FR: dict[str, dict[str, str]] = {
    "HarvestUnits": {
        "lb": "lb",
        "oz": "oz",
    },
    "PlantDatabasePanel": {
        "Opt. temp: {temp}": "Temp. optimale : {temp}",
    },
    "PreferencesDialog": {
        "Area:": "Surface :",
        "Canada (mixed)": "Canada (mixte)",
        _CANADA_TOOLTIP_EN: (
            "Canada (mixte) est provisoire : longueurs et surfaces en pieds et pouces, "
            "météo et récolte en unités métriques. Modifiez une ligne pour le personnaliser."
        ),
        "Custom": "Personnalisé",
        "General": "Général",
        "Harvest mass:": "Masse de récolte :",
        "Imperial (US)": "Impérial (É.-U.)",
        "Length:": "Longueur :",
        "Metric": "Métrique",
        "Online services": "Services en ligne",
        "Orange warning threshold:": "Seuil d'avertissement orange :",
        "Precipitation:": "Précipitations :",
        "Preset:": "Préréglage :",
        "Red alert threshold:": "Seuil d'alerte rouge :",
        "Temperature:": "Température :",
        "The system used for lengths and the canvas.": (
            "Le système utilisé pour les longueurs et le canevas."
        ),
        "Volume:": "Volume :",
    },
    "SeedPacketEditDialog": {
        "Temp. range:": "Plage de température :",
    },
    "Tasks": {
        "Frost {temp}": "Gel {temp}",
    },
    "WeatherWidget": {
        "Max °F": "Max °F",
        "Min °F": "Min °F",
        "Rain in": "Pluie (in)",
    },
    "_DetailPanel": {
        "Min. germ. temp: {temp}": "Temp. min. de germination : {temp}",
    },
}

RU: dict[str, dict[str, str]] = {
    "HarvestUnits": {
        "lb": "фунт",
        "oz": "унц.",
    },
    "PlantDatabasePanel": {
        "Opt. temp: {temp}": "Опт. температура: {temp}",
    },
    "PreferencesDialog": {
        "Area:": "Площадь:",
        "Canada (mixed)": "Канада (смешанная)",
        _CANADA_TOOLTIP_EN: (
            "Канада (смешанная) — предварительно: длины и площади в футах и дюймах, "
            "погода и урожай в метрических единицах. Измените любую строку, чтобы "
            "сделать профиль пользовательским."
        ),
        "Custom": "Пользовательский",
        "General": "Общие",
        "Harvest mass:": "Масса урожая:",
        "Imperial (US)": "Имперская (США)",
        "Length:": "Длина:",
        "Metric": "Метрическая",
        "Online services": "Онлайн-сервисы",
        "Orange warning threshold:": "Оранжевый порог предупреждения:",
        "Precipitation:": "Осадки:",
        "Preset:": "Профиль:",
        "Red alert threshold:": "Красный порог тревоги:",
        "Temperature:": "Температура:",
        "The system used for lengths and the canvas.": "Система для длин и холста.",
        "Volume:": "Объём:",
    },
    "SeedPacketEditDialog": {
        "Temp. range:": "Диапазон температур:",
    },
    "Tasks": {
        "Frost {temp}": "Мороз {temp}",
    },
    "WeatherWidget": {
        "Max °F": "Макс. °F",
        "Min °F": "Мин. °F",
        "Rain in": "Дождь, дюймы",
    },
    "_DetailPanel": {
        "Min. germ. temp: {temp}": "Мин. температура прорастания: {temp}",
    },
}
