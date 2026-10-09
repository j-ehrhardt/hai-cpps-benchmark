# Agent guide

This repository generates HAI-CPPS v2.2. Read `README.md` for installation and the supported campaign and custom simulation commands.

## Supported commands

- `python code/campaign.py --jobs 4`: all ten benchmark datasets, 350 recordings.
- `python code/campaign.py --dataset ds1 --jobs 4`: one complete benchmark dataset.
- `python code/simulate.py --config examples/custom.json --dataset custom1`: one raw simulation with a user topology or module.

Use `--plan` on the campaign command for a read-only inventory. A campaign can be resumed with the same command and unchanged source/configuration. The raw simulation command requires a fresh output directory for each run.

## Code map

- `models/*.mo`: physical and controller models. Valves in the four built-in process modules use 0.1-second ramps for a full opening or closing. The distillation leak fault additionally has a 10-second onset ramp. Preserve equations and fault behavior unless the task calls for a model change.
- `code/benchmark_setup.json`: canonical ds1–ds10 topology, timing, and fault inventory.
- `code/config.py` and `code/schemas/benchmark_setup.schema.json`: config normalization, module and port validation, run specifications.
- `code/model_generation.py` and `code/runner.py`: generated plant and `.mos` files, isolated OpenModelica execution, raw-result checks. Benchmark simulations load MSL 4.0.0.
- `code/campaign_plan.py` and `code/campaign.py`: v2.2 scenario planning, healthy-control dependencies, parallel scheduling, source snapshots, and per-dataset manifests.
- `code/sim.py`, `code/export.py`, `code/diagnosis_export.py`, `code/dataset_metadata.py`, `code/validation.py`, and `code/actuator_channels.py`: established benchmark export and validation path. The campaign calls this path; the custom raw command does not.
- `code/campaign_check.py`: complete campaign artifact checks.
- `code/dataset_io.py`: read-only access to generated datasets. `Dockerfile` and `requirements.txt` define the container and Python dependencies.
- `examples/`: a runnable custom topology and its extra Modelica module.

## Working rules

- Keep benchmark scenario counts, seeds, fault windows, and Modelica sources stable when changing launch code. The full plan is 160 healthy plus 190 fault recordings: 10/3/2/1 healthy recordings per topology in train/validation/calibration/test, 95 single faults with persistent and temporal variants, healthy seed allocation starting at 20261005, paired-control and fault seed 42, fault onset 2500, and temporal fault end 7500.
- `code/actuator_channels.py` pins the four built-in `.mo` files by SHA-256. After an intentional model edit, update those hashes and review command reconstruction, export, and validation assumptions. Check the valve and leak ramp behavior if their equations change.
- Campaign source snapshots are created before workers start. Resuming a campaign requires unchanged source and configuration; use fresh output and build roots after either changes. A `--plan` command checks the schedule but does not create a snapshot or start a worker.
- For a new custom module, declare `type: custom`, `modelica_class`, `input_ports`, `output_ports`, `files`, and empty `faults` in its JSON config. The module must have a replaceable `Medium` package. `code/simulate.py` exports a raw CSV with all Modelica variables.
- Treat `build/`, `output/`, `.venv/`, cache directories, and `data/` as generated or local artifacts. Do not commit them. Inspect an existing output before replacing it.
- After launcher changes, run `python code/campaign.py --plan`, `python code/campaign.py --dataset ds1 --plan`, and `python -m pytest -q`. The shard startup regression in `tests/test_campaigns.py` checks work that `--plan` cannot reach. If OpenModelica is installed, run the small custom example in a fresh output directory. Set `RUN_OMC_TESTS=1` for the optional OpenModelica integration tests; `RUN_OMC_EXTENDED_TESTS=1` enables the longer topology checks.
