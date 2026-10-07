"""Inventory or migrate existing recordings; never invokes a simulator.

Default is a read-only dry run. --apply writes a separate staging tree.
--promote retains the source at --snapshot before promoting validated staging.
"""
import argparse
import copy
from pathlib import Path
import shutil
import sys
import platform
from importlib.metadata import version

import pandas as pd

from actuator_channels import (SCHEMA_VERSION, reconstruct_commands,
                               validate_command_equations, verify_sources)
from config import load_benchmark_config, generate_normal_campaign, generate_single_fault_campaign
from dataset_metadata import update_technical_timing_with_pair
from export import ExportError
from export_v2_1 import (AUDIT_PATH, bundle_from_directory, check_alignment, digest, enrich_release,
                        read_json, run_from_directory, validate_diagnosis_release, write_json,
                        update_diagnosis_pair_timing)
from validation import (validate_release_bundle, validate_fault_pair, require_valid_report,
                        duplicate_signal_groups)

ROOT = Path(__file__).resolve().parents[1]


def tree_hashes(root):
    return {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob("*")) if p.is_file()}


def refresh_hashes(path):
    provenance = read_json(path / "provenance.json")
    hashes = {str(p.relative_to(path)): digest(p) for p in sorted(path.rglob("*"))
              if p.is_file() and p.name != "provenance.json"}
    provenance["release"]["artifact_sha256"] = hashes
    if "processing" in provenance:
        provenance["processing"]["output_sha256"] = hashes
    write_json(path / "provenance.json", provenance)


def pair_metadata(root, paths):
    reports = []
    for path in paths:
        run = run_from_directory(path)
        if not run.is_fault:
            continue
        normal_path = path.parent / f"{run.base_dataset}_normal"
        normal = run_from_directory(normal_path)
        for key in ("openmodelica_version", "modelica_standard_library_version", "seed", "solver", "model_sha256"):
            left, right = read_json(normal_path / "provenance.json"), read_json(path / "provenance.json")
            if key == "model_sha256":
                a = {Path(k).name: v for k, v in left[key].items()}
                b = {Path(k).name: v for k, v in right[key].items()}
            else:
                a, b = left[key], right[key]
            if a != b:
                raise ExportError(f"Incompatible pair {run.scenario_id}: {key}")
        nb, fb = bundle_from_directory(normal_path, True), bundle_from_directory(path, True)
        report = validate_fault_pair(nb.hybrid, fb.hybrid, nb.verification, fb.verification, normal, run)
        require_valid_report(report)
        existing = read_json(path / "validation.json")
        for key in ("raw_result", "safe_columns", "oracle_columns", "release_export", "diagnosis_extension"):
            report[key] = existing.get(key)
        update_technical_timing_with_pair(path / "technical_timing.json", report)
        update_diagnosis_pair_timing(normal_path, path, run, report)
        write_json(path / "validation.json", report)
        refresh_hashes(path)
        reports.append(run.scenario_id)
    for topology in sorted(set(p.parent for p in paths)):
        faults = [p for p in paths if p.parent == topology and run_from_directory(p).is_fault]
        duplicates = duplicate_signal_groups(p / "hybrid/measurements.parquet" for p in faults)
        if duplicates:
            raise ExportError(f"Duplicate fault recordings in {topology.name}")
        write_json(topology / "campaign_validation.json", {"valid": True, "fault_scenarios": len(faults),
                   "duplicate_signal_groups": [], "schema_version": SCHEMA_VERSION,
                   "diagnosis_postprocessing_valid": True})
    return reports


