"""French translations for application commands, reports and plant vocabulary."""

from __future__ import annotations

TRANSLATIONS: dict[str, dict[str, str]] = {
    "GardenPlannerApp": {
        "The plan uses an unsupported group transform at {field}.": (
            "Le plan utilise une transformation de groupe non prise en charge dans {field}."
        ),
        "&3D View": "Vue &3D",
        "Canvas resized to {width} x {height}": "Canevas redimensionné à {width} x {height}",
        "Examples & templates": "Exemples et modèles",
        "Failed to print:\n{error}": "Échec de l’impression :\n{error}",
        "Loaded satellite background (captured map view, zoom {zoom}) — canvas resized to {w_m} x {h_m}": (
            "Fond satellite chargé (vue cartographique capturée, zoom {zoom}) — canevas "
            "redimensionné à {w_m} x {h_m}"
        ),
        "Loaded satellite background ({cols}x{rows} tiles, zoom {zoom}) — canvas resized to {w_m} x {h_m}": (
            "Fond satellite chargé ({cols}x{rows} tuiles, zoom {zoom}) — canevas "
            "redimensionné à {w_m} x {h_m}"
        ),
        "New from example...": "Nouveau à partir d’un exemple...",
        "New from template...": "Nouveau à partir d’un modèle...",
        "New project created: {width} x {height}": "Nouveau projet créé : {width} x {height}",
        "North orientation set to {angle}°": "Orientation du nord définie à {angle}°",
        "Opened as an untitled copy: {name}": "Ouvert comme copie sans titre : {name}",
        "Opened: {name}": "Ouvert : {name}",
        "Point true north on the plan without rotating the drawing": (
            "Indique le nord géographique sur le plan sans faire pivoter le dessin"
        ),
        "Print Error": "Erreur d’impression",
        "Save as template...": "Enregistrer comme modèle...",
        "Saved: {path}. The plan now follows your own date and time, no longer the example's.": (
            "Enregistré : {path}. Le plan suit désormais votre propre date et heure, plus "
            "celles de l’exemple."
        ),
        "Set North Orientation...": "Définir l’orientation du nord...",
        "Show the garden in 3D beside the plan, lit by the simulated sun": (
            "Afficher le jardin en 3D à côté du plan, éclairé par le soleil simulé"
        ),
        "Templates remove location, journal notes and pins, harvest and pest logs, soil tests, season links and year, crop history, seed inventory, propagation overrides, manual tasks and task states, shopping data and amendment preferences, background images, photos and absolute paths. Geometry, species, layers, guilds, constraints and succession plans stay. Review names and free-form text before sharing.": (
            "Les modèles suppriment l’emplacement, les notes et épingles du journal, les "
            "journaux de récolte et de ravageurs, les analyses de sol, les liens de saison "
            "et l’année, l’historique des cultures, l’inventaire des graines, les "
            "remplacements de propagation, les tâches manuelles et les états des tâches, "
            "les données d’achat et les préférences d’amendement, les images de fond, les "
            "photos et les chemins absolus. La géométrie, les espèces, les calques, les "
            "guildes, les contraintes et les plans de succession restent. Vérifiez les noms "
            "et les textes libres avant de partager."
        ),
        "Warning: {count} camera tour(s) could not be read and were skipped.": (
            "Avertissement : {count} visite(s) de caméra n’ont pas pu être lues et ont été ignorées."
        ),
        "X: {x}  Y: {y}": "X : {x}  Y : {y}",
    },
    "Commands": {
        "Change type": "Changer de type",
        "Delete camera tour": "Supprimer la visite de caméra",
        "Edit plant details": "Modifier les détails de la plante",
        "Re-link plants to beds": "Relier à nouveau les plantes aux massifs",
        "Rename camera tour": "Renommer la visite de caméra",
        "Save camera tour": "Enregistrer la visite de caméra",
        "Set north orientation": "Définir l’orientation du nord",
        "Split shape": "Diviser la forme",
        "container drainage": "drainage du bac",
        "container height": "hauteur du bac",
        "container material": "matériau du bac",
        "container soil volume": "volume de terre du bac",
        "fill pattern transform": "transformation du motif de remplissage",
        "grid": "grille",
        "grid spacing": "espacement de la grille",
        "planting date": "date de plantation",
        "removal date": "date de retrait",
        "roof overhang": "débord de toit",
        "roof pitch": "pente du toit",
        "roof style": "style de toit",
        "soil depth": "profondeur de terre",
    },
    "ObjectType": {
        "Garden Light": "Lanterne de jardin",
        "String Lights": "Guirlande lumineuse",
    },
    "GardenItem": {
        "Group": "Grouper",
        "Lock position": "Verrouiller la position",
        "Ungroup": "Dissocier",
        "Unlock position": "Déverrouiller la position",
    },
    "GalleryData": {
        "Bamboo": "Bambou",
        "Garden Light": "Lanterne de jardin",
        "Grape Vine": "Vigne",
        "Japanese Maple": "Érable du Japon",
        "Miscanthus": "Miscanthus",
        "String Lights": "Guirlande lumineuse",
        "Windmill Palm": "Palmier de Chine",
    },
    "CategoryDropdown": {
        "No matching items": "Aucun élément correspondant",
    },
    "ProjectManager": {
        "Choose a template filename outside the current project and bundled examples.": (
            "Choisissez un nom de fichier de modèle en dehors du projet actuel et des "
            "exemples fournis."
        ),
        "Untitled": "Sans titre",
    },
    "TemplateGallery": {
        "Open Selected": "Ouvrir la sélection",
        "Open an example or local template as an untitled copy.": (
            "Ouvrir un exemple ou un modèle local comme copie sans titre."
        ),
    },
    "WelcomeDialog": {
        "Examples & templates": "Exemples et modèles",
    },
    "_DetailPanel": {
        "Seed depth: {depth}": "Profondeur de semis : {depth}",
    },
    "_GanttWidget": {
        "Plant": "Plante",
    },
    "PlantCycle": {
        "Annual": "Annuelle",
        "Biennial": "Bisannuelle",
        "Perennial": "Vivace",
    },
    "EdibleParts": {
        "Bulbs": "Bulbes",
        "Flowers": "Fleurs",
        "Fruit": "Fruits",
        "Leaves": "Feuilles",
        "Pods": "Gousses",
        "Roots": "Racines",
        "Seeds": "Semences",
        "Stems": "Tiges",
        "Tubers": "Tubercules",
    },
    "HarvestUnits": {
        "L": "L",
        "bunch": "botte",
        "g": "g",
        "kg": "kg",
        "pcs": "pièces",
    },
    "TaskText": {
        "Direct sow %1": "Semis direct %1",
        "Harvest %1": "Récolte %1",
        "Prick out %1 seedlings": "Repiquer %1 plants",
        "Start hardening off %1": "Commencer l’endurcissement de %1",
        "Start indoor sowing of %1": "Commencer le semis intérieur de %1",
        "Transplant %1 outdoors": "Transplanter %1 en pleine terre",
    },
    "PdfReportDialog": {
        "Bed detail views (small beds share a page)": (
            "Vues détaillées des massifs (les petits massifs partagent une page)"
        ),
        "Garden Plan": "Plan du jardin",
        "Legend (objects and plants)": "Légende (objets et plantes)",
    },
    "PdfReportService": {
        "Grand total: {total}": "Total général : {total}",
        "Nothing is drawn on this plan yet.": "Rien n’est encore dessiné sur ce plan.",
        "Objects": "Objets",
        "Plan as of {date}": "Plan au {date}",
        "Plants": "Plantes",
        "Position": "Position",
        "{title} – page {page} of {pages}": "{title} – page {page} sur {pages}",
    },
    "ShoppingListService": {
        "ft²": "ft²",
        "ft³": "ft³",
        "~{avg} spread": "~{avg} d’étalement",
    },
    "DiagnosticsPanel": {
        "Plants ({count}): {status}": "Plantes ({count}) : {status}",
    },
    "ExportPngDialog": {
        "Canvas size: {width} × {height}": "Taille du canevas : {width} × {height}",
    },
    "PrintOptionsDialog": {
        "Canvas: {w} × {h}": "Canevas : {w} × {h}",
    },
    "SeedInventoryView": {
        "No seed packets yet. “+ Add Packet” records the seeds you own.\nThe inventory is yours, not a plan's: every plan you open shows the same packets.": (
            "Aucun sachet de graines pour l’instant. « + Ajouter un sachet » enregistre "
            "les graines que vous possédez.\nL’inventaire vous appartient, pas à un plan : "
            "chaque plan ouvert affiche les mêmes sachets."
        ),
    },
    "CalibrationDialog": {
        "Distance, e.g. 12' 6\"": "Distance, par ex. 12' 6\"",
        "e.g., 1200 (cm) or 12 (m)": "par ex. 1200 (cm) ou 12 (m)",
    },
}
