"""Independent healthy splits and matched test pairs for a fresh diagnosis release.

Planning is the default. Pass --run to execute; --resume verifies completed outputs.
Existing v2/v2.1 releases and backup directories are never campaign destinations.
"""
import argparse
import copy
from dataclasses import replace
from pathlib import Path
import shutil

import pandas as pd

from actuator_channels import command_specs, recorded_commands
from config import load_benchmark_config, generate_normal_campaign, generate_single_fault_campaign
from export_v2_1 import AUDIT_PATH, read_json, write_json, digest
from sim import DEFAULT_CONFIG, _execute_run, _set_seed, _validate_pair
from validation import duplicate_signal_groups

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COUNTS = {"train": 10, "validation": 3, "calibration": 2, "test": 1}
# All 100 fault recordings in the existing preliminary release use this seed.
DEFAULT_FAULT_SEED = 42


def plan_campaign(benchmark, counts=None, seed=20261005, topologies=None, fault_seed=DEFAULT_FAULT_SEED):
    counts = dict(DEFAULT_COUNTS if counts is None else counts)
    if set(counts) != set(DEFAULT_COUNTS) or any(type(n) is not int or n < 1 for n in counts.values()):
        raise ValueError("Each of train/validation/calibration/test requires a positive recording count")
    selected = sorted(benchmark if topologies is None else topologies)
    if not set(selected) <= set(benchmark):
        raise ValueError("Unknown topology")
    if (seed < 1 or seed + len(selected)*sum(counts.values()) + 1 >= 2147483647
            or not 1 <= fault_seed < 2147483647):
        raise ValueError("Campaign seeds must fit positive Modelica integers")
    result = []
    next_seed = seed
    for topology in selected:
        for split in DEFAULT_COUNTS:
            for index in range(counts[split]):
                paired_control = split == "test" and index == 0
                # Reserve the working fault seed for exactly one healthy test control.
                if next_seed == fault_seed:
                    next_seed += 1
                run_seed = fault_seed if paired_control else next_seed
                if not paired_control:
                    next_seed += 1
                config = copy.deepcopy(benchmark)
                _set_seed(config, run_seed)
                group = f"{topology}_{split}_{index+1:03d}_seed{run_seed}"
                normal = generate_normal_campaign(config, [topology])[0]
                normal = replace(normal, scenario_id=group + "_healthy")
                normal.setup["ds_name"] = normal.scenario_id
                result.append((normal, split, group, None))
                if paired_control:
                    for fault in generate_single_fault_campaign(config, [topology]):
                        fault = replace(fault, scenario_id=group + "_" + fault.target_module + "_" + fault.target_fault)
                        fault.setup["ds_name"] = fault.scenario_id
                        result.append((fault, split, group, normal.scenario_id))
    return result


def coverage(path, run):
    audit = pd.read_csv(path / AUDIT_PATH)
    commands = recorded_commands(audit, run.setup)
    if commands is None:
        raise ValueError("Fresh simulations must contain directly recorded commands")
    observed = {}
    missing = []
    for spec in command_specs(run.setup):
        values = sorted(float(v) for v in commands[spec.name].unique())
        expected = sorted(set([spec.off, spec.on]))
        observed[spec.name] = {"observed": values, "expected": expected}
        if values != expected:
            missing.append(spec.name)
    phases = {c: bool(audit[c].astype(bool).any()) for c in audit
              if ".state_" in c and c.endswith(".active")}
    return {"commands": observed, "missing_command_ranges": missing,
            "controller_phases_observed": phases,
            "unvisited_controller_phases": [c for c, active in phases.items() if not active]}


