"""Fill in German translations for the .ts file and add missing contexts.

This script:
1. Reads the pylupdate6-generated .ts file
2. Fills in all German translations
3. Adds missing contexts (ObjectType, expanded GalleryPanel)
4. Writes the completed .ts file
"""

import xml.etree.ElementTree as ET
from pathlib import Path

TS_FILE = (
    Path(__file__).parent.parent
    / "src"
    / "open_garden_planner"
    / "resources"
    / "translations"
    / "open_garden_planner_de.ts"
)

# ── Complete English → German translation mapping ─────────────────────────
TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── CalibrationDialog ──
    "CalibrationDialog": {
        "Calibrate Background Image": "Hintergrundbild kalibrieren",
        "<b>Instructions:</b><br>1. Click two points on the image at a known distance apart<br>2. Enter the real-world distance between those points<br>3. Click OK to apply calibration":
            "<b>Anleitung:</b><br>1. Klicken Sie zwei Punkte im Bild an, deren Abstand bekannt ist<br>2. Geben Sie den realen Abstand zwischen diesen Punkten ein<br>3. Klicken Sie auf OK, um die Kalibrierung anzuwenden",
        "Click the first point on the image": "Klicken Sie den ersten Punkt im Bild an",
        "Real-world distance:": "Realer Abstand:",
        "Reset Points": "Punkte zurücksetzen",
        "Click the second point on the image": "Klicken Sie den zweiten Punkt im Bild an",
        "Distance: {pixels} pixels. Enter the real-world distance below.":
            "Abstand: {pixels} Pixel. Geben Sie den realen Abstand unten ein.",
    },

    # ── CanvasView ──
    "CanvasView": {
        "Distance in cm": "Abstand in cm",
        "House": "Haus",
        "Garage/Shed": "Garage/Schuppen",
        "Terrace/Patio": "Terrasse/Patio",
        "Driveway": "Einfahrt",
        "Pond/Pool": "Teich/Pool",
        "Greenhouse": "Gewächshaus",
        "Garden Bed": "Gartenbeet",
        "Lawn": "Rasen",
        "Fence": "Zaun",
        "Wall": "Mauer",
        "Path": "Weg",
        "Tree": "Baum",
        "Shrub": "Strauch",
        "Perennial": "Staude",
        "Hedge Section": "Heckenabschnitt",
        "Table (Rectangular)": "Tisch (rechteckig)",
        "Chair": "Stuhl",
        "Bench": "Bank",
        "Lounger": "Liege",
        "Table (Round)": "Tisch (rund)",
        "Parasol": "Sonnenschirm",
        "BBQ/Grill": "Grill",
        "Fire Pit": "Feuerstelle",
        "Planter/Pot": "Pflanzgefäß/Topf",
        "Raised Bed": "Hochbeet",
        "Compost Bin": "Komposter",
        "Cold Frame": "Frühbeet",
        "Tool Shed": "Geräteschuppen",
        "Rain Barrel": "Regentonne",
        "Water Tap": "Wasserhahn",
        "Copied {count} item(s)": "{count} Element(e) kopiert",
        "Cut {count} item(s)": "{count} Element(e) ausgeschnitten",
        "Nothing to paste": "Nichts zum Einfügen",
        "Pasted {count} item(s)": "{count} Element(e) eingefügt",
        "Nothing to duplicate": "Nichts zum Duplizieren",
        "Duplicated {count} item(s)": "{count} Element(e) dupliziert",
        "Distance must be positive": "Abstand muss positiv sein",
        "Invalid distance. Enter a number in centimeters.":
            "Ungültiger Abstand. Geben Sie eine Zahl in Zentimetern ein.",
        "Select at least 2 objects to align":
            "Wählen Sie mindestens 2 Objekte zum Ausrichten",
        "Select at least 3 objects to distribute":
            "Wählen Sie mindestens 3 Objekte zum Verteilen",
    },

    # ── CircleTool ──
    "CircleTool": {
        "Circle": "Kreis",
    },

    # ── ColorButton ──
    "ColorButton": {
        "Choose Color": "Farbe wählen",
    },

    # ── CustomPlantsDialog ──
    "CustomPlantsDialog": {
        "Manage Custom Plants": "Eigene Pflanzen verwalten",
        "Custom Plant Library": "Eigene Pflanzenbibliothek",
        "Plants you've created or customized are stored here. These are available across all your projects.":
            "Hier werden Ihre selbst erstellten oder angepassten Pflanzen gespeichert. Diese sind in allen Ihren Projekten verfügbar.",
        "Common Name": "Allgemeiner Name",
        "Scientific Name": "Wissenschaftlicher Name",
        "Family": "Familie",
        "Cycle": "Lebenszyklus",
        "Create New": "Neu erstellen",
        "Create a new custom plant species": "Eine neue eigene Pflanzenart erstellen",
        "Delete": "Löschen",
        "Delete the selected plant": "Die ausgewählte Pflanze löschen",
        "Close": "Schließen",
        "No custom plants yet. Click 'Create New' to add one.":
            "Noch keine eigenen Pflanzen. Klicken Sie auf 'Neu erstellen', um eine hinzuzufügen.",
        "{count} custom plant(s) in library": "{count} eigene Pflanze(n) in der Bibliothek",
        "New plant created. Edit it in the Plant Details panel.":
            "Neue Pflanze erstellt. Bearbeiten Sie sie im Pflanzendetails-Panel.",
        "Delete Plant": "Pflanze löschen",
        "Are you sure you want to delete '{name}'?\n\nThis will remove it from your custom library. Plants already placed in projects will keep their data.":
            "Sind Sie sicher, dass Sie '{name}' löschen möchten?\n\nDies entfernt sie aus Ihrer eigenen Bibliothek. Bereits in Projekten platzierte Pflanzen behalten ihre Daten.",
    },

    # ── DrawingToolsPanel ──
    "DrawingToolsPanel": {
        "Selection & Measurement": "Auswahl & Messung",
        "Basic Shapes": "Grundformen",
        "Structures": "Gebäude",
        "Hardscape": "Befestigte Flächen",
        "Linear Features": "Lineare Elemente",
        "Garden": "Garten",
        "Plants": "Pflanzen",
    },

    # ── ExportPngDialog ──
    "ExportPngDialog": {
        "Export as PNG": "Als PNG exportieren",
        "Output Size": "Ausgabegröße",
        "A4 Landscape (29.7 cm wide)": "A4 Querformat (29,7 cm breit)",
        "Standard A4 paper in landscape orientation": "Standard-A4-Papier im Querformat",
        "A3 Landscape (42.0 cm wide)": "A3 Querformat (42,0 cm breit)",
        "A3 paper in landscape orientation (larger)": "A3-Papier im Querformat (größer)",
        "Letter Landscape (27.9 cm wide)": "Letter Querformat (27,9 cm breit)",
        "US Letter paper in landscape orientation": "US-Letter-Papier im Querformat",
        "Resolution (DPI)": "Auflösung (DPI)",
        "72 DPI (Screen)": "72 DPI (Bildschirm)",
        "Best for on-screen viewing, smallest file size":
            "Optimal für Bildschirmdarstellung, kleinste Dateigröße",
        "150 DPI (Standard Print)": "150 DPI (Standarddruck)",
        "Good balance of quality and file size":
            "Gute Balance zwischen Qualität und Dateigröße",
        "300 DPI (High Quality)": "300 DPI (Hohe Qualität)",
        "Best for high-quality printing, largest file size":
            "Optimal für hochwertigen Druck, größte Dateigröße",
        "Output Preview": "Ausgabevorschau",
        "Canvas size: {width} × {height} m": "Leinwandgröße: {width} × {height} m",
        "Scale: 1:{denom}": "Maßstab: 1:{denom}",
        "<b>Image size: {w} × {h} pixels</b>": "<b>Bildgröße: {w} × {h} Pixel</b>",
    },

    # ── GalleryPanel ──
    "GalleryPanel": {
        "Search objects...": "Objekte suchen...",
        "All Categories": "Alle Kategorien",
        # ── gallery item names (from _tr helper, not extracted by pylupdate6) ──
        "Basic Shapes": "Grundformen",
        "Rectangle": "Rechteck",
        "Polygon": "Polygon",
        "Circle": "Kreis",
        "Trees": "Bäume",
        "Apple Tree": "Apfelbaum",
        "Cherry Tree": "Kirschbaum",
        "Pear Tree": "Birnbaum",
        "Plum Tree": "Pflaumenbaum",
        "Oak Tree": "Eiche",
        "Maple Tree": "Ahorn",
        "Birch Tree": "Birke",
        "Willow Tree": "Weide",
        "Pine Tree": "Kiefer",
        "Spruce Tree": "Fichte",
        "Walnut Tree": "Walnussbaum",
        "Fig Tree": "Feigenbaum",
        "Olive Tree": "Olivenbaum",
        "Lemon Tree": "Zitronenbaum",
        "Shrubs": "Sträucher",
        "Rose Bush": "Rosenstrauch",
        "Lavender": "Lavendel",
        "Boxwood": "Buchsbaum",
        "Hydrangea": "Hortensie",
        "Lilac": "Flieder",
        "Forsythia": "Forsythie",
        "Rhododendron": "Rhododendron",
        "Azalea": "Azalee",
        "Holly": "Stechpalme",
        "Juniper": "Wacholder",
        "Blueberry Bush": "Heidelbeerstrauch",
        "Raspberry Bush": "Himbeerstrauch",
        "Currant Bush": "Johannisbeerstrauch",
        "Gooseberry": "Stachelbeere",
        "Perennials": "Stauden",
        "Hosta": "Funkie",
        "Daylily": "Taglilie",
        "Echinacea": "Sonnenhut",
        "Black-Eyed Susan": "Rudbeckie",
        "Peony": "Pfingstrose",
        "Iris": "Schwertlilie",
        "Aster": "Aster",
        "Sedum": "Fetthenne",
        "Ornamental Grass": "Ziergras",
        "Fern": "Farn",
        "Geranium": "Storchschnabel",
        "Salvia": "Salbei",
        "Catmint": "Katzenminze",
        "Structures": "Gebäude",
        "House": "Haus",
        "Garage/Shed": "Garage/Schuppen",
        "Greenhouse": "Gewächshaus",
        "Hardscape": "Befestigte Flächen",
        "Terrace/Patio": "Terrasse/Patio",
        "Driveway": "Einfahrt",
        "Pond/Pool": "Teich/Pool",
        "Garden": "Garten",
        "Garden Bed": "Gartenbeet",
        "Lawn": "Rasen",
        "Linear Features": "Lineare Elemente",
        "Fence": "Zaun",
        "Wall": "Mauer",
        "Path": "Weg",
        "Hedge": "Hecke",
        "Furniture": "Möbel",
        "Table (Rectangular)": "Tisch (rechteckig)",
        "Chair": "Stuhl",
        "Bench": "Bank",
        "Lounger": "Liege",
        "Table (Round)": "Tisch (rund)",
        "Parasol": "Sonnenschirm",
        "BBQ/Grill": "Grill",
        "Fire Pit": "Feuerstelle",
        "Planter/Pot": "Pflanzgefäß/Topf",
        "Infrastructure": "Infrastruktur",
        "Raised Bed": "Hochbeet",
        "Compost Bin": "Komposter",
        "Cold Frame": "Frühbeet",
        "Tool Shed": "Geräteschuppen",
        "Rain Barrel": "Regentonne",
        "Water Tap": "Wasserhahn",
    },

    # ── GardenPlannerApp ──
    "GardenPlannerApp": {
        "&File": "&Datei",
        "&Edit": "&Bearbeiten",
        "&View": "&Ansicht",
        "&Plants": "&Pflanzen",
        "&Help": "&Hilfe",
        "&New Project": "&Neues Projekt",
        "Create a new garden project": "Ein neues Gartenprojekt erstellen",
        "&Open...": "&Öffnen...",
        "Open an existing project": "Ein bestehendes Projekt öffnen",
        "Open &Recent": "Zuletzt &geöffnet",
        "&Save": "&Speichern",
        "Save the current project": "Das aktuelle Projekt speichern",
        "Save &As...": "Speichern &unter...",
        "Save the project with a new name": "Das Projekt unter neuem Namen speichern",
        "&Import Background Image...": "&Hintergrundbild importieren...",
        "Import a background image (satellite photo, etc.)":
            "Ein Hintergrundbild importieren (Satellitenfoto usw.)",
        "&Export": "&Exportieren",
        "Export as &PNG...": "Als &PNG exportieren...",
        "Export the plan as a PNG image": "Den Plan als PNG-Bild exportieren",
        "Export as &SVG...": "Als &SVG exportieren...",
        "Export the plan as an SVG vector file": "Den Plan als SVG-Vektordatei exportieren",
        "Export Plant List as &CSV...": "Pflanzenliste als &CSV exportieren...",
        "Export all plants to a CSV spreadsheet": "Alle Pflanzen in eine CSV-Tabelle exportieren",
        "E&xit": "&Beenden",
        "Exit the application": "Die Anwendung beenden",
        "&Undo": "&Rückgängig",
        "Undo the last action": "Die letzte Aktion rückgängig machen",
        "&Redo": "&Wiederherstellen",
        "Redo the last undone action": "Die letzte rückgängig gemachte Aktion wiederherstellen",
        "Cu&t": "Aus&schneiden",
        "Cut selected objects": "Ausgewählte Objekte ausschneiden",
        "&Copy": "&Kopieren",
        "Copy selected objects": "Ausgewählte Objekte kopieren",
        "&Paste": "&Einfügen",
        "Paste objects from clipboard": "Objekte aus der Zwischenablage einfügen",
        "D&uplicate": "D&uplizieren",
        "Duplicate selected objects": "Ausgewählte Objekte duplizieren",
        "&Delete": "&Löschen",
        "Delete selected objects": "Ausgewählte Objekte löschen",
        "Select &All": "&Alles auswählen",
        "Select all objects": "Alle Objekte auswählen",
        "Ali&gn && Distribute": "Aus&richten && Verteilen",
        "Align &Left": "Links &ausrichten",
        "Align selected objects to the left edge":
            "Ausgewählte Objekte am linken Rand ausrichten",
        "Align &Right": "&Rechts ausrichten",
        "Align selected objects to the right edge":
            "Ausgewählte Objekte am rechten Rand ausrichten",
        "Align &Top": "&Oben ausrichten",
        "Align selected objects to the top edge":
            "Ausgewählte Objekte am oberen Rand ausrichten",
        "Align &Bottom": "&Unten ausrichten",
        "Align selected objects to the bottom edge":
            "Ausgewählte Objekte am unteren Rand ausrichten",
        "Align Center &Horizontally": "&Horizontal zentrieren",
        "Align selected objects to horizontal center":
            "Ausgewählte Objekte horizontal zentrieren",
        "Align Center &Vertically": "&Vertikal zentrieren",
        "Align selected objects to vertical center":
            "Ausgewählte Objekte vertikal zentrieren",
        "Distribute &Horizontal": "&Horizontal verteilen",
        "Distribute selected objects with equal horizontal spacing":
            "Ausgewählte Objekte mit gleichem horizontalen Abstand verteilen",
        "Distribute &Vertical": "&Vertikal verteilen",
        "Distribute selected objects with equal vertical spacing":
            "Ausgewählte Objekte mit gleichem vertikalen Abstand verteilen",
        "Auto-&Save": "Automatisches &Speichern",
        "&Enable Auto-Save": "Automatisches Speichern &aktivieren",
        "Enable or disable automatic saving": "Automatisches Speichern ein- oder ausschalten",
        "{n} minute(s)": "{n} Minute(n)",
        "Zoom &In": "Ver&größern",
        "Zoom in on the canvas": "In die Leinwand hineinzoomen",
        "Zoom &Out": "Ver&kleinern",
        "Zoom out on the canvas": "Aus der Leinwand herauszoomen",
        "&Fit to Window": "An &Fenster anpassen",
        "Fit the entire canvas in the window": "Die gesamte Leinwand ins Fenster einpassen",
        "Show &Grid": "&Raster anzeigen",
        "Toggle grid visibility": "Rastersichtbarkeit umschalten",
        "&Snap to Grid": "Am &Raster einrasten",
        "Toggle snap to grid": "Einrasten am Raster umschalten",
        "Snap to &Objects": "An &Objekten einrasten",
        "Toggle snap to object edges and centers":
            "Einrasten an Objektkanten und -mittelpunkten umschalten",
        "Show &Shadows": "&Schatten anzeigen",
        "Toggle drop shadows on objects": "Schlagschatten auf Objekten umschalten",
        "Show Scale &Bar": "Maßstabs&leiste anzeigen",
        "Toggle the scale bar overlay on the canvas":
            "Maßstabsleiste auf der Leinwand umschalten",
        "Show &Labels": "&Beschriftungen anzeigen",
        "Toggle object labels on the canvas": "Objektbeschriftungen auf der Leinwand umschalten",
        "&Fullscreen Preview": "&Vollbildvorschau",
        "Toggle fullscreen preview mode (hides all UI)":
            "Vollbildvorschau umschalten (blendet alle UI-Elemente aus)",
        "&Theme": "&Design",
        "&Light": "&Hell",
        "Use light color scheme": "Helles Farbschema verwenden",
        "&Dark": "&Dunkel",
        "Use dark color scheme": "Dunkles Farbschema verwenden",
        "&System": "&System",
        "Follow system color scheme preference": "Systemfarbschema-Einstellung folgen",
        "&Search Plant Database": "Pflanzen&datenbank durchsuchen",
        "Search for plant species in online databases":
            "Pflanzenarten in Online-Datenbanken suchen",
        "&Manage Custom Plants...": "Eigene Pflanzen &verwalten...",
        "View, edit, and delete your custom plant species":
            "Ihre eigenen Pflanzenarten anzeigen, bearbeiten und löschen",
        "&Keyboard Shortcuts": "&Tastenkürzel",
        "Show keyboard shortcuts reference": "Tastenkürzel-Übersicht anzeigen",
        "&About Open Garden Planner": "&Über Open Garden Planner",
        "About this application": "Über diese Anwendung",
        "About &Qt": "Über &Qt",
        "X: 0.00 cm  Y: 0.00 cm": "X: 0,00 cm  Y: 0,00 cm",
        "No selection": "Keine Auswahl",
        "Select": "Auswählen",
        "Ready": "Bereit",
        "Object Gallery": "Objektgalerie",
        "Properties": "Eigenschaften",
        "Layers": "Ebenen",
        "Find Plants": "Pflanzen finden",
        "Plant Details": "Pflanzendetails",
        "Auto-saved": "Automatisch gespeichert",
        "Auto-save failed: {error}": "Automatisches Speichern fehlgeschlagen: {error}",
        "A recovery file was found from {timestamp}.\n\nOriginal project: {original_file}\n\nWould you like to recover this file?":
            "Eine Wiederherstellungsdatei vom {timestamp} wurde gefunden.\n\nUrsprüngliches Projekt: {original_file}\n\nMöchten Sie diese Datei wiederherstellen?",
        "A recovery file for an unsaved project was found from {timestamp}.\n\nWould you like to recover this file?":
            "Eine Wiederherstellungsdatei für ein nicht gespeichertes Projekt vom {timestamp} wurde gefunden.\n\nMöchten Sie diese Datei wiederherstellen?",
        "Recover Auto-Save": "Automatische Speicherung wiederherstellen",
        "Recovered from auto-save. Remember to save your work!":
            "Von automatischer Speicherung wiederhergestellt. Denken Sie daran, Ihre Arbeit zu speichern!",
        "Recovery Complete": "Wiederherstellung abgeschlossen",
        "Your work has been recovered from the auto-save file.\n\nPlease save your project to a permanent location.":
            "Ihre Arbeit wurde aus der automatischen Speicherung wiederhergestellt.\n\nBitte speichern Sie Ihr Projekt an einem dauerhaften Speicherort.",
        "Recovery Failed": "Wiederherstellung fehlgeschlagen",
        "Failed to recover from auto-save:\n{error}":
            "Wiederherstellung von automatischer Speicherung fehlgeschlagen:\n{error}",
        "New project created: {width}m x {height}m":
            "Neues Projekt erstellt: {width}m x {height}m",
        "Open Project": "Projekt öffnen",
        "Open Garden Planner (*.ogp);;All Files (*)":
            "Open Garden Planner (*.ogp);;Alle Dateien (*)",
        "Opened: {path}": "Geöffnet: {path}",
        "Error": "Fehler",
        "Failed to open file:\n{error}": "Datei konnte nicht geöffnet werden:\n{error}",
        "No recent projects": "Keine aktuellen Projekte",
        "{name} (not found)": "{name} (nicht gefunden)",
        "File not found: {path}": "Datei nicht gefunden: {path}",
        "Clear Recent Projects": "Aktuelle Projekte löschen",
        "Recent projects list cleared": "Liste der aktuellen Projekte gelöscht",
        "Save Project As": "Projekt speichern unter",
        "Saved: {path}": "Gespeichert: {path}",
        "Failed to save file:\n{error}": "Datei konnte nicht gespeichert werden:\n{error}",
        "Export as PNG": "Als PNG exportieren",
        "PNG Image (*.png);;All Files (*)": "PNG-Bild (*.png);;Alle Dateien (*)",
        "Exported: {path}": "Exportiert: {path}",
        "Export Error": "Exportfehler",
        "Failed to export PNG:\n{error}": "PNG-Export fehlgeschlagen:\n{error}",
        "Export as SVG": "Als SVG exportieren",
        "SVG Vector (*.svg);;All Files (*)": "SVG-Vektor (*.svg);;Alle Dateien (*)",
        "Failed to export SVG:\n{error}": "SVG-Export fehlgeschlagen:\n{error}",
        "Export Plant List as CSV": "Pflanzenliste als CSV exportieren",
        "CSV Spreadsheet (*.csv);;All Files (*)": "CSV-Tabelle (*.csv);;Alle Dateien (*)",
        "No Plants Found": "Keine Pflanzen gefunden",
        "No plants found in the project. The CSV file will be empty.":
            "Keine Pflanzen im Projekt gefunden. Die CSV-Datei wird leer sein.",
        "Exported {count} plant(s) to: {path}":
            "{count} Pflanze(n) exportiert nach: {path}",
        "Failed to export plant list:\n{error}":
            "Pflanzenliste konnte nicht exportiert werden:\n{error}",
        "Unsaved Changes": "Ungespeicherte Änderungen",
        "Do you want to save changes before proceeding?":
            "Möchten Sie Änderungen speichern, bevor Sie fortfahren?",
        "Undo: {desc}": "Rückgängig: {desc}",
        "Nothing to undo": "Nichts zum Rückgängigmachen",
        "Redo: {desc}": "Wiederherstellen: {desc}",
        "Nothing to redo": "Nichts zum Wiederherstellen",
        "Selected {count} object(s)": "{count} Objekt(e) ausgewählt",
        "Auto-save enabled": "Automatisches Speichern aktiviert",
        "Auto-save disabled": "Automatisches Speichern deaktiviert",
        "Auto-save interval set to {n} minute(s)":
            "Intervall für automatisches Speichern auf {n} Minute(n) gesetzt",
        "Theme changed to {theme}": "Design geändert zu {theme}",
        "Updated plant with species: {name}": "Pflanze aktualisiert mit Art: {name}",
        "Select a plant object (tree, shrub, or perennial) to assign species data":
            "Wählen Sie ein Pflanzenobjekt (Baum, Strauch oder Staude), um Artdaten zuzuweisen",
        "About Open Garden Planner": "Über Open Garden Planner",
        "<p>Version 0.1.0</p>": "<p>Version 0.1.0</p>",
        "<p>Precision garden planning for passionate gardeners.</p><p>Free and open source under GPLv3.</p>":
            "<p>Präzise Gartenplanung für leidenschaftliche Gärtner.</p><p>Frei und quelloffen unter GPLv3.</p>",
        "X: {x} cm  Y: {y} cm": "X: {x} cm  Y: {y} cm",
        "1 object | Area: {area} | Perimeter: {perimeter}":
            "1 Objekt | Fläche: {area} | Umfang: {perimeter}",
        "1 object selected": "1 Objekt ausgewählt",
        "{count} objects | Total Area: {area} | Total Perimeter: {perimeter}":
            "{count} Objekte | Gesamtfläche: {area} | Gesamtumfang: {perimeter}",
        "{count} objects selected": "{count} Objekte ausgewählt",
        "Import Background Image": "Hintergrundbild importieren",
        "Images (*.png *.jpg *.jpeg *.tiff *.bmp);;All Files (*)":
            "Bilder (*.png *.jpg *.jpeg *.tiff *.bmp);;Alle Dateien (*)",
        "Imported: {path}": "Importiert: {path}",
        "Failed to import image:\n{error}":
            "Bild konnte nicht importiert werden:\n{error}",
        "&Language": "&Sprache",
        "Language Changed": "Sprache geändert",
        "Language has been set to {language}.\n\nPlease restart the application for the change to take effect.":
            "Die Sprache wurde auf {language} gesetzt.\n\nBitte starten Sie die Anwendung neu, damit die Änderung wirksam wird.",
    },

    # ── LayerListItem ──
    "LayerListItem": {
        "Toggle visibility": "Sichtbarkeit umschalten",
        "Toggle lock": "Sperre umschalten",
        "Rename Layer": "Ebene umbenennen",
        "Delete Layer": "Ebene löschen",
    },

    # ── LayersPanel ──
    "LayersPanel": {
        "Opacity:": "Deckkraft:",
        "Layer opacity": "Ebenen-Deckkraft",
        "Add Layer": "Ebene hinzufügen",
    },

    # ── MainToolbar ──
    "MainToolbar": {
        "Tools": "Werkzeuge",
        "Select (V)": "Auswählen (V)",
        "Select and move objects": "Objekte auswählen und verschieben",
        "Measure (M)": "Messen (M)",
        "Measure distances between two points": "Abstände zwischen zwei Punkten messen",
    },

    # ── MeasureTool ──
    "MeasureTool": {
        "Measure": "Messen",
    },

    # ── NewProjectDialog ──
    "NewProjectDialog": {
        "New Project": "Neues Projekt",
        "Canvas Dimensions": "Leinwandabmessungen",
        "Width:": "Breite:",
        "Height:": "Höhe:",
        "Tip: You can resize the canvas later from Edit > Canvas Size.":
            "Tipp: Sie können die Leinwandgröße später unter Bearbeiten > Leinwandgröße ändern.",
    },

    # ── PlantDatabasePanel ──
    "PlantDatabasePanel": {
        "Search": "Suchen",
        "Search for plant species in online databases":
            "Pflanzenarten in Online-Datenbanken suchen",
        "Create Custom": "Eigene erstellen",
        "Create a custom plant species entry": "Einen eigenen Pflanzeneintrag erstellen",
        "Load Custom": "Eigene laden",
        "Load a plant from your custom library": "Eine Pflanze aus Ihrer eigenen Bibliothek laden",
        "Select a plant to view details": "Wählen Sie eine Pflanze, um Details anzuzeigen",
        "Enter common name...": "Allgemeinen Namen eingeben...",
        "Common Name:": "Allgemeiner Name:",
        "Enter scientific name...": "Wissenschaftlichen Namen eingeben...",
        "Scientific Name:": "Wissenschaftlicher Name:",
        "Enter plant family...": "Pflanzenfamilie eingeben...",
        "Family:": "Familie:",
        "Enter variety or cultivar...": "Sorte oder Kultivar eingeben...",
        "Variety:": "Sorte:",
        "Cycle:": "Lebenszyklus:",
        "Flower Type:": "Blütentyp:",
        "Pollination:": "Bestäubung:",
        "Sun:": "Sonne:",
        "Water:": "Wasser:",
        "Max Height:": "Max. Höhe:",
        "Max Spread:": "Max. Breite:",
        "Current Height:": "Aktuelle Höhe:",
        "Current Spread:": "Aktuelle Breite:",
        "Edible:": "Essbar:",
        "e.g., fruit, leaves, roots...": "z.B. Früchte, Blätter, Wurzeln...",
        "Edible Parts:": "Essbare Teile:",
        "Min:": "Min.:",
        "Max:": "Max.:",
        "Hardiness:": "Winterhärte:",
        "Planted:": "Gepflanzt:",
        "Notes about this plant...": "Notizen zu dieser Pflanze...",
        "Notes:": "Notizen:",
        "+ Add Field": "+ Feld hinzufügen",
        "Add a custom metadata field": "Ein benutzerdefiniertes Metadatenfeld hinzufügen",
        "Custom:": "Benutzerdefiniert:",
        "(future)": "(zukünftig)",
        "({days} days)": "({days} Tage)",
        "({months} mo)": "({months} Mon.)",
        "({years}y {remaining_months}mo)": "({years}J. {remaining_months}Mon.)",
        "({years}y)": "({years}J.)",
        "Field name": "Feldname",
        "Value": "Wert",
        "Remove this field": "Dieses Feld entfernen",
        "No species data.\n\nClick 'Search' to find species online,\nor 'Create Custom' to define your own.":
            "Keine Artdaten.\n\nKlicken Sie auf 'Suchen', um Arten online zu finden,\noder 'Eigene erstellen', um Ihre eigene zu definieren.",
        "Data Source: {source}": "Datenquelle: {source}",
        "No Plant Selected": "Keine Pflanze ausgewählt",
        "Please select a plant object (tree, shrub, or perennial) first.":
            "Bitte wählen Sie zuerst ein Pflanzenobjekt (Baum, Strauch oder Staude) aus.",
        "No Custom Plants": "Keine eigenen Pflanzen",
        "Your custom plant library is empty.\n\nUse 'Create Custom' to add plants, or use the Plants menu to manage your custom plant library.":
            "Ihre eigene Pflanzenbibliothek ist leer.\n\nVerwenden Sie 'Eigene erstellen', um Pflanzen hinzuzufügen, oder das Pflanzen-Menü, um Ihre eigene Pflanzenbibliothek zu verwalten.",
        "Select Custom Plant": "Eigene Pflanze auswählen",
    },

    # ── PlantSearchDialog ──
    "PlantSearchDialog": {
        "Search Plant Species": "Pflanzenarten suchen",
        "Search:": "Suche:",
        "Enter plant common or scientific name...":
            "Geben Sie den allgemeinen oder wissenschaftlichen Pflanzennamen ein...",
        "Search": "Suchen",
        "Enter a plant name to search": "Geben Sie einen Pflanzennamen zum Suchen ein",
        "Results:": "Ergebnisse:",
        "Plant Details:": "Pflanzendetails:",
        "Select a plant to view details": "Wählen Sie eine Pflanze, um Details anzuzeigen",
        "Searching for '{query}'...": "Suche nach '{query}'...",
        "Found {count} results": "{count} Ergebnisse gefunden",
        "No results found": "Keine Ergebnisse gefunden",
        "Search failed: {error}": "Suche fehlgeschlagen: {error}",
        "Search Failed": "Suche fehlgeschlagen",
        "Failed to search plant database:\n{error}\n\nPlease check your internet connection and API credentials.":
            "Pflanzendatenbank-Suche fehlgeschlagen:\n{error}\n\nBitte überprüfen Sie Ihre Internetverbindung und API-Zugangsdaten.",
        "Botanical Classification": "Botanische Klassifikation",
        "Family:": "Familie:",
        "Genus:": "Gattung:",
        "Growing Requirements": "Wachstumsanforderungen",
        "Cycle:": "Lebenszyklus:",
        "Sun:": "Sonne:",
        "Water:": "Wasser:",
        "Hardiness Zones:": "Winterhärtezonen:",
        "Hardiness Zone:": "Winterhärtezone:",
        "Soil:": "Boden:",
        "Size": "Größe",
        "Max Height:": "Max. Höhe:",
        "Max Spread:": "Max. Breite:",
        "Attributes": "Eigenschaften",
        "Edible:": "Essbar:",
        "Yes": "Ja",
        "Flowering:": "Blüte:",
        "Source: {source}": "Quelle: {source}",
        "No Selection": "Keine Auswahl",
        "Please select a plant from the search results.":
            "Bitte wählen Sie eine Pflanze aus den Suchergebnissen.",
    },

    # ── PolygonTool ──
    "PolygonTool": {
        "Polygon": "Polygon",
    },

    # ── PolylineTool ──
    "PolylineTool": {
        "Polyline": "Polylinie",
    },

    # ── PropertiesDialog ──
    "PropertiesDialog": {
        "Object Properties": "Objekteigenschaften",
        "Basic Information": "Grundinformationen",
        "Type:": "Typ:",
        "Name:": "Name:",
        "Layer:": "Ebene:",
        "Appearance": "Erscheinungsbild",
        "Fill Color:": "Füllfarbe:",
        "Fill Pattern:": "Füllmuster:",
        "Stroke Color:": "Linienfarbe:",
        "Stroke Width:": "Linienstärke:",
        "Stroke Style:": "Linienstil:",
        "Additional Information": "Zusätzliche Informationen",
    },

    # ── PropertiesPanel ──
    "PropertiesPanel": {
        "No objects selected": "Keine Objekte ausgewählt",
        "{count} objects selected": "{count} Objekte ausgewählt",
        "Multi-selection editing\nnot yet implemented":
            "Mehrfachauswahl-Bearbeitung\nnoch nicht implementiert",
        "Type:": "Typ:",
        "Name:": "Name:",
        "Show label on canvas": "Beschriftung auf der Leinwand anzeigen",
        "Label:": "Beschriftung:",
        "Layer:": "Ebene:",
        "Position:": "Position:",
        "Diameter:": "Durchmesser:",
        "Size:": "Größe:",
        "Fill Color:": "Füllfarbe:",
        "Fill Pattern:": "Füllmuster:",
        "Stroke Color:": "Linienfarbe:",
        "Stroke Width:": "Linienstärke:",
        "Stroke Style:": "Linienstil:",
    },

    # ── RectangleTool ──
    "RectangleTool": {
        "Rectangle": "Rechteck",
    },

    # ── SelectTool ──
    "SelectTool": {
        "Select": "Auswählen",
    },

    # ── ShortcutsDialog ──
    "ShortcutsDialog": {
        "Keyboard Shortcuts": "Tastenkürzel",
        "File": "Datei",
        "New Project": "Neues Projekt",
        "Open Project": "Projekt öffnen",
        "Save": "Speichern",
        "Save As": "Speichern unter",
        "Exit": "Beenden",
        "Edit": "Bearbeiten",
        "Undo": "Rückgängig",
        "Redo": "Wiederherstellen",
        "Cut": "Ausschneiden",
        "Copy": "Kopieren",
        "Paste": "Einfügen",
        "Duplicate": "Duplizieren",
        "Delete selected": "Auswahl löschen",
        "Select All": "Alles auswählen",
        "View": "Ansicht",
        "Zoom In": "Vergrößern",
        "Zoom Out": "Verkleinern",
        "Fit to Window": "An Fenster anpassen",
        "Toggle Grid": "Raster umschalten",
        "Toggle Snap to Grid": "Am Raster einrasten umschalten",
        "Fullscreen Preview": "Vollbildvorschau",
        "Exit Fullscreen Preview": "Vollbildvorschau beenden",
        "Scroll Wheel": "Mausrad",
        "Zoom": "Zoom",
        "Middle Mouse Drag": "Mittlere Maustaste ziehen",
        "Pan": "Schwenken",
        "Drawing Tools": "Zeichenwerkzeuge",
        "Select Tool": "Auswahlwerkzeug",
        "Measure Tool": "Messwerkzeug",
        "Rectangle": "Rechteck",
        "Polygon": "Polygon",
        "Circle": "Kreis",
        "Property Objects": "Grundstücksobjekte",
        "House": "Haus",
        "Terrace/Patio": "Terrasse/Patio",
        "Driveway": "Einfahrt",
        "Garden Bed": "Gartenbeet",
        "Fence": "Zaun",
        "Wall": "Mauer",
        "Path": "Weg",
        "Plant Tools": "Pflanzenwerkzeuge",
        "Tree": "Baum",
        "Shrub": "Strauch",
        "Perennial": "Staude",
        "Search Plant Database": "Pflanzendatenbank durchsuchen",
        "Object Manipulation": "Objektbearbeitung",
        "Arrow Keys": "Pfeiltasten",
        "Move selected (by grid size)": "Auswahl verschieben (um Rastergröße)",
        "Shift+Arrow Keys": "Umschalt+Pfeiltasten",
        "Move selected (by 1cm)": "Auswahl verschieben (um 1 cm)",
        "Double-click": "Doppelklick",
        "Edit object label": "Objektbeschriftung bearbeiten",
        "Close": "Schließen",
    },

    # ── WelcomeDialog ──
    "WelcomeDialog": {
        "Welcome to Open Garden Planner": "Willkommen bei Open Garden Planner",
        "Open Garden Planner": "Open Garden Planner",
        "Recent Projects": "Aktuelle Projekte",
        "Clear Recent": "Verlauf löschen",
        "Get Started": "Erste Schritte",
        "New Project": "Neues Projekt",
        "Open Project...": "Projekt öffnen...",
        "Open Selected": "Ausgewähltes öffnen",
        "<b>Tip:</b> Double-click a recent project to open it directly.":
            "<b>Tipp:</b> Doppelklicken Sie auf ein aktuelles Projekt, um es direkt zu öffnen.",
        "Show this screen on startup": "Diesen Bildschirm beim Start anzeigen",
        "Close": "Schließen",
        "No recent projects": "Keine aktuellen Projekte",
        "{name} (not found)": "{name} (nicht gefunden)",
        "File not found: {path}": "Datei nicht gefunden: {path}",
    },

    # ── ObjectType (from QT_TR_NOOP in object_types.py — missing from pylupdate6) ──
    "ObjectType": {
        "Generic Rectangle": "Generisches Rechteck",
        "Generic Polygon": "Generisches Polygon",
        "Generic Circle": "Generischer Kreis",
        "House": "Haus",
        "Garage/Shed": "Garage/Schuppen",
        "Terrace/Patio": "Terrasse/Patio",
        "Driveway": "Einfahrt",
        "Pond/Pool": "Teich/Pool",
        "Greenhouse": "Gewächshaus",
        "Garden Bed": "Gartenbeet",
        "Lawn": "Rasen",
        "Fence": "Zaun",
        "Wall": "Mauer",
        "Path": "Weg",
        "Tree": "Baum",
        "Shrub": "Strauch",
        "Perennial": "Staude",
        "Hedge Section": "Heckenabschnitt",
        "Table (Rectangular)": "Tisch (rechteckig)",
        "Chair": "Stuhl",
        "Bench": "Bank",
        "Lounger": "Liege",
        "Table (Round)": "Tisch (rund)",
        "Parasol": "Sonnenschirm",
        "BBQ/Grill": "Grill",
        "Fire Pit": "Feuerstelle",
        "Planter/Pot": "Pflanzgefäß/Topf",
        "Raised Bed": "Hochbeet",
        "Compost Bin": "Komposter",
        "Cold Frame": "Frühbeet",
        "Tool Shed": "Geräteschuppen",
        "Rain Barrel": "Regentonne",
        "Water Tap": "Wasserhahn",
    },
}


