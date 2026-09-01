"""Benchmark configuration loading, normalization, and validation."""

from __future__ import annotations

import copy
import json
import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from jsonschema import Draft202012Validator


class ConfigError(ValueError):
    """Raised when a benchmark configuration is unsafe or inconsistent."""


@dataclass(frozen=True)
class ModuleSpec:
    modelica_class: str
    filename: str
    input_ports: Tuple[str, ...]
    output_ports: Tuple[str, ...]
    faults: Tuple[str, ...] = ()
    exclusive_fault_pairs: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RunSpec:
    scenario_id: str
    base_dataset: str
    setup: Dict[str, Any]
    target_module: Optional[str] = None
    target_fault: Optional[str] = None

    @property
    def is_fault(self) -> bool:
        return self.target_module is not None and self.target_fault is not None


MODULE_SPECS: Mapping[str, ModuleSpec] = {
    "source": ModuleSpec("sourceModule", "Source.mo", (), ("port_out0",)),
    "sink": ModuleSpec("sinkModule", "Sink.mo", ("port_in0",), ()),
    "mixer": ModuleSpec(
        "mixerModule",
        "Mixer.mo",
        ("port_in0", "port_in1", "port_in2"),
        ("port_out0",),
        (
            "anom_leaking",
            "anom_valve_in0",
            "anom_valve_in1",
            "anom_valve_in2",
            "anom_pump50",
            "anom_pump75",
        ),
        (("anom_pump50", "anom_pump75"),),
    ),
    "filter": ModuleSpec(
        "filterModule",
        "Filter.mo",
        ("port_in0",),
        ("port_out0",),
        (
            "anom_leaking",
            "anom_pollution",
            "anom_valve_in0",
            "anom_pump50",
            "anom_pump75",
        ),
        (("anom_pump50", "anom_pump75"),),
    ),
    "distill": ModuleSpec(
        "distillModule",
        "Distill.mo",
        ("port_in0",),
        ("port_out0", "port_out1"),
        (
            "anom_leaking",
            "anom_valve_in0",
            "anom_pump50",
            "anom_pump75",
            "anom_heat50",
            "anom_heat75",
        ),
        (
            ("anom_pump50", "anom_pump75"),
            ("anom_heat50", "anom_heat75"),
        ),
    ),
    "bottling": ModuleSpec(
        "bottlingModule",
        "Bottling.mo",
        ("port_in0",),
        ("port_out0",),
        (
            "anom_leaking",
            "anom_valve_in0",
            "anom_pump50",
            "anom_pump75",
        ),
        (("anom_pump50", "anom_pump75"),),
    ),
}

_TYPE_BY_FILENAME = {
    spec.filename.lower(): module_type for module_type, spec in MODULE_SPECS.items()
}
_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "benchmark_setup.schema.json"


def _read_schema() -> Dict[str, Any]:
    with _SCHEMA_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _schema_errors(data: Any) -> List[str]:
    validator = Draft202012Validator(_read_schema())
    errors = sorted(
        validator.iter_errors(data),
        key=lambda error: tuple(str(part) for part in error.path),
    )
    rendered = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        rendered.append("{}: {}".format(location, error.message))
    return rendered


def _derive_module_type(module: Mapping[str, Any]) -> str:
    filename = Path(module["files"]).name.lower()
    try:
        return _TYPE_BY_FILENAME[filename]
    except KeyError as exc:
        raise ConfigError("Cannot derive module type from model file {!r}".format(filename)) from exc


def _split_endpoint(endpoint: str) -> Tuple[str, str]:
    if endpoint.count(".") != 1:
        raise ConfigError(
            "Endpoint {!r} must use the form '<module>.<port>'".format(endpoint)
        )
    module_name, port_name = endpoint.split(".", 1)
    return module_name, port_name


