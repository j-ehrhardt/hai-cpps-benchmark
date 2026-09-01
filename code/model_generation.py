"""Generate per-run Modelica plant and OpenModelica command files."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Tuple

from config import MODULE_SPECS


MODEL_NAME = "processPlant"
RESULT_VARIABLE_FILTER = (
    ".*("
    "tank_[A-Za-z0-9_]+[.]level|"
    "sensor_continuous_pressure_[A-Za-z0-9_]+[.]p|"
    "sensor_continuous_volumeFlowRate(_[A-Za-z0-9_]+)?[.]V_flow|"
    "sensor_continuous_temperature_[A-Za-z0-9_]+[.]T|"
    "sensor_discrete_[A-Za-z0-9_]+[.]showActive|"
    "state_[A-Za-z0-9_]+[.]active|"
    "[A-Za-z0-9_]*valve[A-Za-z0-9_]*[.]opening|"
    "pump_[A-Za-z0-9_]+[.]N_in|pump_n_in|uniformNoise[.]y|"
    "fault_window_active|"
    "var_[A-Za-z0-9_]+|leaking_valve[.]m_flow|"
    "filter_[A-Za-z0-9_]+[.]opening|"
    "pollution_value|heater_[A-Za-z0-9_]+[.]Q_flow"
    ")"
)


def _modelica_boolean(value: bool) -> str:
    return "true" if value else "false"


def _modelica_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _edge_sort_key(item: Tuple[str, Any]) -> Tuple[int, Any]:
    edge_id = item[0]
    return (0, int(edge_id)) if edge_id.isdigit() else (1, edge_id)


def stable_local_seed(global_seed: int, instance_name: str) -> int:
    """Return a stable positive Modelica seed without using Python's random hash."""

    payload = "{}:{}".format(global_seed, instance_name).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")
    return value % 2_147_483_646 + 1


def generate_plant_text(setup: Mapping[str, Any]) -> str:
    sim_setup = setup["sim_setup"]
    modules = setup["model"]["modules"]
    edges = setup["model"]["edges"]
    fault_start = sim_setup["faultStart"]
    global_seed = sim_setup["seed"]

    lines = [
        "model {}".format(MODEL_NAME),
        "  replaceable package Medium = Modelica.Media.Water.StandardWater;",
        "  inner Modelica.Blocks.Noise.GlobalSeed globalSeed(useAutomaticSeed = false, fixedSeed = {});".format(
            global_seed
        ),
        "  inner Modelica.Fluid.System system(",
        "    energyDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial,",
        "    massDynamics = Modelica.Fluid.Types.Dynamics.FixedInitial,",
        "    p_ambient = 1e5, T_ambient = 293.15, m_flow_start = 0.0005,",
        "    p_start = 1e5, T_start = 300, dp_small = 100, m_flow_small = 0.01);",
        "",
    ]

    for instance_name in sorted(modules):
        module = modules[instance_name]
        spec = MODULE_SPECS[module["type"]]
        modifiers = ["redeclare package Medium = Medium"]
        if spec.faults:
            modifiers.append("anom_start = {}".format(fault_start))
            modifiers.append(
                "noiseSeed = {}".format(stable_local_seed(global_seed, instance_name))
            )
            for fault_name in spec.faults:
                modifiers.append(
                    "{} = {}".format(
                        fault_name, _modelica_boolean(module["faults"][fault_name])
                    )
                )

        lines.append(
            "  {} {}({});".format(
                spec.modelica_class, instance_name, ", ".join(modifiers)
            )
        )

    lines.extend(("", "equation"))
    for _, connection in sorted(edges.items(), key=_edge_sort_key):
        lines.append("  connect({}, {});".format(connection[0], connection[1]))

    lines.extend(
        (
            "  annotation(",
            "    uses(Modelica(version = \"4.0.0\")),",
            "    experiment(StartTime = {}, StopTime = {}, NumberOfIntervals = {}, Tolerance = 1e-6));".format(
                sim_setup["startTime"],
                sim_setup["stopTime"],
                sim_setup["numberOfIntervals"],
            ),
            "end {};".format(MODEL_NAME),
            "",
        )
    )
    return "\n".join(lines)


def model_files_for_setup(
    setup: Mapping[str, Any], config_dir: Path
) -> List[Path]:
    """Return each used reusable model file once, in registry order."""

    used_types = {module["type"] for module in setup["model"]["modules"].values()}
    files = []
    for module_type, spec in MODULE_SPECS.items():
        if module_type not in used_types:
            continue
        candidates = {
            (config_dir / module["files"]).resolve()
            for module in setup["model"]["modules"].values()
            if module["type"] == module_type
        }
        if len(candidates) != 1:
            raise ValueError(
                "Module type {!r} resolves to multiple files: {}".format(
                    module_type, sorted(str(path) for path in candidates)
                )
            )
        path = candidates.pop()
        if path.name != spec.filename:
            raise ValueError(
                "Module type {!r} must resolve to {}".format(module_type, spec.filename)
            )
        files.append(path)
    return files


def generate_mos_text(
    setup: Mapping[str, Any],
    model_files: Iterable[Path],
    plant_path: Path,
    include_simulation: bool = True,
) -> str:
    sim_setup = setup["sim_setup"]
    lines = ['loadModel(Modelica, {"4.0.0"});', "getVersion(Modelica);"]
    for model_file in model_files:
        lines.append(
            'loadFile("{}");'.format(_modelica_string(str(model_file.resolve())))
        )
    lines.extend(
        (
            'loadFile("{}");'.format(_modelica_string(str(plant_path.resolve()))),
            "checkModel({});".format(MODEL_NAME),
        )
    )
    if include_simulation:
        lines.append(
            'simulate({}, startTime={}, stopTime={}, numberOfIntervals={}, '
            'outputFormat="csv", tolerance=1e-6, variableFilter="{}", '
            'simflags="-noEventEmit");'.format(
                MODEL_NAME,
                sim_setup["startTime"],
                sim_setup["stopTime"],
                sim_setup["numberOfIntervals"],
                _modelica_string(RESULT_VARIABLE_FILTER),
            )
        )
    lines.extend(
        (
            "getErrorString();",
            "",
        )
    )
    return "\n".join(lines)


def write_run_files(
    setup: Mapping[str, Any],
    config_dir: Path,
    run_dir: Path,
    include_simulation: bool = True,
) -> Tuple[Path, Path, List[Path]]:
    run_dir.mkdir(parents=True, exist_ok=False)
    plant_path = run_dir / "Plant.mo"
    mos_path = run_dir / "call.mos"
    model_files = model_files_for_setup(setup, config_dir)

    plant_path.write_text(generate_plant_text(setup), encoding="utf-8")
    mos_path.write_text(
        generate_mos_text(
            setup,
            model_files,
            plant_path,
            include_simulation=include_simulation,
        ),
        encoding="utf-8",
    )
    return plant_path, mos_path, model_files
