"""US-E5 3D engine spike package (#260) — EVIDENCE, NOT PRODUCTION.

Nothing here is imported at app startup: ``main.py`` imports
``qt3d_spike`` only when ``--spike-3d`` is on the command line. The spike
exists to answer ADR-038's GO/NO-GO with machine-checkable artifacts
(a screenshot + exit code from the FROZEN exe). US-E6 starts clean — this
package is deleted or superseded when the production 3D view lands.
"""
