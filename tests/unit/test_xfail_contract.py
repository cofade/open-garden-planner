"""Expected defects must not absorb pytest-timeout's Failed exception (#921)."""


def test_expected_failures_do_not_mask_pytest_timeouts(request):
    unbounded = [
        item.nodeid
        for item in request.session.items
        for marker in item.iter_markers("xfail")
        if marker.kwargs.get("raises") is not AssertionError
    ]
    assert not unbounded, f"Restrict expected defects to AssertionError, leaving timeouts fatal: {unbounded}"
