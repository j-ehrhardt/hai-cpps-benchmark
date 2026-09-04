"""Leakage-safe loading helpers for generated HAI-CPPS releases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

import pandas as pd
import yaml


MEASUREMENT_VIEWS = ("continuous", "discrete", "hybrid")
IDENTIFIER_COLUMNS = ("scenario_id", "simulation_step", "simulation_time")


@dataclass(frozen=True)
class ScenarioDataset:
    """A measurement view and optional, still-separated offline oracle data."""

    measurements: pd.DataFrame
    oracle_states: Optional[pd.DataFrame]
    fault_events: Mapping[str, Any]
    system_knowledge: Mapping[str, Any]
    technical_timing: Mapping[str, Any]

    @property
    def online_features(self) -> pd.DataFrame:
        """Return only deployable signal columns, excluding scenario/time IDs."""

        return self.measurements.drop(columns=list(IDENTIFIER_COLUMNS))


def _read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object in {}".format(path))
    return value


def load_scenario_dataset(
    scenario_dir: Path,
    measurement_view: str = "hybrid",
    include_oracle: bool = False,
) -> ScenarioDataset:
    """Load one scenario without ever merging oracle values into measurements.

    Oracle loading is opt-in and returns a second DataFrame.  This preserves a
    visible boundary even for offline evaluation code.
    """

    scenario_dir = scenario_dir.resolve()
    if measurement_view not in MEASUREMENT_VIEWS:
        raise ValueError(
            "measurement_view must be one of {}".format(", ".join(MEASUREMENT_VIEWS))
        )
    measurements = pd.read_parquet(
        scenario_dir / measurement_view / "measurements.parquet",
        engine="pyarrow",
    )
    oracle_states = (
        pd.read_parquet(scenario_dir / "oracle_states.parquet", engine="pyarrow")
        if include_oracle
        else None
    )
    if oracle_states is not None:
        for identifier in IDENTIFIER_COLUMNS:
            if not measurements[identifier].equals(oracle_states[identifier]):
                raise ValueError(
                    "Measurements and oracle are not aligned on {}".format(identifier)
                )

    system_knowledge = yaml.safe_load(
        (scenario_dir / "system_knowledge.yaml").read_text(encoding="utf-8")
    )
    if not isinstance(system_knowledge, dict):
        raise ValueError("system_knowledge.yaml must contain a mapping")
    return ScenarioDataset(
        measurements=measurements,
        oracle_states=oracle_states,
        fault_events=_read_json(scenario_dir / "fault_events.json"),
        system_knowledge=system_knowledge,
        technical_timing=_read_json(scenario_dir / "technical_timing.json"),
    )
