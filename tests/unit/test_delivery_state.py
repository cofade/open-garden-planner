"""Refuse stale, non-draft, stacked or incomplete package handoffs."""

import pytest
from scripts.check_delivery_state import validate


@pytest.mark.parametrize("change", [
    {"isDraft": False}, {"headRefOid": "old"}, {"headRefName": "master"},
    {"baseRefName": "feature/parent"}, {"closingIssuesReferences": []},
])
def test_refuses_invalid_handoff(change):
    data = {"isDraft": True, "headRefName": "feature/audit", "headRefOid": "new",
            "baseRefName": "master", "closingIssuesReferences": [{"number": 456}]}
    assert validate({**data, **change}, "new", {456})
    assert validate(data, "new", {456}) == []
