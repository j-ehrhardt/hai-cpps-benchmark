"""Deterministic release metadata for fixed-simulator HAI-CPPS exports."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import yaml

from config import MODULE_SPECS, RunSpec
from export import ExportBundle, OracleVariable


RELEASE_SCHEMA_VERSION = "1.0.0"
ORACLE_CATALOGUE_VERSION = "1.0.0"
FUNCTION_LIBRARY_VERSION = "1.0.0"


@dataclass(frozen=True)
class MetadataPaths:
    fault_events: Path
    system_knowledge: Path
    technical_timing: Path


FAULT_DEFINITIONS: Mapping[str, Mapping[str, Any]] = {
    "anom_leaking": {
        "fault_class": "leak",
        "mechanism": "leak_path_opening",
        "component": "leaking_valve",
        "parameter": "opening",
        "normal_value": 0.0,
        "fault_value": 0.25,
        "unit": "1",
        "oracle_raw_suffixes": (
            ".leaking_valve.opening",
            ".leaking_valve.m_flow",
        ),
    },
    "anom_pollution": {
        "fault_class": "filter_pollution",
        "mechanism": "increased_filter_pollution_factor",
        "component": "filter_F101",
        "parameter": "pollution_value",
        "normal_value": 0.5,
        "fault_value": 1.0,
        "unit": "1",
        "oracle_raw_suffixes": (
            ".pollution_value",
            ".filter_F101.opening",
        ),
    },
    "anom_valve_in0": {
        "fault_class": "inlet_valve_cannot_close",
        "mechanism": "minimum_valve_opening",
        "component": "valve_in0",
        "parameter": "minimum_opening",
        "normal_value": 0.0,
        "fault_value": 0.2,
        "unit": "1",
        "oracle_raw_suffixes": (
            ".var_valve_in0",
            ".var_valve_in",
            ".valve_in0.opening",
            ".valve_in.opening",
        ),
    },
    "anom_valve_in1": {
        "fault_class": "inlet_valve_cannot_close",
        "mechanism": "minimum_valve_opening",
        "component": "valve_in1",
        "parameter": "minimum_opening",
        "normal_value": 0.0,
        "fault_value": 0.2,
        "unit": "1",
        "oracle_raw_suffixes": (
            ".var_valve_in1",
            ".valve_in1.opening",
        ),
    },
    "anom_valve_in2": {
        "fault_class": "inlet_valve_cannot_close",
        "mechanism": "minimum_valve_opening",
        "component": "valve_in2",
        "parameter": "minimum_opening",
        "normal_value": 0.0,
        "fault_value": 0.2,
        "unit": "1",
        "oracle_raw_suffixes": (
            ".var_valve_in2",
            ".valve_in2.opening",
        ),
    },
    "anom_pump50": {
        "fault_class": "reduced_pump_performance",
        "mechanism": "pump_performance_factor",
        "component": "pump",
        "parameter": "performance_factor",
        "normal_value": 1.0,
        "fault_value": 0.5,
        "unit": "1",
        "oracle_raw_suffixes": (".var_pump_n", ".pump_n_in"),
    },
    "anom_pump75": {
        "fault_class": "reduced_pump_performance",
        "mechanism": "pump_performance_factor",
        "component": "pump",
        "parameter": "performance_factor",
        "normal_value": 1.0,
        "fault_value": 0.75,
        "unit": "1",
        "oracle_raw_suffixes": (".var_pump_n", ".pump_n_in"),
    },
    "anom_heat50": {
        "fault_class": "reduced_heater_performance",
        "mechanism": "heater_performance_factor",
        "component": "heater_distill",
        "parameter": "performance_factor",
        "normal_value": 1.0,
        "fault_value": 0.5,
        "unit": "1",
        "oracle_raw_suffixes": (".var_heat", ".heater_distill.Q_flow"),
    },
    "anom_heat75": {
        "fault_class": "reduced_heater_performance",
        "mechanism": "heater_performance_factor",
        "component": "heater_distill",
        "parameter": "performance_factor",
        "normal_value": 1.0,
        "fault_value": 0.75,
        "unit": "1",
        "oracle_raw_suffixes": (".var_heat", ".heater_distill.Q_flow"),
    },
}


FUNCTION_LIBRARY: Tuple[Mapping[str, str], ...] = (
    {
        "name": "weighted_sum",
        "description": "Linear weighted sum with documented coefficients.",
    },
    {
        "name": "difference",
        "description": "Signed difference under a documented sign convention.",
    },
    {
        "name": "delayed_difference",
        "description": "Difference after an explicitly validated time shift.",
    },
    {
        "name": "discrete_state_transition",
        "description": "State-machine transition under its declared condition.",
    },
    {
        "name": "product",
        "description": "Product of the named inputs.",
    },
    {
        "name": "saturation",
        "description": "Lower/upper bounded value.",
    },
    {
        "name": "integrator",
        "description": "Continuous-time integral with documented initial state.",
    },
    {
        "name": "conditional_assignment",
        "description": "Mode-dependent deterministic assignment.",
    },
    {
        "name": "first_order_lag",
        "description": "First-order response with a documented time constant.",
    },
    {
        "name": "threshold_comparison",
        "description": "Boolean result of a documented threshold comparison.",
    },
)


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(data), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_yaml(path: Path, data: Mapping[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(
            dict(data),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )


def _measurement_descriptor(column: str) -> Mapping[str, Any]:
    module, local = column.split(".", 1)
    if re.fullmatch(r"tank_[A-Za-z0-9_]+\.level", local):
        kind, unit, views = "liquid_level", "m", ["continuous", "hybrid"]
    elif re.fullmatch(r"sensor_continuous_pressure_[A-Za-z0-9_]+\.p", local):
        kind, unit, views = "pressure", "Pa", ["continuous", "hybrid"]
    elif re.fullmatch(
        r"sensor_continuous_volumeFlowRate(?:_[A-Za-z0-9_]+)?\.V_flow", local
    ):
        kind, unit, views = "volume_flow_rate", "m3/s", ["continuous", "hybrid"]
    elif re.fullmatch(r"sensor_continuous_temperature_[A-Za-z0-9_]+\.T", local):
        kind, unit, views = "temperature", "K", ["continuous", "hybrid"]
    elif re.fullmatch(r"sensor_discrete_[A-Za-z0-9_]+\.showActive", local):
        kind, unit, views = "discrete_sensor_state", "1", ["discrete", "hybrid"]
    else:
        raise ValueError("Cannot describe non-measurement column {!r}".format(column))
    return {
        "name": column,
        "module": module,
        "kind": kind,
        "unit": unit,
        "online_observable": True,
        "online_feature_allowed": True,
        "measurement_views": views,
        "raw_result_column": column,
        "status": "exported",
    }


def _oracle_descriptor(variable: OracleVariable) -> Mapping[str, Any]:
    descriptor: Dict[str, Any] = {
        "name": variable.oracle_column,
        "module": variable.module,
        "component": variable.component,
        "kind": variable.kind,
        "unit": variable.unit,
        "oracle_role": variable.oracle_role,
        "online_observable": False,
        "online_feature_allowed": False,
        "offline_target_allowed": True,
        "direct_fault_revealing": variable.direct_fault_revealing,
        "oracle_column": variable.oracle_column,
        "raw_result_column": variable.raw_column,
        "status": "exported",
    }
    if variable.kind in {
        "operation_phase_indicator",
        "injection_window_indicator",
    }:
        descriptor["lower_bound"] = 0
        descriptor["upper_bound"] = 1
    elif variable.kind in {
        "fault_mechanism_state",
        "effective_filter_opening",
    } or variable.oracle_column.endswith(".opening"):
        descriptor["lower_bound"] = 0.0
        descriptor["upper_bound"] = 1.0
    elif variable.kind in {
        "actuator_command",
        "effective_actuator_input",
        "effective_heat_input",
    }:
        descriptor["lower_bound"] = 0.0
    return descriptor


def _edge_sort_key(item: Tuple[str, Any]) -> Tuple[int, Any]:
    edge_id = item[0]
    return (0, int(edge_id)) if edge_id.isdigit() else (1, edge_id)


def _module_source(setup: Mapping[str, Any], module_name: str) -> Optional[str]:
    module = setup["model"]["modules"].get(module_name)
    return None if module is None else str(module.get("files"))


def _with_provenance(
    descriptor: Mapping[str, Any], setup: Mapping[str, Any]
) -> Mapping[str, Any]:
    result = dict(descriptor)
    result["provenance"] = {
        "modelica_source": _module_source(setup, str(result["module"])),
        "raw_result_column": result["raw_result_column"],
    }
    return result


def _raw_oracle_lookup(
    oracle_variables: Sequence[OracleVariable],
) -> Mapping[str, str]:
    return {
        variable.raw_column: variable.oracle_column for variable in oracle_variables
    }


def _matching_oracle(
    oracle_variables: Sequence[OracleVariable],
    module: str,
    suffixes: Iterable[str],
) -> List[str]:
    suffix_tuple = tuple(suffixes)
    return sorted(
        variable.oracle_column
        for variable in oracle_variables
        if variable.module == module
        and any(variable.raw_column.endswith(suffix) for suffix in suffix_tuple)
    )


def fault_events_document(
    run: RunSpec, oracle_variables: Sequence[OracleVariable]
) -> Mapping[str, Any]:
    events: List[Mapping[str, Any]] = []
    if run.is_fault:
        fault_name = str(run.target_fault)
        try:
            definition = FAULT_DEFINITIONS[fault_name]
        except KeyError as exc:
            raise ValueError(
                "Fault {!r} has no release metadata definition".format(fault_name)
            ) from exc
        onset = float(run.setup["sim_setup"]["faultStart"])
        target_module = str(run.target_module)
        module_type = run.setup["model"]["modules"][target_module]["type"]
        component = str(definition["component"])
        if component == "pump":
            component = "pump_P401" if module_type == "bottling" else "pump_P101"
        elif component == "valve_in0" and module_type != "mixer":
            component = "valve_in"
        events.append(
            {
                "event_id": "fault_001",
                "target_module": target_module,
                "target_module_type": module_type,
                "configuration_flag": fault_name,
                "fault_class": definition["fault_class"],
                "mechanism": definition["mechanism"],
                "intervened_component": "{}.{}".format(target_module, component),
                "intervened_parameter": definition["parameter"],
                "normal_value": definition["normal_value"],
                "fault_value": definition["fault_value"],
                "unit": definition["unit"],
                "injection_intended_time": onset,
                "model_activation": {
                    "condition": "simulation_time >= anom_start",
                    "time": onset,
                    "status": "known_from_model_equation",
                },
                "physical_parameter_change": {
                    "time": onset,
                    "status": "model_intervention_begins",
                    "note": (
                        "A continuous ramp may have its first strictly non-zero "
                        "sample after this time."
                        if fault_name == "anom_leaking"
                        and run.setup["model"]["modules"][target_module]["type"]
                        == "distill"
                        else "The configured intervention is active from this time."
                    ),
                },
                "oracle_columns": _matching_oracle(
                    oracle_variables,
                    target_module,
                    definition["oracle_raw_suffixes"],
                ),
                "online_feature_allowed": False,
            }
        )
    return {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "scenario_id": run.scenario_id,
        "base_dataset": run.base_dataset,
        "events": events,
    }


def _rule(
    name: str,
    module: str,
    function: str,
    inputs: Sequence[str],
    conclusions: Sequence[str],
    expression: str,
    rule_class: str,
    provenance: str,
    valid_modes: Sequence[str] = ("all",),
    parameters: Optional[Mapping[str, Any]] = None,
    delay: Optional[Mapping[str, Any]] = None,
) -> Mapping[str, Any]:
    return {
        "name": name,
        "module": module,
        "function": function,
        "inputs": list(inputs),
        "conclusions": list(conclusions),
        "expression": expression,
        "rule_class": rule_class,
        "valid_modes": list(valid_modes),
        "delay": dict(delay or {"status": "not_modelled"}),
        "uncertainty": {"status": "deterministic_model_equation"},
        "units": "Units are inherited from the referenced variable catalogue entries.",
        "sign_convention": "Raw Modelica sign conventions are retained without transformation.",
        "parameters": dict(parameters or {}),
        "parameter_source": provenance,
        "provenance": provenance,
    }


def _system_rules(
    setup: Mapping[str, Any],
    measurement_columns: Sequence[str],
    oracle_variables: Sequence[OracleVariable],
) -> List[Mapping[str, Any]]:
    lookup = _raw_oracle_lookup(oracle_variables)
    rules: List[Mapping[str, Any]] = []
    pump_active_states: Mapping[str, Tuple[str, ...]] = {
        "mixer": (
            "state_emptying_tank_B201",
            "state_emptying_tank_B202",
            "state_emptying_tank_B203",
        ),
        "filter": ("state_emptying_tank_B101",),
        "distill": ("state_emptying_tank_B101",),
        "bottling": ("state_emptying_tank_B401",),
    }
    mixer_tank_heights = {
        "tank_B201": 0.14,
        "tank_B202": 0.14,
        "tank_B203": 0.14,
        "tank_B204": 0.22,
    }

    measurement_set = set(measurement_columns)
    for discrete_column in sorted(measurement_set):
        match = re.fullmatch(
            r"([^.]+)\.sensor_discrete_(tank_[A-Za-z0-9_]+)_(low|medium|high)\.showActive",
            discrete_column,
        )
        if not match:
            continue
        module_name, tank_name, threshold_name = match.groups()
        level_column = "{}.{}.level".format(module_name, tank_name)
        if level_column not in measurement_set:
            continue
        module = setup["model"]["modules"][module_name]
        threshold_fraction = {"low": 0.1, "medium": 0.5, "high": 0.9}[
            threshold_name
        ]
        height = (
            mixer_tank_heights[tank_name]
            if module["type"] == "mixer"
            else 0.22
        )
        threshold = threshold_fraction * height
        source = str(module.get("files", ""))
        rules.append(
            _rule(
                "{}.{}.{}_threshold".format(
                    module_name, tank_name, threshold_name
                ),
                module_name,
                "threshold_comparison",
                [level_column],
                [discrete_column],
                "showActive = level >= {}".format(threshold),
                "K_imp",
                "{}: level_to_boolean_{}_{} and sensor connection".format(
                    source, tank_name, threshold_name
                ),
                parameters={
                    "tank_height": height,
                    "threshold_fraction": threshold_fraction,
                    "threshold": threshold,
                    "unit": "m",
                },
                delay={"status": "known_zero", "value": 0.0, "unit": "s"},
            )
        )

    for module_name, module in sorted(setup["model"]["modules"].items()):
        source = str(module.get("files", ""))
        window_raw = "{}.fault_window_active".format(module_name)
        if window_raw in lookup:
            rules.append(
                _rule(
                    "{}.fault_window_activation".format(module_name),
                    module_name,
                    "threshold_comparison",
                    ["simulation_time", "sim_setup.faultStart"],
                    [lookup[window_raw]],
                    (
                        "exported active follows the event-boundary recording "
                        "semantics in technical_timing.json; the underlying "
                        "Modelica equation is time >= faultStart"
                    ),
                    "K_imp",
                    "{}: fault_window_active equation".format(source),
                )
            )

        state_columns = sorted(
            variable.oracle_column
            for variable in oracle_variables
            if variable.module == module_name
            and variable.oracle_role == "operation_state"
        )
        if state_columns:
            rules.append(
                _rule(
                    "{}.state_graph_semantics".format(module_name),
                    module_name,
                    "discrete_state_transition",
                    state_columns,
                    state_columns,
                    "State indicators follow the module StateGraph transition conditions.",
                    "documentation_only",
                    "{}: StateGraph declarations and transition equations".format(source),
                )
            )

        command_raw = "{}.pump_n_in".format(module_name)
        factor_raw = "{}.var_pump_n".format(module_name)
        active_raws = [
            "{}.{}.active".format(module_name, state)
            for state in pump_active_states.get(module["type"], ())
        ]
        if command_raw in lookup and factor_raw in lookup and all(
            raw in lookup for raw in active_raws
        ):
            rules.append(
                _rule(
                    "{}.pump_command".format(module_name),
                    module_name,
                    "conditional_assignment",
                    [lookup[raw] for raw in active_raws] + [lookup[factor_raw]],
                    [lookup[command_raw]],
                    "pump_command = 150 * performance_factor in a pump-active mode; otherwise 0",
                    "K_imp",
                    "{}: pump_n_in equation".format(source),
                    parameters={"nominal_command": 150.0, "unit": "rev/min"},
                )
            )

        noise_raw = "{}.uniformNoise.y".format(module_name)
        effective_raws = sorted(
            raw
            for raw in lookup
            if raw.startswith(module_name + ".pump_") and raw.endswith(".N_in")
        )
        if command_raw in lookup and noise_raw in lookup:
            for effective_raw in effective_raws:
                rules.append(
                    _rule(
                        "{}.{}.effective_speed".format(
                            module_name, effective_raw.split(".")[1]
                        ),
                        module_name,
                        "first_order_lag",
                        [lookup[command_raw], lookup[noise_raw]],
                        [lookup[effective_raw]],
                        (
                            "T * der(effective_speed) + effective_speed = "
                            "pump_command * noise_multiplier"
                        ),
                        "K_imp",
                        "{}: product1 and firstOrder connections".format(source),
                        parameters={"time_constant": 1.0, "time_unit": "s"},
                        delay={
                            "status": "modelled_first_order_dynamics",
                            "time_constant": 1.0,
                            "unit": "s",
                        },
                    )
                )

        if module["type"] == "distill":
            phase_raw = "{}.state_destillation.active".format(module_name)
            factor_raw = "{}.var_heat".format(module_name)
            heat_raw = "{}.heater_distill.Q_flow".format(module_name)
            if all(raw in lookup for raw in (phase_raw, factor_raw, heat_raw)):
                rules.append(
                    _rule(
                        "{}.heater_input".format(module_name),
                        module_name,
                        "conditional_assignment",
                        [lookup[phase_raw], lookup[factor_raw]],
                        [lookup[heat_raw]],
                        "heat_flow = 20000 * performance_factor in distillation mode; otherwise 0",
                        "K_imp",
                        "{}: heater_distill.Q_flow equation".format(source),
                        parameters={"nominal_heat_flow": 20000.0, "unit": "W"},
                    )
                )

        if module["type"] == "filter":
            pollution_raw = "{}.pollution_value".format(module_name)
            opening_raw = "{}.filter_F101.opening".format(module_name)
            if pollution_raw in lookup and opening_raw in lookup:
                rules.append(
                    _rule(
                        "{}.filter_effective_opening".format(module_name),
                        module_name,
                        "integrator",
                        [lookup[pollution_raw]],
                        [lookup[opening_raw]],
                        (
                            "opening = 1 / (1 + pollution_factor * "
                            "integral(max(0, filter_mass_flow)))"
                        ),
                        "documentation_only",
                        (
                            "{}: mflow_filter, integrator, product, add and "
                            "division connections"
                        ).format(source),
                        parameters={
                            "missing_input": "filter_F101.port_a.m_flow",
                            "missing_input_status": "known_not_exported",
                        },
                    )
                )
    return rules


def system_knowledge_document(
    run: RunSpec, bundle: ExportBundle
) -> Mapping[str, Any]:
    setup = run.setup
    modules = []
    for module_name, module in sorted(setup["model"]["modules"].items()):
        spec = MODULE_SPECS[module["type"]]
        modules.append(
            {
                "name": module_name,
                "type": module["type"],
                "modelica_class": spec.modelica_class,
                "modelica_source": str(module["files"]),
                "input_ports": list(spec.input_ports),
                "output_ports": list(spec.output_ports),
            }
        )

    edges = []
    for edge_id, connection in sorted(
        setup["model"]["edges"].items(), key=_edge_sort_key
    ):
        edges.append(
            {
                "id": str(edge_id),
                "source": connection[0],
                "target": connection[1],
                "directed": True,
            }
        )

    variables = [
        _with_provenance(_measurement_descriptor(column), setup)
        for column in bundle.safe_columns
    ]
    variables.extend(
        _with_provenance(_oracle_descriptor(variable), setup)
        for variable in bundle.oracle_variables
    )

    return {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "function_library_version": FUNCTION_LIBRARY_VERSION,
        "scenario_id": run.scenario_id,
        "base_dataset": run.base_dataset,
        "scope": "one validated ds setup; graphs are never merged across setups",
        "modules": modules,
        "edges": edges,
        "variables": variables,
        "function_library": list(FUNCTION_LIBRARY),
        "rules": _system_rules(
            setup, bundle.safe_columns, bundle.oracle_variables
        ),
        "limitations": [
            {
                "kind": "fixed_result_boundary",
                "status": "known_not_exported",
                "description": (
                    "Only variables emitted by the frozen OpenModelica result filter "
                    "can be represented in this release."
                ),
            },
            {
                "kind": "edge_process_state",
                "status": "not_exported",
                "description": (
                    "Per-edge material-in-transit, source/target flow, pressure-drop "
                    "and compatibility-residual states are unavailable."
                ),
            },
            {
                "kind": "physical_completeness",
                "status": "not_claimed",
                "description": (
                    "The oracle is the curated set of available simulator internals, "
                    "not a claim of complete physical state observability."
                ),
            },
        ],
    }


def technical_timing_document(run: RunSpec, bundle: ExportBundle) -> Mapping[str, Any]:
    sim_setup = run.setup["sim_setup"]
    start = float(sim_setup["startTime"])
    stop = float(sim_setup["stopTime"])
    intervals = int(sim_setup["numberOfIntervals"])
    step = (stop - start) / intervals
    edges = [
        {
            "edge_id": str(edge_id),
            "source": connection[0],
            "target": connection[1],
            "process_delay": {"status": "not_exported"},
            "delay_bounds": {"status": "not_available"},
        }
        for edge_id, connection in sorted(
            run.setup["model"]["edges"].items(), key=_edge_sort_key
        )
    ]
    channels = [
        {
            "column": column,
            "role": "measurement",
            "sampling": "canonical_simulator_grid",
            "sample_period": step,
            "sensor_delay": {"status": "not_modelled"},
            "communication_delay": {"status": "not_modelled"},
            "logging_delay": {"status": "not_modelled"},
        }
        for column in bundle.safe_columns
    ]
    channels.extend(
        {
            "column": column,
            "role": "oracle_state",
            "sampling": "canonical_simulator_grid",
            "sample_period": step,
            "sensor_delay": {"status": "not_applicable"},
            "communication_delay": {"status": "not_applicable"},
            "logging_delay": {"status": "not_modelled"},
        }
        for column in bundle.oracle_columns
    )
    component_dynamics = []
    for module_name, module in sorted(run.setup["model"]["modules"].items()):
        if module["type"] in {"mixer", "filter", "distill", "bottling"}:
            component_dynamics.extend(
                (
                    {
                        "module": module_name,
                        "component": "pump_command_filter",
                        "kind": "first_order_lag",
                        "time_constant": 1.0,
                        "unit": "s",
                        "status": "known_from_model",
                    },
                    {
                        "module": module_name,
                        "component": "pump_noise",
                        "kind": "sample_period",
                        "sample_period": 1.0,
                        "unit": "s",
                        "status": "known_from_model",
                    },
                )
            )
        if module["type"] == "distill":
            component_dynamics.append(
                {
                    "module": module_name,
                    "component": "leak_activation",
                    "kind": "smooth_ramp_duration",
                    "duration": 10.0,
                    "unit": "s",
                    "status": "known_from_model",
                }
            )
    return {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "scenario_id": run.scenario_id,
        "base_dataset": run.base_dataset,
        "time_axis": {
            "clock": "OpenModelica simulation time",
            "unit": "s",
            "start": start,
            "stop": stop,
            "number_of_intervals": intervals,
            "sample_period": step,
            "rows": intervals + 1,
        },
        "recording": {
            "event_points": False,
            "event_boundary_value": "pre_or_post_event_value",
            "first_recorded_post_event_sample": (
                "the exact boundary row may contain the pre-event or post-event "
                "value; the first canonical time strictly greater than a later "
                "event time is unambiguously post-event; an event configured at "
                "simulation start is active initially"
            ),
            "canonical_grid_selection": (
                "last raw row at each configured output time; timestamp rewritten "
                "to the exact canonical grid"
            ),
            "communication_delay": {"status": "not_modelled"},
            "logging_delay": {"status": "not_modelled"},
        },
        "channel_groups": {
            "measurements": {
                "columns": list(bundle.safe_columns),
                "sampling": "canonical_simulator_grid",
                "sensor_delay": {"status": "not_modelled"},
                "communication_delay": {"status": "not_modelled"},
            },
            "oracle_states": {
                "columns": list(bundle.oracle_columns),
                "sampling": "canonical_simulator_grid",
                "sensor_delay": {"status": "not_applicable"},
                "logging_delay": {"status": "not_modelled"},
            },
        },
        "channels": channels,
        "modelled_component_dynamics": component_dynamics,
        "fault_timing": {
            "has_fault_event": run.is_fault,
            "configured_fault_window_start": float(sim_setup["faultStart"]),
            "intended_injection_time": (
                float(sim_setup["faultStart"]) if run.is_fault else None
            ),
            "activation_condition": "simulation_time >= anom_start",
            "recorded_activation_condition": (
                "simulation_time >= anom_start"
                if float(sim_setup["faultStart"]) == start
                else (
                    "simulation_time > anom_start; at exactly anom_start the "
                    "recorded value may be inactive or active"
                )
            ),
            "first_internal_consequence": {
                "status": "pending_paired_run" if run.is_fault else "not_applicable"
            },
            "first_measurement_consequence": {
                "status": "pending_paired_run" if run.is_fault else "not_applicable"
            },
            "first_physical_state_change": {
                "status": "not_fully_observable" if run.is_fault else "not_applicable"
            },
        },
        "edges": edges,
    }


def write_release_metadata(
    output_dir: Path, run: RunSpec, bundle: ExportBundle
) -> MetadataPaths:
    fault_events_path = output_dir / "fault_events.json"
    system_knowledge_path = output_dir / "system_knowledge.yaml"
    technical_timing_path = output_dir / "technical_timing.json"
    _write_json(fault_events_path, fault_events_document(run, bundle.oracle_variables))
    _write_yaml(system_knowledge_path, system_knowledge_document(run, bundle))
    _write_json(technical_timing_path, technical_timing_document(run, bundle))
    return MetadataPaths(
        fault_events=fault_events_path,
        system_knowledge=system_knowledge_path,
        technical_timing=technical_timing_path,
    )


def _first_observed_change(
    summaries: Mapping[str, Mapping[str, Any]],
    allowed_modules: Optional[Iterable[str]] = None,
) -> Mapping[str, Any]:
    module_prefixes = (
        None
        if allowed_modules is None
        else tuple("{}.".format(module) for module in allowed_modules)
    )
    observations = [
        (column, details.get("first_persistent_change"))
        for column, details in summaries.items()
        if (module_prefixes is None or column.startswith(module_prefixes))
        and details.get("first_persistent_change") is not None
    ]
    if not observations:
        return {"status": "not_observed"}
    first_time = min(float(time) for _, time in observations)
    return {
        "status": "observed_paired_run_difference",
        "time": first_time,
        "columns": sorted(
            column for column, time in observations if float(time) == first_time
        ),
    }


def update_technical_timing_with_pair(
    technical_timing_path: Path, report: Mapping[str, Any]
) -> None:
    """Add threshold-qualified observed timing after matched-pair validation."""

    document = json.loads(technical_timing_path.read_text(encoding="utf-8"))
    target_module = str(report.get("target_module"))
    downstream_modules = report.get("target_connectivity", {}).get(
        "reachable_downstream_modules", ()
    )
    measurement_summaries = report.get("safe_channel_differences", {})
    internal_summaries = report.get("verification_channel_differences", {})
    document["fault_timing"]["paired_run_observations"] = {
        "method": report.get("difference_detection"),
        "first_changed_internal_output": _first_observed_change(
            internal_summaries, [target_module]
        ),
        "first_local_measurement_consequence": _first_observed_change(
            measurement_summaries, [target_module]
        ),
        "first_downstream_measurement_consequence": _first_observed_change(
            measurement_summaries, downstream_modules
        ),
        "interpretation": (
            "Observed differences are threshold- and sampling-dependent evidence; "
            "they are not asserted as exact continuous-time causal onset."
        ),
    }
    _write_json(technical_timing_path, document)
