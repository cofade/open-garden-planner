"""Lazy public compatibility exports (audit A4)."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from open_garden_planner.core.commands import (
        AddConstraintCommand,
        AddHarvestRecordCommand,
        AddJournalNoteCommand,
        AddPestLogCommand,
        AddSoilTestCommand,
        AlignItemsCommand,
        ArrayAlongPathCommand,
        BooleanShapeCommand,
        CircularArrayCommand,
        Command,
        CommandManager,
        CreateItemCommand,
        CreateItemsCommand,
        DeleteHarvestRecordCommand,
        DeleteItemsCommand,
        DeleteJournalNoteCommand,
        DeletePestLogCommand,
        DeleteSoilTestCommand,
        EditConstraintDistanceCommand,
        EditHarvestRecordCommand,
        EditJournalNoteCommand,
        EditPestLogCommand,
        EditSoilTestCommand,
        GridArrayCommand,
        LinearArrayCommand,
        MirrorItemsCommand,
        MoveItemsCommand,
        RemoveConstraintCommand,
        SetParentBedCommand,
        SetSuccessionPlanCommand,
    )
    from open_garden_planner.core.measurements import (
        calculate_area_and_perimeter,
        format_area,
        format_length,
    )
    from open_garden_planner.core.project import (
        ProjectData,
        ProjectManager,
    )

    __all__ = [
        "AddConstraintCommand",
        "AddHarvestRecordCommand",
        "AddJournalNoteCommand",
        "AddPestLogCommand",
        "AddSoilTestCommand",
        "AlignItemsCommand",
        "ArrayAlongPathCommand",
        "BooleanShapeCommand",
        "CircularArrayCommand",
        "Command",
        "CommandManager",
        "CreateItemCommand",
        "CreateItemsCommand",
        "DeleteItemsCommand",
        "DeleteHarvestRecordCommand",
        "DeleteJournalNoteCommand",
        "DeletePestLogCommand",
        "DeleteSoilTestCommand",
        "EditConstraintDistanceCommand",
        "EditHarvestRecordCommand",
        "EditJournalNoteCommand",
        "EditPestLogCommand",
        "EditSoilTestCommand",
        "GridArrayCommand",
        "LinearArrayCommand",
        "MirrorItemsCommand",
        "MoveItemsCommand",
        "RemoveConstraintCommand",
        "SetParentBedCommand",
        "SetSuccessionPlanCommand",
        "ProjectData",
        "ProjectManager",
        "calculate_area_and_perimeter",
        "format_area",
        "format_length",
    ]

_EXPORTS = {
    "AddConstraintCommand": ("open_garden_planner.core.commands", "AddConstraintCommand"),
    "AddHarvestRecordCommand": ("open_garden_planner.core.commands", "AddHarvestRecordCommand"),
    "AddJournalNoteCommand": ("open_garden_planner.core.commands", "AddJournalNoteCommand"),
    "AddPestLogCommand": ("open_garden_planner.core.commands", "AddPestLogCommand"),
    "AddSoilTestCommand": ("open_garden_planner.core.commands", "AddSoilTestCommand"),
    "AlignItemsCommand": ("open_garden_planner.core.commands", "AlignItemsCommand"),
    "ArrayAlongPathCommand": ("open_garden_planner.core.commands", "ArrayAlongPathCommand"),
    "BooleanShapeCommand": ("open_garden_planner.core.commands", "BooleanShapeCommand"),
    "CircularArrayCommand": ("open_garden_planner.core.commands", "CircularArrayCommand"),
    "Command": ("open_garden_planner.core.commands", "Command"),
    "CommandManager": ("open_garden_planner.core.commands", "CommandManager"),
    "CreateItemCommand": ("open_garden_planner.core.commands", "CreateItemCommand"),
    "CreateItemsCommand": ("open_garden_planner.core.commands", "CreateItemsCommand"),
    "DeleteHarvestRecordCommand": (
        "open_garden_planner.core.commands",
        "DeleteHarvestRecordCommand",
    ),
    "DeleteItemsCommand": ("open_garden_planner.core.commands", "DeleteItemsCommand"),
    "DeleteJournalNoteCommand": ("open_garden_planner.core.commands", "DeleteJournalNoteCommand"),
    "DeletePestLogCommand": ("open_garden_planner.core.commands", "DeletePestLogCommand"),
    "DeleteSoilTestCommand": ("open_garden_planner.core.commands", "DeleteSoilTestCommand"),
    "EditConstraintDistanceCommand": (
        "open_garden_planner.core.commands",
        "EditConstraintDistanceCommand",
    ),
    "EditHarvestRecordCommand": ("open_garden_planner.core.commands", "EditHarvestRecordCommand"),
    "EditJournalNoteCommand": ("open_garden_planner.core.commands", "EditJournalNoteCommand"),
    "EditPestLogCommand": ("open_garden_planner.core.commands", "EditPestLogCommand"),
    "EditSoilTestCommand": ("open_garden_planner.core.commands", "EditSoilTestCommand"),
    "GridArrayCommand": ("open_garden_planner.core.commands", "GridArrayCommand"),
    "LinearArrayCommand": ("open_garden_planner.core.commands", "LinearArrayCommand"),
    "MirrorItemsCommand": ("open_garden_planner.core.commands", "MirrorItemsCommand"),
    "MoveItemsCommand": ("open_garden_planner.core.commands", "MoveItemsCommand"),
    "RemoveConstraintCommand": ("open_garden_planner.core.commands", "RemoveConstraintCommand"),
    "SetParentBedCommand": ("open_garden_planner.core.commands", "SetParentBedCommand"),
    "SetSuccessionPlanCommand": ("open_garden_planner.core.commands", "SetSuccessionPlanCommand"),
    "calculate_area_and_perimeter": (
        "open_garden_planner.core.measurements",
        "calculate_area_and_perimeter",
    ),
    "format_area": ("open_garden_planner.core.measurements", "format_area"),
    "format_length": ("open_garden_planner.core.measurements", "format_length"),
    "ProjectData": ("open_garden_planner.core.project", "ProjectData"),
    "ProjectManager": ("open_garden_planner.core.project", "ProjectManager"),
}

__all__ = [
    "AddConstraintCommand",
    "AddHarvestRecordCommand",
    "AddJournalNoteCommand",
    "AddPestLogCommand",
    "AddSoilTestCommand",
    "AlignItemsCommand",
    "ArrayAlongPathCommand",
    "BooleanShapeCommand",
    "CircularArrayCommand",
    "Command",
    "CommandManager",
    "CreateItemCommand",
    "CreateItemsCommand",
    "DeleteItemsCommand",
    "DeleteHarvestRecordCommand",
    "DeleteJournalNoteCommand",
    "DeletePestLogCommand",
    "DeleteSoilTestCommand",
    "EditConstraintDistanceCommand",
    "EditHarvestRecordCommand",
    "EditJournalNoteCommand",
    "EditPestLogCommand",
    "EditSoilTestCommand",
    "GridArrayCommand",
    "LinearArrayCommand",
    "MirrorItemsCommand",
    "MoveItemsCommand",
    "RemoveConstraintCommand",
    "SetParentBedCommand",
    "SetSuccessionPlanCommand",
    "ProjectData",
    "ProjectManager",
    "calculate_area_and_perimeter",
    "format_area",
    "format_length",
]


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
