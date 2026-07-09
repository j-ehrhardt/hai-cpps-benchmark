[![Python Version](https://img.shields.io/badge/python-3.12%2B-brightgreen.svg)](https://www.python.org/downloads/release/python-3120/)
[![Mamba](https://img.shields.io/badge/Mamba-1.5.8-green)](https://mamba.readthedocs.io)
[![OpenModelica](https://img.shields.io/badge/OpenModelica-1.25-cyan)]()
[![Documentation](https://img.shields.io/badge/docs-v2.0-orange)](https://j-ehrhardt.github.io/hai-cps-benchmark/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![DOI:XXX](https://img.shields.io/badge/DOI-XXXX-blue)](<doi link>)


<img title="" src="./figs/logo.png" alt="alt text" width="200">

# Hamburg AI Benchmark for Cyber-Physical Production Systems (HAI-CPPS)

The **Hamburg AI Benchmark for Cyber-Physical Production Systems (HAI-CPPS)** is a comprehensive dataset for evaluating AI models from the domains of **anomaly detection, diagnosis, reconfiguration, and planning** for Cyber-Physical Production Sytems. 

HAI-CPPS is constructed as a benchmark, consisting of ten different scenarios of a modular process plant showing different functionalities and increasing complexities. This allows you to comprehensively test your algorithm not only on a single use-case but systematically on increasingly complex examples from the same domain. Each scenario can show a range of multiple anomalies occurring in a single or multiple modules of the CPS. 

HAI-CPPS consists of

- OpenModelica simulation models
- Pre-simulated datasets for benchmarking
- Docker integration for easy execution

In addition to the existing setups, you can create and simulate your own simulations and system constellations, using the OpenModelica models and the HAI-CPPS python API. 

You can find the documentation of HAI-CPPS [here](https://j-ehrhardt.github.io/hai-cpps-benchmark/)

> [!NOTE]
> HAI-CPPS extends the **Benchmark for Diagnosis, Reconfiguration, and Planning (BeRfiPl)**. You can access the previous version [here](https://github.com/j-ehrhardt/benchmark-for-diagnosis-reconf-planning/tree/benchmark_v1).

### Table of Contents

1. [Introduction](#hamburg-ai-benchmark-for-cyber-physical-systems-hai-cps)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [HAI-CPPS - Overview](#hai-cpps-overview)
   - [CPPS - Modules](#cpps-modules)
   - [Anomalies](#anomalies)
   - [Benchmark Datasets](#benchmark-datasets)
   - [Access the Benchmark Datasets](#accessing-the-benchmark-datasets)
5. [Using the Simulation Models](#using-the-simulation-models)
   - [Create Your Own Simulations](#create-your-own-simulations)
   - [Replicating the Benchmark](#replicating-the-benchmark)
6. [Using the Benchmark](#using-the-benchmark)
7. [Citation](#citation)

# Requirements

**For local use**:

> [!NOTE]
> Local use has only been tested on Ubuntu 22.04 LTS and Ubuntu 24.04 LTS. While the models should work without a problem in the OpenModelica Shell or OpenModelica Editor, the Python API run into problems.

- For running the benchmark you need an Installatoin of OpenModelica `1.25` and OpenModelica Standard Library `4.0.0`.
- All other requirements can be found in the `venv.yml` file. 

**Using Docker:**

- If you want to run the simulation from within the Docker container, you need a current version of Docker and Docker Compose.

# Installation

**For local use:**

Install OpenModelica by following the install instruction from the [OpenModelica website](https://openmodelica.org/download/download-linux/).

For installing all other requirements, install a current version of Mini-Forge and type the following into your terminal: 

```bash
mamba env create -f env.yml
```

**Using Docker:**

Set up the docker container via the `Dockerfile`, by navigating into the directory, where the `Dockerfile` lives and enter: 

```bash
docker compose up -d
```

# HAI-CPPS - Overview

The HAI-CPPS benchmark consists of ten datasets from ten different configurations of a modular Cyber-Physical Process plant. The process plant itself has four different types of modules that can be interchangeably connected. Each dataset in the benchmark is recorded from a different configuration of the Cyber-Physical Process plant.

### CPPS - Modules

The Cyber-Physical Process plant has four different types of modules: **(a) mixing, (b) filtering, (c) distilling, (d) bottling**. In addition there is a source and a sink module. 

You can find the OpenModelica models for the four different modules in the `models` directory along. All modules are controlled by their own automaton. 

| (a)<img src="figs/mixer.png" width="400"/>       | (b)<img src="figs/filter.png" width="400"/>       |
| ------------------------------------------------ | ------------------------------------------------- |
| **(c)**<img src="figs/distill.png" width="400"/> | **(d)**<img src="figs/bottling.png" width="400"/> |

### Anomalies

There are eight different anomalies that can be induced in the CPPS modules. 
While some anomalies only affect the modules in which they are induced, some propagate directly and indirectly into other modules. 

- **Leaking Anomaly:** The leaking valve is opened and a continuous volume flow is diverted into a separate sink and vanishes from the system.

- **Clogging Anomaly:** The clogging valve is partially closed to impede the the volume flow.

- **Pump Lower Performance 75%:** The pump is only working on 75% of its actual performance.

- **Pump Lower Performance 50%:** The pump is only working on 50% of its actual performance.

- **Pump Noise in Performance:** Noise is injected into the RPM of the pump.

- **Inlet Valve Anomaly:** An inlet valve cannot close completely and remains opened at 20%.

- **Outlet Valve Anomaly:** An outlet valve cannot close completely and remains opened at 20%.

- **Filter Pollution Anomaly:** The pollution of the filter is set to 50% from start on.

## Benchmark Datasets

The idea of HAI-CPPS is to offer a comprehensive benchmark for Machine Learning Algorithms for technical system. HAI-CPPS is especially suited for algorithms from the domains of **anomaly detection, reconfiguration, and diagnosis**. Therefore HAI-CPPS provides ten different datasets that each are recorded from a different, increasingly complex instance of the CPPS. The setup allows you to evaluate and compare your algorithms systematically in the dimensions of CPPS complexity and problem complexity. 

The benchmark datasets come in four different modes:

- **Discrete mode:** Only discrete values from the process plant are recorded. 
- **Continuous mode:** Only continuous values from the process plant are recorded. 
- **Hybrid mode:** All values from the process plant are recorded. 
- **Including states:** The states from the automatons running the individual models are included.

Below is an image of ten standard setups of HAI-CPPS.

<img src="figs/cpps-setups.png" width="800"/>

## Access the Benchmark Datasets

<img src="https://ieee-dataport.org/themes/custom/dataport_bootstrap/logo.svg" width="200"/>

The benchmark datasets are published via IEEE Dataport. You can access the datasets by following this [link](https://ieee-dataport.org/open-access/hai-cpps-hamburg-ai-benchmark-cyber-physical-production-systems).

Alternatively, you can replicate the datasets by running the simulation setups yourself. Therefore follow the instructions in [Replicate the Benchmark Datasets](#replicate-the-benchmark-datasets).

# Using the Simulation Models

You can use the code and models from this repository in two ways. 
Either, you simulate your own scenarios or you recreate the benchmark.

> If you want to use the models in Simulink, you can export to FMU models from the OMEdit and import them into Simulink.

## Replicate the Benchmark Datasets

If you simply want to replicate all datasets from the benchmark run the `sim.py` file with the virtual environemtn activated (either from the docker container or your terminal)
The script will automatically select the `benchmark_setup.json` file and run all simulations.

> [!WARNING]
> Attention! The simulations takes time, so be prepared to let your computer run for a while. 

## Create Your Own Simulation

If you want to create your own CPPS configurations and simulations, you can either use the OpenModelica Editor (OMEdit) or you use the python interface provided in this repository.

When using the OMEdit, simply load the models from the `models` directory and assemble them into new configurations within the `ProcessPlant.mo` file.

When using the Python interface, create your unique setup as a `config.json` and run the `sim.py` file within the virtual environment. (This is especially suited for the docker usage). 
You can orient yourself on the setup file for the benchmark `benchmark_setup.json` in the `code` directory. 

# Using the Benchmark

Using HAI-CPPS benchmark is pretty self-explanatory. Download or create the datasets yourself. Select the mode (discrete, continuous, hybrid, including states) in which you want to operate. Train your models using the normal data and test them on an anomalous test dataset. All anomalies are induced after 2500 time-steps and occur within the component, within the module that are indicated in the dataset name.

As a reference, you can have a look at the following repository [Discret2Di](https://github.com/lmoddemann/Discret2Di). 

# Citation

When using the HAI-CPPS benchmark, please use the following citation: 

```bibtex
   @data{haicpps,
   doi = {10.21227/5ewb-cn40},
   url = {https://dx.doi.org/10.21227/5ewb-cn40},
   author = {Jonas Ehrhardt and Lukas Moddemann and Alexander Diedrich and Oliver Niggemann},
   publisher = {IEEE Dataport},
   title = {HAI-CPPS: The Hamburg AI Benchmark for Cyber-Physical Production Sytems},
   year = {2025} }
}
```

When using the original benchmark (BeRFiPl) please cite: 

```bibtex
@INPROCEEDINGS{Ehrhardt2022,
  author={Ehrhardt, Jonas and Ramonat, Malte and Heesch, René and Balzereit, Kaja and Diedrich, Alexander and Niggemann, Oliver},
  booktitle={2022 IEEE 27th International Conference on Emerging Technologies and Factory Automation (ETFA)}, 
  title={An AI benchmark for Diagnosis, Reconfiguration & Planning}, 
  year={2022},
  pages={1-8},
  organization = {IEEE},
  doi={10.1109/ETFA52439.2022.9921546}}
```

## LICENSE

The simulation models are licensed under [MIT license](LICENSE).
