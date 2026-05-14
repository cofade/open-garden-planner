"""Side panel components (properties, layers, constraints, journal, etc.).

The object gallery now lives in the top toolbar
(open_garden_planner.ui.widgets.toolbar) as category dropdowns + global
search, so it is no longer exported here.
"""

from .companion_panel import CompanionPanel
from .constraints_panel import ConstraintsPanel
from .crop_rotation_panel import CropRotationPanel
from .journal_panel import JournalPanel
from .layers_panel import LayersPanel
from .pest_overview_panel import PestOverviewPanel
from .plant_database_panel import PlantDatabasePanel
from .plant_search_panel import PlantSearchPanel
from .properties_panel import PropertiesPanel

__all__ = [
    "CompanionPanel",
    "ConstraintsPanel",
    "CropRotationPanel",
    "JournalPanel",
    "LayersPanel",
    "PestOverviewPanel",
    "PlantDatabasePanel",
    "PlantSearchPanel",
    "PropertiesPanel",
]
