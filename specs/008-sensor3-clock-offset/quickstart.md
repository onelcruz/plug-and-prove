# Quickstart: validate sensor 3's fail → fix → pass

Prerequisites: repo root, dependencies from `requirements.txt` installed.

1. Lint and import contracts:
   ```bash
   ruff check . && lint-imports
   ```
   Expected: `All checks passed!`; `Contracts: 2 kept, 0 broken.`

2. Sensor 3's tests:
   ```bash
   python -m pytest tests/test_sensor3.py -v
   ```
   Expected: all pass. They cover the config (FR-002), the guard (FR-004/FR-008), buggy →
   BLOCKED by check 4 only, fixed → ADMITTED, fail → fix → pass on one gate (FR-007), the
   unmodified scenario (SC-004), and sensors 1 and 2 unchanged (SC-005).

3. Full suite, timed (SC-003: ≤ 60 s):
   ```bash
   time python -m pytest
   ```

4. Manual demo beat (optional, in a Python shell):
   ```python
   from src.adapters import sensor1, sensor2, sensor3
   from src.config.loader import load_scenario_config
   from src.conformance.gate import ConformanceGate
   from src.simulator.scenario import run_simulation
   scenario = load_scenario_config("config/scenarios/example_scenario.yaml")
   sensors = [sensor1.sensor_config, sensor2.sensor_config, sensor3.sensor_config]
   raw = run_simulation(scenario, sensors).detections_by_sensor["sensor-3"]
   gate = ConformanceGate()
   gate.submit(sensor3.translate_with_clock_bug, sensor3.sensor_config, scenario, raw)  # BLOCKED: check 4
   gate.submit(sensor3.translate, sensor3.sensor_config, scenario, raw)                 # ADMITTED: 7/7
   ```
   For the expected verdicts and reasons, see [contracts/sensor3-adapter.md](./contracts/sensor3-adapter.md).
