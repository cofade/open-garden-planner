"""Protocols and typing contracts for the 3D workspace (Phase 17 L2, issue #583).

Defines the interfaces for:
- 2D analysis sources connected to the 3D workspace (shadow controller, heatmap controller,
  hours of sun).
- The 3D engine host and sink.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QWidget

from open_garden_planner.core.scene3d.sink import EngineSink

__all__ = [
    "EngineHost",
    "EngineSink",
    "HeatmapSource",
    "ShadowsSource",
    "SunHoursSource",
]


@runtime_checkable
class EngineHost(Protocol):
    """What the workspace requires from the 3D engine host."""

    def container(self, parent: QWidget | None = None) -> QWidget: ...
    def install_event_filter(self, watcher: QObject) -> None: ...
    def focus(self) -> None: ...
    def has_focus(self) -> bool: ...
    def release_cached_resources(self) -> None: ...
    def set_camera(
        self,
        eye_scene: tuple[float, float, float],
        target_scene: tuple[float, float, float],
        fov_deg: float = ...,
    ) -> None: ...
    def view_size(self) -> tuple[float, float]: ...
    def health(self) -> Any: ...
    def close(self) -> None: ...
    def set_look(self, look: Any) -> None: ...
    def set_sky(self, sky: Any) -> None: ...
    def set_wind_running(self, running: bool) -> None: ...
    def rest_wind(self) -> None: ...
    def set_overlay(self, layer: str, mesh: Any) -> None: ...
    def set_roofs_hidden(self, hidden: bool) -> None: ...
    def set_faded_items(self, item_ids: frozenset[str], opacity: float = ...) -> None: ...


@runtime_checkable
class ShadowsSource(Protocol):
    """The 2D shadow overlay controller that supplies shadow polygons for 3D drapes."""

    shadows_changed: Any

    def drape_polygons(self) -> Sequence[Sequence[tuple[float, float]]]: ...


@runtime_checkable
class HeatmapSource(Protocol):
    """The 2D heatmap controller that supplies solar analysis maps for 3D drapes."""

    computed: Any

    def result(self) -> Any: ...


@runtime_checkable
class SunHoursSource(Protocol):
    """The shared Hours of Sun controller (LiveSunMap)."""

    enabled: bool
    enabled_changed: Any

    def set_enabled(self, enabled: bool) -> None: ...
    def is_current(self) -> bool: ...

