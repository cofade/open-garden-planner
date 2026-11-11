"""The one row text for a generated task (#856).

The Today dashboard (``planting_calendar_view``) and the Tasks tab used to
render the same task differently: the dashboard said "Harvest Rosemary" through
its templates, the Tasks tab showed only "Rosemary". Both now ask this module,
so a new task type or a translation change cannot reach one surface and miss
the other.
"""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication

#: Task types whose title is a bare plant name and need their verb. Every other
#: type (succession, soil, manual) carries a complete label in ``title``.
_VERB_TEMPLATES = {
    "indoor_sow": "Start indoor sowing of %1",
    "direct_sow": "Direct sow %1",
    "transplant": "Transplant %1 outdoors",
    "harvest": "Harvest %1",
    "prick_out": "Prick out %1 seedlings",
    "harden_off": "Start hardening off %1",
}


def task_row_text(task_type: str, name: str) -> str:
    """A task's row text: the verb template for a plant task, else *name*."""
    template = _VERB_TEMPLATES.get(task_type)
    if template is None:
        return name
    return QCoreApplication.translate("TaskText", template).replace("%1", name)
