## Case study: frozen self-test kept the pre-layer provider contract (D2.4/D2.5, fixed 2026-09-06)

**Symptom**: The full test suite had one failure in `test_main_hardening.py`: the Qt3D checks passed, but the embedded Agent API self-test returned 1 with `AgentProviders.__init__()` missing the six layer providers.

**Wrong theories**: The failure initially looked like an Agent API server or PyInstaller regression because it occurred in the self-test that protects the frozen executable.

**Key evidence**: The captured self-test output named the exact constructor error before the server could start; the application startup path already supplied all six new layer callables by keyword.

**Root cause**: D2.4 added required layer providers to the shared `AgentProviders` dataclass, but the independent `_run_selftest()` probe in `main.py` still instantiated the old contract.

**Fix**: Update the self-test probe with no-op callables for every provider, preserving its rule that no provider may be invoked. The existing self-test then covers constructor completeness and server startup together.

**Lesson**: When extending an injected provider contract, search for every constructor—not only production wiring and tests. Keep the frozen self-test's no-op provider fixture aligned so it remains a whole-contract smoke test.

