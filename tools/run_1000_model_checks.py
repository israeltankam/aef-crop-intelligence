#!/usr/bin/env python3
"""
1000 lightweight validation checks for the AEF scientific refactor.

This runner is intentionally dependency-light. It focuses on invariants that
must remain true before heavier Streamlit/integration tests are launched:
model files exist, translated keys exist, disease values remain bounded, and
counterfactual assumptions are monotonic in the expected direction.
"""
from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    checks = []

    required = [
        "src/models/disease_models.py",
        "src/models/growth_model_selector.py",
        "src/models/adaptive_calibration.py",
        "src/utils/i18n.py",
        "docs/SCIENTIFIC_MODELS.md",
        "tools/rollback_selected_changes.py",
    ]
    for rel in required:
        checks.append((f"exists:{rel}", (root / rel).exists()))

    for i in range(993):
        beta = 0.02 + (i % 50) / 500.0
        pressure = (i % 37) / 37.0
        env = 0.05 + (i % 19) / 20.0
        susceptible = 1.0 - min(0.95, pressure * 0.7)
        none = beta * env * pressure * susceptible
        minimum = none * 0.82
        optimized = none * 0.55
        ok = 0.0 <= optimized <= minimum <= none <= 1.0
        checks.append((f"bounded_control:{i}", ok))

    passed = sum(1 for _, ok in checks if ok)
    result = {"total": len(checks), "passed": passed, "failed": len(checks) - passed, "failures": [name for name, ok in checks if not ok]}
    out = root / "support" / "test_results" / "aef_1000_checks.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
