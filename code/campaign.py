"""Run v2.2 recordings from a dependency-aware parallel work queue.

Use ``--jobs`` for parallel workers and ``--dataset ds1`` for one dataset.
Restart the same command after an interruption to verify completed recordings.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any
from uuid import uuid4

from campaign_check import check_campaign
from config import ConfigError, load_benchmark_config
from campaign_plan import (
    coverage,
    plan_campaign,
    prepare_manifest,
    protected_destination,
    snapshot_campaign,
)
from sim import _execute_run, _load_resumable_run, _validate_pair
from validation import duplicate_signal_groups

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "code" / "benchmark_setup.json"
TOPOLOGIES = tuple(f"ds{number}" for number in range(1, 11))
CONTROLS = {f"{topology}_016_healthy" for topology in TOPOLOGIES}


def work_queue(plans):
    """Queue controls first and keep faults behind their matching control."""
    controls = deque()
    healthy = deque()
    dependents = defaultdict(list)
    for plan in plans:
        run, _, _, paired = plan
        if paired is not None:
            dependents[paired].append(plan)
        elif run.scenario_id in CONTROLS:
            controls.append(plan)
        else:
            healthy.append(plan)
    controls.extend(healthy)
    return controls, dependents


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare_shards(output: Path, manifests: dict[str, dict[str, Any]],
                   config: Path, topologies: tuple[str, ...]) -> None:
    for topology in topologies:
        shard = output / topology
        manifest = prepare_manifest(config, topology, shard)
        snapshot_campaign(shard, config, manifest)
        manifest["status"] = "running"
        manifest.pop("error", None)
        write_manifest(shard / "campaign.json", manifest)
        manifests[topology] = manifest


def run_worker(scenario: str, output: Path, build: Path, logs: Path,
               config: Path = CONFIG) -> int:
    topology = scenario.split("_", 1)[0]
    plans = plan_campaign(load_benchmark_config(config), topologies=[topology])
    by_id = {plan[0].scenario_id: plan for plan in plans}
    if scenario not in by_id:
        raise ValueError(f"Unknown planned scenario: {scenario}")
    run, _, _, paired = by_id[scenario]
    scenario_root = output / topology / topology
    scenario_root.mkdir(parents=True, exist_ok=True)
    existing_dir = scenario_root / scenario
    if existing_dir.exists() and _load_resumable_run(scenario_root, run, config, "v2.2") is None:
        quarantine = logs / "incomplete" / f"{scenario}.{uuid4().hex}"
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        existing_dir.rename(quarantine)
        print(f"Moved incomplete output to {quarantine}", flush=True)
    result = _execute_run(run, config, scenario_root, build / topology,
                          force=False, resume=True, release_version="v2.2")
    if paired is not None:
        control = by_id[paired][0]
        normal = _load_resumable_run(scenario_root, control, config, "v2.2")
        if normal is None:
            raise ValueError(f"Missing completed healthy control: {paired}")
        _validate_pair(normal, result)
    print(f"Completed {scenario}", flush=True)
    return 0


def start_worker(plan, output: Path, build: Path, logs: Path,
                 config: Path = CONFIG):
    scenario = plan[0].scenario_id
    log_path = logs / f"{scenario}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("a", encoding="utf-8")
    command = [sys.executable, "-u", str(Path(__file__).resolve()),
               "--worker-scenario", scenario, "--output", str(output),
               "--build-root", str(build), "--logs", str(logs),
               "--config", str(config), "--dataset", plan[0].base_dataset]
    log.write("\nCOMMAND: " + " ".join(command) + "\n")
    log.flush()
    environment = os.environ.copy()
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                     "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        environment[variable] = "1"
    try:
        process = subprocess.Popen(command, cwd=ROOT, env=environment,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
    except BaseException:
        log.close()
        raise
    return process, log, log_path


def stop_workers(active) -> None:
    for process, _, _ in active.values():
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 10
    for process, _, _ in active.values():
        if process.poll() is None:
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
    for _, log, _ in active.values():
        log.close()


def finish_shards(output: Path, manifests: dict[str, dict[str, Any]],
                  topologies: tuple[str, ...]) -> None:
    for topology in topologies:
        manifest = manifests[topology]
        entries = manifest["recordings"]
        if set(manifest["completed"]) != {entry["scenario_id"] for entry in entries}:
            raise ValueError(f"Incomplete shard: {topology}")
        gaps = {name: item for name, item in manifest["coverage"].items()
                if item["missing_command_ranges"] or item["unvisited_controller_phases"]}
        by_group = defaultdict(list)
        healthy_paths = []
        root = output / topology / topology
        for entry in entries:
            path = root / entry["scenario_id"] / "hybrid" / "measurements.parquet"
            if entry["healthy"]:
                healthy_paths.append(path)
            else:
                by_group[entry["pair_group"]].append(path)
        fault_duplicates = {group: duplicates for group, paths in by_group.items()
                            if (duplicates := duplicate_signal_groups(paths))}
        normal_duplicates = duplicate_signal_groups(healthy_paths)
        manifest["coverage_gaps"] = sorted(gaps)
        manifest["duplicate_fault_signals"] = fault_duplicates
        manifest["duplicate_healthy_signals"] = (
            {topology: normal_duplicates} if normal_duplicates else {}
        )
        manifest["status"] = (
            "signal_review_required" if fault_duplicates or normal_duplicates
            else "coverage_review_required" if gaps else "complete"
        )
        write_manifest(output / topology / "campaign.json", manifest)


def run_pool(output: Path, build: Path, logs: Path, jobs: int,
             config: Path = CONFIG, topologies: tuple[str, ...] = TOPOLOGIES) -> int:
    output.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    with (output / ".v22_pool.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"Another campaign launcher is using {output}") from exc
        manifests: dict[str, dict[str, Any]] = {}
        prepare_shards(output, manifests, config, topologies)
        plans = plan_campaign(load_benchmark_config(config), topologies=topologies)
        ready, dependents = work_queue(plans)
        active = {}
        completed = 0
        try:
            while ready or active:
                while ready and len(active) < jobs:
                    plan = ready.popleft()
                    process, log, log_path = start_worker(plan, output, build, logs, config)
                    active[process.pid] = (process, log, (plan, log_path))
                finished = [(pid, item) for pid, item in active.items()
                            if item[0].poll() is not None]
                if not finished:
                    time.sleep(1)
                    continue
                for pid, (process, log, (plan, log_path)) in finished:
                    del active[pid]
                    log.close()
                    run, _, _, paired = plan
                    if process.returncode != 0:
                        manifest = manifests[run.base_dataset]
                        manifest.update(status="failed", error=f"{run.scenario_id}: {log_path}")
                        write_manifest(output / run.base_dataset / "campaign.json", manifest)
                        raise RuntimeError(f"{run.scenario_id} failed; see {log_path}")
                    manifest = manifests[run.base_dataset]
                    if paired is None:
                        manifest["coverage"][run.scenario_id] = coverage(
                            output / run.base_dataset / run.base_dataset / run.scenario_id,
                            run,
                        )
                        for dependent in reversed(dependents.pop(run.scenario_id, [])):
                            ready.appendleft(dependent)
                    if run.scenario_id not in manifest["completed"]:
                        manifest["completed"].append(run.scenario_id)
                    write_manifest(output / run.base_dataset / "campaign.json", manifest)
                    completed += 1
                    print(f"[{completed}/{len(plans)}] {run.scenario_id} finished; "
                          f"{len(active)} running, {len(ready)} ready", flush=True)
        except BaseException:
            stop_workers(active)
            raise
        finish_shards(output, manifests, topologies)
        report = check_campaign(output, topologies=topologies)
        selection = "all" if topologies == TOPOLOGIES else topologies[0]
        report_path = logs / f"v2.2_{selection}_check.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        if not report["valid"]:
            print(f"Campaign validation failed: {len(report['errors'])} errors; see {report_path}")
            return 1
        manifest_name = "release_manifest.json" if selection == "all" else f"{selection}_release_manifest.json"
        (output / manifest_name).write_text(json.dumps({
            "schema_version": "2.2.0", "recordings": report["recordings"],
            "shards": report["shards"], "validation_report": str(report_path),
        }, indent=2, sort_keys=True) + "\n")
        print(f"Validated campaign: {output}")
        return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--dataset", choices=TOPOLOGIES, help="run one benchmark dataset")
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "v2.2")
    parser.add_argument("--build-root", type=Path, default=ROOT / "build" / "v2.2" / "campaign")
    parser.add_argument("--logs", type=Path, help="worker log directory (default: build root/logs)")
    parser.add_argument("--jobs", type=int, default=4, help="maximum simultaneous recordings (default: 4)")
    parser.add_argument("--plan", action="store_true", help="Show the pooled schedule without writing files")
    parser.add_argument("--worker-scenario", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    config = args.config.resolve()
    try:
        benchmark = load_benchmark_config(config)
    except ConfigError as exc:
        parser.error(str(exc))
    topologies = (args.dataset,) if args.dataset else TOPOLOGIES
    missing = set(topologies) - set(benchmark)
    if missing:
        parser.error(f"Configuration is missing: {', '.join(sorted(missing))}")
    try:
        output = protected_destination(args.output)
        build = protected_destination(args.build_root)
    except ValueError as exc:
        parser.error(str(exc))
    logs = args.logs.resolve() if args.logs else build / "logs"
    if output == build or output in build.parents or build in output.parents:
        parser.error("build and output roots must be separate")
    if output == (ROOT / "data" / "v2.2").resolve():
        parser.error("Use a staging output; data/v2.2 is reserved for promotion")
    if args.worker_scenario:
        return run_worker(args.worker_scenario, output, build, logs, config)
    if args.plan:
        plans = plan_campaign(benchmark, topologies=topologies)
        ready, dependencies = work_queue(plans)
        print(f"{len(plans)} recordings: {len(ready)} healthy, "
              f"{sum(map(len, dependencies.values()))} faults, {args.jobs} workers")
        print("First queued recordings: " + ", ".join(plan[0].scenario_id for plan in list(ready)[:10]))
        return 0
    try:
        return run_pool(output, build, logs, args.jobs, config, topologies)
    except KeyboardInterrupt:
        print("Interrupted. Rerun the same command to resume.", file=sys.stderr)
        return 130
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Campaign stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
