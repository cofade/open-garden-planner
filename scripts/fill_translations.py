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
    # ── BackgroundImageItem ──
    "BackgroundImageItem": {
        "Calibrate Scale...": "Skalierung kalibrieren...",
        "Set Opacity ({pct}%)...": "Deckkraft festlegen ({pct}%)...",
        "Lock Image": "Bild sperren",
        "Unlock Image": "Bild entsperren",
        "Remove Image": "Bild entfernen",
    },

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
        "Import Background Image...": "Hintergrundbild importieren...",
        "Hedge": "Hecke",
        "Distance": "Abstand",
        "Edge length": "Kantenlänge",
        "Horizontal": "Horizontal",
        "Vertical": "Vertikal",
        "Horizontal distance": "Horizontaler Abstand",
        "Vertical distance": "Vertikaler Abstand",
        "Angle": "Winkel",
        "Parallel": "Parallel",
        "Perpendicular": "Senkrecht",
        "Equal": "Gleich",
        "Fixed": "Fixiert",
        "Coincident": "Koinzident",
        "Horizontal symmetry": "Horizontale Symmetrie",
        "Vertical symmetry": "Vertikale Symmetrie",
        "Point on edge": "Punkt auf Kante",
        "Point on circle": "Punkt auf Kreis",
        "Delete Bed": "Beet löschen",
        "The selected bed(s) contain plants. What would you like to do?":
            "Das/die ausgewählte(n) Beet(e) enthält/enthalten Pflanzen. Was möchten Sie tun?",
        "Delete bed and plants": "Beet und Pflanzen löschen",
        "Keep plants": "Pflanzen behalten",
        "Select 2 or more items to group": "Mindestens 2 Elemente zum Gruppieren auswählen",
        "Grouped {n} items": "{n} Elemente gruppiert",
        "No group selected": "Keine Gruppe ausgewählt",
        "Ungrouped": "Gruppierung aufgelöst",
        "Distance must be positive": "Abstand muss positiv sein",
        "Invalid distance. Enter a number in centimeters.":
            "Ungültiger Abstand. Geben Sie eine Zahl in Zentimetern ein.",
        "Select at least 2 objects to align":
            "Wählen Sie mindestens 2 Objekte zum Ausrichten",
        "Select at least 3 objects to distribute":
            "Wählen Sie mindestens 3 Objekte zum Verteilen",
        "Select a shape to offset": "Form zum Versetzen auswählen",
        "Offset result is empty — try a smaller distance":
            "Versatzergebnis ist leer – versuchen Sie einen kleineren Abstand",
        "Created {dir} offset of {dist} cm": "{dir}er Versatz von {dist} cm erstellt",
        "inward": "einwärts",
        "outward": "auswärts",
    },

    # ── CoincidentConstraintTool ──
    "CoincidentConstraintTool": {
        "Conflicting Constraint": "Widersprüchliche Randbedingung",
        "This constraint conflicts with existing constraints and cannot be applied. The existing constraints are unchanged.":
            "Diese Randbedingung widerspricht bestehenden Randbedingungen und kann nicht angewendet werden. Die bestehenden Randbedingungen bleiben unverändert.",
        "⊙ On Circle": "⊙ Auf Kreis",
        "⊥ On Edge": "⊥ Auf Kante",
    },

    # ── ConstraintConflictDialog ──
    "ConstraintConflictDialog": {
        "Constraint conflict": "Randbedingungskonflikt",
        "The new constraint cannot be satisfied together with the following existing constraints. Select which ones to delete, or cancel.":
            "Die neue Randbedingung kann nicht zusammen mit den folgenden bestehenden Randbedingungen erfüllt werden. Wählen Sie aus, welche gelöscht werden sollen, oder brechen Sie ab.",
        "Override (delete selected)": "Überschreiben (Auswahl löschen)",
        "Cancel": "Abbrechen",
    },

    # ── ConstraintListItem ──
    "ConstraintListItem": {
        "= Equal": "= Gleich",
        "{a} equal size to {b}": "{a} gleiche Größe wie {b}",
        "🔒 Fixed": "🔒 Fixiert",
        "{a} is fixed in place": "{a} ist fixiert",
        "Edge {d:.2f} m": "Kante {d:.2f} m",
        "{a} edge length: {d:.2f} m": "{a} Kantenlänge: {d:.2f} m",
        "{a} ↔ H-dist {b}: {d:.2f} m": "{a} ↔ H-Abst. {b}: {d:.2f} m",
        "{a} ↕ V-dist {b}: {d:.2f} m": "{a} ↕ V-Abst. {b}: {d:.2f} m",
    },

    # ── ConstraintTool ──
    "ConstraintTool": {
        "Intra-object edge constraints are only supported for polygons and polylines.":
            "Interne Kantenrandbedingungen werden nur für Polygone und Polylinien unterstützt.",
        "Please select two adjacent (connected) edges of the same polygon.":
            "Bitte wählen Sie zwei angrenzende (verbundene) Kanten desselben Polygons.",
        "Parallel Constraint": "Parallelrandbedingung",
        "The polygon needs at least 4 vertices for a parallel constraint between non-adjacent edges.":
            "Das Polygon benötigt mindestens 4 Knoten für eine Parallelrandbedingung zwischen nicht angrenzenden Kanten.",
        "Adjacent edges of the same polygon cannot be made parallel. To set a specific corner angle, use the Angle constraint tool.":
            "Angrenzende Kanten desselben Polygons können nicht parallel gemacht werden. Um einen bestimmten Winkel festzulegen, verwenden Sie das Winkelrandbedingungswerkzeug.",
    },

    # ── CircleItem (context menu — pylupdate6 cannot extract _ alias) ──
    "CircleItem": {
        "Delete": "Löschen",
        "Duplicate": "Duplizieren",
        "Create Linear Array...": "Lineares Muster erstellen...",
        "Create Grid Array...": "Rastermuster erstellen...",
        "Create Circular Array...": "Kreismuster erstellen...",
        "Boolean": "Bool'sche Operation",
        "Union": "Vereinigung",
        "Intersect": "Schnittmenge",
        "Subtract": "Subtraktion",
        "Array Along Path...": "Muster entlang Pfad...",
    },

    # ── CircleTool ──
    "CircleTool": {
        "Circle": "Kreis",
    },

    # ── EdgeLengthConstraintTool ──
    "EdgeLengthConstraintTool": {
        "Edge Length Constraint": "Kantenlängenrandbedingung",
        "Conflicting Constraint": "Widersprüchliche Randbedingung",
        "This constraint conflicts with existing constraints and cannot be applied. The existing constraints are unchanged.":
            "Diese Randbedingung widerspricht bestehenden Randbedingungen und kann nicht angewendet werden. Die bestehenden Randbedingungen bleiben unverändert.",
    },

    # ── ColorButton ──
    "ColorButton": {
        "Choose Color": "Farbe wählen",
    },

    # ── ConstructionCircleItem ──
    "ConstructionCircleItem": {
        "Delete Construction Circle": "Hilfskreis löschen",
    },

    # ── ConstructionLineItem ──
    "ConstructionLineItem": {
        "Delete Construction Line": "Hilfslinie löschen",
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

    # ── GardenItemMixin (context menu submenus — pylupdate6 cannot extract _ alias) ──
    "GardenItemMixin": {
        "Move to Layer": "Auf Ebene verschieben",
        "Change Type": "Typ ändern",
    },

    # ── GroupItem ──
    "GroupItem": {
        "Ungroup": "Gruppe aufheben",
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
        "Ellipse": "Ellipse",
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
        "&Find && Replace…": "Su&chen && Ersetzen…",
        "Find and replace objects by name, type, layer or species":
            "Objekte nach Name, Typ, Ebene oder Art suchen und ersetzen",
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
        "Set Garden &Location...": "Gartenstandort &festlegen...",
        "Set GPS coordinates and frost dates for planting calendar":
            "GPS-Koordinaten und Frostdaten für den Pflanzkalender festlegen",
        "&Print...": "&Drucken...",
        "Print the garden plan": "Den Gartenplan drucken",
        "Canvas &Size...": "Leinwand&größe...",
        "Resize the canvas dimensions": "Die Leinwandabmessungen ändern",
        "&Preferences...": "&Einstellungen...",
        "Configure application settings and API keys":
            "Anwendungseinstellungen und API-Schlüssel konfigurieren",
        "Show &Constraints": "Randbedingungen &anzeigen",
        "Toggle constraint dimension lines on the canvas":
            "Maßlinien für Randbedingungen auf der Leinwand umschalten",
        "Show C&onstruction Geometry": "K&onstruktionsgeometrie anzeigen",
        "Toggle construction geometry visibility (excluded from exports)":
            "Sichtbarkeit der Konstruktionsgeometrie umschalten (von Exporten ausgeschlossen)",
        "Show &Guide Lines": "&Hilfslinien anzeigen",
        "Toggle ruler and guide lines (drag from ruler to create)":
            "Lineale und Hilfslinien umschalten (vom Lineal ziehen zum Erstellen)",
        "Show Companion &Warnings": "Begleitpflanzen&warnungen anzeigen",
        "Highlight compatible and incompatible plants near the selected plant":
            "Kompatible und inkompatible Pflanzen in der Nähe der ausgewählten Pflanze hervorheben",
        "Show S&pacing Circles": "Ab&standskreise anzeigen",
        "Show recommended spacing zones around plants":
            "Empfohlene Abstandszonen um Pflanzen anzeigen",
        "Show &Minimap": "&Übersichtskarte anzeigen",
        "Show a minimap overview for quick navigation":
            "Übersichtskarte für schnelle Navigation anzeigen",
        "Check &Companion Planting...": "&Mischkulturen prüfen...",
        "Analyse the whole plan for companion planting compatibility":
            "Den gesamten Plan auf Mischkulturkompatibilität analysieren",
        "No location set": "Kein Standort festgelegt",
        "Garden GPS location — use File > Set Garden Location to configure":
            "Garten-GPS-Standort — Datei > Gartenstandort festlegen zum Konfigurieren verwenden",
        "Garden Plan": "Gartenplan",
        "Planting Calendar": "Pflanzkalender",
        "Seed Inventory": "Saatgutbestand",
        "Constraints": "Randbedingungen",
        "Delete all constraints": "Alle Randbedingungen löschen",
        "Companion Planting": "Mischkulturen",
        "Crop Rotation": "Fruchtfolge",
        "Canvas Size": "Leinwandgröße",
        "Canvas resized to {width}m x {height}m": "Leinwand auf {width}m x {height}m geändert",
        "<p>Version {v}</p>": "<p>Version {v}</p>",
        "Garden location updated": "Gartenstandort aktualisiert",
        "Latitude: {lat}, Longitude: {lon}": "Breite: {lat}, Länge: {lon}",
        "Zone": "Zone",
        "Last spring frost": "Letzter Spätfrost",
        "First fall frost": "Erster Herbstfrost",
        "Frost alert — click to view details in Planting Calendar":
            "Frostwarnung — klicken, um Details im Pflanzkalender anzuzeigen",
        "frost alert": "Frostwarnung",
        "frost alerts": "Frostwarnungen",
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
        "Text": "Text",
        "Place a text annotation": "Eine Textanmerkung platzieren",
        "Callout": "Beschriftungspfeil",
        "Place a callout annotation with leader line": "Beschriftungspfeil mit Führungslinie platzieren",
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
        "Garden Year": "Gartenjahr",
        "Assign a year to this plan": "Diesem Plan ein Jahr zuweisen",
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

    # ── PolygonItem (context menu — pylupdate6 cannot extract _ alias) ──
    "PolygonItem": {
        "Exit Vertex Edit Mode": "Knotenbearbeitungsmodus beenden",
        "Edit Vertices": "Knoten bearbeiten",
        "Edit Label": "Beschriftung bearbeiten",
        "Hide Grid": "Raster ausblenden",
        "Show Grid": "Raster einblenden",
        "Delete": "Löschen",
        "Duplicate": "Duplizieren",
        "Create Linear Array...": "Lineares Muster erstellen...",
        "Create Grid Array...": "Rastermuster erstellen...",
        "Create Circular Array...": "Kreismuster erstellen...",
        "Boolean": "Bool'sche Operation",
        "Union": "Vereinigung",
        "Intersect": "Schnittmenge",
        "Subtract": "Subtraktion",
        "Array Along Path...": "Muster entlang Pfad...",
    },

    # ── PolygonTool ──
    "PolygonTool": {
        "Polygon": "Polygon",
    },

    # ── PolylineItem (context menu — pylupdate6 cannot extract _ alias) ──
    "PolylineItem": {
        "Exit Vertex Edit Mode": "Knotenbearbeitungsmodus beenden",
        "Edit Vertices": "Knoten bearbeiten",
        "Edit Label": "Beschriftung bearbeiten",
        "Delete": "Löschen",
        "Duplicate": "Duplizieren",
        "Create Linear Array...": "Lineares Muster erstellen...",
        "Create Grid Array...": "Rastermuster erstellen...",
        "Create Circular Array...": "Kreismuster erstellen...",
        "Array Along Path...": "Muster entlang Pfad...",
    },

    # ── PolylineTool ──
    "PolylineTool": {
        "Polyline": "Polylinie",
    },

    # ── PlantingCalendarView ──
    "PlantingCalendarView": {
        "Germination": "Keimung",
        "Prick out": "Pikieren",
        "Harden off": "Abhärten",
    },

    # ── PrintOptionsDialog ──
    "PrintOptionsDialog": {
        "Print Options": "Druckoptionen",
        "Scale": "Maßstab",
        "Print scale:": "Druckmaßstab:",
        "Include": "Einschließen",
        "Grid": "Raster",
        "Object labels": "Objektbeschriftungen",
        "Legend (project name, scale, date)": "Legende (Projektname, Maßstab, Datum)",
        "Canvas: {w} m × {h} m": "Leinwand: {w} m × {h} m",
        "Single page (scaled to fit)": "Eine Seite (skaliert passend)",
        "1 page at {scale}": "1 Seite bei {scale}",
        "{total} pages ({cols} × {rows}) at {scale}": "{total} Seiten ({cols} × {rows}) bei {scale}",
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

    # ── WeatherWidget (US-12.1) ──
    "WeatherWidget": {
        "Weather Forecast": "Wettervorhersage",
        "Refresh forecast": "Vorhersage aktualisieren",
        "Show / hide full forecast": "Vollständige Vorhersage anzeigen/ausblenden",
        "Loading forecast …": "Vorhersage wird geladen …",
        "Set a location to enable weather forecast.\n"
        "Use File › Set Garden Location to configure GPS coordinates.":
            "Legen Sie einen Standort fest, um die Wettervorhersage zu aktivieren.\n"
            "Verwenden Sie Datei › Gartenstandort festlegen zum Konfigurieren der GPS-Koordinaten.",
        "Date": "Datum",
        "Weather": "Wetter",
        "Max °C": "Max °C",
        "Min °C": "Min °C",
        "Rain mm": "Regen mm",
        "Weather forecast unavailable:\n{message}": "Wettervorhersage nicht verfügbar:\n{message}",
        "Last updated %1 min ago": "Zuletzt aktualisiert vor %1 Min.",
        "Last updated %1 h ago": "Zuletzt aktualisiert vor %1 Std.",
    },

    # ── _WeatherFetchWorker ──
    "_WeatherFetchWorker": {
        "Forecast unavailable": "Vorhersage nicht verfügbar",
    },

    # ── _DashboardPanel (US-12.2 frost task templates) ──
    "_DashboardPanel": {
        "⚠ Frost: %1": "⚠ Frost: %1",
        "❄ Hard frost: %1": "❄ Starker Frost: %1",
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
        "Semi-axes:": "Halbachsen:",
        "Fill Color:": "Füllfarbe:",
        "Fill Pattern:": "Füllmuster:",
        "Stroke Color:": "Linienfarbe:",
        "Stroke Width:": "Linienstärke:",
        "Stroke Style:": "Linienstil:",
        "Group ({n} items)": "Gruppe ({n} Elemente)",
        "Ctrl+Shift+G to ungroup": "Strg+Umschalt+G zum Aufheben der Gruppierung",
        "Contained Plants": "Enthaltene Pflanzen",
        "No plants in this bed": "Keine Pflanzen in diesem Beet",
        "Total: {count} plant(s)": "Gesamt: {count} Pflanze(n)",
        "Unlink": "Verknüpfung aufheben",
        "Parent Bed": "Übergeordnetes Beet",
        "Grid Overlay": "Rasterüberlagerung",
        "Show grid": "Raster anzeigen",
        "Grid:": "Raster:",
        "Spacing:": "Abstand:",
        "Cells:": "Zellen:",
        "—": "—",
        "Recommended spacing radius (half of plant spread)":
            "Empfohlener Abstandsradius (halbe Pflanzenbreite)",
        "Spacing radius:": "Abstandsradius:",
        "Needs frost protection": "Frostschutz benötigt",
        "Frost protection:": "Frostschutz:",
        "Override frost sensitivity:\n☑ Always protect  ☐ Never protect  ‒ Use plant database default":
            "Frostempfindlichkeit überschreiben:\n☑ Immer schützen  ☐ Nie schützen  ‒ Datenbankstandard verwenden",
        "Text": "Text",
        "Content:": "Inhalt:",
        "Font:": "Schriftart:",
        "Bold": "Fett",
        "Italic": "Kursiv",
        "Style:": "Stil:",
        "Color:": "Farbe:",
        "── Paths ──": "── Wege ──",
        "── Fences ──": "── Zäune ──",
    },

    # ── EllipseItem (context menu — pylupdate6 cannot extract _ alias) ──
    "EllipseItem": {
        "Edit Label": "Beschriftung bearbeiten",
        "Delete": "Löschen",
        "Duplicate": "Duplizieren",
        "Create Linear Array...": "Lineares Muster erstellen...",
        "Create Grid Array...": "Rastermuster erstellen...",
        "Create Circular Array...": "Kreismuster erstellen...",
        "Boolean": "Bool'sche Operation",
        "Union": "Vereinigung",
        "Intersect": "Schnittmenge",
        "Subtract": "Subtraktion",
        "Array Along Path...": "Muster entlang Pfad...",
    },

    # ── EllipseTool ──
    "EllipseTool": {
        "Ellipse": "Ellipse",
    },

    # ── OffsetTool / CanvasView strings for offset ──
    "OffsetTool": {
        "Offset": "Versatz",
    },

    # ── RectangleItem (context menu — pylupdate6 cannot extract _ alias) ──
    "RectangleItem": {
        "Exit Vertex Edit Mode": "Knotenbearbeitungsmodus beenden",
        "Edit Vertices": "Knoten bearbeiten",
        "Edit Label": "Beschriftung bearbeiten",
        "Hide Grid": "Raster ausblenden",
        "Show Grid": "Raster einblenden",
        "Delete": "Löschen",
        "Duplicate": "Duplizieren",
        "Create Linear Array...": "Lineares Muster erstellen...",
        "Create Grid Array...": "Rastermuster erstellen...",
        "Create Circular Array...": "Kreismuster erstellen...",
        "Boolean": "Bool'sche Operation",
        "Union": "Vereinigung",
        "Intersect": "Schnittmenge",
        "Subtract": "Subtraktion",
        "Array Along Path...": "Muster entlang Pfad...",
    },

    # ── RectangleTool ──
    "RectangleTool": {
        "Rectangle": "Rechteck",
    },

    # ── ResizeHandle ──
    "ResizeHandle": {
        "Scale blocked: item has dimensional constraints": "Skalierung blockiert: Element hat Maßeinschränkungen",
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

    # ── SeedInventoryView ──
    "SeedInventoryView": {
        "(unnamed plant)": "(unbenannte Pflanze)",
    },

    # ── TextItem (context menu — pylupdate6 cannot extract _ alias) ──
    "TextItem": {
        "Edit Text": "Text bearbeiten",
        "Delete": "Löschen",
    },

    # ── TextTool ──
    "TextTool": {
        "Text": "Text",
    },

    # ── VertexHandle (context menu — pylupdate6 cannot extract _ alias) ──
    "VertexHandle": {
        "Delete Vertex": "Knoten löschen",
    },

    # ── _DetailPanel ──
    "_DetailPanel": {
        "↺": "↺",
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

    # ── CalloutItem (US-11.10) ──
    "CalloutItem": {
        "Edit Text": "Text bearbeiten",
        "Delete": "Löschen",
    },

    # ── CircleItem — area label (US-11.9) ──
    "CircleItem": {
        "Show Area": "Fläche anzeigen",
    },

    # ── EllipseItem — area label (US-11.9) ──
    "EllipseItem": {
        "Show Area": "Fläche anzeigen",
    },

    # ── FindReplacePanel (US-11.24) ──
    "FindReplacePanel": {
        "Find & Replace": "Suchen & Ersetzen",
        "Name contains:": "Name enthält:",
        "Type:": "Typ:",
        "Layer:": "Ebene:",
        "Species contains:": "Art enthält:",
        "(any)": "(beliebig)",
        "Search": "Suchen",
        "Select All Matching": "Alle Treffer auswählen",
        "All Types": "Alle Typen",
        "All Layers": "Alle Ebenen",
        "(unnamed)": "(unbenannt)",
        "Bulk change layer:": "Ebene ändern:",
        "Replace species:": "Art ersetzen:",
        "Apply": "Anwenden",
    },

    # ── PolygonItem — area label (US-11.9) ──
    "PolygonItem": {
        "Show Area": "Fläche anzeigen",
    },

    # ── RectangleItem — area label (US-11.9) ──
    "RectangleItem": {
        "Show Area": "Fläche anzeigen",
    },

    # ── ObjectType (from QT_TR_NOOP in object_types.py — missing from pylupdate6) ──
    "ObjectType": {
        "Generic Rectangle": "Generisches Rechteck",
        "Generic Polygon": "Generisches Polygon",
        "Generic Circle": "Generischer Kreis",
        "Ellipse": "Ellipse",
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
        "Text": "Text",
        "Callout": "Beschriftungspfeil",
    },

    # ── PreferencesDialog (US-12.2 weather section) ──
    "PreferencesDialog": {
        "Preferences": "Einstellungen",
        "Configure your plant database API keys below. "
        "Keys are stored locally and never shared. "
        "Environment variables (.env) are used as fallback.":
            "Konfigurieren Sie unten Ihre Pflanzendatenbank-API-Schlüssel. "
            "Schlüssel werden lokal gespeichert und nie weitergegeben. "
            "Umgebungsvariablen (.env) werden als Fallback verwendet.",
        "Trefle (trefle.io)": "Trefle (trefle.io)",
        "API Token:": "API-Token:",
        "Enter Trefle API token...": "Trefle-API-Token eingeben...",
        "Get API Key": "API-Schlüssel erhalten",
        "Test": "Testen",
        "Perenual (perenual.com)": "Perenual (perenual.com)",
        "API Key:": "API-Schlüssel:",
        "Enter Perenual API key...": "Perenual-API-Schlüssel eingeben...",
        "Permapeople (permapeople.org)": "Permapeople (permapeople.org)",
        "Key ID:": "Schlüssel-ID:",
        "Enter Key ID...": "Schlüssel-ID eingeben...",
        "Key Secret:": "Schlüssel-Geheimnis:",
        "Enter Key Secret...": "Schlüssel-Geheimnis eingeben...",
        "Show": "Anzeigen",
        "Hide": "Ausblenden",
        "Cancel": "Abbrechen",
        "Save": "Speichern",
        "Please enter a Trefle API token first.": "Bitte zuerst einen Trefle-API-Token eingeben.",
        "Please enter a Perenual API key first.": "Bitte zuerst einen Perenual-API-Schlüssel eingeben.",
        "Please enter both Permapeople Key ID and Key Secret.":
            "Bitte sowohl Permapeople-Schlüssel-ID als auch Schlüssel-Geheimnis eingeben.",
        # Weather section (US-12.2)
        "Weather": "Wetter",
        "Orange warning threshold (°C):": "Orange Warnschwelle (°C):",
        "Red alert threshold (°C):": "Roter Alarm-Schwellenwert (°C):",
        "Temperature at or below which half-hardy plants are at risk":
            "Temperatur, bei der oder darunter halbharte Pflanzen gefährdet sind",
        "Temperature at or below which tender plants are at risk":
            "Temperatur, bei der oder darunter empfindliche Pflanzen gefährdet sind",
    },

    # ── UpdateBar ──
    "UpdateBar": {
        "A new version ({version}) is available.": "Eine neue Version ({version}) ist verfügbar.",
        "What's new": "Was ist neu",
        "Download && Install": "Herunterladen && Installieren",
        "Skip this version": "Diese Version überspringen",
        "Remind me later": "Später erinnern",
        "Install Update": "Update installieren",
        "The installer will be downloaded and launched.\n"
        "Open Garden Planner will close when the installer starts.\n\n"
        "Continue?":
            "Das Installationsprogramm wird heruntergeladen und gestartet.\n"
            "Open Garden Planner wird geschlossen, wenn die Installation beginnt.\n\n"
            "Fortfahren?",
        "Downloading {filename}…": "{filename} wird heruntergeladen…",
        "Cancel": "Abbrechen",
        "Download Failed": "Download fehlgeschlagen",
        "Could not download the installer:\n{error}\n\n"
        "Download the latest release directly:\n{url}":
            "Das Installationsprogramm konnte nicht heruntergeladen werden:\n{error}\n\n"
            "Neueste Version direkt herunterladen:\n{url}",
        "Launch Failed": "Start fehlgeschlagen",
        "Could not launch the installer:\n{error}\n\n"
        "Try running Open Garden Planner as Administrator, "
        "or download the installer directly:\n{url}":
            "Das Installationsprogramm konnte nicht gestartet werden:\n{error}\n\n"
            "Starten Sie Open Garden Planner als Administrator, "
            "oder laden Sie das Installationsprogramm direkt herunter:\n{url}",
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
