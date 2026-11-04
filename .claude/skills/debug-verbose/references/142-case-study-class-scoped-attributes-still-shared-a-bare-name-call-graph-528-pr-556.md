## Case study: class-scoped attributes still shared a bare-name call graph (#528, PR #556)

**Symptom.** The perf-marker guard still flagged the ordinary ground-bake edit
session when its timed helper was restored to the same module.
**Wrong theory.** Class-scoped attribute identities were assumed to resolve the
method collision. The initial regression separated modules and asserted equality,
so it never reached the original false positive.
**Evidence.** An isolated instrumented AST probe printed `[PERF-528] clock closure:
['bake', 'test_session']` and `verdict: [('test_session', False)]` for an ordinary
baker and a tile-count bound. The unexpected sensitivity trace included
traceback.format_stack(). Both same-module class orders and the real ground-bake
AST replay failed first.
**Root cause/fix.** The function index and both propagation closures used bare names,
while attributes had qualified identities. One cached lexical index now retains class
and enclosing-function ownership throughout; unresolved receivers do not borrow another
class's method. The real G3 duration stays detected and the ordinary session stays unmarked.
**Lesson.** Reproduce the original module placement and assertion shape. A documented
limitation does not satisfy an issue whose acceptance requires that limitation removed.
Pins: test_same_module_bakers_keep_their_own_clock_sensitivity,
test_duplicate_methods_keep_both_call_graph_closures_scoped,
test_nested_helpers_with_the_same_name_do_not_share_a_clock, and
test_the_original_ground_bake_module_accepts_its_timed_helper_inline in
tests/unit/test_perf_marker_guard.py. Temporary probes are absent from committed code.


