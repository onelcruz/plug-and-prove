# Plug-and-Prove

A sensor-agnostic C-UAS (counter-drone) integration demo: new sensors plug in through a
documented adapter contract, get automatically verified by a conformance harness, and
visibly improve a fused, explainable air picture on a TAK map — all offline, on simulated
data. See [`docs/architecture.md`](docs/architecture.md) for the full system design.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running tests

```bash
pytest
```

## Linting

```bash
ruff check .
```

## Project layout

See [`docs/architecture.md`](docs/architecture.md) §2 for the full package layout and
component responsibilities. In short:

- `config/` — scenario and sensor YAML configuration.
- `src/` — all source code, one package per architecture component (`simulator/`,
  `adapters/`, `conformance/`, `fusion/`, `classification/`, `recommendation/`,
  `output/`, `recordkeeping/`), plus `config/` for the shared config loader and
  `orchestrator.py` tying everything together.
- `tests/` — tests mirroring the `src/` layout.
- `runs/` — generated test-record files from demo runs.

## Project tracking

Work is tracked as an epic ([#1](https://github.com/onelcruz/plug-and-prove/issues/1)) with
dependency-ordered sub-issues. See `.specify/memory/constitution.md` for project principles
and `.github/copilot-instructions.md` for agent operating instructions.