def fill_translations() -> None:
    """Fill in German translations in the .ts file."""
    tree = ET.parse(TS_FILE)
    root = tree.getroot()

    # Set the target language
    root.set("language", "de_DE")

    # Track stats
    filled = 0
    missing = 0
    added_contexts = 0

    # Collect existing context names
    existing_contexts = {ctx.find("name").text for ctx in root.findall("context")}

    # Process existing contexts
    for context_elem in root.findall("context"):
        context_name = context_elem.find("name").text
        context_translations = TRANSLATIONS.get(context_name, {})

        for message_elem in context_elem.findall("message"):
            source_elem = message_elem.find("source")
            translation_elem = message_elem.find("translation")

            if source_elem is None or translation_elem is None:
                continue

            source_text = source_elem.text or ""

            if source_text in context_translations:
                translation_elem.text = context_translations[source_text]
                # Remove 'type="unfinished"'
                if "type" in translation_elem.attrib:
                    del translation_elem.attrib["type"]
                filled += 1
            else:
                missing += 1
                print(f"  MISSING [{context_name}]: {source_text[:60]!r}")

    # Add missing contexts (ObjectType, expanded GalleryPanel items)
    for context_name, translations in TRANSLATIONS.items():
        if context_name not in existing_contexts:
            # Create new context
            context_elem = ET.SubElement(root, "context")
            name_elem = ET.SubElement(context_elem, "name")
            name_elem.text = context_name

            for source_text, german_text in translations.items():
                message_elem = ET.SubElement(context_elem, "message")
                source_elem = ET.SubElement(message_elem, "source")
                source_elem.text = source_text
                translation_elem = ET.SubElement(message_elem, "translation")
                translation_elem.text = german_text
                filled += 1

            added_contexts += 1
            print(f"  ADDED context '{context_name}' with {len(translations)} strings")
        else:
            # Check if there are extra strings to add to existing context
            context_elem = None
            for ctx in root.findall("context"):
                if ctx.find("name").text == context_name:
                    context_elem = ctx
                    break

            if context_elem is None:
                continue

            # Get existing source texts
            existing_sources = set()
            for msg in context_elem.findall("message"):
                src = msg.find("source")
                if src is not None and src.text:
                    existing_sources.add(src.text)

            # Add missing strings
            for source_text, german_text in translations.items():
                if source_text not in existing_sources:
                    message_elem = ET.SubElement(context_elem, "message")
                    source_elem = ET.SubElement(message_elem, "source")
                    source_elem.text = source_text
                    translation_elem = ET.SubElement(message_elem, "translation")
                    translation_elem.text = german_text
                    filled += 1
                    print(f"  ADDED [{context_name}]: {source_text[:60]!r}")

    # Write the result with proper XML formatting
    ET.indent(tree, space="    ")
    tree.write(TS_FILE, encoding="utf-8", xml_declaration=True)

    # Post-process to add DOCTYPE
    content = TS_FILE.read_text(encoding="utf-8")
    content = content.replace(
        '<?xml version=\'1.0\' encoding=\'utf-8\'?>',
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>',
    )
    TS_FILE.write_text(content, encoding="utf-8")

    print(f"\nDone! Filled {filled} translations, {missing} missing, {added_contexts} new contexts added.")


if __name__ == "__main__":
    fill_translations()
