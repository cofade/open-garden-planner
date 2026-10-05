"""Shared ``AgentProviders`` stubs for the US-D3.3 / US-D3.4 task and soil tools.

Nine integration suites each build their own ``AgentProviders`` bundle of stubs,
and US-D3.3/D3.4 added NINE more provider fields. Spelling all nine out in every
suite would be nine copies of one list, and the copies would drift the moment a
tenth tool landed — which is precisely the failure this module exists to prevent.

So the nine live here once, and every suite spreads ``**TASK_SOIL_STUBS`` into
its constructor call. Two things keep that honest:

* ``AgentProviders`` is a frozen dataclass with NO defaults, so a field added
  without a stub raises ``TypeError`` at construction. That is the drift guard,
  and it is why these fields are required rather than defaulted — a default
  would let a suite silently pass with no wiring at all, which is the #291
  shape (a subsystem dead while the process is alive).
* :func:`assert_stub_coverage` states the expectation outright, so the failure
  names the missing tool instead of pointing at a constructor call nine suites
  away.

These are stubs: they return empty-but-valid dicts. The real behaviour is
exercised by ``test_agent_domain_tools.py``, which drives the domain functions
directly, and by the live-client dogfood run.
"""

from __future__ import annotations

from typing import Any

from open_garden_planner.agent_api.providers import AgentProviders

#: The provider fields US-D3.3 and US-D3.4 added, in dataclass order.
TASK_SOIL_PROVIDER_NAMES: tuple[str, ...] = (
    "get_tasks",
    "get_task_calendar",
    "add_manual_task",
    "edit_manual_task",
    "delete_manual_task",
    "get_soil_status",
    "recommend_amendments",
    "get_soil_mismatches",
    "record_soil_test",
)

def _inert(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """A provider that accepts anything and does nothing.

    One shared callable rather than nine ``lambda *a, **k: {}`` entries: the
    stubs are inert by design, and nine identical lambdas would be nine places
    for a future edit to diverge — plus ``lambda *a, **k`` trips ruff's ARG005
    for every unused argument, sixteen findings for what is one function.
    """
    return {}


#: Keyword arguments to spread into an ``AgentProviders(...)`` call.
#:
#: ``_inert`` rather than explicit signatures on purpose: these are placeholders
#: in suites that exercise OTHER tools. The Protocol-typed fields
#: (``add_manual_task``, ``edit_manual_task``, ``record_soil_test``) are still
#: declared with their real signatures in ``providers.py`` — a Protocol is a
#: static contract, not something a stub satisfies at runtime.
TASK_SOIL_STUBS: dict[str, Any] = dict.fromkeys(("get_tasks", "get_task_calendar", "add_manual_task", "edit_manual_task", "delete_manual_task", "get_soil_status", "recommend_amendments", "get_soil_mismatches", "record_soil_test"), _inert)


def assert_stub_coverage() -> None:
    """Fail loudly if the stub set and the dataclass disagree.

    Called by the drift-guard test in ``test_agent_domain_tools.py``. Two
    directions matter and neither is automatic:

    * a stub name that is no longer a field means the module is stale;
    * a field this module was meant to cover but does not means a suite is about
      to fail with a ``TypeError`` nine files away from the cause.
    """
    fields = set(AgentProviders.__dataclass_fields__)
    stubs = set(TASK_SOIL_STUBS)
    assert stubs == set(TASK_SOIL_PROVIDER_NAMES), (
        "TASK_SOIL_STUBS and TASK_SOIL_PROVIDER_NAMES disagree: "
        f"{stubs ^ set(TASK_SOIL_PROVIDER_NAMES)}"
    )
    assert stubs <= fields, (
        "stub names are not AgentProviders fields any more: "
        f"{sorted(stubs - fields)}"
    )
