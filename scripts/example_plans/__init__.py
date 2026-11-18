"""The bundled example plans: one module per plan, shared building blocks beside them.

A plan module has a ``SLUG``, the sidecar's ``META`` and ``build()``, which returns the
authored ``(scene, manager)``. ``scripts/generate_examples.py`` turns that into the files
that ship.
"""

from __future__ import annotations

from . import allotment, balcony, cottage_garden, family_garden, food_forest, raised_bed

PLANS = {plan.SLUG: plan for plan in (food_forest, raised_bed, balcony, family_garden,
                                         allotment, cottage_garden)}
