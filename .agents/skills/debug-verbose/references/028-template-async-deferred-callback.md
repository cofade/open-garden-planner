## Template — async/deferred callback

```python
def _deferred_action():
    import time
    print(f"[TAG] _deferred_action fired — isVisible={item.isVisible()}  hasFocus={item.hasFocus()}")
    if not item.isVisible():
        print("[TAG] ABORT — item hidden before callback ran")
        return
    item.do_thing()
    print(f"[TAG] after do_thing — hasFocus={item.hasFocus()}")

QTimer.singleShot(0, _deferred_action)
```

---

