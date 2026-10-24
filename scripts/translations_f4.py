"""German and Spanish targets for the plan timeline (US-F4)."""

DE = {
    "Commands": {"planting date": "Pflanzdatum", "removal date": "Entfernungsdatum"},
    "PdfReportService": {"Plan as of {date}": "Plan zum {date}"},
    "GardenPlannerApp": {
        "Print Error": "Druckfehler",
        "Failed to print:\n{error}": "Drucken fehlgeschlagen:\n{error}",
    },
    "PlantDatabasePanel": {
        "Clear": "Zurücksetzen",
        "Invalid plant dates": "Ungültige Pflanzendaten",
        "Not removed": "Nicht entfernt",
        "Choose dates between {min} and {max}. Removal must be after planting.": "Wählen Sie Daten zwischen {min} und {max}. Das Entfernungsdatum muss nach dem Pflanzdatum liegen.",
        "Removed on:": "Entfernt am:",
    },
}

ES = {
    "Commands": {"planting date": "fecha de plantación", "removal date": "fecha de retirada"},
    "PdfReportService": {"Plan as of {date}": "Plano a fecha de {date}"},
    "GardenPlannerApp": {
        "Print Error": "Error de impresión",
        "Failed to print:\n{error}": "No se pudo imprimir:\n{error}",
    },
    "PlantDatabasePanel": {
        "Clear": "Borrar",
        "Invalid plant dates": "Fechas de planta no válidas",
        "Not removed": "Sin retirar",
        "Choose dates between {min} and {max}. Removal must be after planting.": "Elija fechas entre {min} y {max}. La retirada debe ser posterior a la plantación.",
        "Removed on:": "Retirada el:",
    },
}

