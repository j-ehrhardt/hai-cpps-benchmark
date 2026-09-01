"""Fail-fast simulation and paired-dataset validation."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from config import RunSpec
from export import ExportError, FORBIDDEN_SAFE_FRAGMENTS, canonical_grid_indices


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


def signal_sha256(path: Path) -> str:
    """Hash only ordered signal values, excluding scenario/time identifiers."""

    frame = pd.read_csv(path)
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


def _signal_columns(frame: pd.DataFrame) -> List[str]:
    return [column for column in frame.columns if column not in IDENTIFIER_COLUMNS]


def _align_pair(normal: pd.DataFrame, fault: pd.DataFrame) -> List[str]:
    if len(normal) != len(fault):
        raise ValidationError(
            "Normal/fault row counts differ: {} versus {}".format(len(normal), len(fault))
        )
    if not normal["simulation_time"].equals(fault["simulation_time"]):
        raise ValidationError("Normal/fault simulation time axes differ")
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

    normal = pd.read_csv(normal_measurements_path)
    fault = pd.read_csv(fault_measurements_path)
    safe_columns = _align_pair(normal, fault)
    validate_safe_columns(list(normal.columns))
    validate_safe_columns(list(fault.columns))

    normal_verification = pd.read_csv(normal_verification_path)
    fault_verification = pd.read_csv(fault_verification_path)
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