def inspect_scenario(path):
    run = run_from_directory(path)
    provenance = read_json(path / "provenance.json")
    if provenance.get("processing"):
        raise ExportError(f"Already processed: {path}; use the preserved original for reproducible migration")
    hashes = verify_sources(run.setup, provenance["model_sha256"])
    for relative, value in provenance["release"]["artifact_sha256"].items():
        file = (path / relative).resolve()
        if not file.is_relative_to(path.resolve()) or not file.is_file() or digest(file) != value:
            raise ExportError(f"Input artifact hash mismatch: {file}")
    bundle = bundle_from_directory(path)
    validate_release_bundle(bundle, run, path / "fault_events.json", path / "system_knowledge.yaml", path / "technical_timing.json")
    audit = pd.read_csv(bundle.verification)
    check_alignment(pd.read_parquet(bundle.hybrid), audit)
    commands = reconstruct_commands(audit, run.setup)
    checks = validate_command_equations(commands, audit, run.setup)
    coverage = {c: {"values": sorted(float(v) for v in commands[c].unique()),
                    "transitions": int(commands[c].diff().fillna(0).ne(0).sum())} for c in list(commands)[3:]}
    phases = {c: {"active_samples": int(audit[c].sum()), "entries": int(audit[c].diff().fillna(audit[c].iloc[0]).gt(0).sum())}
              for c in audit if ".state_" in c and c.endswith(".active")}
    return {"scenario_id": run.scenario_id, "topology": run.base_dataset, "fault": run.is_fault,
            "seed": provenance["seed"], "rows": len(audit), "command_count": len(commands.columns)-3,
            "source_hashes": hashes, "command_coverage": coverage, "phase_coverage": phases,
            "complete_process_cycle_count": "not_inferred_from_phase_entries",
            "equations_checked": checks, "raw_simulation_csv": "not_present_in_release",
            "full_raw_fidelity": "unverified_without_original_raw_csv",
            "healthy_signal_hash": digest(bundle.hybrid) if not run.is_fault else None}


def migrate_scenario(source, target, info, invocation):
    shutil.copytree(source, target)
    run = run_from_directory(target)
    original_provenance = read_json(target / "provenance.json")
    inputs = tree_hashes(source)
    bundle, extension = enrich_release(target, run, bundle_from_directory(target), original_provenance["model_sha256"])
    report = validate_release_bundle(bundle, run, target / "fault_events.json", target / "system_knowledge.yaml", target / "technical_timing.json")
    validate_diagnosis_release(target, run)
    setup = read_json(target / "sim_setup.json")
    setup["release_schema_version"] = SCHEMA_VERSION
    setup["oracle_catalogue_version"] = SCHEMA_VERSION
    setup["data_roles"].pop("audit/internal_verification.csv", None)
    setup["data_roles"].update({AUDIT_PATH: "internal_validation_non_feature", "commands.parquet": "controller_command_features",
                               "channel_catalogue.yaml": "channel_metadata_non_feature", "permitted_inputs.json": "diagnostic_input_policy"})
    write_json(target / "sim_setup.json", setup)
    validation = read_json(target / "validation.json")
    validation.update({"release_export": report, "diagnosis_extension": extension, "oracle_columns": list(bundle.oracle_columns)})
    write_json(target / "validation.json", validation)
    provenance = copy.deepcopy(original_provenance)
    provenance["release"].update({"schema_version": SCHEMA_VERSION, "oracle_catalogue_version": SCHEMA_VERSION,
                                  "diagnosis_feature_loader": "dataset_io.load_diagnosis_dataset"})
    provenance["processing"] = {
        "schema_version": SCHEMA_VERSION, "input_artifact_sha256": inputs,
        "original_simulation_provenance": original_provenance,
        "command": invocation, "source_sha256": {p.name: digest(p) for p in (ROOT / "code").glob("*.py")},
        "python_version": platform.python_version(),
        "packages": {name: version(name) for name in ("pandas", "numpy", "pyarrow", "PyYAML")},
        "reconstruction_model_sha256": info["source_hashes"],
        "sensor_and_audit_values_changed": False, "audit_path_migration": {"from": "audit/internal_verification.csv", "to": AUDIT_PATH},
        "split": "test", "pair_group": run.base_dataset + "_seed_" + str(info["seed"]),
        "independent_healthy_splits": {"training": "unavailable", "validation": "unavailable", "calibration": "unavailable"},
        "coverage": {"commands": info["command_coverage"], "phases": info["phase_coverage"]},
        "raw_fidelity": info["full_raw_fidelity"],
    }
    write_json(target / "provenance.json", provenance)
    for view in ("continuous", "discrete", "hybrid"):
        relative = f"{view}/measurements.parquet"
        if digest(target / relative) != inputs[relative]:
            raise ExportError(f"Measurement changed: {target / relative}")
    if digest(target / AUDIT_PATH) != inputs["audit/internal_verification.csv"]:
        raise ExportError("Audit bytes changed")
    refresh_hashes(target)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data/v2.1")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args(argv)
    source = args.source.resolve()
    protected = [ROOT / "data/backup", ROOT / "data/v2"]
    for path in (source, args.output, args.report, args.snapshot):
        if path is not None and any(path.resolve().is_relative_to(p.resolve()) or p.resolve().is_relative_to(path.resolve()) for p in protected):
            raise ExportError("Source/output/report/snapshot may not touch v2 or backup")
    if args.apply:
        if not args.output or args.output.exists() or args.output.resolve().is_relative_to(source) or source.is_relative_to(args.output.resolve()):
            raise ExportError("--apply needs a new, separate --output directory")
    if args.promote and (not args.apply or not args.snapshot or args.snapshot.exists()):
        raise ExportError("--promote requires --apply and a new --snapshot path")
    if args.snapshot and (args.snapshot.resolve().is_relative_to(source) or source.is_relative_to(args.snapshot.resolve())):
        raise ExportError("Snapshot must be separate from source")
    if args.report.resolve().is_relative_to(source):
        raise ExportError("Report must be outside the read-only source tree")
    if args.snapshot and args.output and (args.snapshot.resolve().is_relative_to(args.output.resolve()) or args.output.resolve().is_relative_to(args.snapshot.resolve())):
        raise ExportError("Snapshot and staging must be separate")
    before = tree_hashes(source)
    v2_before = tree_hashes(ROOT / "data/v2")
    paths = sorted(p.parent for p in source.glob("*/*/sim_setup.json"))
    config = load_benchmark_config(ROOT / "code/benchmark_setup.json")
    expected = {r.scenario_id for r in generate_normal_campaign(config) + generate_single_fault_campaign(config)}
    if {p.name for p in paths} != expected:
        raise ExportError("Dataset scenario coverage differs from configured campaign")
    infos = []
    for path in paths:
        info = inspect_scenario(path)
        infos.append(info)
        print(f"[verified] {path.name}: {info['command_count']} commands", flush=True)
    report = {"schema_version": SCHEMA_VERSION, "scenarios": infos, "count": len(infos), "dry_run": not args.apply,
              "independent_healthy_runs_per_topology": {name: sum(not i["fault"] and i["topology"] == name for i in infos) for name in config},
              "independent_training_validation_calibration": "unavailable; existing healthy baselines reserved with fault families in test",
              "source_sha256": before, "v2_sha256": v2_before}
    if args.apply:
        output = args.output.resolve()
        output.mkdir(parents=True)
        targets = []
        for path, info in zip(paths, infos):
            target = output / path.relative_to(source)
            migrate_scenario(path, target, info, " ".join(sys.argv))
            targets.append(target)
            print(f"[exported] {target.name}", flush=True)
        report["validated_fault_pairs"] = pair_metadata(output, targets)
        for target in targets:
            validate_diagnosis_release(target, run_from_directory(target))
        processing = output / "processing"
        processing.mkdir()
        for directory in ("code", "models"):
            shutil.copytree(ROOT / directory, processing / directory, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(ROOT / "venv.yml", processing / "venv.yml")
        shutil.copy2(ROOT / "LICENSE", output / "LICENSE")
        shutil.copy2(ROOT / "docs/source/diagnosis-v2.1.md", output / "README.md")
        write_json(processing / "release_manifest.json", {"schema_version": SCHEMA_VERSION, "scenarios": [i["scenario_id"] for i in infos],
                   "split": "test", "healthy_independence_shortfall": report["independent_training_validation_calibration"],
                   "preserved_input_sha256": before})
        report["output_sha256"] = tree_hashes(output)
    if before != tree_hashes(source) or v2_before != tree_hashes(ROOT / "data/v2"):
        raise ExportError("Source or v2 changed during processing")
    if args.promote:
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        source.rename(args.snapshot)
        try:
            args.output.rename(source)
        except Exception:
            args.snapshot.rename(source)
            raise
        if tree_hashes(args.snapshot) != before:
            raise ExportError("Snapshot verification failed")
        report["promoted_to"] = str(source)
        report["snapshot"] = str(args.snapshot.resolve())
    report["valid"] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, report)
    print(f"Complete: {len(infos)} scenarios; report {args.report}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, ExportError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
