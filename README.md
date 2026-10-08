# HAI-CPPS benchmark

This repository generates the HAI-CPPS v2.2 simulation benchmark with OpenModelica. It contains ten predefined plant topologies (`ds1` through `ds10`). Each topology has healthy recordings and single-fault recordings with persistent and temporary fault windows. A complete campaign has **350 recordings**: 160 healthy and 190 faulty.

The three commands below are the supported workflows. Run them from the repository root.

## 1. Install on Ubuntu

Install system packages and OpenModelica. The repository setup below follows the [official Ubuntu installation instructions](https://openmodelica.org/download/download-linux/) and uses the [2026 signing key](https://openmodelica.org/news/january-27-2026-new-gpg-key/). Ubuntu 22.04 and 24.04 use their own `VERSION_CODENAME` automatically.

```bash
sudo apt update
sudo apt install ca-certificates curl gnupg build-essential python3 python3-venv python3-pip
curl -fsSL https://build.openmodelica.org/apt/openmodelica-2026.asc \
  | sudo gpg --dearmor --yes -o /usr/share/keyrings/openmodelica-keyring.gpg
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/openmodelica-keyring.gpg] https://build.openmodelica.org/apt ${VERSION_CODENAME} stable" \
  | sudo tee /etc/apt/sources.list.d/openmodelica.list
sudo apt update
sudo apt install --no-install-recommends omc
omc --version
```

The models require **Modelica Standard Library 4.0.0**. OpenModelica manages libraries separately from the compiler. Install the exact version with its [package manager](https://openmodelica.org/doc/OpenModelicaUsersGuide/latest/packagemanager.html):

```bash
cat > /tmp/hai-cpps-msl.mos <<'MOS'
updatePackageIndex();
installPackage(Modelica, "4.0.0", exactMatch=true);
loadModel(Modelica, {"4.0.0"}, requireExactVersion=true);
getVersion(Modelica);
getErrorString();
MOS
omc /tmp/hai-cpps-msl.mos
```

Check that the installation prints `true` for `installPackage` and `loadModel`, and `"4.0.0"` for `getVersion`. The exact-version option is documented in the [OpenModelica scripting API](https://openmodelica.org/doc/OpenModelicaUsersGuide/latest/scripting_api.html). This repository was smoke tested with OpenModelica 1.26.1 and MSL 4.0.0.

Create a Python virtual environment and install the direct dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Activate the environment again with `source .venv/bin/activate` in each new shell.

## 2. Run all benchmark datasets

First inspect the work list without writing outputs:

```bash
python code/campaign.py --plan
```

Run all ten datasets and all configured faults with four concurrent simulations:

```bash
python code/campaign.py --jobs 4
```

Set `--jobs` to the number of simulations your computer can run at once. Each worker has an isolated OpenModelica build directory. The launcher schedules healthy controls before their paired faults, writes logs under `build/v2.2/campaign/logs/`, and validates the completed campaign. Rerun the same command after an interruption to reuse complete recordings. Choose new `--output` and `--build-root` directories if you change the configuration or source after starting a campaign.

The default result is `output/v2.2/`. For example, one recording is in `output/v2.2/ds1/ds1/ds1_001_healthy/`. Each recording contains continuous, discrete, and hybrid Parquet measurements, controller commands, fault and timing metadata, validation results, and provenance. `output/v2.2/release_manifest.json` summarizes a validated full campaign. Generated files stay outside the source directories and are ignored by Git.

You can choose output locations explicitly:

```bash
python code/campaign.py --jobs 8 --output /path/to/results --build-root /path/to/build
```

## 3. Run one benchmark dataset

Use the same launcher with `--dataset`:

```bash
python code/campaign.py --dataset ds1 --jobs 4
```

This plans and runs the complete `ds1` campaign: 16 healthy recordings and 12 fault recordings. Its summary is `output/v2.2/ds1_release_manifest.json`. Any of `ds1` through `ds10` is accepted. Run `python code/campaign.py --dataset ds1 --plan` to inspect the selected work first.

## 4. Simulate your own topology

Copy [the example configuration](examples/custom.json) and edit its `modules` and `edges`. Each edge connects one output port to one input port. Every declared port must be connected exactly once. `files` paths are relative to the JSON file. You can combine the modules in `models/` without changing them.

For a new Modelica module, add a `.mo` file and set its `type` to `custom`. Supply `modelica_class`, `input_ports`, and `output_ports` in the JSON. The class must define a replaceable `Medium` package and expose the listed ports. [PassThrough.mo](examples/PassThrough.mo) shows a small custom pipe module. Custom modules currently have an empty `faults` object; the benchmark's predefined fault campaign applies to its validated built-in modules.

Run the included example:

```bash
python code/simulate.py --config examples/custom.json --dataset custom1
```

The raw result is `output/custom/custom1/processPlant_res.csv`. The same directory contains the generated plant, OpenModelica script, and compiler logs. `simulate.py` checks that OpenModelica loaded MSL 4.0.0 and produced the full requested time grid. Use `--output /path/to/new/output` for another run; an existing run directory is kept rather than overwritten.

For an existing topology or a built-in-only combination, use the same JSON format and command. Keep a source, a sink, and a valid connection for every port. The `sim_setup` object sets `startTime`, `stopTime`, `numberOfIntervals`, `faultStart`, and `seed`.

## Repository map

- `models/`: validated Modelica modules used by the benchmark.
- `code/benchmark_setup.json`: ten benchmark topologies and fault inventories.
- `code/campaign.py`: parallel full or single-dataset v2.2 campaign.
- `code/simulate.py`: one raw simulation for a user topology.
- `code/config.py`, `code/model_generation.py`, `code/runner.py`, `code/sim.py`: configuration, plant generation, OpenModelica execution, and validated benchmark export.
- `examples/`: a working configuration with an additional Modelica module.

To run the focused Python tests, install `pytest` in the virtual environment and run `python -m pytest -q`.

## License

See [LICENSE](LICENSE).