def protected_destination(path):
    path = path.resolve()
    for name in ("v2", "v2.1", "backup"):
        protected = ROOT / "data" / name
        if path == protected or protected in path.parents or path in protected.parents:
            raise ValueError(f"Campaign destination overlaps protected release: {name}")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=ROOT / "data/v2.1-rerun")
    parser.add_argument("--build-root", type=Path, default=ROOT / "build/diagnosis-rerun")
    parser.add_argument("--seed", type=int, default=20261005)
    parser.add_argument("--fault-seed", type=int, default=DEFAULT_FAULT_SEED,
                        help="seed for each fault and its healthy test control (default: existing release seed 42)")
    parser.add_argument("--topology", action="append")
    for split, count in DEFAULT_COUNTS.items():
        parser.add_argument(f"--{split}", type=int, default=count)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-runs", type=int, help="Stop after this many planned runs (pilot only; release stays incomplete)")
    args = parser.parse_args(argv)
    if args.max_runs is not None and args.max_runs < 1:
        parser.error("--max-runs must be positive")
    output = protected_destination(args.output)
    build = protected_destination(args.build_root)
    if output == build or output in build.parents or build in output.parents:
        parser.error("Build and release roots must be separate")
    config = args.config.resolve()
    plans = plan_campaign(load_benchmark_config(config), {s: getattr(args, s) for s in DEFAULT_COUNTS}, args.seed, args.topology, args.fault_seed)
    entries = [{"scenario_id": r.scenario_id, "topology": r.base_dataset, "split": split,
                "seed": r.setup["sim_setup"]["seed"], "pair_group": group,
                "paired_healthy": paired, "healthy": not r.is_fault}
               for r, split, group, paired in plans]
    manifest = {"schema_version": "2.1.0", "campaign_version": "recorded-commands-2",
                "healthy_counts_per_topology": {s: getattr(args, s) for s in DEFAULT_COUNTS},
                "fault_seed": args.fault_seed, "recordings_per_fault": 1,
                "configuration_sha256": digest(config), "recordings": entries,
                "independence": "Distinct healthy seeds within each topology. The fixed fault seed is reserved for one healthy test control per topology; all other healthy seeds are unique across the campaign. Derived per-instance local seeds and unchanged deterministic initial conditions. Exactly one recording per fault, paired only within test.",
                "status": "planned", "completed": [], "coverage": {}}
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "campaign.json"
    if manifest_path.exists():
        previous = read_json(manifest_path)
        if previous["recordings"] != entries or previous["configuration_sha256"] != digest(config):
            raise ValueError("Existing campaign differs; choose a new destination")
        if not args.run:
            print(f"Existing campaign: {len(entries)} planned recordings; {len(previous['completed'])} completed")
            return 0
        if not args.resume:
            raise ValueError("Existing campaign requires --resume")
    elif any(output.iterdir()):
        raise ValueError("Refusing to write into a nonempty unrecognized destination")
    print(f"Planned {sum(e['healthy'] for e in entries)} healthy and {sum(not e['healthy'] for e in entries)} fault recordings", flush=True)
    if not args.run:
        write_json(manifest_path, manifest)
        return 0
    # Ship the exact generation procedure, model sources and usage licence.
    snapshot = output / "generation"
    for directory, patterns in (("code", ("*.py", "*.json", "schemas/*.json")), ("models", ("*.mo",))):
        for pattern in patterns:
            for source in (ROOT / directory).glob(pattern):
                target = snapshot / source.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and digest(target) != digest(source):
                    raise ValueError(f"Frozen campaign source changed: {source}")
                shutil.copy2(source, target)
    shutil.copy2(ROOT / "LICENSE", output / "LICENSE")
    shutil.copy2(ROOT / "LICENSE", snapshot / "LICENSE")
    shutil.copy2(ROOT / "venv.yml", snapshot / "venv.yml")
    (snapshot / "docs/source").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "docs/source/diagnosis-rerun.md", snapshot / "docs/source/diagnosis-rerun.md")
    shutil.copy2(config, snapshot / "requested_configuration.json")
    # Portable replay config, with model paths relative to generation/code.
    replay_config = load_benchmark_config(config)
    for setup in replay_config.values():
        for module in setup["model"]["modules"].values():
            module["files"] = "../models/" + Path(module["files"]).name
    write_json(snapshot / "code/campaign_configuration.json", replay_config)
    manifest["generation_sha256"] = {str(p.relative_to(snapshot)): digest(p)
                                      for p in sorted(snapshot.rglob("*")) if p.is_file()}
    shutil.copy2(ROOT / "docs/source/diagnosis-rerun.md", output / "README.md")
    completed = {}
    fault_groups = {}
    manifest["status"] = "running"
    write_json(manifest_path, manifest)
    try:
        for run, split, group, paired in plans[:args.max_runs]:
            result = _execute_run(run, config, output / run.base_dataset, build, False, args.resume, "v2.1")
            run_coverage = coverage(result.output_dir, run)
            if paired:
                _validate_pair(completed[paired], result)
                fault_groups.setdefault(group, []).append(result.hybrid)
            else:
                manifest["coverage"][run.scenario_id] = run_coverage
            completed[run.scenario_id] = result
            manifest["completed"].append(run.scenario_id)
            write_json(manifest_path, manifest)
    except BaseException as exc:
        manifest.update(status="failed", error=str(exc))
        write_json(manifest_path, manifest)
        raise
    gaps = {name: c for name, c in manifest["coverage"].items()
            if c["missing_command_ranges"] or c["unvisited_controller_phases"]}
    manifest["status"] = ("incomplete_pilot" if len(completed) != len(plans)
                          else "coverage_review_required" if gaps else "complete")
    manifest["coverage_gaps"] = sorted(gaps)
    manifest["duplicate_fault_signals"] = {group: duplicates for group, paths in fault_groups.items()
                                          if (duplicates := duplicate_signal_groups(paths))}
    healthy_duplicates = {}
    for topology in sorted({run.base_dataset for run, _, _, _ in plans}):
        paths = [completed[run.scenario_id].hybrid for run, _, _, paired in plans
                 if paired is None and run.base_dataset == topology and run.scenario_id in completed]
        duplicates = duplicate_signal_groups(paths)
        if duplicates:
            healthy_duplicates[topology] = duplicates
    manifest["duplicate_healthy_signals"] = healthy_duplicates
    if len(completed) == len(plans) and (healthy_duplicates or manifest["duplicate_fault_signals"]):
        manifest["status"] = "signal_review_required"
    write_json(manifest_path, manifest)
    print(f"Campaign status: {manifest['status']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
