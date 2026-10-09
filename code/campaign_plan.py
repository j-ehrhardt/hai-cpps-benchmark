"""Plan v2.2 recordings and prepare one dataset's campaign manifest."""
import copy
from dataclasses import replace
from pathlib import Path
import shutil

import pandas as pd

from actuator_channels import command_specs, recorded_commands
from config import load_benchmark_config, generate_normal_campaign, generate_single_fault_campaign
from diagnosis_export import AUDIT_PATH, read_json, write_json, digest
from sim import _set_seed

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COUNTS = {"train": 10, "validation": 3, "calibration": 2, "test": 1}
# Every released fault recording and its healthy test control use this seed.
DEFAULT_FAULT_SEED = 42
FAULT_VARIANTS = (
    ("persistent", 1, None),
    ("temporal", 2, 7500),
)


def _topology_key(name):
    return int(name[2:])


def plan_campaign(benchmark, counts=None, seed=20261005, topologies=None, fault_seed=DEFAULT_FAULT_SEED):
    counts = dict(DEFAULT_COUNTS if counts is None else counts)
    if set(counts) != set(DEFAULT_COUNTS) or any(type(n) is not int or n < 1 for n in counts.values()):
        raise ValueError("Each of train/validation/calibration/test requires a positive recording count")
    all_topologies = sorted(benchmark, key=_topology_key)
    selected = all_topologies if topologies is None else sorted(set(topologies), key=_topology_key)
    if not set(selected) <= set(benchmark):
        raise ValueError("Unknown topology")
    if (seed < 1 or seed + len(selected)*sum(counts.values()) + 1 >= 2147483647
            or not 1 <= fault_seed < 2147483647):
        raise ValueError("Campaign seeds must fit positive Modelica integers")
    result = []
    next_seed = seed
    selected_set = set(selected)
    for topology in all_topologies:
        healthy_ordinal = 0
        for split in DEFAULT_COUNTS:
            for index in range(counts[split]):
                healthy_ordinal += 1
                paired_control = split == "test" and index == 0
                # Reserve the working fault seed for exactly one healthy test control.
                if next_seed == fault_seed:
                    next_seed += 1
                run_seed = fault_seed if paired_control else next_seed
                if not paired_control:
                    next_seed += 1
                if topology not in selected_set:
                    continue
                config = copy.deepcopy(benchmark)
                _set_seed(config, run_seed)
                group = f"{topology}_{healthy_ordinal:03d}"
                normal = generate_normal_campaign(config, [topology])[0]
                normal = replace(normal, scenario_id=group + "_healthy")
                normal.setup["ds_name"] = normal.scenario_id
                result.append((normal, split, group, None))
                if paired_control:
                    for fault in generate_single_fault_campaign(config, [topology]):
                        for variant, ordinal, end in FAULT_VARIANTS:
                            setup = copy.deepcopy(fault.setup)
                            setup["sim_setup"]["faultEnd"] = end
                            scenario_id = (
                                f"{topology}_{ordinal:03d}_"
                                f"{fault.target_module}_{fault.target_fault}_{variant}"
                            )
                            setup["ds_name"] = scenario_id
                            variant_run = replace(
                                fault,
                                scenario_id=scenario_id,
                                setup=setup,
                                fault_variant=variant,
                            )
                            result.append(
                                (variant_run, split, group, normal.scenario_id)
                            )
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
    protected = ROOT / "data"
    if path == protected or protected in path.parents or path in protected.parents:
        raise ValueError("Campaign destination overlaps the data directory")
    return path


def snapshot_campaign(output, config, manifest):
    """Freeze the source used by one shard before its recordings start."""
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
    shutil.copy2(ROOT / "requirements.txt", snapshot / "requirements.txt")
    shutil.copy2(config, snapshot / "requested_configuration.json")
    replay_config = load_benchmark_config(config)
    for setup in replay_config.values():
        for module in setup["model"]["modules"].values():
            module["files"] = "../models/" + Path(module["files"]).name
    write_json(snapshot / "code/campaign_configuration.json", replay_config)
    manifest["generation_sha256"] = {str(p.relative_to(snapshot)): digest(p)
                                      for p in sorted(snapshot.rglob("*")) if p.is_file()}


def prepare_manifest(config: Path, topology: str, output: Path):
    """Create or verify the planned recordings for one benchmark dataset."""

    plans = plan_campaign(load_benchmark_config(config), topologies=[topology])
    entries = [{"scenario_id": run.scenario_id, "topology": run.base_dataset,
                "split": split, "seed": run.setup["sim_setup"]["seed"],
                "pair_group": group, "paired_healthy": paired,
                "healthy": not run.is_fault, "fault_variant": run.fault_variant,
                "fault_start": run.setup["sim_setup"]["faultStart"] if run.is_fault else None,
                "fault_end": run.setup["sim_setup"].get("faultEnd") if run.is_fault else None,
                "active_duration_steps": (
                    int((run.setup["sim_setup"].get("faultEnd") or run.setup["sim_setup"]["stopTime"])
                        - run.setup["sim_setup"]["faultStart"])
                    if run.is_fault else None)}
               for run, split, group, paired in plans]
    manifest = {
        "schema_version": "2.2.0", "campaign_version": "recorded-commands-3",
        "healthy_counts_per_topology": DEFAULT_COUNTS,
        "fault_seed": DEFAULT_FAULT_SEED, "recordings_per_fault": 2,
        "fault_variants": [
            {"name": name, "ordinal": ordinal, "fault_start": 2500,
             "fault_end": end, "active_duration_steps": (end or 25000) - 2500}
            for name, ordinal, end in FAULT_VARIANTS
        ],
        "configuration_sha256": digest(config), "recordings": entries,
        "status": "planned", "completed": [], "coverage": {},
    }
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "campaign.json"
    if manifest_path.exists():
        previous = read_json(manifest_path)
        if previous["recordings"] != entries or previous["configuration_sha256"] != digest(config):
            raise ValueError(f"Existing campaign differs: {output}")
        return previous
    if any(output.iterdir()):
        raise ValueError(f"Refusing nonempty campaign destination: {output}")
    write_json(manifest_path, manifest)
    return manifest
