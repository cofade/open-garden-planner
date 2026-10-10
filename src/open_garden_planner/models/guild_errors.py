"""Language-independent guild validation errors with English API messages."""

from typing import Any

MESSAGES = {
    "count": "Role minimum must be a positive integer",
    "radius": "Radius must be positive and finite, or canopy_edge",
    "suggestions": "Suggested species must be a list of canonical species keys",
    "object": "Template must be a JSON object",
    "id": "ID must use letters, numbers, dots, underscores or hyphens",
    "version": "Version must be a positive integer",
    "field": "{field} must be a nonempty string",
    "text": "{field} must be text",
    "function": "Unknown function: {function}",
    "missing_field": "Missing template field: {field}",
    "roles": "Roles must be a list",
    "duplicate": "Each function may appear in only one role row",
    "limit": "A guild stamp may contain at most 200 plants, including its centre",
    "sources": "Sources must be a list of references",
    "spacing": "Canopy-edge layout needs mature spacing; choose an explicit radius",
    "name": "A guild needs an instance name",
    "centre": "Choose a plant in the current plan as centre",
    "occupied": "Remove this plant from its current guild before using it as centre",
    "unresolved_centre": "Select a resolved centre species",
    "centre_function": "Centre species does not record the required function",
    "centre_species": "Centre species does not match this template",
    "unresolved": "Unresolved suggested species: choose a replacement",
    "member_function": "Selected member species does not record its required function",
    "layer": "Guild placement needs visible, unlocked target layers",
    "bounds": "Guild layout extends outside the canvas; choose another position or radius",
    "link": "Guild link needs a nonempty guild_id",
    "centre_name": "Guild centre needs an instance name",
    "one_centre": "Guild must have exactly one valid centre",
}


class GuildValidationError(ValueError):
    def __init__(self, code: str, **details: Any) -> None:
        self.code = code
        self.details = details
        super().__init__(MESSAGES[code].format(**details))


def validated_function(value: Any) -> str:
    from open_garden_planner.models.plant_data import PlantFunction

    try:
        return PlantFunction(value).value
    except (TypeError, ValueError) as error:
        raise GuildValidationError("function", function=str(value)) from error
