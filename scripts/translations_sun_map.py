"""German, Spanish and Russian targets for the key of the hours-of-sun map (#794).

Russian has no fill script: its targets are entered in the ``.ts`` file when the
catalogs are updated. They are kept here so the three languages stay together.

The hours on the key's bar are the map's own contour labels
(``SunHeatmapController``, "{n} h"), which are translated already.
"""

DE = {
    "SunMapLegend": {
        "Hours of sun": "Sonnenstunden",
        "Hours of sun · {date}": "Sonnenstunden · {date}",
    },
}

ES = {
    "SunMapLegend": {
        "Hours of sun": "Horas de sol",
        "Hours of sun · {date}": "Horas de sol · {date}",
    },
}

RU = {
    "SunMapLegend": {
        "Hours of sun": "Часы солнца",
        "Hours of sun · {date}": "Часы солнца · {date}",
    },
}
