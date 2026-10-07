"""Repair paired timing and derived cooler references in an existing v2.1 release.

Stages and validates the complete update before promotion; retains a snapshot.
Never invokes a simulator or reads data/backup.
"""
import argparse
from pathlib import Path
import shutil
import sys

import pandas as pd
import yaml

from actuator_channels import command_catalogue, verify_sources, REGISTRY_VERSION
from dataset_metadata import enrich_diagnosis_metadata, update_technical_timing_with_pair
from export import ExportError
from export_v2_1 import (add_cooler_references, bundle_from_directory, derived_cooler_variables,
                        digest, read_json, run_from_directory, write_json)
from postprocess_v2_1 import tree_hashes, refresh_hashes
from validation import validate_release_bundle

ROOT = Path(__file__).resolve().parents[1]
FIX_ID = "paired-timing-and-cooler-references-1"


def repair_scenario(path):
    run = run_from_directory(path)
    provenance = read_json(path / "provenance.json")
    hashes = verify_sources(run.setup, provenance["model_sha256"])
    inputs = tree_hashes(path)
    for relative, expected in provenance["release"]["artifact_sha256"].items():
        if inputs.get(relative) != expected:
            raise ExportError(f"Input hash mismatch: {path / relative}")
    bundle = bundle_from_directory(path, extended=True)
    original_oracle = pd.read_parquet(bundle.oracle_states)
    original_catalogue = yaml.safe_load((path / "channel_catalogue.yaml").read_text())
    fault_timing = read_json(path / "technical_timing.json")["fault_timing"]
    bundle = add_cooler_references(path, run, bundle, hashes)
    enrich_diagnosis_metadata(path, run, bundle, command_catalogue(run.setup, hashes),
                             hashes, original_catalogue["oracle_renames"])
    timing = read_json(path / "technical_timing.json")
    # Preserve completed observations, physical onset and deactivation exactly.
    timing["fault_timing"] = fault_timing
    write_json(path / "technical_timing.json", timing)
    validation = read_json(path / "validation.json")
    if run.is_fault:
        if not validation.get("valid") or "safe_channel_differences" not in validation:
            raise ExportError(f"Missing completed pair evidence: {run.scenario_id}")
        update_technical_timing_with_pair(path / "technical_timing.json", validation)
    validation["release_export"] = validate_release_bundle(
        bundle, run, path / "fault_events.json", path / "system_knowledge.yaml", path / "technical_timing.json")
    validation["oracle_columns"] = list(bundle.oracle_columns)
    derived = [v.oracle_column for v in derived_cooler_variables(run.setup)]
    validation["diagnosis_extension"]["equation_derived_cooler_references_checked"] = derived
    validation["diagnosis_extension"]["registry_version"] = REGISTRY_VERSION
    validation["diagnosis_extension"]["paired_timing_resolved"] = run.is_fault
    write_json(path / "validation.json", validation)
    oracle = pd.read_parquet(bundle.oracle_states)
    if not oracle[list(original_oracle.columns)].equals(original_oracle):
        raise ExportError("Existing oracle values changed")
    protected = ["commands.parquet", "permitted_inputs.json", "audit_for_verification/internal_verification.csv"]
    protected += [f"{view}/measurements.parquet" for view in ("continuous", "discrete", "hybrid")]
    for relative in protected:
        if digest(path / relative) != inputs[relative]:
            raise ExportError(f"Protected observations changed: {path / relative}")
    source_hashes = {name: digest(ROOT / "code" / name) for name in
                     ("actuator_channels.py", "dataset_metadata.py", "export_v2_1.py", "repair_v2_1.py")}
    fix = {"id": FIX_ID, "input_sha256": inputs, "source_sha256": source_hashes,
           "registry_version": REGISTRY_VERSION, "derived_cooler_columns": derived,
           "paired_timing_resolved": run.is_fault,
           "observations_and_original_oracle_values_preserved": True}
    provenance.setdefault("processing", {}).setdefault("fixes", []).append(fix)
    write_json(path / "provenance.json", provenance)
    refresh_hashes(path)
    return {"scenario": run.scenario_id, "timing_fixed": run.is_fault,
            "cooler_references": len(derived), "valid": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data/v2.1")
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    source, staging, snapshot, report_path = [p.resolve() for p in
                                              (args.source, args.staging, args.snapshot, args.report)]
    paths = (source, staging, snapshot, report_path)
    for path in paths:
        for protected in (ROOT / "data/v2", ROOT / "data/backup"):
            if path.is_relative_to(protected) or protected.is_relative_to(path):
                raise ExportError(f"Protected release path: {path}")
    for i, left in enumerate(paths):
        for right in paths[i+1:]:
            if left.is_relative_to(right) or right.is_relative_to(left):
                raise ExportError("Source, staging, snapshot and report paths must not overlap")
    if staging.exists() or snapshot.exists() or report_path.exists():
        raise ExportError("Staging, snapshot and report must be new paths")
    before = tree_hashes(source)
    v2_before = tree_hashes(ROOT / "data/v2")
    shutil.copytree(source, staging)
    results = []
    for setup in sorted(staging.glob("*/*/sim_setup.json")):
        result = repair_scenario(setup.parent)
        results.append(result)
        print(f"[validated] {result['scenario']}", flush=True)
    # Preserve the historical generation snapshot and package the repair separately.
    repair_code = staging / "processing" / "fixes" / FIX_ID / "code"
    shutil.copytree(ROOT / "code", repair_code, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "models", repair_code.parent / "models")
    write_json(repair_code.parent / "manifest.json", {
        "id": FIX_ID, "command": " ".join(sys.argv), "results": results,
        "source_sha256": tree_hashes(repair_code),
    })
    for campaign in staging.glob("*/campaign_validation.json"):
        value = read_json(campaign)
        value["timing_and_cooler_reference_fix"] = {"id": FIX_ID, "valid": True}
        write_json(campaign, value)
    readme = staging / "README.md"
    readme.write_text(readme.read_text() + "\n## Timing and cooler-reference correction\n\n"
        "The two first-consequence timing fields now contain completed sampled pair comparisons, "
        "including scope, tolerances, and persistence. They are not exact physical onset times. "
        "Both inactive distillation coolers now have constant-zero effective heat-input columns "
        "in oracle_states.parquet, marked equation-derived, unmeasured, and offline-only. "
        "Their command entries link to these references. Existing observations are unchanged. "
        "The repair code and manifest are preserved under processing/fixes/" + FIX_ID + "/.\n")
    after = tree_hashes(staging)
    if before != tree_hashes(source) or v2_before != tree_hashes(ROOT / "data/v2"):
        raise ExportError("Source or v2 changed during repair")
    report = {"valid": True, "id": FIX_ID, "scenarios": results,
              "timing_fixed": sum(r["timing_fixed"] for r in results),
              "cooler_columns_added_or_verified": sum(r["cooler_references"] for r in results),
              "input_sha256": before, "output_sha256": after, "v2_unchanged": True,
              "snapshot": str(snapshot), "release": str(source)}
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    source.rename(snapshot)
    try:
        staging.rename(source)
    except Exception:
        snapshot.rename(source)
        raise
    if tree_hashes(snapshot) != before or tree_hashes(source) != after:
        raise ExportError("Promotion hash verification failed")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(report_path, report)
    print(f"Complete: {len(results)} scenarios; {report['timing_fixed']} timing fixes; "
          f"{report['cooler_columns_added_or_verified']} cooler columns. Report: {report_path}")


if __name__ == "__main__":
    main()
