"""Create conservative Part 1 datasets from one OpenModelica result."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import pandas as pd


class ExportError(RuntimeError):
    """Raised when safe dataset export cannot be guaranteed."""


@dataclass(frozen=True)
class ExportBundle:
    continuous: Path
    discrete: Path
    hybrid: Path
    verification: Path
    safe_columns: Tuple[str, ...]


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


def export_result_csvs(
    raw_path: Path,
    output_dir: Path,
    scenario_id: str,
    sim_setup: Mapping[str, object],
) -> ExportBundle:
    raw = pd.read_csv(raw_path, index_col=False)
    continuous_columns, discrete_columns, verification_columns = classify_columns(
        list(raw.columns)
    )
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
    verification = _with_signals(base, raw, verification_columns)

    output_dir.mkdir(parents=True, exist_ok=True)
    continuous_path = output_dir / "{}_continuous.csv".format(scenario_id)
    discrete_path = output_dir / "{}_discrete.csv".format(scenario_id)
    hybrid_path = output_dir / "{}_hybrid.csv".format(scenario_id)
    verification_path = output_dir / "verification.csv"

    continuous.to_csv(continuous_path, index=False)
    discrete.to_csv(discrete_path, index=False)
    hybrid.to_csv(hybrid_path, index=False)
    verification.to_csv(verification_path, index=False)

    return ExportBundle(
        continuous_path,
        discrete_path,
        hybrid_path,
        verification_path,
        tuple(hybrid_columns),
    )
