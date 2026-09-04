"""Command-line entry point for validated HAI-CPPS v2 generation."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from config import (
    ConfigError,
    RunSpec,
    focused_fault_pair,
    generate_normal_campaign,
    generate_single_fault_campaign,
    load_benchmark_config,
)
from dataset_metadata import (
    ORACLE_CATALOGUE_VERSION,
    RELEASE_SCHEMA_VERSION,
    update_technical_timing_with_pair,
    write_release_metadata,
)
from export import ExportError, export_result_files
from runner import SimulationError, check_openmodelica_topologies, run_openmodelica
from validation import (
    ValidationError,
    duplicate_signal_groups,
    require_valid_report,
    sha256_file,
    validate_fault_pair,
    validate_release_bundle,
    write_validation_report,
)


DEFAULT_CONFIG = Path(__file__).resolve().parent / "benchmark_setup.json"
DEFAULT_SEED = 20260831
RUNTIME_SOURCE_PATHS = (
    Path(__file__).resolve(),
    Path(__file__).resolve().parent / "config.py",
    Path(__file__).resolve().parent / "dataset_metadata.py",
    Path(__file__).resolve().parent / "export.py",
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
        "data_roles": {
            "continuous/measurements.parquet": "measurement_features",
            "discrete/measurements.parquet": "measurement_features",
            "hybrid/measurements.parquet": "measurement_features",
            "oracle_states.parquet": "offline_oracle_non_feature",
            "fault_events.json": "labels_and_fault_metadata_non_feature",
            "system_knowledge.yaml": "structural_knowledge_non_feature",
            "technical_timing.json": "timing_metadata_non_feature",
            "audit/internal_verification.csv": "internal_validation_non_feature",
        },
        "release_schema_version": RELEASE_SCHEMA_VERSION,
        "oracle_catalogue_version": ORACLE_CATALOGUE_VERSION,
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
            "schema_version": RELEASE_SCHEMA_VERSION,
            "oracle_catalogue_version": ORACLE_CATALOGUE_VERSION,
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
        verification=output_dir / "audit" / "internal_verification.csv",
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
    )
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
    )
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
    release_validation = validate_release_bundle(
        exported,
        run,
        metadata.fault_events,
        metadata.system_knowledge,
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
    )
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
    update_technical_timing_with_pair(fault.technical_timing, report)
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


def _selected_datasets(
    benchmark: Mapping[str, Any], scenario: Optional[str]
) -> Optional[List[str]]:
    if scenario is None:
        return None
    if scenario not in benchmark:
        raise ConfigError("Unknown dataset {!r}".format(scenario))
    return [scenario]


def _normal_outputs_for_faults(
    output_root: Path,
    benchmark: Mapping[str, Any],
    fault_runs: Iterable[RunSpec],
    config_path: Path,
) -> Dict[str, CompletedRun]:
    needed = sorted({run.base_dataset for run in fault_runs})
    normal_specs = {
        run.base_dataset: run
        for run in generate_normal_campaign(benchmark, selected=needed)
    }
    outputs: Dict[str, CompletedRun] = {}
    missing = []
    for dataset_name, normal_spec in normal_specs.items():
        completed = _load_resumable_run(output_root, normal_spec, config_path)
        if completed is None:
            missing.append(normal_spec.scenario_id)
        else:
            outputs[dataset_name] = completed
    if missing:
        raise SimulationError(
            "Single-fault validation requires existing normal runs: {}. "
            "Run the normal or full campaign first.".format(", ".join(missing))
        )
    return outputs


def _validate_campaign_duplicates(fault_outputs: Sequence[CompletedRun], output_root: Path) -> None:
    groups = duplicate_signal_groups(output.hybrid for output in fault_outputs)
    report_path = output_root / "campaign_validation.json"
    _write_json(
        report_path,
        {
            "valid": not groups,
            "fault_scenarios": len(fault_outputs),
            "duplicate_signal_groups": groups,
        },
    )
    if groups:
        raise ValidationError(
            "Different fault labels produced identical hybrid signals. See {}".format(
                report_path
            )
        )


def run_command(args: argparse.Namespace) -> int:
    config_path = args.config.resolve()
    benchmark = load_benchmark_config(config_path)
    _set_seed(benchmark, args.seed)
    selected = _selected_datasets(benchmark, args.scenario)
    output_root = args.output.resolve()
    build_root = args.build_root.resolve()

    if bool(args.module) != bool(args.fault):
        raise ConfigError("--module and --fault must be supplied together")
    if args.module and not args.scenario:
        raise ConfigError("A focused --module/--fault run also requires --scenario")

    output_root.mkdir(parents=True, exist_ok=True)
    build_root.mkdir(parents=True, exist_ok=True)

    normal_outputs: Dict[str, CompletedRun] = {}
    fault_outputs: List[CompletedRun] = []

    if args.module:
        normal_spec, fault_spec = focused_fault_pair(
            benchmark, args.scenario, args.module, args.fault
        )
        normal = _execute_run(
            normal_spec,
            config_path,
            output_root,
            build_root,
            args.force,
            args.resume,
        )
        normal_outputs[normal_spec.base_dataset] = normal
        fault = _execute_run(
            fault_spec,
            config_path,
            output_root,
            build_root,
            args.force,
            args.resume,
        )
        _validate_pair(normal, fault)
        fault_outputs.append(fault)
    else:
        if args.campaign in ("normal", "full"):
            for run in generate_normal_campaign(benchmark, selected):
                completed = _execute_run(
                    run,
                    config_path,
                    output_root,
                    build_root,
                    args.force,
                    args.resume,
                )
                normal_outputs[run.base_dataset] = completed

        if args.campaign in ("single-fault", "full"):
            fault_runs = generate_single_fault_campaign(benchmark, selected)
            if args.campaign == "single-fault":
                normal_outputs = _normal_outputs_for_faults(
                    output_root, benchmark, fault_runs, config_path
                )
            for run in fault_runs:
                completed = _execute_run(
                    run,
                    config_path,
                    output_root,
                    build_root,
                    args.force,
                    args.resume,
                )
                _validate_pair(normal_outputs[run.base_dataset], completed)
                fault_outputs.append(completed)

    if fault_outputs:
        _validate_campaign_duplicates(fault_outputs, output_root)
    print(
        "Completed {} normal and {} fault run(s).".format(
            len(normal_outputs), len(fault_outputs)
        )
    )
    return 0


def validate_command(args: argparse.Namespace) -> int:
    benchmark = load_benchmark_config(args.config.resolve())
    normal_count = len(generate_normal_campaign(benchmark))
    fault_count = len(generate_single_fault_campaign(benchmark))
    print(
        "Configuration valid: {} datasets, {} normal runs, {} single-fault runs.".format(
            len(benchmark), normal_count, fault_count
        )
    )
    if args.check_modelica:
        logs = check_openmodelica_topologies(
            benchmark,
            args.config.resolve().parent,
            args.build_root.resolve(),
            force=args.force,
        )
        print("OpenModelica checks passed for {} topologies.".format(len(logs)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validated HAI-CPPS v2 simulation and dataset generation"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate", help="validate configuration without simulation"
    )
    validate_parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="benchmark JSON path"
    )
    validate_parser.add_argument(
        "--check-modelica",
        action="store_true",
        help="also run OpenModelica checkModel for every topology",
    )
    validate_parser.add_argument(
        "--build-root",
        type=Path,
        default=Path("build/model-check"),
        help="directory for optional model-check artifacts",
    )
    validate_parser.add_argument(
        "--force",
        action="store_true",
        help="replace existing model-check directories",
    )
    validate_parser.set_defaults(handler=validate_command)

    run_parser = subparsers.add_parser("run", help="run a validated campaign")
    run_parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="benchmark JSON path"
    )
    run_parser.add_argument(
        "--campaign",
        choices=("normal", "single-fault", "full"),
        default="normal",
        help="'full' means normal plus all one-fault-at-a-time scenarios",
    )
    run_parser.add_argument("--scenario", help="limit execution to one ds name")
    run_parser.add_argument("--module", help="focused fault target module")
    run_parser.add_argument("--fault", help="focused Boolean fault name")
    run_parser.add_argument(
        "--output", type=Path, default=Path("data"), help="dataset output root"
    )
    run_parser.add_argument(
        "--build-root",
        type=Path,
        default=Path("build"),
        help="isolated OpenModelica build root",
    )
    run_parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    output_policy = run_parser.add_mutually_exclusive_group()
    output_policy.add_argument(
        "--force", action="store_true", help="replace this campaign's existing run paths"
    )
    output_policy.add_argument(
        "--resume", action="store_true", help="reuse complete existing run outputs"
    )
    run_parser.set_defaults(handler=run_command)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (ConfigError, ExportError, SimulationError, ValidationError) as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
