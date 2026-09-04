"""Create separated measurement and oracle datasets from one OMC result.

The OpenModelica invocation is deliberately outside this module's scope.  This
exporter consumes only the columns already present in the fixed raw result and
creates three deployable measurement views plus one non-deployable oracle view.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd


class ExportError(RuntimeError):
    """Raised when safe dataset export cannot be guaranteed."""


@dataclass(frozen=True)
class OracleVariable:
    """One explicitly classified raw-to-oracle column mapping."""

    raw_column: str
    oracle_column: str
    module: str
    component: str
    kind: str
    unit: str
    oracle_role: str
    direct_fault_revealing: bool = False


@dataclass(frozen=True)
class ExportBundle:
    continuous: Path
    discrete: Path
    hybrid: Path
    oracle_states: Path
    verification: Path
    safe_columns: Tuple[str, ...]
    oracle_columns: Tuple[str, ...]
    oracle_variables: Tuple[OracleVariable, ...]


_CONTINUOUS_PATTERNS = (
    re.compile(r"^[^.]+\.tank_[A-Za-z0-9_]+\.level$"),
    re.compile(r"^[^.]+\.sensor_continuous_pressure_[A-Za-z0-9_]+\.p$"),
    re.compile(
        r"^[^.]+\.sensor_continuous_volumeFlowRate(?:_[A-Za-z0-9_]+)?\.V_flow$"
    ),
    re.compile(r"^[^.]+\.sensor_continuous_temperature_[A-Za-z0-9_]+\.T$"),
)
_DISCRETE_PATTERNS = (
    re.compile(r"^[^.]+\.sensor_discrete_[A-Za-z0-9_]+\.showActive$"),
)
_VERIFICATION_PATTERNS = (
    re.compile(r"^[^.]+\.state_[A-Za-z0-9_]+\.active$"),
    re.compile(r"^[^.]+\.[A-Za-z0-9_]*valve[A-Za-z0-9_]*\.opening$"),
    re.compile(r"^[^.]+\.filter_[A-Za-z0-9_]+\.opening$"),
    re.compile(r"^[^.]+\.pump_[A-Za-z0-9_]+\.N_in$"),
    re.compile(r"^[^.]+\.pump_n_in$"),
    re.compile(r"^[^.]+\.uniformNoise\.y$"),
    re.compile(r"^[^.]+\.fault_window_active$"),
    re.compile(r"^[^.]+\.var_[A-Za-z0-9_]+$"),
    re.compile(r"^[^.]+\.leaking_valve\.m_flow$"),
    re.compile(r"^[^.]+\.pollution_value$"),
    re.compile(r"^[^.]+\.heater_[A-Za-z0-9_]+\.Q_flow$"),
)

FORBIDDEN_SAFE_FRAGMENTS = (
    "anom_",
    "clogging_valve",
    "leaking_valve",
    "pump_n_in",
    ".N_in",
    ".opening",
    ".state_",
    ".var_",
    "pollution_value",
    "fault_window_active",
)

IDENTIFIER_COLUMNS = ("scenario_id", "simulation_step", "simulation_time")


def _oracle_name(
    module: str,
    namespace: str,
    component: str,
    quantity: str,
) -> str:
    return "{}.oracle.{}.{}.{}".format(module, namespace, component, quantity)


def _oracle_variable(column: str) -> Optional[OracleVariable]:
    """Return the deliberate semantic oracle mapping for one raw column.

    This is an allowlist.  Unknown internals are retained in the private audit
    export only.  Clogging variables are intentionally omitted from every new
    release artifact.
    """

    if "clogging" in column or "." not in column:
        return None
    module, local = column.split(".", 1)

    state_match = re.fullmatch(r"(state_[A-Za-z0-9_]+)\.active", local)
    if state_match:
        component = state_match.group(1)
        return OracleVariable(
            column,
            _oracle_name(module, "operation_phase", component, "active"),
            module,
            component,
            "operation_phase_indicator",
            "1",
            "operation_state",
        )

    if local == "fault_window_active":
        return OracleVariable(
            column,
            _oracle_name(module, "experiment", "fault_window", "active"),
            module,
            "fault_window",
            "injection_window_indicator",
            "1",
            "experiment_state",
            True,
        )

    fault_mechanisms = {
        "var_pump_n": ("pump", "performance_factor"),
        "var_heat": ("heater", "performance_factor"),
        "var_valve_in": ("valve_in", "minimum_opening"),
        "var_valve_in0": ("valve_in0", "minimum_opening"),
        "var_valve_in1": ("valve_in1", "minimum_opening"),
        "var_valve_in2": ("valve_in2", "minimum_opening"),
        "pollution_value": ("filter", "pollution_factor"),
    }
    if local in fault_mechanisms:
        component, quantity = fault_mechanisms[local]
        return OracleVariable(
            column,
            _oracle_name(module, "fault_mechanism", component, quantity),
            module,
            component,
            "fault_mechanism_state",
            "1",
            "fault_mechanism_state",
            True,
        )

    if local == "pump_n_in":
        return OracleVariable(
            column,
            _oracle_name(module, "actuator_command", "pump", "speed"),
            module,
            "pump",
            "actuator_command",
            "rev/min",
            "actuator_state",
        )

    pump_match = re.fullmatch(r"(pump_[A-Za-z0-9_]+)\.N_in", local)
    if pump_match:
        component = pump_match.group(1)
        return OracleVariable(
            column,
            _oracle_name(module, "actuator_effective", component, "speed"),
            module,
            component,
            "effective_actuator_input",
            "rev/min",
            "actuator_state",
        )

    if local == "uniformNoise.y":
        return OracleVariable(
            column,
            _oracle_name(module, "disturbance", "pump", "speed_multiplier"),
            module,
            "uniformNoise",
            "actuator_disturbance_multiplier",
            "1",
            "disturbance_state",
        )

    if local == "leaking_valve.m_flow":
        return OracleVariable(
            column,
            _oracle_name(module, "fault_mechanism", "leaking_valve", "mass_flow"),
            module,
            "leaking_valve",
            "realized_fault_flow",
            "kg/s",
            "fault_mechanism_state",
            True,
        )

    valve_match = re.fullmatch(r"([A-Za-z0-9_]*valve[A-Za-z0-9_]*)\.opening", local)
    if valve_match:
        component = valve_match.group(1)
        namespace = (
            "fault_mechanism" if component == "leaking_valve" else "actuator_effective"
        )
        return OracleVariable(
            column,
            _oracle_name(module, namespace, component, "opening"),
            module,
            component,
            (
                "fault_mechanism_state"
                if component == "leaking_valve"
                else "effective_actuator_input"
            ),
            "1",
            (
                "fault_mechanism_state"
                if component == "leaking_valve"
                else "actuator_state"
            ),
            component == "leaking_valve",
        )

    filter_match = re.fullmatch(r"(filter_[A-Za-z0-9_]+)\.opening", local)
    if filter_match:
        component = filter_match.group(1)
        return OracleVariable(
            column,
            _oracle_name(module, "process_state", component, "effective_opening"),
            module,
            component,
            "effective_filter_opening",
            "1",
            "process_state",
        )

    heater_match = re.fullmatch(r"(heater_[A-Za-z0-9_]+)\.Q_flow", local)
    if heater_match:
        component = heater_match.group(1)
        return OracleVariable(
            column,
            _oracle_name(module, "actuator_effective", component, "heat_flow"),
            module,
            component,
            "effective_heat_input",
            "W",
            "actuator_state",
        )
    return None


def _matches_any(column: str, patterns: Iterable[re.Pattern[str]]) -> bool:
    return any(pattern.fullmatch(column) for pattern in patterns)


def canonical_grid_indices(
    times: pd.Series, sim_setup: Mapping[str, object]
) -> List[int]:
    """Select the last row at each configured output time, excluding event rows."""

    grid = canonical_grid_times(sim_setup)
    step = grid[1] - grid[0] if len(grid) > 1 else 0.0
    tolerance = max(1e-9, abs(step) * 1e-8)
    values = pd.to_numeric(times, errors="coerce")
    if values.isna().any():
        raise ExportError("Simulation time contains non-numeric values")

    indices: List[int] = []
    cursor = 0
    raw_times = values.tolist()
    for expected in grid:
        while (
            cursor + 1 < len(raw_times)
            and raw_times[cursor + 1] <= expected + tolerance
        ):
            cursor += 1
        if cursor >= len(raw_times) or abs(raw_times[cursor] - expected) > tolerance:
            raise ExportError(
                "Raw result has no output row for configured time {}".format(expected)
            )
        indices.append(cursor)
    return indices


def canonical_grid_times(sim_setup: Mapping[str, object]) -> List[float]:
    """Return the one canonical timestamp sequence used by every safe export."""

    start = float(sim_setup["startTime"])
    stop = float(sim_setup["stopTime"])
    intervals = int(sim_setup["numberOfIntervals"])
    step = (stop - start) / intervals
    return [start + output_step * step for output_step in range(intervals + 1)]


def classify_columns(columns: Sequence[str]) -> Tuple[List[str], List[str], List[str]]:
    """Return explicit continuous, discrete, and verification raw columns."""

    continuous = sorted(
        column for column in columns if _matches_any(column, _CONTINUOUS_PATTERNS)
    )
    discrete = sorted(
        column for column in columns if _matches_any(column, _DISCRETE_PATTERNS)
    )
    verification = sorted(
        column
        for column in columns
        if "clogging_valve" not in column
        and _matches_any(column, _VERIFICATION_PATTERNS)
    )
    return continuous, discrete, verification


def classify_oracle_variables(columns: Sequence[str]) -> List[OracleVariable]:
    """Return deterministic, semantically named oracle mappings."""

    variables = [
        variable
        for column in columns
        for variable in [_oracle_variable(column)]
        if variable is not None
    ]
    variables.sort(key=lambda variable: variable.oracle_column)
    names = [variable.oracle_column for variable in variables]
    if len(names) != len(set(names)):
        raise ExportError("Oracle semantic column names are not unique")
    return variables


def assert_leakage_safe(columns: Iterable[str]) -> None:
    leaked = sorted(
        column
        for column in columns
        if any(fragment in column for fragment in FORBIDDEN_SAFE_FRAGMENTS)
    )
    if leaked:
        raise ExportError(
            "Unsafe internal/fault columns selected for measurements: {}".format(
                ", ".join(leaked)
            )
        )


def _base_frame(raw: pd.DataFrame, scenario_id: str) -> pd.DataFrame:
    if "time" not in raw.columns:
        raise ExportError("OpenModelica result has no 'time' column")
    return pd.DataFrame(
        {
            "scenario_id": scenario_id,
            "simulation_step": range(len(raw)),
            "simulation_time": raw["time"],
        }
    )


def _with_signals(
    base: pd.DataFrame, raw: pd.DataFrame, signal_columns: Sequence[str]
) -> pd.DataFrame:
    result = base.copy()
    for column in signal_columns:
        result[column] = raw[column]
    return result


def _with_renamed_signals(
    base: pd.DataFrame,
    raw: pd.DataFrame,
    variables: Sequence[OracleVariable],
) -> pd.DataFrame:
    result = base.copy()
    for variable in variables:
        result[variable.oracle_column] = raw[variable.raw_column]
    return result


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        frame.to_parquet(path, index=False, engine="pyarrow")
    except (ImportError, ModuleNotFoundError) as exc:
        raise ExportError(
            "Parquet export requires pyarrow; recreate the project environment "
            "from venv.yml"
        ) from exc
    except Exception as exc:
        raise ExportError(
            "Could not write Parquet dataset {}: {}".format(path, exc)
        ) from exc


def export_result_files(
    raw_path: Path,
    output_dir: Path,
    scenario_id: str,
    sim_setup: Mapping[str, object],
) -> ExportBundle:
    raw = pd.read_csv(raw_path, index_col=False)
    continuous_columns, discrete_columns, verification_columns = classify_columns(
        list(raw.columns)
    )
    oracle_variables = classify_oracle_variables(verification_columns)
    if not continuous_columns:
        raise ExportError("No allowlisted continuous sensor channels found")
    if not discrete_columns:
        raise ExportError("No allowlisted discrete sensor channels found")

    assert_leakage_safe(continuous_columns)
    assert_leakage_safe(discrete_columns)

    canonical_times = canonical_grid_times(sim_setup)
    raw = raw.iloc[canonical_grid_indices(raw["time"], sim_setup)].reset_index(
        drop=True
    )
    # OMC's equivalent output grids can differ by round-off between runs.
    raw["time"] = canonical_times
    selected_columns = sorted(
        set(continuous_columns + discrete_columns + verification_columns)
    )
    selected_values = raw[selected_columns].apply(
        pd.to_numeric, errors="coerce"
    )
    if selected_values.isna().any().any() or not selected_values.apply(
        lambda column: column.map(math.isfinite)
    ).all().all():
        raise ExportError("Selected result channels contain missing or non-finite values")

    base = _base_frame(raw, scenario_id)
    continuous = _with_signals(base, raw, continuous_columns)
    discrete = _with_signals(base, raw, discrete_columns)
    hybrid_columns = sorted(set(continuous_columns + discrete_columns))
    hybrid = _with_signals(base, raw, hybrid_columns)
    oracle = _with_renamed_signals(base, raw, oracle_variables)
    verification = _with_signals(base, raw, verification_columns)

    output_dir.mkdir(parents=True, exist_ok=True)
    continuous_path = output_dir / "continuous" / "measurements.parquet"
    discrete_path = output_dir / "discrete" / "measurements.parquet"
    hybrid_path = output_dir / "hybrid" / "measurements.parquet"
    oracle_path = output_dir / "oracle_states.parquet"
    verification_path = output_dir / "audit" / "internal_verification.csv"

    _write_parquet(continuous, continuous_path)
    _write_parquet(discrete, discrete_path)
    _write_parquet(hybrid, hybrid_path)
    _write_parquet(oracle, oracle_path)
    verification_path.parent.mkdir(parents=True, exist_ok=True)
    verification.to_csv(verification_path, index=False)

    return ExportBundle(
        continuous_path,
        discrete_path,
        hybrid_path,
        oracle_path,
        verification_path,
        tuple(hybrid_columns),
        tuple(variable.oracle_column for variable in oracle_variables),
        tuple(oracle_variables),
    )


def export_result_csvs(
    raw_path: Path,
    output_dir: Path,
    scenario_id: str,
    sim_setup: Mapping[str, object],
) -> ExportBundle:
    """Backward-compatible function name for the release-file exporter."""

    return export_result_files(raw_path, output_dir, scenario_id, sim_setup)
