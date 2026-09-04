"""Fail-fast simulation and paired-dataset validation."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd
import yaml

from config import RunSpec
from export import (
    ExportBundle,
    ExportError,
    FORBIDDEN_SAFE_FRAGMENTS,
    canonical_grid_indices,
)


class ValidationError(RuntimeError):
    """Raised when a run or fault pair is not valid for release."""


IDENTIFIER_COLUMNS = ("scenario_id", "simulation_step", "simulation_time")
DIRECT_FAULT_EFFECT_SUFFIXES: Mapping[str, Tuple[str, ...]] = {
    "anom_leaking": (".leaking_valve.opening",),
    "anom_pollution": (".pollution_value",),
    "anom_valve_in0": (".var_valve_in0", ".var_valve_in"),
    "anom_valve_in1": (".var_valve_in1",),
    "anom_valve_in2": (".var_valve_in2",),
    "anom_pump50": (".var_pump_n",),
    "anom_pump75": (".var_pump_n",),
    "anom_heat50": (".var_heat",),
    "anom_heat75": (".var_heat",),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_dataset_table(path: Path) -> pd.DataFrame:
    """Read one supported release or internal validation table."""

    if path.suffix == ".parquet":
        try:
            return pd.read_parquet(path, engine="pyarrow")
        except (ImportError, ModuleNotFoundError) as exc:
            raise ValidationError(
                "Parquet validation requires pyarrow; recreate the project "
                "environment from venv.yml"
            ) from exc
    if path.suffix == ".csv":
        return pd.read_csv(path)
    raise ValidationError("Unsupported dataset table format: {}".format(path))


def signal_sha256(path: Path) -> str:
    """Hash only ordered signal values, excluding scenario/time identifiers."""

    frame = read_dataset_table(path)
    signals = frame.drop(columns=list(IDENTIFIER_COLUMNS), errors="ignore")
    payload = signals.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def duplicate_signal_groups(paths: Iterable[Path]) -> List[List[str]]:
    groups: Dict[str, List[str]] = {}
    for path in paths:
        groups.setdefault(signal_sha256(path), []).append(str(path))
    return [sorted(group) for group in groups.values() if len(group) > 1]


def snapshot_hashes(paths: Iterable[Path]) -> Dict[str, str]:
    return {str(path.resolve()): sha256_file(path) for path in paths}


def assert_hashes_unchanged(before: Mapping[str, str], paths: Iterable[Path]) -> None:
    after = snapshot_hashes(paths)
    changed = sorted(path for path, digest in before.items() if after.get(path) != digest)
    if changed:
        raise ValidationError(
            "Reusable Modelica sources changed during simulation: {}".format(
                ", ".join(changed)
            )
        )


def validate_matched_run_specs(normal_run: RunSpec, fault_run: RunSpec) -> None:
    """Require a pair to differ only by its ID and one target Boolean."""

    if normal_run.is_fault or not fault_run.is_fault:
        raise ValidationError("A fault pair requires one normal and one fault RunSpec")
    if normal_run.base_dataset != fault_run.base_dataset:
        raise ValidationError("Normal/fault runs refer to different base datasets")

    for module_name, module in normal_run.setup["model"]["modules"].items():
        active = sorted(name for name, enabled in module["faults"].items() if enabled)
        if active:
            raise ValidationError(
                "Normal run has active faults on {}: {}".format(
                    module_name, ", ".join(active)
                )
            )

    expected_fault = copy.deepcopy(normal_run.setup)
    expected_fault["ds_name"] = fault_run.setup["ds_name"]
    try:
        expected_fault["model"]["modules"][fault_run.target_module]["faults"][
            fault_run.target_fault
        ] = True
    except KeyError as exc:
        raise ValidationError(
            "Fault target {}.{} is missing from the paired setup".format(
                fault_run.target_module, fault_run.target_fault
            )
        ) from exc
    if expected_fault != fault_run.setup:
        raise ValidationError(
            "Normal/fault configurations differ beyond the target Boolean {}.{}".format(
                fault_run.target_module, fault_run.target_fault
            )
        )


def validate_raw_result(raw_path: Path, sim_setup: Mapping[str, Any]) -> Dict[str, Any]:
    if not raw_path.is_file():
        raise ValidationError("Expected OpenModelica result is missing: {}".format(raw_path))

    frame = pd.read_csv(raw_path, usecols=["time"])
    if frame["time"].isna().any() or not frame["time"].map(math.isfinite).all():
        raise ValidationError("Simulation time contains missing or non-finite values")

    actual_start = float(frame["time"].iloc[0])
    actual_stop = float(frame["time"].iloc[-1])
    expected_start = float(sim_setup["startTime"])
    expected_stop = float(sim_setup["stopTime"])
    if not math.isclose(actual_start, expected_start, abs_tol=1e-9):
        raise ValidationError(
            "Simulation starts at {}; expected {}".format(actual_start, expected_start)
        )
    if not math.isclose(actual_stop, expected_stop, abs_tol=1e-7):
        raise ValidationError(
            "Simulation stops at {}; expected {}".format(actual_stop, expected_stop)
        )
    if not frame["time"].is_monotonic_increasing:
        raise ValidationError("Simulation time is not monotonic")

    try:
        canonical_rows = len(canonical_grid_indices(frame["time"], sim_setup))
    except ExportError as exc:
        raise ValidationError(str(exc)) from exc

    return {
        "rows": len(frame),
        "canonical_rows": canonical_rows,
        "extra_event_rows": len(frame) - canonical_rows,
        "start_time": actual_start,
        "stop_time": actual_stop,
        "sha256": sha256_file(raw_path),
    }


def validate_safe_columns(columns: Sequence[str]) -> None:
    missing_identifiers = [column for column in IDENTIFIER_COLUMNS if column not in columns]
    if missing_identifiers:
        raise ValidationError(
            "Safe export is missing identifiers: {}".format(", ".join(missing_identifiers))
        )
    leaked = sorted(
        column
        for column in columns
        if any(fragment in column for fragment in FORBIDDEN_SAFE_FRAGMENTS)
    )
    if leaked:
        raise ValidationError(
            "Safe export contains forbidden channels: {}".format(", ".join(leaked))
        )


def _validate_identifier_frame(
    frame: pd.DataFrame, scenario_id: str, label: str
) -> None:
    if tuple(frame.columns[: len(IDENTIFIER_COLUMNS)]) != IDENTIFIER_COLUMNS:
        raise ValidationError(
            "{} must start with identifiers {}".format(label, IDENTIFIER_COLUMNS)
        )
    if frame.empty:
        raise ValidationError("{} must not be empty".format(label))
    if frame["scenario_id"].isna().any() or set(frame["scenario_id"]) != {
        scenario_id
    }:
        raise ValidationError("{} has an inconsistent scenario_id".format(label))
    expected_steps = list(range(len(frame)))
    if frame["simulation_step"].tolist() != expected_steps:
        raise ValidationError("{} has a non-canonical simulation_step".format(label))


def _assert_aligned(
    reference: pd.DataFrame, candidate: pd.DataFrame, label: str
) -> None:
    if len(reference) != len(candidate):
        raise ValidationError("{} has a different row count".format(label))
    for identifier in IDENTIFIER_COLUMNS:
        if not reference[identifier].equals(candidate[identifier]):
            raise ValidationError(
                "{} is not aligned on {}".format(label, identifier)
            )


def _load_json_object(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError("Cannot read {} {}: {}".format(label, path, exc)) from exc
    if not isinstance(value, dict):
        raise ValidationError("{} must contain a JSON object".format(label))
    return value


def _load_yaml_object(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError("Cannot read {} {}: {}".format(label, path, exc)) from exc
    if not isinstance(value, dict):
        raise ValidationError("{} must contain a YAML mapping".format(label))
    return value


def _assert_numeric_equation(
    actual: pd.Series,
    expected: pd.Series,
    equation_name: str,
    tolerance: float = 1e-9,
) -> None:
    difference = (actual.astype(float) - expected.astype(float)).abs()
    if difference.isna().any() or float(difference.max()) > tolerance:
        raise ValidationError(
            "Oracle equation {} failed (maximum residual {})".format(
                equation_name, float(difference.max())
            )
        )


def _validate_oracle_equations(
    oracle: pd.DataFrame,
    run: RunSpec,
    bundle: ExportBundle,
) -> List[str]:
    """Check deterministic algebraic oracle relations in the frozen models."""

    lookup = {
        variable.raw_column: variable.oracle_column
        for variable in bundle.oracle_variables
    }
    times = oracle["simulation_time"].astype(float)
    onset = float(run.setup["sim_setup"]["faultStart"])
    # With the fixed -noEventEmit simulation call, OMC may serialize either
    # the pre-event or post-event value on a canonical output row exactly at a
    # later event boundary.  Values strictly before and after that row remain
    # unambiguous.  An intervention configured at simulation start is active
    # initially because there is no preceding state to record.
    start = float(run.setup["sim_setup"]["startTime"])
    onset_at_start = math.isclose(onset, start, rel_tol=0.0, abs_tol=1e-12)
    boundary_tolerance = max(1e-9, abs(onset) * 1e-12)
    at_onset = (times - onset).abs() <= boundary_tolerance
    recorded_after_onset = times >= onset if onset_at_start else times > onset
    checked: List[str] = []

    def raw_series(raw_column: str) -> Optional[pd.Series]:
        oracle_column = lookup.get(raw_column)
        return None if oracle_column is None else oracle[oracle_column]

    for module_name, module in sorted(run.setup["model"]["modules"].items()):
        module_type = module["type"]
        faults = module["faults"]

        window_raw = "{}.fault_window_active".format(module_name)
        window = raw_series(window_raw)
        fault_window_active = recorded_after_onset
        if window is not None:
            numeric_window = window.astype(float)
            if not numeric_window.isin((0.0, 1.0)).all():
                raise ValidationError(
                    "Oracle equation {}.fault_window_active contains a "
                    "non-Boolean value".format(module_name)
                )
            comparable = (
                pd.Series(True, index=oracle.index)
                if onset_at_start
                else ~at_onset
            )
            _assert_numeric_equation(
                numeric_window.loc[comparable],
                recorded_after_onset.loc[comparable].astype(float),
                "{}.fault_window_active".format(module_name),
            )
            fault_window_active = numeric_window.astype(bool)
            checked.append("{}.fault_window_active".format(module_name))

        factor_raw = "{}.var_pump_n".format(module_name)
        factor = raw_series(factor_raw)
        if factor is not None:
            fault_factor = (
                0.5
                if faults.get("anom_pump50")
                else 0.75 if faults.get("anom_pump75") else 1.0
            )
            expected_factor = pd.Series(1.0, index=oracle.index)
            expected_factor.loc[fault_window_active] = fault_factor
            _assert_numeric_equation(
                factor, expected_factor, "{}.pump_performance_factor".format(module_name)
            )
            checked.append("{}.pump_performance_factor".format(module_name))

            command = raw_series("{}.pump_n_in".format(module_name))
            active_states: Mapping[str, Tuple[str, ...]] = {
                "mixer": (
                    "state_emptying_tank_B201",
                    "state_emptying_tank_B202",
                    "state_emptying_tank_B203",
                ),
                "filter": ("state_emptying_tank_B101",),
                "distill": ("state_emptying_tank_B101",),
                "bottling": ("state_emptying_tank_B401",),
            }
            state_series = [
                raw_series("{}.{}.active".format(module_name, state))
                for state in active_states.get(module_type, ())
            ]
            if command is not None and state_series and all(
                state is not None for state in state_series
            ):
                active = pd.Series(False, index=oracle.index)
                for state in state_series:
                    active |= state.astype(bool)
                expected_command = active.astype(float) * 150.0 * factor.astype(float)
                _assert_numeric_equation(
                    command,
                    expected_command,
                    "{}.pump_command".format(module_name),
                )
                checked.append("{}.pump_command".format(module_name))

        heat_factor = raw_series("{}.var_heat".format(module_name))
        if heat_factor is not None:
            fault_factor = (
                0.5
                if faults.get("anom_heat50")
                else 0.75 if faults.get("anom_heat75") else 1.0
            )
            expected_factor = pd.Series(1.0, index=oracle.index)
            expected_factor.loc[fault_window_active] = fault_factor
            _assert_numeric_equation(
                heat_factor,
                expected_factor,
                "{}.heater_performance_factor".format(module_name),
            )
            checked.append("{}.heater_performance_factor".format(module_name))
            heat_flow = raw_series("{}.heater_distill.Q_flow".format(module_name))
            phase = raw_series("{}.state_destillation.active".format(module_name))
            if heat_flow is not None and phase is not None:
                expected_heat = phase.astype(float) * 20000.0 * heat_factor.astype(float)
                _assert_numeric_equation(
                    heat_flow, expected_heat, "{}.heater_input".format(module_name)
                )
                checked.append("{}.heater_input".format(module_name))

        pollution = raw_series("{}.pollution_value".format(module_name))
        if pollution is not None:
            expected_pollution = pd.Series(0.5, index=oracle.index)
            if faults.get("anom_pollution"):
                expected_pollution.loc[fault_window_active] = 1.0
            _assert_numeric_equation(
                pollution,
                expected_pollution,
                "{}.filter_pollution_factor".format(module_name),
            )
            checked.append("{}.filter_pollution_factor".format(module_name))

        valve_variables: Mapping[str, Tuple[str, str]] = {
            "var_valve_in": ("anom_valve_in0", "valve_in"),
            "var_valve_in0": ("anom_valve_in0", "valve_in0"),
            "var_valve_in1": ("anom_valve_in1", "valve_in1"),
            "var_valve_in2": ("anom_valve_in2", "valve_in2"),
        }
        for variable_name, (fault_name, component) in valve_variables.items():
            minimum_opening = raw_series(
                "{}.{}".format(module_name, variable_name)
            )
            if minimum_opening is None:
                continue
            expected_minimum = pd.Series(0.0, index=oracle.index)
            if faults.get(fault_name):
                expected_minimum.loc[fault_window_active] = 0.2
            _assert_numeric_equation(
                minimum_opening,
                expected_minimum,
                "{}.{}.minimum_opening".format(module_name, component),
            )
            checked.append("{}.{}.minimum_opening".format(module_name, component))

        leak_opening = raw_series("{}.leaking_valve.opening".format(module_name))
        if leak_opening is not None:
            expected_leak = pd.Series(0.0, index=oracle.index)
            if faults.get("anom_leaking"):
                if module_type == "distill":
                    progress = ((times - onset) / 10.0).clip(lower=0.0, upper=1.0)
                    expected_leak = 0.25 * progress.pow(2) * (3.0 - 2.0 * progress)
                else:
                    expected_leak.loc[fault_window_active] = 0.25
            _assert_numeric_equation(
                leak_opening,
                expected_leak,
                "{}.leaking_valve.opening".format(module_name),
            )
            checked.append("{}.leaking_valve.opening".format(module_name))
    return checked


def validate_release_bundle(
    bundle: ExportBundle,
    run: RunSpec,
    fault_events_path: Path,
    system_knowledge_path: Path,
    technical_timing_path: Path,
) -> Mapping[str, Any]:
    """Validate separation, alignment and metadata before releasing a run."""

    continuous = read_dataset_table(bundle.continuous)
    discrete = read_dataset_table(bundle.discrete)
    hybrid = read_dataset_table(bundle.hybrid)
    oracle = read_dataset_table(bundle.oracle_states)
    frames = {
        "continuous measurements": continuous,
        "discrete measurements": discrete,
        "hybrid measurements": hybrid,
        "oracle states": oracle,
    }
    for label, frame in frames.items():
        _validate_identifier_frame(frame, run.scenario_id, label)
        if frame is not hybrid:
            _assert_aligned(hybrid, frame, label)

    continuous_signals = set(_signal_columns(continuous))
    discrete_signals = set(_signal_columns(discrete))
    hybrid_signals = set(_signal_columns(hybrid))
    oracle_signals = set(_signal_columns(oracle))
    if continuous_signals & discrete_signals:
        raise ValidationError("Continuous and discrete measurement views overlap")
    if hybrid_signals != continuous_signals | discrete_signals:
        raise ValidationError("Hybrid measurements are not the union of both views")
    if hybrid_signals != set(bundle.safe_columns):
        raise ValidationError("Hybrid measurements differ from the export allowlist")
    validate_safe_columns(list(hybrid.columns))

    if oracle_signals != set(bundle.oracle_columns):
        raise ValidationError("Oracle table differs from the oracle catalogue")
    if hybrid_signals & oracle_signals:
        raise ValidationError("Measurement and oracle columns overlap")
    invalid_oracle_names = sorted(
        column
        for column in oracle_signals
        if ".oracle." not in column or "clogging" in column.lower()
    )
    if invalid_oracle_names:
        raise ValidationError(
            "Invalid oracle column names: {}".format(", ".join(invalid_oracle_names))
        )

    fault_events = _load_json_object(fault_events_path, "fault events")
    system_knowledge = _load_yaml_object(system_knowledge_path, "system knowledge")
    technical_timing = _load_json_object(technical_timing_path, "technical timing")
    for label, document in (
        ("fault events", fault_events),
        ("system knowledge", system_knowledge),
        ("technical timing", technical_timing),
    ):
        if document.get("scenario_id") != run.scenario_id:
            raise ValidationError("{} scenario_id does not match the run".format(label))
        if document.get("base_dataset") != run.base_dataset:
            raise ValidationError("{} base_dataset does not match the run".format(label))
        if not document.get("schema_version"):
            raise ValidationError("{} has no schema_version".format(label))

    events = fault_events.get("events")
    if not isinstance(events, list) or len(events) != (1 if run.is_fault else 0):
        raise ValidationError("Fault-event count does not match the run")
    if run.is_fault:
        event = events[0]
        if event.get("target_module") != run.target_module:
            raise ValidationError("Fault-event target does not match RunSpec")
        if event.get("configuration_flag") != run.target_fault:
            raise ValidationError("Fault-event class does not match RunSpec")
        if event.get("online_feature_allowed") is not False:
            raise ValidationError("Fault-event metadata must be non-feature data")
        event_oracle_columns = set(event.get("oracle_columns", ()))
        if not event_oracle_columns:
            raise ValidationError("Fault event has no matching oracle mechanism state")
        if not event_oracle_columns.issubset(oracle_signals):
            raise ValidationError("Fault event references an unknown oracle column")

    variable_entries = system_knowledge.get("variables")
    if not isinstance(variable_entries, list):
        raise ValidationError("System knowledge has no variable catalogue")
    by_name = {
        entry.get("name"): entry
        for entry in variable_entries
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    expected_variables = hybrid_signals | oracle_signals
    if set(by_name) != expected_variables:
        missing = sorted(expected_variables - set(by_name))
        extra = sorted(set(by_name) - expected_variables)
        raise ValidationError(
            "System variable catalogue mismatch (missing: {}; extra: {})".format(
                ", ".join(missing), ", ".join(extra)
            )
        )
    for column in hybrid_signals:
        entry = by_name[column]
        if entry.get("online_observable") is not True or entry.get(
            "online_feature_allowed"
        ) is not True:
            raise ValidationError(
                "Measurement {} is not declared as an online feature".format(column)
            )
    for column in oracle_signals:
        entry = by_name[column]
        if entry.get("online_observable") is not False or entry.get(
            "online_feature_allowed"
        ) is not False:
            raise ValidationError(
                "Oracle {} is not declared non-deployable".format(column)
            )
        if not entry.get("unit") or not entry.get("provenance"):
            raise ValidationError("Oracle {} lacks unit or provenance".format(column))

    function_names = {
        item.get("name")
        for item in system_knowledge.get("function_library", ())
        if isinstance(item, dict)
    }
    for rule in system_knowledge.get("rules", ()):
        if rule.get("function") not in function_names:
            raise ValidationError(
                "Rule {} uses an unknown function".format(rule.get("name"))
            )
        if rule.get("rule_class") not in {
            "K_imp",
            "K_score",
            "documentation_only",
        }:
            raise ValidationError(
                "Rule {} has an invalid class".format(rule.get("name"))
            )
        for required_field in (
            "valid_modes",
            "units",
            "sign_convention",
            "parameter_source",
            "delay",
            "uncertainty",
            "provenance",
        ):
            if not rule.get(required_field):
                raise ValidationError(
                    "Rule {} lacks {}".format(rule.get("name"), required_field)
                )
        unknown_conclusions = set(rule.get("conclusions", ())) - expected_variables
        if unknown_conclusions:
            raise ValidationError(
                "Rule {} has unknown conclusions".format(rule.get("name"))
            )

    knowledge_equations_checked = []
    for rule in system_knowledge.get("rules", ()):
        conclusions = rule.get("conclusions", ())
        inputs = rule.get("inputs", ())
        if (
            rule.get("function") == "threshold_comparison"
            and len(conclusions) == 1
            and conclusions[0] in hybrid_signals
            and len(inputs) == 1
            and inputs[0] in hybrid_signals
        ):
            threshold = float(rule.get("parameters", {}).get("threshold"))
            values = hybrid[inputs[0]].astype(float)
            away_from_event_boundary = (values - threshold).abs() > 1e-10
            expected = values >= threshold
            actual = hybrid[conclusions[0]].astype(bool)
            if not actual.loc[away_from_event_boundary].equals(
                expected.loc[away_from_event_boundary]
            ):
                raise ValidationError(
                    "Measurement equation {} failed".format(rule.get("name"))
                )
            knowledge_equations_checked.append(rule.get("name"))

    expected_edges = {
        str(edge_id) for edge_id in run.setup["model"]["edges"]
    }
    knowledge_edges = {
        str(edge.get("id")) for edge in system_knowledge.get("edges", ())
    }
    timing_edges = {
        str(edge.get("edge_id")) for edge in technical_timing.get("edges", ())
    }
    if knowledge_edges != expected_edges or timing_edges != expected_edges:
        raise ValidationError("Graph/timing edge metadata is incomplete")

    time_axis = technical_timing.get("time_axis", {})
    if int(time_axis.get("rows", -1)) != len(hybrid):
        raise ValidationError("Technical timing row count is inconsistent")
    expected_step = (
        float(run.setup["sim_setup"]["stopTime"])
        - float(run.setup["sim_setup"]["startTime"])
    ) / int(run.setup["sim_setup"]["numberOfIntervals"])
    if not math.isclose(
        float(time_axis.get("sample_period", float("nan"))),
        expected_step,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValidationError("Technical timing sample period is inconsistent")
    timing_channels = technical_timing.get("channels", ())
    timing_columns = {
        channel.get("column")
        for channel in timing_channels
        if isinstance(channel, dict)
    }
    if timing_columns != hybrid_signals | oracle_signals:
        raise ValidationError("Per-channel technical timing metadata is incomplete")
    for channel in timing_channels:
        if channel.get("role") not in {"measurement", "oracle_state"}:
            raise ValidationError("Technical timing has an invalid channel role")
        if not math.isclose(
            float(channel.get("sample_period", float("nan"))),
            expected_step,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValidationError("A channel has an inconsistent sample period")

    if not oracle_signals:
        raise ValidationError("The release has no exported oracle states")
    equations_checked = _validate_oracle_equations(oracle, run, bundle)

    return {
        "valid": True,
        "measurement_rows": len(hybrid),
        "continuous_columns": len(continuous_signals),
        "discrete_columns": len(discrete_signals),
        "hybrid_columns": len(hybrid_signals),
        "oracle_columns": len(oracle_signals),
        "fault_events": len(events),
        "graph_edges": len(expected_edges),
        "oracle_equations_checked": equations_checked,
        "knowledge_equations_checked": knowledge_equations_checked,
    }


def _signal_columns(frame: pd.DataFrame) -> List[str]:
    return [column for column in frame.columns if column not in IDENTIFIER_COLUMNS]


def _align_pair(normal: pd.DataFrame, fault: pd.DataFrame) -> List[str]:
    if len(normal) != len(fault):
        raise ValidationError(
            "Normal/fault row counts differ: {} versus {}".format(len(normal), len(fault))
        )
    normal_times = pd.to_numeric(normal["simulation_time"], errors="coerce")
    fault_times = pd.to_numeric(fault["simulation_time"], errors="coerce")
    if normal_times.isna().any() or fault_times.isna().any():
        raise ValidationError("Normal/fault simulation time axes contain non-numeric values")
    for index, (normal_time, fault_time) in enumerate(zip(normal_times, fault_times)):
        if not math.isclose(
            float(normal_time), float(fault_time), rel_tol=0.0, abs_tol=1e-9
        ):
            raise ValidationError(
                "Normal/fault simulation time axes differ at row {}: {} versus {}".format(
                    index, normal_time, fault_time
                )
            )
    normal_columns = set(_signal_columns(normal))
    fault_columns = set(_signal_columns(fault))
    if normal_columns != fault_columns:
        raise ValidationError("Normal/fault signal schemas differ")
    return sorted(normal_columns)


def _first_persistent_change(
    normal: pd.Series,
    fault: pd.Series,
    times: pd.Series,
    onset: float,
    absolute_tolerance: float,
    relative_tolerance: float,
    persistence: int,
) -> Optional[float]:
    difference = (fault.astype(float) - normal.astype(float)).abs()
    threshold = absolute_tolerance + relative_tolerance * normal.astype(float).abs()
    changed = (difference > threshold) & (times >= onset)
    persistent = changed.rolling(persistence, min_periods=persistence).sum() >= persistence
    matches = persistent[persistent].index
    if len(matches) == 0:
        return None
    first_end = matches[0]
    first_start = max(0, int(first_end) - persistence + 1)
    return float(times.iloc[first_start])


def _change_summary(
    normal: pd.DataFrame,
    fault: pd.DataFrame,
    columns: Sequence[str],
    onset: float,
    absolute_tolerance: float,
    relative_tolerance: float,
    persistence: int,
) -> Dict[str, Dict[str, Optional[float]]]:
    times = normal["simulation_time"]
    post_onset = times >= onset
    summary: Dict[str, Dict[str, Optional[float]]] = {}
    for column in columns:
        difference = (fault[column].astype(float) - normal[column].astype(float)).abs()
        normal_scale = normal[column].astype(float).abs().where(post_onset)
        denominator = normal_scale.where(normal_scale > absolute_tolerance)
        relative = (difference.where(post_onset) / denominator).replace(
            [float("inf"), float("-inf")], float("nan")
        )
        first_change = _first_persistent_change(
            normal[column],
            fault[column],
            times,
            onset,
            absolute_tolerance,
            relative_tolerance,
            persistence,
        )
        summary[column] = {
            "max_absolute_difference": float(difference.where(post_onset).max()),
            "max_relative_difference": (
                None if relative.dropna().empty else float(relative.max())
            ),
            "first_persistent_change": first_change,
        }
    return summary


def _effect_columns(
    frame: pd.DataFrame, module_name: str, fault_name: str
) -> List[str]:
    suffixes = DIRECT_FAULT_EFFECT_SUFFIXES.get(fault_name, ())
    return sorted(
        column
        for column in _signal_columns(frame)
        if column.startswith(module_name + ".")
        and any(column.endswith(suffix) for suffix in suffixes)
    )


def _pre_onset_max_difference(
    normal: pd.DataFrame,
    fault: pd.DataFrame,
    columns: Sequence[str],
    onset: float,
) -> float:
    before = normal["simulation_time"] < onset
    if not columns or not before.any():
        return 0.0
    return max(
        float(
            (fault[column].astype(float) - normal[column].astype(float))
            .abs()
            .where(before)
            .max()
        )
        for column in columns
    )


def _connectivity_evidence(setup: Mapping[str, Any], target: str) -> Dict[str, Any]:
    modules = setup["model"]["modules"]
    adjacency: Dict[str, List[str]] = {name: [] for name in modules}
    upstream: List[str] = []
    for source_endpoint, target_endpoint in setup["model"]["edges"].values():
        source = source_endpoint.split(".", 1)[0]
        destination = target_endpoint.split(".", 1)[0]
        adjacency[source].append(destination)
        if destination == target:
            upstream.append(source)

    reachable = set()
    queue: List[Tuple[str, List[str]]] = [(target, [target])]
    path_to_sink: Optional[List[str]] = None
    while queue:
        module, path = queue.pop(0)
        if module in reachable:
            continue
        reachable.add(module)
        if modules[module]["type"] == "sink":
            if path_to_sink is None:
                path_to_sink = path
            continue
        for destination in sorted(adjacency[module]):
            queue.append((destination, path + [destination]))

    return {
        "upstream_modules": sorted(set(upstream)),
        "immediate_downstream_modules": sorted(set(adjacency[target])),
        "reachable_downstream_modules": sorted(reachable - {target}),
        "path_to_sink": path_to_sink,
    }


def _operation_evidence(
    normal_measurements: pd.DataFrame,
    normal_verification: pd.DataFrame,
    fault_verification: pd.DataFrame,
    module_name: str,
    fault_name: str,
    onset: float,
    tolerance: float,
) -> Dict[str, Any]:
    source = normal_verification
    suffixes: Tuple[str, ...]
    if fault_name == "anom_leaking":
        source = fault_verification
        suffixes = (".leaking_valve.m_flow",)
    elif fault_name == "anom_pollution":
        source = normal_measurements
        suffixes = (".sensor_continuous_volumeFlowRate.V_flow",)
    elif fault_name.startswith("anom_pump"):
        suffixes = (".pump_n_in",)
    elif fault_name.startswith("anom_heat"):
        suffixes = (".heater_distill.Q_flow",)
    elif fault_name.startswith("anom_valve_in"):
        valve_name = fault_name.removeprefix("anom_")
        suffixes = (".{}.opening".format(valve_name),)
        if fault_name == "anom_valve_in0":
            suffixes += (".valve_in.opening",)

        columns = sorted(
            column
            for column in _signal_columns(normal_verification)
            if column.startswith(module_name + ".")
            and any(column.endswith(suffix) for suffix in suffixes)
        )
        after = normal_verification["simulation_time"] >= onset
        maxima = {
            column: float(
                (
                    fault_verification[column].astype(float)
                    - normal_verification[column].astype(float)
                )
                .abs()
                .where(after)
                .max()
            )
            for column in columns
        }
        return {
            "operated_after_onset": (
                None if not maxima else any(value > tolerance for value in maxima.values())
            ),
            "evidence_basis": "normal_fault_opening_difference",
            "evidence_columns": maxima,
        }
    else:
        suffixes = ()

    columns = sorted(
        column
        for column in _signal_columns(source)
        if column.startswith(module_name + ".")
        and any(column.endswith(suffix) for suffix in suffixes)
    )
    after = source["simulation_time"] >= onset
    maxima = {
        column: float(source[column].astype(float).abs().where(after).max())
        for column in columns
    }
    return {
        "operated_after_onset": (
            None if not maxima else any(value > tolerance for value in maxima.values())
        ),
        "evidence_basis": "post_onset_absolute_value",
        "evidence_columns": maxima,
    }


def _noise_evidence(
    normal_verification: pd.DataFrame, module_name: str, onset: float
) -> Dict[str, Any]:
    column = "{}.uniformNoise.y".format(module_name)
    if column not in normal_verification:
        return {"column": None, "minimum": None, "maximum": None, "span": None}
    values = normal_verification.loc[
        normal_verification["simulation_time"] >= onset, column
    ].astype(float)
    if values.empty:
        return {"column": column, "minimum": None, "maximum": None, "span": None}
    minimum = float(values.min())
    maximum = float(values.max())
    return {
        "column": column,
        "minimum": minimum,
        "maximum": maximum,
        "span": maximum - minimum,
        "maximum_absolute_deviation_from_one": max(
            abs(minimum - 1.0), abs(maximum - 1.0)
        ),
    }


def validate_fault_pair(
    normal_measurements_path: Path,
    fault_measurements_path: Path,
    normal_verification_path: Path,
    fault_verification_path: Path,
    normal_run: RunSpec,
    run: RunSpec,
    absolute_tolerance: float = 1e-9,
    relative_tolerance: float = 1e-7,
    persistence: int = 3,
) -> Dict[str, Any]:
    validate_matched_run_specs(normal_run, run)
    if not run.is_fault:
        raise ValueError("Fault-pair validation requires a fault RunSpec")

    normal = read_dataset_table(normal_measurements_path)
    fault = read_dataset_table(fault_measurements_path)
    safe_columns = _align_pair(normal, fault)
    validate_safe_columns(list(normal.columns))
    validate_safe_columns(list(fault.columns))

    normal_verification = read_dataset_table(normal_verification_path)
    fault_verification = read_dataset_table(fault_verification_path)
    verification_columns = _align_pair(normal_verification, fault_verification)

    onset = float(run.setup["sim_setup"]["faultStart"])
    safe_summary = _change_summary(
        normal,
        fault,
        safe_columns,
        onset,
        absolute_tolerance,
        relative_tolerance,
        persistence,
    )
    target_effect_columns = _effect_columns(
        fault_verification, run.target_module or "", run.target_fault or ""
    )
    target_summary = _change_summary(
        normal_verification,
        fault_verification,
        target_effect_columns,
        onset,
        absolute_tolerance,
        relative_tolerance,
        persistence,
    )
    verification_summary = _change_summary(
        normal_verification,
        fault_verification,
        verification_columns,
        onset,
        absolute_tolerance,
        relative_tolerance,
        persistence,
    )

    injection_observed = any(
        details["first_persistent_change"] is not None
        for details in target_summary.values()
    )
    safe_effect_observed = any(
        details["first_persistent_change"] is not None
        for details in safe_summary.values()
    )

    pre_onset_max = max(
        _pre_onset_max_difference(normal, fault, safe_columns, onset),
        _pre_onset_max_difference(
            normal_verification, fault_verification, verification_columns, onset
        ),
    )
    pre_onset_equal = pre_onset_max <= absolute_tolerance

    target_type = run.setup["model"]["modules"][run.target_module]["type"]
    non_target_changes: Dict[str, List[str]] = {}
    for module_name, module in run.setup["model"]["modules"].items():
        if module_name == run.target_module or module["type"] != target_type:
            continue
        columns = _effect_columns(
            fault_verification, module_name, run.target_fault or ""
        )
        summary = _change_summary(
            normal_verification,
            fault_verification,
            columns,
            onset,
            absolute_tolerance,
            relative_tolerance,
            persistence,
        )
        changed = [
            column
            for column, details in summary.items()
            if details["first_persistent_change"] is not None
        ]
        if changed:
            non_target_changes[module_name] = changed

    target_effect_set = set(target_effect_columns)
    changed_internal = {
        column: details
        for column, details in verification_summary.items()
        if column not in target_effect_set
        and details["first_persistent_change"] is not None
    }
    operation = _operation_evidence(
        normal,
        normal_verification,
        fault_verification,
        run.target_module or "",
        run.target_fault or "",
        onset,
        absolute_tolerance,
    )
    connectivity = _connectivity_evidence(run.setup, run.target_module or "")
    noise = _noise_evidence(
        normal_verification, run.target_module or "", onset
    )
    maximum_direct_difference = max(
        (
            float(details["max_absolute_difference"] or 0.0)
            for details in target_summary.values()
        ),
        default=0.0,
    )
    noise_deviation = noise.get("maximum_absolute_deviation_from_one")
    noise["relative_to_direct_fault_effect"] = (
        float(noise_deviation) / maximum_direct_difference
        if (run.target_fault or "").startswith("anom_pump")
        and noise_deviation is not None
        and maximum_direct_difference > 0.0
        else None
    )
    maximum_safe_difference = max(
        (
            float(details["max_absolute_difference"] or 0.0)
            for details in safe_summary.values()
        ),
        default=0.0,
    )

    if not injection_observed:
        category = "injection_failed_or_effect_channel_missing"
    elif non_target_changes:
        category = "cross_instance_fault_injection"
    elif not pre_onset_equal:
        category = "normal_fault_pair_differs_before_onset"
    elif not safe_effect_observed:
        if operation["operated_after_onset"] is False:
            category = "component_never_operated_after_onset"
        elif connectivity["path_to_sink"] is None:
            category = "topology_disconnected_the_effect"
        elif changed_internal:
            category = "change_exists_only_in_forbidden_channels"
        elif maximum_safe_difference > 0.0:
            category = "physical_effect_below_tolerance_or_masked_by_noise"
        else:
            category = "model_equation_not_coupled_to_process"
    else:
        category = "valid"

    valid = category == "valid"
    changed_safe = {
        column: details
        for column, details in safe_summary.items()
        if details["first_persistent_change"] is not None
    }
    report: Dict[str, Any] = {
        "valid": valid,
        "category": category,
        "scenario_id": run.scenario_id,
        "base_dataset": run.base_dataset,
        "target_module": run.target_module,
        "target_fault": run.target_fault,
        "fault_onset": onset,
        "difference_detection": {
            "absolute_tolerance": absolute_tolerance,
            "relative_tolerance": relative_tolerance,
            "persistence_samples": persistence,
        },
        "injection_observed": injection_observed,
        "target_effect_columns": target_summary,
        "non_target_direct_effects": non_target_changes,
        "safe_effect_observed": safe_effect_observed,
        "changed_safe_channels": changed_safe,
        "safe_channel_differences": safe_summary,
        "maximum_safe_absolute_difference": maximum_safe_difference,
        "changed_internal_channels_beyond_direct_flag": changed_internal,
        "verification_channel_differences": verification_summary,
        "component_operation": operation,
        "target_connectivity": connectivity,
        "normal_noise_evidence": noise,
        "pre_onset_max_absolute_difference": pre_onset_max,
        "verification_columns_checked": verification_columns,
    }
    return report


def write_validation_report(report: Mapping[str, Any], output_path: Path) -> None:
    output_path.write_text(
        json.dumps(dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def require_valid_report(report: Mapping[str, Any]) -> None:
    if report.get("valid"):
        return
    raise ValidationError(
        "Fault {} is not valid/detectable in {} (category: {}). See validation.json".format(
            report.get("target_fault"),
            report.get("scenario_id"),
            report.get("category"),
        )
    )
