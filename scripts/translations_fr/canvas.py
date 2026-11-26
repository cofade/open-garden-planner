"""French translations for the 2D canvas, constraints and plant panels."""

from __future__ import annotations

TRANSLATIONS: dict[str, dict[str, str]] = {
    "GroupItem": {
        "A constrained member cannot be rotated with the group": "Un membre contraint ne peut pas être tourné avec le groupe",
        "A linked plant belongs to another group; remove it from that group before turning this one": "Une plante liée appartient à un autre groupe ; retirez-la de ce groupe avant de tourner celui-ci",
        "A member on a locked layer cannot be rotated with the group": "Un membre sur un calque verrouillé ne peut pas être tourné avec le groupe",
        "This group has an unsupported transform and cannot be edited": "Ce groupe a une transformation non prise en charge et ne peut pas être modifié",
    },
    "CanvasView": {
        "Rotate the group back to 0° before ungrouping": "Ramenez le groupe à 0° avant de dissocier",
        "This group has an unsupported transform and cannot be edited": "Ce groupe a une transformation non prise en charge et ne peut pas être modifié",
        "A constrained member or group cannot be moved while drilled down": (
            "Un membre ou un groupe contraint ne peut pas être déplacé pendant l’exploration"
        ),
        "A constrained shape cannot be split": "Une forme contrainte ne peut pas être divisée",
        "All shapes must be on the same layer": (
            "Toutes les formes doivent être sur le même calque"
        ),
        "Boolean operations refuse plants, linked objects, constraints, and locked layers": (
            "Les opérations booléennes refusent les plantes, les objets liés, les "
            "contraintes et les calques verrouillés"
        ),
        "Click the first point of the cutting line. Esc cancels.": (
            "Cliquez sur le premier point de la ligne de coupe. Échap annule."
        ),
        "Created a parallel line at {dist}": "Ligne parallèle créée à {dist}",
        "Created {dir} offset of {dist}": "Décalage {dir} de {dist} créé",
        "Distance, e.g. 12' 6\"": "Distance, par ex. 12' 6\"",
        "Garden Light": "Lanterne de jardin",
        "Invalid distance. Enter a length such as 12' 6\" or 150 in.": (
            "Distance invalide. Saisissez une longueur telle que 12' 6\" ou 150 in."
        ),
        "N": "N",
        "Only closed shapes (polygon, rectangle, circle, or ellipse) can be split": (
            "Seules les formes fermées (polygone, rectangle, cercle ou ellipse) peuvent être divisées"
        ),
        "Plants and linked objects cannot be split": (
            "Les plantes et les objets liés ne peuvent pas être divisés"
        ),
        "Press Esc to leave the group before cutting or deleting one of its members": (
            "Appuyez sur Échap pour quitter le groupe avant de couper ou de supprimer l’un "
            "de ses membres"
        ),
        "Select at least two shapes (intersection and subtraction need exactly two)": (
            "Sélectionnez au moins deux formes (l’intersection et la soustraction en "
            "exigent exactement deux)"
        ),
        "Shapes must overlap for this operation": (
            "Les formes doivent se chevaucher pour cette opération"
        ),
        "Shapes must touch or overlap": "Les formes doivent se toucher ou se chevaucher",
        "String Lights": "Guirlande lumineuse",
        "The merged outline would contain a hole; keep the shapes separate": (
            "Le contour fusionné contiendrait un trou ; gardez les formes séparées"
        ),
        "The result would have {count} vertices; the plan supports at most {limit}. Keep the shapes separate.": (
            "Le résultat aurait {count} sommets ; le plan en accepte au maximum {limit}. "
            "Gardez les formes séparées."
        ),
        "The roof ridge is on a locked layer": "Le faîtage se trouve sur un calque verrouillé",
        "The shape carries links that a split cannot preserve": (
            "La forme porte des liens qu’une division ne peut pas conserver"
        ),
        "The shape has tracking records that a split cannot preserve": (
            "La forme possède des enregistrements de suivi qu’une division ne peut pas conserver"
        ),
        "The shape is no longer in this plan": "La forme ne fait plus partie de ce plan",
        "The shape is on a locked layer": "La forme se trouve sur un calque verrouillé",
        "The shapes contain different data; keep them separate or make their data consistent": (
            "Les formes contiennent des données différentes ; gardez-les séparées ou "
            "harmonisez leurs données"
        ),
        "This edge length belongs to a rigid shape. Remove the constraint and resize the shape instead.": (
            "Cette longueur de côté appartient à une forme rigide. Retirez la contrainte et "
            "redimensionnez plutôt la forme."
        ),
        "This shape has no closed outline to split": (
            "Cette forme n’a pas de contour fermé à diviser"
        ),
        "This shape type has no polygonal form to split into": (
            "Ce type de forme n’a pas de forme polygonale dans laquelle être divisé"
        ),
        "Ungroup the shape before splitting it": "Dissociez la forme avant de la diviser",
        "Ungroup {n} groups": "Dissocier {n} groupes",
        "Ungrouped {n} groups": "{n} groupes dissociés",
        "{axis} position": "Position {axis}",
    },
    "PlantDatabasePanel": {
        " (ID: {id})": " (ID : {id})",
        "Choose dates between {min} and {max}. Removal must be after planting.": (
            "Choisissez des dates entre {min} et {max}. Le retrait doit suivre la plantation."
        ),
        "Clear": "Effacer",
        "Create Custom": "Créer une plante personnelle",
        "Invalid plant dates": "Dates de plante invalides",
        "Load Custom": "Charger une plante personnelle",
        "No species data.\n\nClick 'Search' to find species online,\nor 'Create Custom' to define your own.": (
            "Aucune donnée d’espèce.\n\nCliquez sur « Rechercher » pour trouver des "
            "espèces en ligne,\nou sur « Créer une plante personnelle » pour définir la vôtre."
        ),
        "Not removed": "Non retirée",
        "Removed on:": "Retirée le :",
    },
    "SoilOverlayLegend": {
        "Fair": "Moyen",
        "Good": "Bon",
        "No soil test": "Aucun test de sol",
        "Poor": "Pauvre",
    },
    "SplitShapeMenu": {
        "Split Along Line…": "Diviser le long d’une ligne…",
    },
    "SplitShapeTool": {
        "A piece would have {count} vertices; the plan supports at most {limit}. Choose a simpler cut.": (
            "Une pièce aurait {count} sommets ; le plan en accepte au maximum {limit}. "
            "Choisissez une coupe plus simple."
        ),
        "Click the first point of the cutting line. Esc cancels.": (
            "Cliquez sur le premier point de la ligne de coupe. Échap annule."
        ),
        "Click the second point of the cutting line; Shift constrains the angle. Esc cancels.": (
            "Cliquez sur le second point de la ligne de coupe ; Maj contraint l’angle. "
            "Échap annule."
        ),
        "Nothing was split: {reason}": "Rien n’a été divisé : {reason}",
        "Split along line": "Diviser le long d’une ligne",
        "Split cancelled": "Division annulée",
        "Split the shape into {count} pieces": "Diviser la forme en {count} pièces",
        "Split {count} shapes": "Diviser {count} formes",
        "Split {shapes} shapes into {pieces} pieces": "Diviser {shapes} formes en {pieces} pièces",
        "The cut would leave a piece too small to keep": (
            "La coupe laisserait une pièce trop petite pour être conservée"
        ),
        "The cutting line must cross a closed shape. Choose another second point.": (
            "La ligne de coupe doit traverser une forme fermée. Choisissez un autre second point."
        ),
        "The shape to split is no longer available.": (
            "La forme à diviser n’est plus disponible."
        ),
        "{message}; 1 crossed object could not be split": (
            "{message} ; 1 objet traversé n’a pas pu être divisé"
        ),
        "{message}; {count} crossed objects could not be split": (
            "{message} ; {count} objets traversés n’ont pas pu être divisés"
        ),
    },
    "SuccessionBadgeItem": {
        "+{count} more": "+{count} de plus",
    },
    "TrimExtendTool": {
        "Cannot trim this object: beds and group members cannot become an open line, and a constrained object must be unconstrained first.": (
            "Impossible de rogner cet objet : les massifs et les membres de groupe ne "
            "peuvent pas devenir une ligne ouverte, et un objet contraint doit d’abord "
            "être libéré de sa contrainte."
        ),
    },
    "ChamferTool": {
        "Cannot edit this corner: a constraint is attached to it or to its edges": (
            "Impossible de modifier ce coin : une contrainte y est attachée ou à ses côtés"
        ),
        "Cannot edit this corner: the object is inside a group": (
            "Impossible de modifier ce coin : l’objet fait partie d’un groupe"
        ),
        "Cannot edit this corner: this object type has no polygonal form": (
            "Impossible de modifier ce coin : ce type d’objet n’a pas de forme polygonale"
        ),
        "Chamfer distance: {distance} — press D to change": (
            "Distance du chanfrein : {distance} — appuyez sur D pour modifier"
        ),
        "Distance:": "Distance :",
    },
    "FilletTool": {
        "Cannot edit this corner: a constraint is attached to it or to its edges": (
            "Impossible de modifier ce coin : une contrainte y est attachée ou à ses côtés"
        ),
        "Cannot edit this corner: the object is inside a group": (
            "Impossible de modifier ce coin : l’objet fait partie d’un groupe"
        ),
        "Cannot edit this corner: this object type has no polygonal form": (
            "Impossible de modifier ce coin : ce type d’objet n’a pas de forme polygonale"
        ),
        "Fillet radius: {radius} — press R to change": (
            "Rayon du congé : {radius} — appuyez sur R pour modifier"
        ),
        "Radius:": "Rayon :",
    },
    "ConstraintListItem": {
        "Edge {d}": "Côté {d}",
        "{a} edge length: {d}": "Longueur du côté {a} : {d}",
        "{a} tangent to {b} (r={d})": "{a} tangent à {b} (r={d})",
        "{a} to {b}: horizontal distance {d}": "{a} à {b} : distance horizontale {d}",
        "{a} to {b}: vertical distance {d}": "{a} à {b} : distance verticale {d}",
        "{a} to {b}: {d}": "{a} à {b} : {d}",
        "{d}": "{d}",
    },
    "ConstraintToolbar": {
        "Chamfer — bevel a corner": "Chanfrein — biseauter un coin",
        "Fillet — round a corner": "Congé — arrondir un coin",
        "Mirror — reflect selection across an axis": (
            "Symétrie — refléter la sélection selon un axe"
        ),
        "Offset — parallel copy or parallel line": (
            "Décalage — copie parallèle ou ligne parallèle"
        ),
        "Split along line — cut the eligible closed shapes a two-point line crosses": (
            "Diviser le long d’une ligne — couper les formes fermées éligibles traversées "
            "par une ligne à deux points"
        ),
        "Trim/Extend — X toggles mode": "Rogner / Prolonger — X bascule le mode",
    },
    "ConstraintTools": {
        "Constraint cannot be applied": "La contrainte ne peut pas être appliquée",
        "The selected edges cannot be aligned without changing a locked object or an existing orientation constraint. Unlock an object or remove the conflicting constraint first.": (
            "Les côtés sélectionnés ne peuvent pas être alignés sans modifier un objet "
            "verrouillé ou une contrainte d’orientation existante. Déverrouillez un objet "
            "ou retirez d’abord la contrainte en conflit."
        ),
    },
    "DistanceInputDialog": {
        "Current distance: {distance}": "Distance actuelle : {distance}",
        "Enter the target distance:": "Saisissez la distance cible :",
    },
    "HDistanceInputDialog": {
        "Current horizontal distance: {distance}": "Distance horizontale actuelle : {distance}",
        "Enter the target horizontal distance:": (
            "Saisissez la distance horizontale cible :"
        ),
    },
    "VDistanceInputDialog": {
        "Current vertical distance: {distance}": "Distance verticale actuelle : {distance}",
        "Enter the target vertical distance:": "Saisissez la distance verticale cible :",
    },
    "HorizontalDistanceConstraintTool": {
        "↔ {d}": "↔ {d}",
    },
    "VerticalDistanceConstraintTool": {
        "↕ {d}": "↕ {d}",
    },
    "RadiusEditor": {
        "Distance": "Distance",
    },
}
