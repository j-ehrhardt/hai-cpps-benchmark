# Agent guide

This repository is the source generator for HAI-CPPS v2.2. Read `README.md` for installation and the three user workflows.

## Supported commands

- `python code/campaign.py --jobs 4`: all ten benchmark datasets, 350 recordings.
- `python code/campaign.py --dataset ds1 --jobs 4`: one complete benchmark dataset.
- `python code/simulate.py --config examples/custom.json --dataset custom1`: one raw simulation with a user topology or module.

Use `--plan` on the campaign command for a read-only inventory. A campaign can be resumed with the same command and unchanged source/configuration. The raw simulation command requires a fresh output directory for each run.

## Code map

- `models/*.mo`: validated physical and controller models. Preserve their equations and fault behavior unless the user explicitly requests and verifies a physics change.
- `code/benchmark_setup.json`: canonical ds1–ds10 topology, timing, and fault inventory.
- `code/config.py` and `code/schemas/benchmark_setup.schema.json`: config normalization, module and port validation, run specifications.
- `code/model_generation.py` and `code/runner.py`: generated plant and `.mos` files, isolated OpenModelica execution, raw-result checks. Benchmark simulations load MSL 4.0.0.
- `code/campaign_plan.py` and `code/campaign.py`: v2.2 scenario planning, healthy-control dependencies, parallel scheduling, and per-dataset manifests.
- `code/sim.py`, `code/export.py`, `code/diagnosis_export.py`, `code/dataset_metadata.py`, `code/validation.py`, and `code/actuator_channels.py`: established benchmark export and validation path. The campaign calls this path; the custom raw command does not.
- `code/campaign_check.py`: complete campaign artifact checks.
- `examples/`: a runnable custom topology and its extra Modelica module.

## Working rules

- Keep benchmark scenario counts, seeds, fault windows, and Modelica sources stable when changing launch code. The full v2.2 plan is 160 healthy plus 190 fault recordings.
- For a new custom module, declare `type: custom`, `modelica_class`, `input_ports`, `output_ports`, `files`, and empty `faults` in its JSON config. The module must have a replaceable `Medium` package. `code/simulate.py` exports a raw CSV with all Modelica variables.
- Treat `build/`, `output/`, `.venv/`, cache directories, and `data/` as generated or local artifacts. Do not commit them. Inspect an existing output before replacing it.
- After launcher changes, run `python code/campaign.py --plan`, `python code/campaign.py --dataset ds1 --plan`, and `python -m pytest -q`. If OpenModelica is installed, run the small custom example as a smoke test in a fresh output directory.
