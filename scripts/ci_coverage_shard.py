"""Partition a collected non-perf suite across CI runners without dropping tests (#601).

Load with ``-p scripts.ci_coverage_shard --coverage-shard=0/2``. Every xdist
worker selects the same stable hash partition of test IDs. Collection order and
Python's randomized hash seed cannot change membership across runners. No
hand-maintained file list or extra dependency is involved. The serial perf step
does not load this plugin.
"""

from __future__ import annotations

from hashlib import sha256

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


def shard_of(node_id: str, total: int) -> int:
    return int.from_bytes(sha256(node_id.encode("utf-8")).digest()[:8], "big") % total


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
    selected, deselected = [], []
    for item in items:
        (selected if shard_of(item.nodeid, total) == index else deselected).append(item)
    if not selected:
        raise pytest.UsageError(f"coverage shard {value} selected no tests")
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected
