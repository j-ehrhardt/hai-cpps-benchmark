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


@dataclass(frozen=True)
class DiagnosisDataset:
    """Permitted observations with identifiers and evaluation references separated."""
    online_features: pd.DataFrame
    identifiers: pd.DataFrame
    oracle_states: Optional[pd.DataFrame] = None
    annotations: Optional[Mapping[str, Any]] = None


def load_diagnosis_dataset(scenario_dir: Path, measurement_view: str = "hybrid",
                           include_oracle: bool = False,
                           include_annotations: bool = False) -> DiagnosisDataset:
    import re
    import numpy as np
    from actuator_channels import SCHEMA_VERSION, command_specs
    from export import classify_columns
    from export_v2_1 import check_alignment

    root = Path(scenario_dir)
    if measurement_view not in MEASUREMENT_VIEWS:
        raise ValueError("Unknown measurement view")
    policy = _read_json(root / "permitted_inputs.json")
    if policy.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported diagnosis schema")
    allowed_measurements = policy.get("measurements", [])
    continuous, discrete, _ = classify_columns(allowed_measurements)
    if sorted(continuous + discrete) != sorted(allowed_measurements):
        raise ValueError("Policy contains a non-measurement input")
    pattern = r"^[A-Za-z_][A-Za-z0-9_]*\.command\.(?:pump_P(?:101|401)\.speed|valve_[A-Za-z0-9_]+\.opening|(?:heater_distill|cooler_B10[23])\.heat_flow)$"
    allowed_commands = policy.get("commands", [])
    if not allowed_commands or len(set(allowed_commands)) != len(allowed_commands) or any(not re.fullmatch(pattern, c) for c in allowed_commands):
        raise ValueError("Policy contains an invalid controller command")
    module_types = policy.get("module_types", {})
    if not module_types or any(t not in {"mixer", "filter", "distill", "bottling", "source", "sink"} for t in module_types.values()):
        raise ValueError("Invalid diagnostic module registry")
    expected_commands = [s.name for s in command_specs({"model": {"modules": {n: {"type": t} for n, t in module_types.items()}}})]
    if allowed_commands != expected_commands:
        raise ValueError("Policy commands differ from module registry")
    if policy.get("actuator_responses") != []:
        raise ValueError("This registry has no measured actuator responses")
    measurements = pd.read_parquet(root / measurement_view / "measurements.parquet")
    commands = pd.read_parquet(root / "commands.parquet")
    expected = {"hybrid": allowed_measurements, "continuous": continuous, "discrete": discrete}[measurement_view]
    if set(measurements) != set(IDENTIFIER_COLUMNS) | set(expected):
        raise ValueError("Measurement table differs from permitted inputs")
    if list(commands) != list(IDENTIFIER_COLUMNS) + allowed_commands:
        raise ValueError("Command table differs from permitted inputs")
    check_alignment(measurements, commands)
    features = pd.concat([measurements[sorted(expected)], commands[allowed_commands]], axis=1)
    if not np.isfinite(features.to_numpy(dtype=float)).all():
        raise ValueError("Diagnostic inputs contain nonfinite values")
    oracle = pd.read_parquet(root / "oracle_states.parquet") if include_oracle else None
    if oracle is not None:
        check_alignment(measurements, oracle)
    annotations = None
    if include_annotations:
        annotations = {name: _read_json(root / (name + ".json"))
                       for name in ("fault_events", "technical_timing")}
    return DiagnosisDataset(features, measurements[list(IDENTIFIER_COLUMNS)].copy(), oracle, annotations)