DE["SunSimToolbar"] = {
    "Set location for sunlight…": "Standort für Sonnenlicht festlegen…",
    "Sun shadows and Hours of Sun need a garden location. Opens File → Set Garden Location…": "Schatten und Sonnenstunden benötigen einen Gartenstandort. Öffnet Datei → Gartenstandort festlegen…",
    "Plan & Sun": "Plan & Sonne",
    "Plan date: plant presence, growth and sunlight": "Plandatum: Pflanzenbestand, Wachstum und Sonnenlicht",
    "Today": "Heute", "Past": "Vergangenheit", "Future": "Zukunft", "Months": "Monate",
    "Scrub by month; Page Up/Down jumps one year": "Monatsweise durchlaufen; Bild auf/ab springt um ein Jahr",
    "Animate the sun across the selected day": "Den Sonnenlauf am ausgewählten Tag animieren",
    "Plants hidden by the plan date": "Wegen des Plandatums ausgeblendete Pflanzen",
    "Full-day hours of sun; updates automatically while enabled": "Sonnenstunden des ganzen Tages; bei Aktivierung automatisch aktualisiert",
    "Map: {date}": "Karte: {date}", "Map: {date} — Updating…": "Karte: {date} — Wird aktualisiert…",
    "Map: {date} — Unavailable": "Karte: {date} — Nicht verfügbar",
    "Updating…": "Wird aktualisiert…", "{count} hidden": "{count} ausgeblendet",
    "{name} — planted: {planted}; removed: {removed}": "{name} — gepflanzt: {planted}; entfernt: {removed}",
    "Plant date unavailable": "Pflanzendatum nicht verfügbar",
    "This plant is not present within the supported plan dates ({min} to {max}). Its stored dates have been preserved.": "Diese Pflanze ist innerhalb der unterstützten Plandaten ({min} bis {max}) nicht vorhanden. Ihre gespeicherten Daten wurden beibehalten.",
}
ES["SunSimToolbar"] = {
    "Set location for sunlight…": "Establecer ubicación para la luz solar…",
    "Sun shadows and Hours of Sun need a garden location. Opens File → Set Garden Location…": "Las sombras y las horas de sol necesitan una ubicación del jardín. Abre Archivo → Establecer ubicación del jardín…",
    "Plan & Sun": "Plano y sol",
    "Plan date: plant presence, growth and sunlight": "Fecha del plano: presencia de plantas, crecimiento y luz solar",
    "Today": "Hoy", "Past": "Pasado", "Future": "Futuro", "Months": "Meses",
    "Scrub by month; Page Up/Down jumps one year": "Recorrer por meses; Re Pág/Av Pág salta un año",
    "Animate the sun across the selected day": "Animar el recorrido del sol durante el día seleccionado",
    "Plants hidden by the plan date": "Plantas ocultas por la fecha del plano",
    "Full-day hours of sun; updates automatically while enabled": "Horas de sol del día completo; se actualiza automáticamente mientras está activado",
    "Map: {date}": "Mapa: {date}", "Map: {date} — Updating…": "Mapa: {date} — Actualizando…",
    "Map: {date} — Unavailable": "Mapa: {date} — No disponible",
    "Updating…": "Actualizando…", "{count} hidden": "{count} ocultas",
    "{name} — planted: {planted}; removed: {removed}": "{name} — plantada: {planted}; retirada: {removed}",
    "Plant date unavailable": "Fecha de planta no disponible",
    "This plant is not present within the supported plan dates ({min} to {max}). Its stored dates have been preserved.": "Esta planta no está presente dentro de las fechas admitidas del plano ({min} a {max}). Se han conservado sus fechas guardadas.",
}
DE["LiveSunMap"] = {
    "Hours of Sun was switched off during export.": "Sonnenstunden wurde während des Exports ausgeschaltet.",
    "Set a garden location before computing Hours of Sun.": "Legen Sie vor der Berechnung der Sonnenstunden einen Gartenstandort fest.",
    "Hours of Sun could not be computed.": "Die Sonnenstunden konnten nicht berechnet werden.",
    "The garden is closing.": "Der Garten wird geschlossen.",
    "Sun-map settings changed during export. Please retry.": "Die Einstellungen der Sonnenkarte wurden während des Exports geändert. Bitte erneut versuchen.",
    "The garden changed during export. Please retry.": "Der Garten wurde während des Exports geändert. Bitte erneut versuchen.",
    "Sun map unavailable": "Sonnenkarte nicht verfügbar",
    "The garden document was replaced during export.": "Das Gartendokument wurde während des Exports ersetzt.",
}
ES["LiveSunMap"] = {
    "Hours of Sun was switched off during export.": "Horas de sol se desactivó durante la exportación.",
    "Set a garden location before computing Hours of Sun.": "Establezca la ubicación del jardín antes de calcular las horas de sol.",
    "Hours of Sun could not be computed.": "No se pudieron calcular las horas de sol.",
    "The garden is closing.": "El jardín se está cerrando.",
    "Sun-map settings changed during export. Please retry.": "La configuración del mapa solar cambió durante la exportación. Vuelva a intentarlo.",
    "The garden changed during export. Please retry.": "El jardín cambió durante la exportación. Vuelva a intentarlo.",
    "Sun map unavailable": "Mapa solar no disponible",
    "The garden document was replaced during export.": "El documento del jardín se reemplazó durante la exportación.",
}
DE["SunExportGate"] = {
    "The garden changed during export. Please retry.": "Der Garten wurde während des Exports geändert. Bitte erneut versuchen.",
    "Updating Hours of Sun for export…": "Sonnenstunden für den Export werden aktualisiert…",
    "Cancel": "Abbrechen", "Export canceled.": "Export abgebrochen.",
    "Sun-map calculation timed out. Please retry.": "Zeitüberschreitung bei der Berechnung der Sonnenkarte. Bitte erneut versuchen.",
}
ES["SunExportGate"] = {
    "The garden changed during export. Please retry.": "El jardín cambió durante la exportación. Vuelva a intentarlo.",
    "Updating Hours of Sun for export…": "Actualizando las horas de sol para exportar…",
    "Cancel": "Cancelar", "Export canceled.": "Exportación cancelada.",
    "Sun-map calculation timed out. Please retry.": "Se agotó el tiempo de cálculo del mapa solar. Vuelva a intentarlo.",
}
