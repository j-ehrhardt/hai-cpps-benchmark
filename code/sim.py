"""Validated simulation, export, resume, and healthy/fault pair checks."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from config import ConfigError, RunSpec
from dataset_metadata import (
    update_technical_timing_with_pair,
    write_release_metadata,
)
from export import export_result_files
from diagnosis_export import (AUDIT_PATH, EXTRA_ARTIFACTS, enrich_release,
                        validate_diagnosis_release, update_diagnosis_pair_timing)
from actuator_channels import SCHEMA_VERSION as DIAGNOSIS_SCHEMA_VERSION
from runner import SimulationError, run_openmodelica
from validation import (
    require_valid_report,
    sha256_file,
    validate_fault_pair,
    validate_release_bundle,
    write_validation_report,
)


RUNTIME_SOURCE_PATHS = (
    Path(__file__).resolve(),
    Path(__file__).resolve().parent / "config.py",
    Path(__file__).resolve().parent / "dataset_metadata.py",
    Path(__file__).resolve().parent / "export.py",
    Path(__file__).resolve().parent / "diagnosis_export.py",
    Path(__file__).resolve().parent / "actuator_channels.py",
    Path(__file__).resolve().parent / "campaign_plan.py",
    Path(__file__).resolve().parent / "model_generation.py",
    Path(__file__).resolve().parent / "runner.py",
    Path(__file__).resolve().parent / "validation.py",
    Path(__file__).resolve().parent / "schemas" / "benchmark_setup.schema.json",
)


@dataclass(frozen=True)
class CompletedRun:
    run: RunSpec
    output_dir: Path
    continuous: Path
    discrete: Path
    hybrid: Path
    oracle_states: Path
    verification: Path
    fault_events: Path
    system_knowledge: Path
    technical_timing: Path


def _run_metadata(run: RunSpec) -> Dict[str, Any]:
    return {
        "scenario_id": run.scenario_id,
        "base_dataset": run.base_dataset,
        "target_module": run.target_module,
        "target_fault": run.target_fault,
        "fault_variant": run.fault_variant,
        "data_roles": {
            "continuous/measurements.parquet": "measurement_features",
            "discrete/measurements.parquet": "measurement_features",
            "hybrid/measurements.parquet": "measurement_features",
            "oracle_states.parquet": "offline_oracle_non_feature",
            "fault_events.json": "labels_and_fault_metadata_non_feature",
            "system_knowledge.yaml": "structural_knowledge_non_feature",
            "technical_timing.json": "timing_metadata_non_feature",
            AUDIT_PATH: "internal_validation_non_feature",
            "commands.parquet": "controller_command_features",
            "channel_catalogue.yaml": "channel_metadata_non_feature",
            "permitted_inputs.json": "diagnostic_input_policy",
        },
        "release_schema_version": DIAGNOSIS_SCHEMA_VERSION,
        "oracle_catalogue_version": DIAGNOSIS_SCHEMA_VERSION,
        "setup": run.setup,
    }


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(data), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _command_output(command: Sequence[str], cwd: Path) -> Optional[str]:
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _package_version(package: str) -> Optional[str]:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _runtime_source_hashes() -> Dict[str, str]:
    return {str(path): sha256_file(path) for path in RUNTIME_SOURCE_PATHS}


def _refresh_provenance_artifact_hash(output_dir: Path, artifact: Path) -> None:
    """Refresh a mutable post-pair metadata hash without changing run identity."""

    provenance_path = output_dir / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    relative = str(artifact.relative_to(output_dir))
    provenance["release"]["artifact_sha256"][relative] = sha256_file(artifact)
    _write_json(provenance_path, provenance)


def _provenance(
    config_path: Path,
    run: RunSpec,
    raw_validation: Mapping[str, Any],
    model_hashes: Mapping[str, str],
    modelica_version: Optional[str],
    output_dir: Path,
    release_artifacts: Iterable[Path],
) -> Dict[str, Any]:
    repository = Path(__file__).resolve().parent.parent
    git_commit = _command_output(("git", "rev-parse", "HEAD"), repository)
    git_status = _command_output(("git", "status", "--porcelain"), repository)
    omc_version = _command_output(("omc", "--version"), repository)
    return {
        "scenario_id": run.scenario_id,
        "base_dataset": run.base_dataset,
        "target_module": run.target_module,
        "target_fault": run.target_fault,
        "fault_variant": run.fault_variant,
        "configuration_sha256": sha256_file(config_path),
        "git_commit": git_commit,
        "git_dirty": bool(git_status),
        "model_sha256": dict(model_hashes),
        "runtime_source_sha256": _runtime_source_hashes(),
        "openmodelica_version": omc_version,
        "modelica_standard_library_version": modelica_version,
        "python_version": platform.python_version(),
        "python_packages": {
            "pandas": _package_version("pandas"),
            "pyarrow": _package_version("pyarrow"),
            "pyyaml": _package_version("PyYAML"),
        },
        "platform": platform.platform(),
        "seed": run.setup["sim_setup"]["seed"],
        "solver": {
            "tolerance": 1e-6,
            "output_format": "csv",
            "emit_event_points": False,
        },
        "release": {
            "schema_version": DIAGNOSIS_SCHEMA_VERSION,
            "oracle_catalogue_version": DIAGNOSIS_SCHEMA_VERSION,
            "table_format": "Apache Parquet",
            "parquet_engine": "pyarrow",
            "online_feature_default": "hybrid/measurements.parquet",
            "artifact_sha256": {
                str(path.relative_to(output_dir)): sha256_file(path)
                for path in sorted(release_artifacts, key=lambda item: str(item))
            },
        },
        "raw_result": dict(raw_validation),
    }


def _safe_remove_output(path: Path, output_root: Path) -> None:
    resolved_path = path.resolve()
    resolved_root = output_root.resolve()
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise SimulationError(
            "Refusing to remove output outside configured root: {}".format(resolved_path)
        ) from exc
    if not relative.parts:
        raise SimulationError("Refusing to remove the output root itself")
    shutil.rmtree(resolved_path)


def _completed_paths(output_root: Path, run: RunSpec) -> CompletedRun:
    output_dir = output_root / run.scenario_id
    return CompletedRun(
        run=run,
        output_dir=output_dir,
        continuous=output_dir / "continuous" / "measurements.parquet",
        discrete=output_dir / "discrete" / "measurements.parquet",
        hybrid=output_dir / "hybrid" / "measurements.parquet",
        oracle_states=output_dir / "oracle_states.parquet",
        verification=output_dir / AUDIT_PATH,
        fault_events=output_dir / "fault_events.json",
        system_knowledge=output_dir / "system_knowledge.yaml",
        technical_timing=output_dir / "technical_timing.json",
    )


def _load_resumable_run(
    output_root: Path, run: RunSpec, config_path: Path
) -> Optional[CompletedRun]:
    completed = _completed_paths(output_root, run)
    required = (
        completed.continuous,
        completed.discrete,
        completed.hybrid,
        completed.oracle_states,
        completed.verification,
        completed.fault_events,
        completed.system_knowledge,
        completed.technical_timing,
        completed.output_dir / "sim_setup.json",
        completed.output_dir / "provenance.json",
        completed.output_dir / "validation.json",
    ) + tuple(completed.output_dir / name for name in EXTRA_ARTIFACTS)
    if not all(path.is_file() for path in required):
        return None

    try:
        sim_setup = json.loads(
            (completed.output_dir / "sim_setup.json").read_text(encoding="utf-8")
        )
        provenance = json.loads(
            (completed.output_dir / "provenance.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise SimulationError(
            "Existing output metadata is unreadable for {}: {}".format(
                run.scenario_id, exc
            )
        ) from exc

    expected_setup = _run_metadata(run)
    stale_reasons = []
    if sim_setup != expected_setup:
        stale_reasons.append("scenario configuration differs")
    if provenance.get("configuration_sha256") != sha256_file(config_path):
        stale_reasons.append("benchmark configuration file changed")
    if provenance.get("runtime_source_sha256") != _runtime_source_hashes():
        stale_reasons.append("simulation/export source changed")

    expected_release_paths = (
        completed.continuous,
        completed.discrete,
        completed.hybrid,
        completed.oracle_states,
        completed.verification,
        completed.fault_events,
        completed.system_knowledge,
        completed.technical_timing,
        completed.output_dir / "sim_setup.json",
    ) + tuple(completed.output_dir / name for name in EXTRA_ARTIFACTS)
    recorded_release_hashes = provenance.get("release", {}).get(
        "artifact_sha256", {}
    )
    expected_relative_paths = {
        str(path.relative_to(completed.output_dir)) for path in expected_release_paths
    }
    if (
        not isinstance(recorded_release_hashes, dict)
        or set(recorded_release_hashes) != expected_relative_paths
        or any(
            not (completed.output_dir / relative).is_file()
            or sha256_file(completed.output_dir / relative) != digest
            for relative, digest in recorded_release_hashes.items()
        )
    ):
        stale_reasons.append("release artifact changed")

    recorded_models = provenance.get("model_sha256", {})
    if not isinstance(recorded_models, dict) or not recorded_models or any(
        not Path(path).is_file() or sha256_file(Path(path)) != digest
        for path, digest in recorded_models.items()
    ):
        stale_reasons.append("reusable Modelica source changed")

    if stale_reasons:
        raise SimulationError(
            "Cannot resume stale output {}: {}. Use --force to regenerate it.".format(
                completed.output_dir, "; ".join(stale_reasons)
            )
        )
    validate_diagnosis_release(completed.output_dir, run)
    return completed


def _execute_run(
    run: RunSpec,
    config_path: Path,
    output_root: Path,
    build_root: Path,
    force: bool,
    resume: bool,
) -> CompletedRun:
    if resume:
        existing = _load_resumable_run(output_root, run, config_path)
        if existing is not None:
            print("[resume] {}".format(run.scenario_id))
            return existing

    output_dir = output_root / run.scenario_id
    if output_dir.exists():
        if not force:
            raise SimulationError(
                "Output already exists or is incomplete: {} (use --force)".format(
                    output_dir
                )
            )
        _safe_remove_output(output_dir, output_root)

    print("[simulate] {}".format(run.scenario_id))
    artifacts = run_openmodelica(
        setup=run.setup,
        config_dir=config_path.parent,
        build_root=build_root,
        scenario_id=run.scenario_id,
        force=force or resume,
    )

    exported = export_result_files(
        artifacts.raw_result,
        output_dir,
        run.scenario_id,
        run.setup["sim_setup"],
    )
    metadata = write_release_metadata(output_dir, run, exported)
    exported, diagnosis_validation = enrich_release(
        output_dir, run, exported, artifacts.model_hashes, require_recorded=True
    )
    release_validation = validate_release_bundle(
        exported, run, metadata.fault_events, metadata.system_knowledge,
        metadata.technical_timing,
    )
    _write_json(
        output_dir / "sim_setup.json",
        _run_metadata(run),
    )
    release_artifacts = (
        exported.continuous,
        exported.discrete,
        exported.hybrid,
        exported.oracle_states,
        exported.verification,
        metadata.fault_events,
        metadata.system_knowledge,
        metadata.technical_timing,
        output_dir / "sim_setup.json",
    ) + tuple(output_dir / name for name in EXTRA_ARTIFACTS)
    _write_json(
        output_dir / "provenance.json",
        _provenance(
            config_path,
            run,
            artifacts.raw_validation,
            artifacts.model_hashes,
            artifacts.modelica_version,
            output_dir,
            release_artifacts,
        ),
    )
    _write_json(
        output_dir / "validation.json",
        {
            "valid": not run.is_fault,
            "category": "normal_run" if not run.is_fault else "pending_pair_validation",
            "raw_result": dict(artifacts.raw_validation),
            "safe_columns": list(exported.safe_columns),
            "oracle_columns": list(exported.oracle_columns),
            "release_export": dict(release_validation),
            "diagnosis_extension": diagnosis_validation,
        },
    )
    return CompletedRun(
        run=run,
        output_dir=output_dir,
        continuous=exported.continuous,
        discrete=exported.discrete,
        hybrid=exported.hybrid,
        oracle_states=exported.oracle_states,
        verification=exported.verification,
        fault_events=metadata.fault_events,
        system_knowledge=metadata.system_knowledge,
        technical_timing=metadata.technical_timing,
    )


def _validate_pair(normal: CompletedRun, fault: CompletedRun) -> None:
    existing_validation = json.loads(
        (fault.output_dir / "validation.json").read_text(encoding="utf-8")
    )
    report = validate_fault_pair(
        normal_measurements_path=normal.hybrid,
        fault_measurements_path=fault.hybrid,
        normal_verification_path=normal.verification,
        fault_verification_path=fault.verification,
        normal_run=normal.run,
        run=fault.run,
    )
    report["raw_result"] = existing_validation.get("raw_result")
    report["safe_columns"] = existing_validation.get("safe_columns")
    report["oracle_columns"] = existing_validation.get("oracle_columns")
    report["release_export"] = existing_validation.get("release_export")
    report["diagnosis_extension"] = existing_validation.get("diagnosis_extension")
    update_technical_timing_with_pair(fault.technical_timing, report)
    if report.get("diagnosis_extension"):
        update_diagnosis_pair_timing(normal.output_dir, fault.output_dir, fault.run, report)
    _refresh_provenance_artifact_hash(fault.output_dir, fault.technical_timing)
    write_validation_report(report, fault.output_dir / "validation.json")
    if not report["valid"]:
        print(
            "[undetectable] {}: {}".format(
                fault.run.scenario_id, report["category"]
            ),
            file=sys.stderr,
        )
    require_valid_report(report)


def _set_seed(benchmark: Dict[str, Any], seed: int) -> None:
    if not 1 <= seed <= 2_147_483_646:
        raise ConfigError("--seed must be between 1 and 2147483646")
    for scenario in benchmark.values():
        scenario["sim_setup"]["seed"] = seed
