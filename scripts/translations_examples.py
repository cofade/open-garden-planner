"""German, Spanish and Russian targets for the examples' showcase state (#795).

Russian has no fill script: its targets are entered in the ``.ts`` file when the
catalogs are updated. They are kept here so the three languages stay together.
"""

_SEED_EMPTY = (
    "No seed packets yet. “+ Add Packet” records the seeds you own.\n"
    "The inventory is yours, not a plan's: every plan you open shows the same packets."
)

DE = {
    "GardenPlannerApp": {
        "Opened as an untitled copy: {name}": "Als unbenannte Kopie geöffnet: {name}",
        "Saved: {path}. The plan now follows your own date and time, no longer the example's.": (
            "Gespeichert: {path}. Der Plan folgt jetzt Ihrem eigenen Datum und Ihrer eigenen Uhrzeit, nicht mehr denen des Beispiels."
        ),
    },
    "SeedInventoryView": {
        _SEED_EMPTY: (
            "Noch keine Saatgutpakete. Mit „+ Paket hinzufügen“ erfassen Sie Ihr eigenes Saatgut.\n"
            "Der Bestand gehört Ihnen, nicht einem Plan: Jeder Plan, den Sie öffnen, zeigt dieselben Pakete."
        ),
    },
    "DiagnosticsPanel": {
        "Plants ({count}): {status}": "Pflanzen ({count}): {status}",
    },
}

ES = {
    "GardenPlannerApp": {
        "Opened as an untitled copy: {name}": "Abierto como copia sin título: {name}",
        "Saved: {path}. The plan now follows your own date and time, no longer the example's.": (
            "Guardado: {path}. El plano sigue ahora su propia fecha y hora, ya no las del ejemplo."
        ),
    },
    "SeedInventoryView": {
        _SEED_EMPTY: (
            "Aún no hay sobres de semillas. Con «+ Añadir sobre» registra las semillas que tiene.\n"
            "El inventario es suyo, no de un plano: todos los planos que abra muestran los mismos sobres."
        ),
    },
    "DiagnosticsPanel": {
        "Plants ({count}): {status}": "Plantas ({count}): {status}",
    },
}

RU = {
    "GardenPlannerApp": {
        "Opened as an untitled copy: {name}": "Открыто как безымянная копия: {name}",
        "Saved: {path}. The plan now follows your own date and time, no longer the example's.": (
            "Сохранено: {path}. Теперь план следует вашим дате и времени, а не дате и времени примера."
        ),
    },
    "SeedInventoryView": {
        _SEED_EMPTY: (
            "Пакетов семян пока нет. Кнопка «+ Добавить пакет» записывает семена, которые у вас есть.\n"
            "Учёт принадлежит вам, а не плану: в каждом открытом плане видны одни и те же пакеты."
        ),
    },
    "DiagnosticsPanel": {
        "Plants ({count}): {status}": "Растения ({count}): {status}",
    },
}
