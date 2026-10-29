## How to instrument

### 1. Identify the execution spine

Map the path from trigger to outcome. For every node on that path add a `print`:

```
trigger → A() → B() → [condition] → C()  ← expected
                               ↘ D()      ← what actually happens?
```

### 2. What to print at each node

| Node type | Print |
|-----------|-------|
| Entry to function | function name + key arguments + `type(self).__name__` |
| State that the condition reads | the exact values used in the `if` |
| Timestamps for time-based guards | `time.monotonic()` before AND inside the guard |
| Focus / visibility / flag checks | `hasFocus()`, `isVisible()`, `flags()` |
| Async callbacks (timers, slots) | "fired" + whether preconditions hold |
| Exit paths | which branch was taken, what was returned |
| Unexpected call sites | `traceback.format_stack()[:-1]` — always include this for "who called me?" questions |

### 3. Use `print`, not `logging`

`logging` requires configuration. `print` goes to stdout unconditionally — exactly what you need when the app is run from a terminal.

### 4. Prefix every line

Use a consistent tag like `[MODULE]` so output is grep-able and doesn't get lost in Qt warnings:

```python
print(f"[LABEL] focusOutEvent: elapsed={elapsed:.4f}s  isVisible={self.isVisible()}")
```

### 5. Include call stacks at "unexpected" sites

Any function that should only be called from specific places should print its caller when debugging:

```python
import traceback
for line in traceback.format_stack()[:-1]:
    print(f"[TAG]   {line.strip()}")
```

This is what revealed the minimap as the culprit below.

---

