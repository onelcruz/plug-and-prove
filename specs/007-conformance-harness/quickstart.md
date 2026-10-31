# Quickstart: validating the conformance harness (#7)

## Prerequisites

```bash
pip install -r requirements.txt
```

## 1. Repo gates

```bash
ruff check . && lint-imports && pytest
```

Expected: `All checks passed!`, `Contracts: 2 kept, 0 broken.`, all tests pass.

## 2. Import-boundary probes (create, run, delete; never commit)

| Probe file | Line | Expected `lint-imports` |
|---|---|---|
| `src/conformance/_probe.py` | `from src.simulator.detections import RawDetection` | 2 kept, 0 broken |
| `src/conformance/_probe.py` | `from src.simulator.trajectories import TruthObject` | `no-ground-truth-leak` BROKEN |
| `src/adapters/_probe.py` | `from src.simulator.trajectories import TruthObject` | `no-ground-truth-leak` BROKEN |

## 3. Acceptance scenarios → tests

| Scenario | Test file | Expected |
|---|---|---|
| Sensors 1 & 2 admitted, all 7 PASS, < 60 s (US1, SC-001, SC-005) | `tests/test_conformance_harness.py` | pass; wall-clock asserted < 60 s |
| Clock-offset fixture fails only check 4, blocked (US2, SC-002) | `tests/test_conformance_harness.py` | check 4 FAIL with offset + limit in reason; 1–3, 5–7 PASS |
| Fixed fixture re-submitted → admitted (US2 #3) | `tests/test_conformance_gate.py` | verdict flips; detections released |
| Blocked adapter's detections never reach stub fusion (SC-004) | `tests/test_conformance_gate.py` | stub consumer receives 0 from blocked sensor |
| Pass + fail fixture per check (US3, SC-003) | `tests/test_conformance_checks.py` | 14+ cases |
| Report: 7 rows per adapter, one-line reasons, deterministic (US4, SC-006) | `tests/test_conformance_report.py` | byte-identical across two renders |
| New config validators | `tests/test_config_loader.py` | invalid combos rejected |
