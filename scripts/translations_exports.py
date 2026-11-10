"""German, Spanish and Russian targets for the export fixes (#787, #788, #789).

Russian has no fill script: its targets are entered in the ``.ts`` file when the
catalogs are updated. They are kept here so the three languages stay together.
"""

DE = {
    "PdfReportService": {
        "{title} – page {page} of {pages}": "{title} – Seite {page} von {pages}",
        "Objects": "Objekte",
        "Plants": "Pflanzen",
        "Nothing is drawn on this plan yet.": "Auf diesem Plan ist noch nichts gezeichnet.",
    },
    "PdfReportDialog": {
        "Legend (objects and plants)": "Legende (Objekte und Pflanzen)",
    },
}

ES = {
    "PdfReportService": {
        "{title} – page {page} of {pages}": "{title} – página {page} de {pages}",
        "Objects": "Objetos",
        "Plants": "Plantas",
        "Nothing is drawn on this plan yet.": "Todavía no hay nada dibujado en este plano.",
    },
    "PdfReportDialog": {
        "Legend (objects and plants)": "Leyenda (objetos y plantas)",
    },
}

RU = {
    "PdfReportService": {
        "{title} – page {page} of {pages}": "{title} – страница {page} из {pages}",
        "Objects": "Объекты",
        "Plants": "Растения",
        "Nothing is drawn on this plan yet.": "На этом плане пока ничего не нарисовано.",
    },
    "PdfReportDialog": {
        "Legend (objects and plants)": "Условные обозначения (объекты и растения)",
    },
}
