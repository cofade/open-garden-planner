"""Partition a collected non-perf suite across CI runners without dropping tests (#601).

Load with ``-p scripts.ci_coverage_shard --coverage-shard=0/2``. Every xdist
worker collects the same suite, then selects the same ordered slice. Round-robin
selection distributes expensive parametrized modules across both runners; no
hand-maintained file list or extra dependency is involved. The serial perf step
does not load this plugin.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--coverage-shard", metavar="INDEX/TOTAL", help=__doc__)


def shard_spec(value: str) -> tuple[int, int]:
    """Validate the zero-based slice before running any test."""
    try:
        index, total = (int(part) for part in value.split("/"))
    except ValueError as error:
        raise pytest.UsageError("--coverage-shard needs INDEX/TOTAL") from error
    if not 0 <= index < total:
        raise pytest.UsageError("--coverage-shard needs 0 <= INDEX < TOTAL")
    return index, total


def pytest_configure(config: pytest.Config) -> None:
    value = config.getoption("--coverage-shard")
    if value is not None:
        shard_spec(value)


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    value = config.getoption("--coverage-shard")
    if value is None:
        return
    index, total = shard_spec(value)
    selected = items[index::total]
    if not selected:
        raise pytest.UsageError(f"coverage shard {value} selected no tests")
    deselected = [item for position, item in enumerate(items) if position % total != index]
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected
