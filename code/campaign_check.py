"""Validate a complete sharded HAI-CPPS v2.2 release."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List

import pandas as pd


SCHEMA = "2.2.0"
EXPECTED_FAULTS = {
    "ds1": 6,
    "ds2": 6,
    "ds3": 5,
    "ds4": 4,
    "ds5": 10,
    "ds6": 14,
    "ds7": 9,
    "ds8": 15,
    "ds9": 19,
    "ds10": 7,
}
REQUIRED = (
    "continuous/measurements.parquet",
    "discrete/measurements.parquet",
    "hybrid/measurements.parquet",
    "commands.parquet",
    "oracle_states.parquet",
    "audit_for_verification/internal_verification.csv",
    "sim_setup.json",
    "fault_events.json",
    "channel_catalogue.yaml",
    "permitted_inputs.json",
    "system_knowledge.yaml",
    "technical_timing.json",
    "provenance.json",
    "validation.json",
)
NAME = re.compile(
    r"^(ds(?:10|[1-9]))_(\d{3})_(healthy|[A-Za-z0-9]+_anom_[A-Za-z0-9_]+_(persistent|temporal))$"
)


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def issue(report: Dict[str, Any], category: str, detail: str) -> None:
    report["errors"].append({"category": category, "detail": detail})


def check_identifiers(frame: pd.DataFrame, scenario: str, label: str, report: Dict[str, Any]) -> None:
    required = ["scenario_id", "simulation_step", "simulation_time"]
    if not set(required).issubset(frame):
        issue(report, "missing_identifiers", f"{scenario}:{label}")
        return
    if len(frame) != 25001:
        issue(report, "row_count", f"{scenario}:{label}:{len(frame)}")
    if not frame["scenario_id"].eq(scenario).all():
        issue(report, "scenario_id", f"{scenario}:{label}")
    if not frame["simulation_step"].reset_index(drop=True).equals(
        pd.Series(range(25001), name="simulation_step")
    ):
        issue(report, "simulation_step", f"{scenario}:{label}")
    expected_time = pd.Series(range(25001), dtype=float, name="simulation_time")
    if not frame["simulation_time"].astype(float).reset_index(drop=True).equals(expected_time):
        issue(report, "simulation_time", f"{scenario}:{label}")


def check_scenario(path: Path, entry: Dict[str, Any], report: Dict[str, Any]) -> None:
    scenario = entry["scenario_id"]
    match = NAME.fullmatch(scenario)
    if not match or match.group(1) != entry["topology"]:
        issue(report, "scenario_name", scenario)
        return
    missing = [name for name in REQUIRED if not (path / name).is_file()]
    if missing:
        issue(report, "missing_artifact", f"{scenario}:{','.join(missing)}")
        return

    setup = read_json(path / "sim_setup.json")
    simulation = setup.get("setup", {}).get("sim_setup", {})
    if setup.get("release_schema_version") != SCHEMA:
        issue(report, "schema", scenario)
    expected_clock = {
        "startTime": 0,
        "stopTime": 25000,
        "numberOfIntervals": 25000,
        "faultStart": 2500,
    }
    if any(simulation.get(key) != value for key, value in expected_clock.items()):
        issue(report, "simulation_clock", scenario)
    if setup.get("fault_variant") != entry.get("fault_variant"):
        issue(report, "variant_identity", scenario)

    tables = {
        "hybrid": pd.read_parquet(path / "hybrid/measurements.parquet"),
        "commands": pd.read_parquet(path / "commands.parquet"),
        "oracle": pd.read_parquet(path / "oracle_states.parquet"),
    }
    for label, frame in tables.items():
        check_identifiers(frame, scenario, label, report)
    identifiers = ["scenario_id", "simulation_step", "simulation_time"]
    for label in ("commands", "oracle"):
        left = tables["hybrid"][identifiers].copy()
        right = tables[label][identifiers].copy()
        left["scenario_id"] = scenario
        if not left.equals(right):
            issue(report, "table_alignment", f"{scenario}:{label}")

    provenance = read_json(path / "provenance.json")
    for relative, expected in provenance.get("release", {}).get("artifact_sha256", {}).items():
        artifact = path / relative
        if not artifact.is_file() or digest(artifact) != expected:
            issue(report, "artifact_hash", f"{scenario}:{relative}")

    validation = read_json(path / "validation.json")
    if validation.get("valid") is not True:
        issue(report, "scenario_validation", scenario)

    if entry["healthy"]:
        if read_json(path / "fault_events.json").get("events"):
            issue(report, "healthy_fault_event", scenario)
        return

    variant = entry.get("fault_variant")
    expected = {"persistent": ("001", None), "temporal": ("002", 7500)}
    if variant not in expected:
        issue(report, "fault_variant", scenario)
        return
    expected_ordinal, expected_end = expected[variant]
    if (match.group(2) != expected_ordinal or match.group(4) != variant
            or simulation.get("faultEnd") != expected_end):
        issue(report, "fault_window_identity", scenario)
    events = read_json(path / "fault_events.json")
    if events.get("schema_version") != SCHEMA or len(events.get("events", [])) != 1:
        issue(report, "fault_events", scenario)
    else:
        event = events["events"][0]
        if (
            event.get("fault_variant") != variant
            or event.get("deactivation_time") != expected_end
            or event.get("active_duration_steps") != (22500 if expected_end is None else 5000)
        ):
            issue(report, "fault_event_window", scenario)

    window_columns = [
        column
        for column in tables["oracle"]
        if column.endswith(".oracle.experiment.fault_window.active")
    ]
    time = tables["oracle"]["simulation_time"].astype(float)
    before = time < 2500
    inside = (time > 2500) & (time < (expected_end or 25001))
    after = time > expected_end if expected_end is not None else pd.Series(False, index=time.index)
    for column in window_columns:
        values = tables["oracle"][column].astype(bool)
        if values[before].any() or not values[inside].all() or values[after].any():
            issue(report, "oracle_fault_window", f"{scenario}:{column}")
    if expected_end is not None and validation.get("direct_effect_returned_to_nominal") is not True:
        issue(report, "finite_deactivation", scenario)


def check_campaign(root: Path, topologies=None) -> Dict[str, Any]:
    report: Dict[str, Any] = {"root": str(root.resolve()), "errors": [], "shards": {}}
    all_entries: List[Dict[str, Any]] = []
    selected = EXPECTED_FAULTS if topologies is None else {
        name: EXPECTED_FAULTS[name] for name in topologies
    }
    for topology, expected_faults in selected.items():
        shard = root / topology
        manifest_path = shard / "campaign.json"
        if not manifest_path.is_file():
            issue(report, "missing_manifest", topology)
            continue
        manifest = read_json(manifest_path)
        entries = manifest.get("recordings", [])
        completed = set(manifest.get("completed", []))
        planned = {entry.get("scenario_id") for entry in entries}
        healthy = [entry for entry in entries if entry.get("healthy")]
        faulty = [entry for entry in entries if not entry.get("healthy")]
        if (
            manifest.get("schema_version") != SCHEMA
            or manifest.get("campaign_version") != "recorded-commands-3"
            or manifest.get("recordings_per_fault") != 2
        ):
            issue(report, "manifest_schema", topology)
        if len(healthy) != 16 or len(faulty) != 2 * expected_faults:
            issue(report, "manifest_counts", f"{topology}:{len(healthy)}:{len(faulty)}")
        if completed != planned:
            issue(report, "incomplete_manifest", f"{topology}:{len(completed)}/{len(planned)}")
        for entry in entries:
            check_scenario(shard / topology / entry["scenario_id"], entry, report)
        all_entries.extend(entries)
        report["shards"][topology] = {
            "healthy": len(healthy),
            "fault_recordings": len(faulty),
            "status": manifest.get("status"),
        }

    names = [entry.get("scenario_id") for entry in all_entries]
    expected_count = 16 * len(selected) + 2 * sum(selected.values())
    if len(names) != expected_count or len(set(names)) != expected_count:
        issue(report, "release_count", f"{len(names)}:{len(set(names))}")
    report["recordings"] = len(names)
    report["valid"] = not report["errors"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = check_campaign(args.root)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        f"v2.2 campaign: valid={report['valid']} recordings={report['recordings']} "
        f"errors={len(report['errors'])}"
    )
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