def _normalize(data: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = copy.deepcopy(dict(data))
    for dataset_name, scenario in normalized.items():
        sim_setup = scenario["sim_setup"]
        sim_setup.setdefault("faultStart", 2500)
        sim_setup.setdefault("seed", 20260831)

        for module_name, module in scenario["model"]["modules"].items():
            if "type" not in module:
                module["type"] = _derive_module_type(module)
                warnings.warn(
                    "Module {!r} in {!r} has no explicit type; deriving it from the "
                    "model filename is deprecated.".format(module_name, dataset_name),
                    DeprecationWarning,
                    stacklevel=3,
                )

            module_type = module["type"]
            if module_type in MODULE_SPECS:
                faults = module.setdefault("faults", {})
                for fault_name in MODULE_SPECS[module_type].faults:
                    faults.setdefault(fault_name, False)
    return normalized


def _validate_semantics(data: Mapping[str, Any], base_dir: Optional[Path]) -> List[str]:
    errors: List[str] = []

    for dataset_name, scenario in data.items():
        modules = scenario["model"]["modules"]
        edges = scenario["model"]["edges"]
        sim_setup = scenario["sim_setup"]

        if scenario["ds_name"] != dataset_name:
            errors.append(
                "{}: ds_name must match its dataset key".format(dataset_name)
            )

        start = sim_setup["startTime"]
        stop = sim_setup["stopTime"]
        onset = sim_setup["faultStart"]
        if not all(math.isfinite(float(value)) for value in (start, stop, onset)):
            errors.append("{}: simulation times must be finite".format(dataset_name))
        elif not start < stop:
            errors.append("{}: startTime must be lower than stopTime".format(dataset_name))
        elif not start <= onset < stop:
            errors.append(
                "{}: faultStart must be at or after startTime and before stopTime".format(
                    dataset_name
                )
            )

        specs: Dict[str, ModuleSpec] = {}
        for module_name, module in modules.items():
            module_type = module["type"]
            spec = MODULE_SPECS.get(module_type)
            if spec is None:
                errors.append(
                    "{}: module {!r} has unknown type {!r}".format(
                        dataset_name, module_name, module_type
                    )
                )
                continue
            specs[module_name] = spec

            if Path(module["files"]).name != spec.filename:
                errors.append(
                    "{}: module {!r} of type {!r} must use {}".format(
                        dataset_name, module_name, module_type, spec.filename
                    )
                )
            if base_dir is not None and not (base_dir / module["files"]).resolve().is_file():
                errors.append(
                    "{}: model file for module {!r} does not exist: {}".format(
                        dataset_name, module_name, (base_dir / module["files"]).resolve()
                    )
                )

            faults = module["faults"]
            unknown_faults = sorted(set(faults) - set(spec.faults))
            if unknown_faults:
                errors.append(
                    "{}: module {!r} does not support faults {}".format(
                        dataset_name, module_name, ", ".join(unknown_faults)
                    )
                )
            for left, right in spec.exclusive_fault_pairs:
                if faults.get(left, False) and faults.get(right, False):
                    errors.append(
                        "{}: module {!r} cannot enable {} and {} together".format(
                            dataset_name, module_name, left, right
                        )
                    )

        source_use: Dict[Tuple[str, str], int] = {}
        target_use: Dict[Tuple[str, str], int] = {}
        seen_connections = set()

        for edge_id, connection in edges.items():
            try:
                source = _split_endpoint(connection[0])
                target = _split_endpoint(connection[1])
            except (ConfigError, IndexError) as exc:
                errors.append("{}: edge {!r}: {}".format(dataset_name, edge_id, exc))
                continue

            if (source, target) in seen_connections:
                errors.append("{}: duplicate connection at edge {!r}".format(dataset_name, edge_id))
            seen_connections.add((source, target))

            source_module, source_port = source
            target_module, target_port = target
            if source_module not in specs:
                errors.append(
                    "{}: edge {!r} references unknown source module {!r}".format(
                        dataset_name, edge_id, source_module
                    )
                )
            elif source_port not in specs[source_module].output_ports:
                errors.append(
                    "{}: edge {!r} source {}.{} is not an output port".format(
                        dataset_name, edge_id, source_module, source_port
                    )
                )

            if target_module not in specs:
                errors.append(
                    "{}: edge {!r} references unknown target module {!r}".format(
                        dataset_name, edge_id, target_module
                    )
                )
            elif target_port not in specs[target_module].input_ports:
                errors.append(
                    "{}: edge {!r} target {}.{} is not an input port".format(
                        dataset_name, edge_id, target_module, target_port
                    )
                )

            source_use[source] = source_use.get(source, 0) + 1
            target_use[target] = target_use.get(target, 0) + 1

        for module_name, spec in specs.items():
            for port in spec.output_ports:
                count = source_use.get((module_name, port), 0)
                if count != 1:
                    errors.append(
                        "{}: output {}.{} must be connected exactly once (found {})".format(
                            dataset_name, module_name, port, count
                        )
                    )
            for port in spec.input_ports:
                count = target_use.get((module_name, port), 0)
                if count != 1:
                    errors.append(
                        "{}: input {}.{} must be connected exactly once (found {})".format(
                            dataset_name, module_name, port, count
                        )
                    )

    return errors


def normalize_and_validate(
    data: Mapping[str, Any], base_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Return an independent, normalized configuration or fail with all errors."""

    schema_errors = _schema_errors(data)
    if schema_errors:
        raise ConfigError("Invalid benchmark configuration:\n- " + "\n- ".join(schema_errors))

    normalized = _normalize(data)
    semantic_errors = _validate_semantics(normalized, base_dir)
    if semantic_errors:
        raise ConfigError("Invalid benchmark configuration:\n- " + "\n- ".join(semantic_errors))
    return normalized


def load_benchmark_config(config_path: Path) -> Dict[str, Any]:
    config_path = config_path.resolve()
    try:
        with config_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError("Cannot load configuration {}: {}".format(config_path, exc)) from exc
    return normalize_and_validate(data, config_path.parent)


def _all_faults_false(setup: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(setup))
    for module in result["model"]["modules"].values():
        for fault_name in module["faults"]:
            module["faults"][fault_name] = False
    return result


def normal_run(dataset_name: str, setup: Mapping[str, Any]) -> RunSpec:
    scenario = _all_faults_false(setup)
    scenario_id = "{}_normal".format(dataset_name)
    scenario["ds_name"] = scenario_id
    return RunSpec(scenario_id, dataset_name, scenario)


def generate_normal_campaign(
    benchmark: Mapping[str, Mapping[str, Any]], selected: Optional[Iterable[str]] = None
) -> List[RunSpec]:
    selected_names = set(selected) if selected is not None else None
    return [
        normal_run(dataset_name, setup)
        for dataset_name, setup in benchmark.items()
        if selected_names is None or dataset_name in selected_names
    ]


def generate_single_fault_campaign(
    benchmark: Mapping[str, Mapping[str, Any]], selected: Optional[Iterable[str]] = None
) -> List[RunSpec]:
    selected_names = set(selected) if selected is not None else None
    runs: List[RunSpec] = []

    for dataset_name, setup in benchmark.items():
        if selected_names is not None and dataset_name not in selected_names:
            continue
        modules = setup["model"]["modules"]
        for module_name, module in modules.items():
            spec = MODULE_SPECS[module["type"]]
            for fault_name in spec.faults:
                scenario = _all_faults_false(setup)
                scenario["model"]["modules"][module_name]["faults"][fault_name] = True
                scenario_id = "{}_{}_{}".format(dataset_name, module_name, fault_name)
                scenario["ds_name"] = scenario_id
                runs.append(
                    RunSpec(
                        scenario_id,
                        dataset_name,
                        scenario,
                        target_module=module_name,
                        target_fault=fault_name,
                    )
                )
    return runs


def focused_fault_pair(
    benchmark: Mapping[str, Mapping[str, Any]],
    dataset_name: str,
    module_name: str,
    fault_name: str,
) -> Tuple[RunSpec, RunSpec]:
    try:
        setup = benchmark[dataset_name]
        module = setup["model"]["modules"][module_name]
    except KeyError as exc:
        raise ConfigError("Unknown focused fault target: {}.{}".format(dataset_name, module_name)) from exc

    spec = MODULE_SPECS[module["type"]]
    if fault_name not in spec.faults:
        raise ConfigError(
            "Module {} does not support fault {}".format(module_name, fault_name)
        )

    normal = normal_run(dataset_name, setup)
    fault_setup = _all_faults_false(setup)
    fault_setup["model"]["modules"][module_name]["faults"][fault_name] = True
    scenario_id = "{}_{}_{}".format(dataset_name, module_name, fault_name)
    fault_setup["ds_name"] = scenario_id
    fault = RunSpec(
        scenario_id,
        dataset_name,
        fault_setup,
        target_module=module_name,
        target_fault=fault_name,
    )
    return normal, fault
