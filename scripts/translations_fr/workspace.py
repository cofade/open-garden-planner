"""French translations for the 3D workspace, camera tours and sun toolbar.

The source keys are added by the Phase 17 and post-Phase 17 packages; the fork's
catalog predates them. Keep the French typography of the existing catalog:
U+2019 apostrophes and a space before ``:``, ``;`` and ``!``.
"""

from __future__ import annotations

TRANSLATIONS: dict[str, dict[str, str]] = {
    "Workspace": {
        "&3D": "&3D",
        "&Plan": "&Plan",
        "&Reset 3D View": "&Réinitialiser la vue 3D",
        "&Split": "&Diviser",
        "&Walk": "&Visite",
        "&Workspace": "&Espace de travail",
        "+1 Year": "+1 an",
        "+10 Years": "+10 ans",
        "+3 Years": "+3 ans",
        "1 object is not shown in 3D": "1 objet n’est pas affiché en 3D",
        "1 object is not shown in 3D; the 3D ground does not show all of the plan": (
            "1 objet n’est pas affiché en 3D ; le sol 3D ne montre pas tout le plan"
        ),
        "20 March": "20 mars",
        "21 December": "21 décembre",
        "21 June": "21 juin",
        "2D Shadows on the Ground": "Ombres 2D sur le sol",
        "3D is running in compatibility mode (software rendering) because it did not start properly last time.": (
            "La 3D s’exécute en mode de compatibilité (rendu logiciel), car elle n’a pas "
            "démarré correctement la dernière fois."
        ),
        "3D is running in compatibility mode (software rendering).": (
            "La 3D s’exécute en mode de compatibilité (rendu logiciel)."
        ),
        "3D is switched off on this computer: it did not start, not even in compatibility mode (software rendering). The rest of the application is not affected.": (
            "La 3D est désactivée sur cet ordinateur : elle n’a pas démarré, même en mode "
            "de compatibilité (rendu logiciel). Le reste de l’application n’est pas affecté."
        ),
        "3D is switched off: it did not start in compatibility mode (software rendering) either.": (
            "La 3D est désactivée : elle n’a pas démarré non plus en mode de compatibilité "
            "(rendu logiciel)."
        ),
        "3D is unavailable on this graphics device. The rest of the application is not affected.\n\nDetails: {error}": (
            "La 3D n’est pas disponible sur ce périphérique graphique. Le reste de "
            "l’application n’est pas affecté.\n\nDétails : {error}"
        ),
        "4K (3840 x 2160)": "4K (3840 x 2160)",
        "A clear sky: the sun and its shadows as the plan's sun study has them": (
            "Un ciel clair : le soleil et ses ombres comme dans l’étude d’ensoleillement du plan"
        ),
        "A colour grade for the whole picture": "Un étalonnage colorimétrique pour toute l’image",
        "A grey sky: soft, faint shadows; the sun stays where it is": (
            "Un ciel gris : des ombres douces et ténues ; le soleil reste à sa place"
        ),
        "Adult": "Adulte",
        "After: {date}": "Après : {date}",
        "Analyze": "Analyser",
        "Back to the Starting Date": "Retour à la date de départ",
        "Back to {date}": "Retour au {date}",
        "Before: {date}": "Avant : {date}",
        "Black and White": "Noir et blanc",
        "Blur": "Flou",
        "Brighter or darker, in photographers' stops": (
            "Plus clair ou plus sombre, en valeurs d’exposition photographique"
        ),
        "Building the 3D view…": "Construction de la vue 3D…",
        "Camera &Tour...": "&Visite de caméra...",
        "Camera Tour": "Visite de caméra",
        "Capture": "Capturer",
        "Child": "Enfant",
        "Clear": "Effacer",
        "Click an object to see what the 3D view shows of it.": (
            "Cliquez sur un objet pour voir ce que la vue 3D en montre."
        ),
        "Click the ground to read its hours of sun.": (
            "Cliquez sur le sol pour lire ses heures de soleil."
        ),
        "Click the view to set the focus": "Cliquez sur la vue pour régler la mise au point",
        "Compatibility mode (software rendering) is switched on.": (
            "Le mode de compatibilité (rendu logiciel) est activé."
        ),
        "Compatibility mode will be used the next time the application starts.": (
            "Le mode de compatibilité sera utilisé au prochain démarrage de l’application."
        ),
        "Cool Morning": "Matin frais",
        "Crisp Day": "Journée nette",
        "Cutaway": "Coupe",
        "Darken the corners of the picture": "Assombrir les coins de l’image",
        "Day": "Jour",
        "Develop the view like a photo and save it, up to 4K": (
            "Développer la vue comme une photo et l’enregistrer, jusqu’en 4K"
        ),
        "Exposure": "Exposition",
        "Exposure, colour grade, vignette and a click to set the focus. Changes how the picture looks, never what stands in the garden.": (
            "Exposition, étalonnage, vignettage et un clic pour la mise au point. Modifie "
            "l’aspect de l’image, jamais ce qui se trouve dans le jardin."
        ),
        "Eye height while walking": "Hauteur des yeux pendant la visite",
        "Fly a camera through the garden and save it as a video or a PNG sequence": (
            "Faites voler une caméra dans le jardin et enregistrez-la en vidéo ou en séquence PNG"
        ),
        "Focus {distance} away": "Mise au point à {distance}",
        "Full HD (1920 x 1080)": "Full HD (1920 x 1080)",
        "Golden Hour": "Heure dorée",
        "Golden hour": "Heure dorée",
        "Ground at {east} east, {north} north: {hours} h of direct sun on {date} — {band}.": (
            "Sol à {east} à l’est, {north} au nord : {hours} h de soleil direct le {date} — {band}."
        ),
        "Growth": "Croissance",
        "Hardware rendering will be tried the next time the application starts.": (
            "Le rendu matériel sera essayé au prochain démarrage de l’application."
        ),
        "Hours of Sun on the Ground": "Heures de soleil sur le sol",
        "How far out of focus everything else goes. Click the view to choose what stays sharp.": (
            "Jusqu’où le reste devient flou. Cliquez sur la vue pour choisir ce qui reste net."
        ),
        "Lay the hours-of-sun map on the 3D ground; click the ground to read it": (
            "Pose la carte des heures de soleil sur le sol 3D ; cliquez sur le sol pour la lire"
        ),
        "Lay the plan's 2D shadows on the 3D ground: the sun study's own answer": (
            "Pose les ombres 2D du plan sur le sol 3D : la réponse de l’étude d’ensoleillement"
        ),
        "Mood: {mood}": "Ambiance : {mood}",
        "Morning dew": "Rosée du matin",
        "Move the plan date forward and compare before and after": (
            "Avance la date du plan et compare avant et après"
        ),
        "Night": "Nuit",
        "No Grade": "Sans étalonnage",
        "Nothing on the Ground": "Rien sur le sol",
        "On the ground": "Sur le sol",
        "Overcast": "Couvert",
        "P&hoto Mode": "Mode p&hoto",
        "PNG image (*.png);;JPEG image (*.jpg)": "Image PNG (*.png);;Image JPEG (*.jpg)",
        "Partly cloudy": "Partiellement nuageux",
        "Plan date": "Date du plan",
        "Play the plan date from sunrise to sunset and watch the hours of sun add up": (
            "Faites défiler la date du plan du lever au coucher du soleil et regardez les "
            "heures de soleil s’additionner"
        ),
        "QHD (2560 x 1440)": "QHD (2560 x 1440)",
        "Rain": "Pluie",
        "Rain: a grey sky, wet leaves and ground, falling rain": (
            "Pluie : un ciel gris, des feuilles et un sol mouillés, de la pluie qui tombe"
        ),
        "Save Photo": "Enregistrer la photo",
        "Save Photo...": "Enregistrer la photo...",
        "Set a garden location to draw the sun path.": (
            "Définissez un emplacement pour le jardin afin de tracer la course du soleil."
        ),
        "Show List": "Afficher la liste",
        "Show butterflies at the flowers, fireflies on summer evenings and falling leaves in autumn": (
            "Afficher les papillons sur les fleurs, les lucioles les soirs d’été et les "
            "feuilles qui tombent en automne"
        ),
        "Show the garden in 3D": "Afficher le jardin en 3D",
        "Show the garden in 3D without an analysis on the ground": (
            "Afficher le jardin en 3D sans analyse sur le sol"
        ),
        "Show the plan and the 3D view side by side": "Afficher le plan et la vue 3D côte à côte",
        "Show the plan only": "Afficher le plan uniquement",
        "Show the whole garden again ({key})": "Réafficher tout le jardin ({key})",
        "Show the whole garden in the 3D view again": "Réafficher tout le jardin dans la vue 3D",
        "Show where the sun goes today, at both solstices and at the equinox, and a compass": (
            "Montrer la course du soleil aujourd’hui, aux deux solstices et à l’équinoxe, "
            "ainsi qu’une boussole"
        ),
        "Show which objects are missing from the 3D view": (
            "Montrer quels objets manquent dans la vue 3D"
        ),
        "Smaller adult": "Adulte plus petit",
        "Snow": "Neige",
        "Snow on the ground and the leaves, falling snow": (
            "Neige sur le sol et les feuilles, chute de neige"
        ),
        "Soft Film": "Film doux",
        "Sun Path and Compass": "Course du soleil et boussole",
        "Sun and scattered clouds: the shadows stay, a little softer. The clouds show with the atmosphere sky (Preferences, 3D View, Sky)": (
            "Soleil et nuages épars : les ombres restent, un peu plus douces. Les nuages "
            "apparaissent avec le ciel atmosphérique (Préférences, Vue 3D, Ciel)"
        ),
        "Sun and shade on the ground, the sun path, a day sweep, Cutaway and growth": (
            "Soleil et ombre sur le sol, la course du soleil, le défilement d’une journée, "
            "la coupe et la croissance"
        ),
        "Sweep the Day": "Défiler la journée",
        "Take the roofs off and let what stands in front of the selection fade": (
            "Retire les toits et estompe ce qui se trouve devant la sélection"
        ),
        "That spot lies outside the hours-of-sun map.": (
            "Cet endroit se trouve hors de la carte des heures de soleil."
        ),
        "The 3D ground does not show all of the plan": "Le sol 3D ne montre pas tout le plan",
        "The 3D view could not be started. The rest of the application is not affected.\n\nDetails: {error}": (
            "La vue 3D n’a pas pu être démarrée. Le reste de l’application n’est pas "
            "affecté.\n\nDétails : {error}"
        ),
        "The 3D view could not be updated. It will try again with the next change.": (
            "La vue 3D n’a pas pu être mise à jour. Elle réessaiera à la prochaine modification."
        ),
        "The 3D view is not visible right now. Bring it back and try again.": (
            "La vue 3D n’est pas visible pour le moment. Réaffichez-la et réessayez."
        ),
        "The 3D view reported a problem. Details are in the log file.": (
            "La vue 3D a signalé un problème. Les détails se trouvent dans le fichier journal."
        ),
        "The analysis on the ground shows the clear sun's colours; the weather returns when the ground shows nothing.": (
            "L’analyse sur le sol montre les couleurs du soleil clair ; la météo revient "
            "lorsque le sol n’affiche rien."
        ),
        "The focus moves to the new plan when it is shown": (
            "Le focus passe au nouveau plan lorsqu’il est affiché"
        ),
        "The forecast for today is not loaded yet, or could not be fetched.": (
            "La prévision du jour n’est pas encore chargée ou n’a pas pu être récupérée."
        ),
        "The forecast's weather while the plan date is today; on any other date a clear sky": (
            "La météo prévue tant que la date du plan est aujourd’hui ; à toute autre date, "
            "un ciel clair"
        ),
        "The hours of sun are being updated for the changed plan.": (
            "Les heures de soleil sont mises à jour pour le plan modifié."
        ),
        "The hours of sun are not computed yet for this plan date.": (
            "Les heures de soleil ne sont pas encore calculées pour cette date du plan."
        ),
        "The hours of sun could not be computed for the changed plan.": (
            "Les heures de soleil n’ont pas pu être calculées pour le plan modifié."
        ),
        "The picture could not be made: {error}": "L’image n’a pas pu être créée : {error}",
        "The picture could not be saved to {path}.": (
            "L’image n’a pas pu être enregistrée dans {path}."
        ),
        "The recording could not be closed before the window went. Its unfinished output may stay at {path}.": (
            "L’enregistrement n’a pas pu être fermé avant la fermeture de la fenêtre. Sa "
            "sortie inachevée peut rester dans {path}."
        ),
        "The setting could not be changed. Details are in the log file.": (
            "Le réglage n’a pas pu être modifié. Les détails se trouvent dans le fichier journal."
        ),
        "The size of the saved picture. The other sizes keep the view's height in the picture and show more or less at the sides.": (
            "La taille de l’image enregistrée. Les autres tailles conservent la hauteur de "
            "la vue dans l’image et montrent plus ou moins sur les côtés."
        ),
        "There is no daylight to sweep on this date here, or the garden has no location.": (
            "Il n’y a pas de lumière du jour à faire défiler à cette date ici, ou le jardin "
            "n’a pas d’emplacement."
        ),
        "There is no free ground to walk on.": "Il n’y a pas de sol libre sur lequel marcher.",
        "Today's Weather": "Météo du jour",
        "Today's weather follows the forecast only while the plan date is today; on any other date the sky is clear.": (
            "La météo du jour suit la prévision uniquement tant que la date du plan est "
            "aujourd’hui ; à toute autre date, le ciel est clair."
        ),
        "Today's weather needs a garden location for its forecast.": (
            "La météo du jour a besoin d’un emplacement pour le jardin afin d’obtenir sa prévision."
        ),
        "Try Again": "Réessayer",
        "Try Hardware Next Time": "Essayer le matériel la prochaine fois",
        "Twilight": "Crépuscule",
        "Updating the 3D view…": "Mise à jour de la vue 3D…",
        "Use Compatibility Mode Next Time": "Utiliser le mode de compatibilité la prochaine fois",
        "Video delivery is still finishing. Its destination is {path}; if it cannot be delivered, the render is kept as {part}. Check the application log for the result.": (
            "La livraison de la vidéo se termine. Sa destination est {path} ; si elle ne "
            "peut pas être livrée, le rendu est conservé sous {part}. Consultez le journal "
            "de l’application pour le résultat."
        ),
        "View Size": "Taille de la vue",
        "Vignette": "Vignettage",
        "Walk through the garden at eye height": "Parcourir le jardin à hauteur des yeux",
        "Walk through the garden at eye height (W A S D or the arrow keys walk, drag to look around, Shift runs, Esc leaves)": (
            "Parcourir le jardin à hauteur des yeux (W A S D ou les flèches pour marcher, "
            "faites glisser pour regarder autour, Maj pour courir, Échap pour quitter)"
        ),
        "Weather": "Météo",
        "Weather: Today ({weather})": "Météo : aujourd’hui ({weather})",
        "Weather: {weather}": "Météo : {weather}",
        "Wildlife and Falling Leaves": "Faune et feuilles qui tombent",
        "{count} objects are not shown in 3D": "{count} objets ne sont pas affichés en 3D",
        "{count} objects are not shown in 3D; the 3D ground does not show all of the plan": (
            "{count} objets ne sont pas affichés en 3D ; le sol 3D ne montre pas tout le plan"
        ),
        "{count} objects selected.": "{count} objets sélectionnés.",
        "{day} — same path as the plan date": "{day} — même course que la date du plan",
        "{tip} ({shortcut})": "{tip} ({shortcut})",
        "{weather} (paused while analysing)": "{weather} (en pause pendant l’analyse)",
        "{who} – {height}": "{who} – {height}",
    },
    "TourDialog": {
        " s": " s",
        " °": " °",
        "3D is not available on this computer.": "La 3D n’est pas disponible sur cet ordinateur.",
        "A frame could not be saved. Is the disk full?": (
            "Une image n’a pas pu être enregistrée. Le disque est-il plein ?"
        ),
        "A plan keeps at most {count} tours. Delete one first.": (
            "Un plan conserve au maximum {count} visites. Supprimez-en une d’abord."
        ),
        "A recording is already running.": "Un enregistrement est déjà en cours.",
        "A tour named '{name}' already exists.": "Une visite nommée « {name} » existe déjà.",
        "A tour named '{name}' already exists. Replace it?": (
            "Une visite nommée « {name} » existe déjà. La remplacer ?"
        ),
        "A video frame could not be prepared.": "Une image vidéo n’a pas pu être préparée.",
        "Add Current View": "Ajouter la vue actuelle",
        "Best, for Publishing": "Meilleure, pour publication",
        "Camera": "Caméra",
        "Camera Tour": "Visite de caméra",
        "Camera tilt:": "Inclinaison de la caméra :",
        "Cancel": "Annuler",
        "Cancelled.": "Annulé.",
        "Clockwise": "Dans le sens horaire",
        "Close": "Fermer",
        "Delete": "Supprimer",
        "Deleted the tour '{name}'. Undo brings it back.": (
            "Visite « {name} » supprimée. Annuler la restaure."
        ),
        "Discard the changes to the current tour?": (
            "Abandonner les modifications de la visite actuelle ?"
        ),
        "Drone Orbit Around the Plan": "Orbite de drone autour du plan",
        "Duration:": "Durée :",
        "Finishing the file…": "Finalisation du fichier…",
        "Fly Through My Keyframes": "Voler entre mes images clés",
        "Fly back to the start": "Revenir au début",
        "Folder for the frames (*)": "Dossier des images (*)",
        "Frame rate:": "Fréquence d’images :",
        "Frame {done} of {total}": "Image {done} sur {total}",
        "From:": "De :",
        "How long the video lasts. A drone orbit takes 30 s a turn until you set a length here.": (
            "Durée de la vidéo. Une orbite de drone dure 30 s par tour jusqu’à ce que vous "
            "définissiez une durée ici."
        ),
        "How much detail the video keeps. Best keeps nearly every leaf and makes a larger file: use it for a video you publish. Only for Save Video: a PNG sequence keeps every detail.": (
            "Niveau de détail conservé dans la vidéo. Meilleure conserve presque chaque "
            "feuille et produit un fichier plus volumineux : utilisez-la pour une vidéo que "
            "vous publiez. Uniquement pour Enregistrer la vidéo : une séquence PNG conserve "
            "tous les détails."
        ),
        "How steeply the camera looks down at the garden. A low tilt shows the horizon and the sky; a high one looks down into the beds.": (
            "Inclinaison de la caméra vers le jardin. Une faible inclinaison montre "
            "l’horizon et le ciel ; une forte inclinaison plonge dans les massifs."
        ),
        "Keep the Current View": "Conserver la vue actuelle",
        "MP4 video (*.mp4)": "Vidéo MP4 (*.mp4)",
        "Name of the tour:": "Nom de la visite :",
        "Open the 3D view first: switch to 3D or Split.": (
            "Ouvrez d’abord la vue 3D : passez en 3D ou en mode Divisé."
        ),
        "Picture": "Image",
        "Play the tour small and in real time, here in this window. Saves nothing.": (
            "Lire la visite en petit et en temps réel, ici dans cette fenêtre. N’enregistre rien."
        ),
        "Preview": "Aperçu",
        "Remove": "Retirer",
        "Rename Tour": "Renommer la visite",
        "Rename...": "Renommer...",
        "Rendering…": "Rendu en cours…",
        "Save PNG Sequence": "Enregistrer la séquence PNG",
        "Save PNG Sequence...": "Enregistrer la séquence PNG...",
        "Save Tour": "Enregistrer la visite",
        "Save Tour As": "Enregistrer la visite sous",
        "Save Tour As...": "Enregistrer la visite sous...",
        "Save Video": "Enregistrer la vidéo",
        "Save Video...": "Enregistrer la vidéo...",
        "Saved the tour '{name}' in the plan.": "Visite « {name} » enregistrée dans le plan.",
        "Saved {frames} frames to {path}.": "{frames} images enregistrées dans {path}.",
        "Size:": "Taille :",
        "Standard": "Standard",
        "Start and stop smoothly": "Démarrer et s’arrêter en douceur",
        "Start the orbit exactly where the 3D view is now, with the view's own tilt.": (
            "Démarre l’orbite exactement là où se trouve la vue 3D, avec sa propre inclinaison."
        ),
        "Starts at the view saved with this tour.": (
            "Commence à la vue enregistrée avec cette visite."
        ),
        "Starts where the view is now, at the same distance, with the tilt set here.": (
            "Commence là où se trouve la vue, à la même distance, avec l’inclinaison définie ici."
        ),
        "Stay at the Plan's Date and Time": "Rester à la date et à l’heure du plan",
        "Stop the recording? It has been running for {seconds:.0f} s, and the video is not saved yet.": (
            "Arrêter l’enregistrement ? Il dure depuis {seconds:.0f} s et la vidéo n’est pas "
            "encore enregistrée."
        ),
        "Stop the render? The frames already written to {path} stay.": (
            "Arrêter le rendu ? Les images déjà écrites dans {path} sont conservées."
        ),
        "Stopping…": "Arrêt en cours…",
        "The 3D view is still building. Try again in a moment.": (
            "La vue 3D est encore en construction. Réessayez dans un instant."
        ),
        "The camera speeds up gently at the start and slows down to a stop at the end. Turn it off for a video that plays in a loop: then the end leads straight back into the start.": (
            "La caméra accélère doucement au début et ralentit jusqu’à l’arrêt à la fin. "
            "Désactivez cette option pour une vidéo en boucle : la fin enchaîne alors "
            "directement sur le début."
        ),
        "The camera stays at the view saved with this tour. Good for a time-lapse.": (
            "La caméra reste à la vue enregistrée avec cette visite. Idéal pour un time-lapse."
        ),
        "The camera stays where the view is now. Good for a time-lapse.": (
            "La caméra reste là où se trouve la vue. Idéal pour un time-lapse."
        ),
        "The recording failed: {message}": "L’enregistrement a échoué : {message}",
        "The tours kept in this plan. They are saved with the plan file.": (
            "Les visites conservées dans ce plan. Elles sont enregistrées avec le fichier du plan."
        ),
        "The video could not be prepared. The render is kept as {part}. The destination was not replaced.": (
            "La vidéo n’a pas pu être préparée. Le rendu est conservé sous {part}. La "
            "destination n’a pas été remplacée."
        ),
        "The video file could not be closed.": "Le fichier vidéo n’a pas pu être fermé.",
        "The video file {path} cannot be written: {error}": (
            "Le fichier vidéo {path} ne peut pas être écrit : {error}"
        ),
        "This computer has no video encoder for MP4 files. Save a PNG sequence instead.": (
            "Cet ordinateur n’a pas d’encodeur vidéo pour les fichiers MP4. Enregistrez "
            "plutôt une séquence PNG."
        ),
        "This folder already holds the frames of another tour. Choose an empty one.": (
            "Ce dossier contient déjà les images d’une autre visite. Choisissez-en un vide."
        ),
        "Time": "Heure",
        "Time-Lapse Through the Year": "Time-lapse sur l’année",
        "Time-Lapse of a Day": "Time-lapse d’une journée",
        "To:": "À :",
        "Tours in This Plan": "Visites de ce plan",
        "Turns:": "Tours :",
        "Unsaved Tour": "Visite non enregistrée",
        "Use Current View": "Utiliser la vue actuelle",
        "Video delivery failed. Check {path} and {part} for the output.": (
            "La livraison de la vidéo a échoué. Vérifiez {path} et {part} pour la sortie."
        ),
        "Video is not available in this build of the app.": (
            "La vidéo n’est pas disponible dans cette version de l’application."
        ),
        "Video quality:": "Qualité de la vidéo :",
        "View {number}: from {east} / {north}, {height} high": (
            "Vue {number} : depuis {east} / {north}, à {height} de haut"
        ),
        "Waiting: the 3D view is not visible. The recording goes on when it is back.": (
            "En attente : la vue 3D n’est pas visible. L’enregistrement reprend dès son retour."
        ),
        "{count} frames were rendered before the 3D view had caught up with their date.": (
            "{count} images ont été rendues avant que la vue 3D n’ait rattrapé leur date."
        ),
        "{path} could not be replaced ({error}). The video is saved as {part}.": (
            "{path} n’a pas pu être remplacé ({error}). La vidéo est enregistrée sous {part}."
        ),
        "{rate} frames per second": "{rate} images par seconde",
    },
    "View3DInfoCard": {
        "Area:": "Surface :",
        "Bed:": "Massif :",
        "Canopy diameter:": "Diamètre de la couronne :",
        "Centre the plan on this object": "Centrer le plan sur cet objet",
        "Diameter:": "Diamètre :",
        "Drawn on the ground in 3D: the plan gives it no height.": (
            "Dessiné au sol en 3D : le plan ne lui donne aucune hauteur."
        ),
        "Group": "Groupe",
        "Growth:": "Croissance :",
        "Harvest:": "Récolte :",
        "Height:": "Hauteur :",
        "Length:": "Longueur :",
        "Not shown in 3D: this kind of object has no 3D form.": (
            "Non affiché en 3D : ce type d’objet n’a pas de forme 3D."
        ),
        "Not shown in 3D: {reason}.": "Non affiché en 3D : {reason}.",
        "Object": "Objet",
        "Scientific name:": "Nom scientifique :",
        "Show in Plan": "Afficher dans le plan",
        "Size:": "Taille :",
        "Sizes on:": "Dimensions selon :",
        "Sow indoors:": "Semis à l’intérieur :",
        "Sow outdoors:": "Semis en pleine terre :",
        "Species:": "Espèce :",
        "Sun:": "Soleil :",
        "Type:": "Type :",
        "as measured": "tel que mesuré",
        "fill height": "hauteur de remplissage",
        "grown to the plan date": "crû jusqu’à la date du plan",
        "not known": "inconnu",
        "set on the object": "défini sur l’objet",
        "species maximum": "maximum de l’espèce",
        "usual for the type": "habituel pour le type",
        "{height} (estimated)": "{height} (estimé)",
        "{height} ({source})": "{height} ({source})",
        "{hours} h on {date} — {band}": "{hours} h le {date} — {band}",
        "{percent} % of the way to full size": "{percent} % de la taille adulte",
        "{start} – {end}": "{start} – {end}",
        "{width} × {depth}": "{width} × {depth}",
    },
    "View3DProblemsDialog": {
        "3D ground: in one place the plan puts more surfaces than the ground can show; the smallest are left out": (
            "Sol 3D : à un endroit, le plan place plus de surfaces que le sol ne peut en "
            "afficher ; les plus petites sont omises"
        ),
        "3D ground: in {count} places the plan puts more surfaces than the ground can show; the smallest are left out": (
            "Sol 3D : à {count} endroits, le plan place plus de surfaces que le sol ne peut "
            "en afficher ; les plus petites sont omises"
        ),
        "3D ground: it could not be finished; it is tried again with the next change": (
            "Sol 3D : il n’a pas pu être terminé ; une nouvelle tentative aura lieu à la "
            "prochaine modification"
        ),
        "3D ground: it could not be painted; it shows an older picture": (
            "Sol 3D : il n’a pas pu être peint ; il affiche une image plus ancienne"
        ),
        "3D ground: one piece could not be painted and shows an older picture": (
            "Sol 3D : une pièce n’a pas pu être peinte et affiche une image plus ancienne"
        ),
        "3D ground: {count} pieces could not be painted and show an older picture": (
            "Sol 3D : {count} pièces n’ont pas pu être peintes et affichent une image plus ancienne"
        ),
        "Not Shown in 3D": "Non affiché en 3D",
        "These objects are on the plan but cannot be shown in the 3D view. Double-click an entry to select the object on the plan.": (
            "Ces objets figurent sur le plan mais ne peuvent pas être affichés dans la vue "
            "3D. Double-cliquez sur une entrée pour sélectionner l’objet sur le plan."
        ),
        "another object on the plan has the same internal id": (
            "un autre objet du plan possède le même identifiant interne"
        ),
        "it could not be painted completely on the 3D ground": (
            "il n’a pas pu être entièrement peint sur le sol 3D"
        ),
        "it could not be shown": "il n’a pas pu être affiché",
        "its 3D model could not be built": "son modèle 3D n’a pas pu être construit",
        "its outline cannot be turned into a solid": (
            "son contour ne peut pas être transformé en solide"
        ),
        "its outline has too many points for the 3D view": (
            "son contour a trop de points pour la vue 3D"
        ),
        "its shape could not be worked out": "sa forme n’a pas pu être déterminée",
        "one of its sizes is outside what the 3D view can show": (
            "l’une de ses dimensions sort de ce que la vue 3D peut afficher"
        ),
        "{kind}: {reason}": "{kind} : {reason}",
        "{name} ({kind}): {reason}": "{name} ({kind}) : {reason}",
        "… and {count} more": "… et {count} de plus",
    },
    "SunSimToolbar": {
        "Animate the plan date through its year at this time of day": (
            "Anime la date du plan au fil de l’année à cette heure de la journée"
        ),
        "Animate the sun across the selected day": (
            "Anime le soleil au cours de la journée sélectionnée"
        ),
        "Fast": "Rapide",
        "Full-day hours of sun; updates automatically while enabled": (
            "Heures de soleil sur la journée entière ; se met à jour automatiquement lorsqu’activé"
        ),
        "Future": "Futur",
        "Go to the current date and time": "Aller à la date et à l’heure actuelles",
        "Map: {date}": "Carte : {date}",
        "Map: {date} — Unavailable": "Carte : {date} — indisponible",
        "Map: {date} — Updating…": "Carte : {date} — mise à jour…",
        "Months": "Mois",
        "Normal": "Normale",
        "Past": "Passé",
        "Plan & Sun": "Plan et soleil",
        "Plan date: plant presence, growth and sunlight": (
            "Date du plan : présence des plantes, croissance et ensoleillement"
        ),
        "Plant date unavailable": "Date de plantation indisponible",
        "Plants hidden by the plan date": "Plantes masquées par la date du plan",
        "Play": "Lire",
        "Play the plan date through its year at this time of day": (
            "Fait défiler la date du plan au fil de l’année à cette heure de la journée"
        ),
        "Play the time of day; the plan date stays": (
            "Fait défiler l’heure de la journée ; la date du plan reste fixe"
        ),
        "Scrub by month; Page Up/Down jumps one year": (
            "Faites glisser par mois ; Page haut/bas saute d’une année"
        ),
        "Set location for sunlight…": "Définir l’emplacement pour l’ensoleillement…",
        "Slow": "Lent",
        "Speed": "Vitesse",
        "Sun shadows and Hours of Sun need a garden location. Opens File → Set Garden Location…": (
            "Les ombres du soleil et les heures de soleil nécessitent un emplacement. "
            "Ouvre Fichier → Définir l’emplacement du jardin…"
        ),
        "The Day": "La journée",
        "The Year": "L’année",
        "This plant is not present within the supported plan dates ({min} to {max}). Its stored dates have been preserved.": (
            "Cette plante n’est pas présente dans les dates de plan prises en charge "
            "({min} à {max}). Ses dates enregistrées ont été conservées."
        ),
        "Today": "Aujourd’hui",
        "Updating…": "Mise à jour…",
        "{count} hidden": "{count} masquées",
        "{name} — planted: {planted}; removed: {removed}": (
            "{name} — plantée : {planted} ; retirée : {removed}"
        ),
    },
    "ShortcutsDialog": {
        "3D View": "Vue 3D",
        "3D only": "3D uniquement",
        "CAD Editing": "Édition CAO",
        "Cancel and return to the Select tool": "Annuler et revenir à l’outil Sélection",
        "Chamfer": "Chanfrein",
        "Click": "Clic",
        "Fillet": "Congé",
        "Leave walk mode": "Quitter le mode visite",
        "Left Mouse Drag": "Glisser avec le bouton gauche",
        "Look around": "Regarder autour",
        "Mirror": "Symétrie",
        "Mouse Drag": "Glisser avec la souris",
        "Offset": "Décalage",
        "Orbit the 3D view": "Orbiter autour de la vue 3D",
        "Page Up / Page Down": "Page haut / Page bas",
        "Pan the 3D view": "Déplacer la vue 3D",
        "Plan and 3D side by side (Split)": "Plan et 3D côte à côte (Divisé)",
        "Plan only": "Plan uniquement",
        "Reset 3D View": "Réinitialiser la vue 3D",
        "Right Mouse Drag": "Glisser avec le bouton droit",
        "Run": "Courir",
        "Select the object under the pointer": "Sélectionner l’objet sous le pointeur",
        "Split along line": "Diviser le long d’une ligne",
        "Trim/Extend": "Rogner / Prolonger",
        "W A S D / Arrow Keys": "W A S D / touches fléchées",
        "Walk": "Visite",
        "Walk Mode (3D)": "Mode visite (3D)",
    },
    "PropertiesPanel": {
        "A group member stays on its group's layer": (
            "Un membre de groupe reste sur le calque de son groupe"
        ),
        "Automatic": "Automatique",
        "Cannot resize this shape: its edge length is constrained. Remove the constraint first.": (
            "Impossible de redimensionner cette forme : la longueur de son côté est "
            "contrainte. Retirez d’abord la contrainte."
        ),
        "Flat": "Plat",
        "Font height on the plan. Capital letters are about 70 % as tall. The text takes the nearest available size.": (
            "Hauteur de police sur le plan. Les majuscules mesurent environ 70 % de cette "
            "hauteur. Le texte prend la taille disponible la plus proche."
        ),
        "Gable": "À deux pans",
        "H: ": "H : ",
        "Hip": "À quatre pans",
        "Invalid symbol parameter value — geometry unchanged.": (
            "Valeur de paramètre de symbole invalide — géométrie inchangée."
        ),
        "Locked in place: unlock to move (Fix in place constraint).": (
            "Verrouillé en place : déverrouillez pour déplacer (contrainte Fixer en place)."
        ),
        "No height — no shadow on the 2D plan": "Aucune hauteur — aucune ombre sur le plan 2D",
        "Pattern Angle:": "Angle du motif :",
        "Pattern Offset:": "Décalage du motif :",
        "Pattern Scale:": "Échelle du motif :",
        "Reset Pattern": "Réinitialiser le motif",
        "Restore the pattern's original angle, scale and offset": (
            "Restaure l’angle, l’échelle et le décalage d’origine du motif"
        ),
        "Roof overhang:": "Débord de toit :",
        "Roof pitch:": "Pente du toit :",
        "Roof style:": "Style de toit :",
        "Single slope": "Un seul pan",
        "Symbol definition version mismatch — saved geometry is read-only.": (
            "Version de définition du symbole incompatible — la géométrie enregistrée est "
            "en lecture seule."
        ),
        "The 2D plan draws the roof style. The sun study and 3D view also use pitch and overhang.": (
            "Le plan 2D dessine le style de toit. L’étude d’ensoleillement et la vue 3D "
            "utilisent aussi la pente et le débord."
        ),
        "Turns the 2D texture only; the object's geometry and measurements stay unchanged": (
            "Ne fait tourner que la texture 2D ; la géométrie et les mesures de l’objet "
            "restent inchangées"
        ),
        "W: ": "L : ",
    },
    "PreferencesDialog": {
        "3D View": "Vue 3D",
        "Atmosphere with clouds": "Atmosphère avec nuages",
        "Automatic": "Automatique",
        "Canvas": "Canevas",
        "Enable touch gestures (pinch to zoom, two-finger pan)": (
            "Activer les gestes tactiles (pincer pour zoomer, défiler à deux doigts)"
        ),
        "High": "Élevée",
        "How detailed the 3D view is drawn. Automatic picks a level from the frame rate it measures on this computer.": (
            "Niveau de détail de la vue 3D. Automatique choisit un niveau d’après la "
            "fréquence d’images mesurée sur cet ordinateur."
        ),
        "Imperial (in, ft)": "Impérial (po, pi)",
        "Keep leaves and grass still instead of swaying in the wind. The operating system's animation-effects setting also stops the wind.": (
            "Garder les feuilles et l’herbe immobiles au lieu de les balancer au vent. Le "
            "réglage des effets d’animation du système arrête aussi le vent."
        ),
        "Low": "Faible",
        "Medium": "Moyenne",
        "Metric (cm, m)": "Métrique (cm, m)",
        "On a touch screen, pinch with two fingers to zoom the plan and drag two fingers to move it. A single finger still selects and moves objects as a mouse does.": (
            "Sur un écran tactile, pincez avec deux doigts pour zoomer sur le plan et faites "
            "glisser deux doigts pour le déplacer. Un seul doigt sélectionne et déplace "
            "encore les objets comme une souris."
        ),
        "Painted": "Peint",
        "Painted: the soft painted sky. Atmosphere with clouds: a physically based sky with volumetric clouds by day, which costs more on the graphics card. The sun, the shadows and the night are the same in both.": (
            "Peint : le ciel peint et doux. Atmosphère avec nuages : un ciel physiquement "
            "réaliste avec des nuages volumétriques le jour, plus coûteux pour la carte "
            "graphique. Le soleil, les ombres et la nuit sont identiques dans les deux."
        ),
        "Quality:": "Qualité :",
        "Reduce motion in the 3D view": "Réduire les mouvements dans la vue 3D",
        "Sky:": "Ciel :",
        "Ultra": "Ultra",
        "Units": "Unités",
    },
    "BeforeAfterWipe": {
        "Back to 3D View": "Retour à la vue 3D",
        "Close the comparison and show the 3D view (Esc)": (
            "Fermer la comparaison et afficher la vue 3D (Échap)"
        ),
    },
    "BackgroundImageItem": {
        "Failed to encode the background image as PNG": (
            "Échec de l’encodage de l’image de fond en PNG"
        ),
        "Failed to load image from embedded data": (
            "Échec du chargement de l’image depuis les données intégrées"
        ),
        "Failed to load image: {path}": "Échec du chargement de l’image : {path}",
        "This image is {megapixels} megapixels and needs about {megabytes} MB of memory. Background images are limited to {limit} megapixels.": (
            "Cette image fait {megapixels} mégapixels et nécessite environ {megabytes} Mo "
            "de mémoire. Les images de fond sont limitées à {limit} mégapixels."
        ),
    },
    "LiveSunMap": {
        "Hours of Sun could not be computed.": "Les heures de soleil n’ont pas pu être calculées.",
        "Hours of Sun was switched off during export.": (
            "Les heures de soleil ont été désactivées pendant l’exportation."
        ),
        "Set a garden location before computing Hours of Sun.": (
            "Définissez un emplacement pour le jardin avant de calculer les heures de soleil."
        ),
        "Sun map unavailable": "Carte solaire indisponible",
        "Sun-map settings changed during export. Please retry.": (
            "Les réglages de la carte solaire ont changé pendant l’exportation. Veuillez réessayer."
        ),
        "The garden changed during export. Please retry.": (
            "Le jardin a changé pendant l’exportation. Veuillez réessayer."
        ),
        "The garden document was replaced during export.": (
            "Le document du jardin a été remplacé pendant l’exportation."
        ),
        "The garden is closing.": "Le jardin est en cours de fermeture.",
    },
    "SunExportGate": {
        "Cancel": "Annuler",
        "Export canceled.": "Exportation annulée.",
        "Sun-map calculation timed out. Please retry.": (
            "Le calcul de la carte solaire a expiré. Veuillez réessayer."
        ),
        "The garden changed during export. Please retry.": (
            "Le jardin a changé pendant l’exportation. Veuillez réessayer."
        ),
        "Updating Hours of Sun for export…": (
            "Mise à jour des heures de soleil pour l’exportation…"
        ),
    },
    "SunMapLegend": {
        "Hours of sun": "Heures de soleil",
        "Hours of sun · {date}": "Heures de soleil · {date}",
    },
    "SunExposure": {
        "Estimated at soil level, excluding this plant's own shadow; leaf height and canopy translucency are not modelled.": (
            "Estimé au niveau du sol, sans l’ombre de la plante elle-même ; la hauteur des "
            "feuilles et la translucidité de la couronne ne sont pas modélisées."
        ),
    },
    "NorthCompassWidget": {
        "Click or drag to point true north on the plan": (
            "Cliquez ou faites glisser pour indiquer le nord géographique sur le plan"
        ),
        "E": "E",
        "N": "N",
        "S": "S",
        "W": "O",
    },
    "Compass": {
        "E": "E",
        "N": "N",
        "S": "S",
        "W": "O",
    },
    "LocationDialog": {
        "Same as this computer": "Comme cet ordinateur",
        "The garden's time zone. The plan's clock, its sun and a camera tour's time range use it. Leave it on the computer's zone when the garden is where this computer is.": (
            "Fuseau horaire du jardin. L’horloge du plan, son soleil et la plage horaire "
            "d’une visite de caméra l’utilisent. Laissez celui de l’ordinateur lorsque le "
            "jardin se trouve là où se trouve cet ordinateur."
        ),
        "Time zone:": "Fuseau horaire :",
        "Unknown time zone": "Fuseau horaire inconnu",
        "{name} is not a known time zone.": "{name} n’est pas un fuseau horaire connu.",
    },
    "NorthOrientationDialog": {
        "0° points up. The arrow shows where true north lies on the plan; no object is rotated. The sun, shadows, hours of sun and the report's north arrow all follow this angle.": (
            "0° pointe vers le haut. La flèche indique où se trouve le nord géographique "
            "sur le plan ; aucun objet n’est pivoté. Le soleil, les ombres, les heures de "
            "soleil et la flèche du nord du rapport suivent tous cet angle."
        ),
        "North is": "Le nord est à",
        "Set North Orientation": "Définir l’orientation du nord",
        "° clockwise from up": "° dans le sens horaire depuis le haut",
    },
    "DateFormat": {
        "MMM d": "d MMM",
        "d MMM yyyy": "d MMM yyyy",
    },
}
