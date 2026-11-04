"""Theme preference values, independent of rendering and widgets."""

from enum import Enum


class ThemeMode(Enum):
    """Available theme modes."""

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


