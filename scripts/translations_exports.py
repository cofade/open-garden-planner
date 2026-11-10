"""German, Spanish and Russian targets for the export fixes (#787, #788, #789, #836).

Russian has no fill script: its targets are entered in the ``.ts`` file when the
catalogs are updated. They are kept here so the three languages stay together.

#836 changed one source string: ``Bed detail views (one page per bed)`` (context
``PdfReportDialog``) became ``Bed detail views (small beds share a page)``. The old
entries in ``fill_translations.py`` and ``translations_es/dialogs.py`` are orphans
once the catalogs are regenerated.
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
        "Bed detail views (small beds share a page)":
            "Beet-Detailansichten (kleine Beete teilen sich eine Seite)",
        "Garden Plan": "Gartenplan",
    },
    "ProjectManager": {
        "Untitled": "Unbenannt",
    },
    "PropertiesPanel": {
        "Font height on the plan. "
        "Capital letters are about 70 % as tall. The text takes the nearest available size.":
            "Schrifthöhe im Plan. Großbuchstaben sind etwa 70 % so hoch. Der Text nimmt die nächste verfügbare Größe an.",
    },
    "SuccessionBadgeItem": {
        "+{count} more": "+{count} weitere",
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
        "Bed detail views (small beds share a page)":
            "Vistas detalladas de bancales (los bancales pequeños comparten página)",
        "Garden Plan": "Plano del huerto",
    },
    "ProjectManager": {
        "Untitled": "Sin título",
    },
    "PropertiesPanel": {
        "Font height on the plan. "
        "Capital letters are about 70 % as tall. The text takes the nearest available size.":
            "Altura de la fuente en el plano. Las mayúsculas miden aproximadamente el 70 %. El texto adopta el tamaño disponible más cercano.",
    },
    "SuccessionBadgeItem": {
        "+{count} more": "+{count} más",
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
        "Bed detail views (small beds share a page)":
            "Детализация грядок (маленькие грядки на одной странице)",
        "Garden Plan": "План участка",
    },
    "ProjectManager": {
        "Untitled": "Без названия",
    },
    "PropertiesPanel": {
        "Font height on the plan. "
        "Capital letters are about 70 % as tall. The text takes the nearest available size.":
            "Высота шрифта на плане. Заглавные буквы составляют около 70 % этой высоты. Текст принимает ближайший доступный размер.",
    },
    "SuccessionBadgeItem": {
        "+{count} more": "ещё {count}",
    },
}
