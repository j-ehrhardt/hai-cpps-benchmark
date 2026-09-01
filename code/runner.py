"""Isolated and checked OpenModelica execution."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from config import normal_run
from model_generation import model_files_for_setup, write_run_files
from validation import (
    ValidationError,
    assert_hashes_unchanged,
    snapshot_hashes,
    validate_raw_result,
)


class SimulationError(RuntimeError):
    """Raised when OpenModelica does not produce a complete result."""


@dataclass(frozen=True)
class SimulationArtifacts:
    run_dir: Path
    raw_result: Path
    stdout_log: Path
    stderr_log: Path
    raw_validation: Mapping[str, Any]
    model_hashes: Mapping[str, str]
    modelica_version: Optional[str]


def _omc_executable() -> str:
    omc_path = shutil.which("omc")
    if omc_path is None:
        raise SimulationError("OpenModelica executable 'omc' is not available on PATH")
    return omc_path


def _modelica_version(stdout: str) -> Optional[str]:
    for line in stdout.splitlines():
        match = re.fullmatch(r'"(\d+\.\d+\.\d+(?:[^\"]*)?)"', line.strip())
        if match:
            return match.group(1)
    return None


def _safe_remove_directory(path: Path, root: Path) -> None:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise SimulationError(
            "Refusing to remove path outside run root: {}".format(resolved_path)
        ) from exc
    if not relative.parts:
        raise SimulationError("Refusing to remove the run root itself")
    shutil.rmtree(resolved_path)


def _compiler_environment() -> Dict[str, str]:
    """Prefer the system compiler so Conda compiler shims cannot break OMC linking."""

    environment = os.environ.copy()
    system_bin = Path("/usr/bin")
    gcc = system_bin / "gcc"
    gxx = system_bin / "g++"
    if gcc.is_file():
        environment["CC"] = str(gcc)
    if gxx.is_file():
        environment["CXX"] = str(gxx)

    path_parts = environment.get("PATH", "").split(os.pathsep)
    preferred = ["/usr/bin", "/bin"]
    environment["PATH"] = os.pathsep.join(
        preferred + [part for part in path_parts if part and part not in preferred]
    )
    return environment


def run_openmodelica(
    setup: Mapping[str, Any],
    config_dir: Path,
    build_root: Path,
    scenario_id: str,
    force: bool = False,
) -> SimulationArtifacts:
    omc_path = _omc_executable()

    build_root.mkdir(parents=True, exist_ok=True)
    run_dir = build_root / scenario_id
    if run_dir.exists():
        if not force:
            raise SimulationError(
                "Build directory already exists: {} (use --force or --resume)".format(
                    run_dir
                )
            )
        _safe_remove_directory(run_dir, build_root)

    reusable_models = model_files_for_setup(setup, config_dir)
    model_hashes = snapshot_hashes(reusable_models)
    _, mos_path, _ = write_run_files(setup, config_dir, run_dir)
    stdout_path = run_dir / "omc.stdout.log"
    stderr_path = run_dir / "omc.stderr.log"

    try:
        completed = subprocess.run(
            [omc_path, mos_path.name],
            cwd=str(run_dir),
            env=_compiler_environment(),
            text=True,
            capture_output=True,
            check=False,
        )
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")

        raw_result = run_dir / "processPlant_res.csv"
        if completed.returncode != 0:
            raise SimulationError(
                "OpenModelica exited with status {} for {}. Logs: {}, {}".format(
                    completed.returncode, scenario_id, stdout_path, stderr_path
                )
            )
        if "Check of processPlant completed successfully." not in completed.stdout:
            raise SimulationError(
                "OpenModelica model check did not succeed for {}. Logs: {}, {}".format(
                    scenario_id, stdout_path, stderr_path
                )
            )
        if not raw_result.is_file():
            raise SimulationError(
                "OpenModelica reported no shell error but produced no result for {}. "
                "Inspect {} and {}".format(scenario_id, stdout_path, stderr_path)
            )
        try:
            raw_validation = validate_raw_result(raw_result, setup["sim_setup"])
        except ValidationError as exc:
            raise SimulationError(
                "Incomplete/invalid OpenModelica result for {}: {}. Build: {}".format(
                    scenario_id, exc, run_dir
                )
            ) from exc
    finally:
        assert_hashes_unchanged(model_hashes, reusable_models)

    modelica_version = _modelica_version(completed.stdout)
    if modelica_version != "4.0.0":
        raise SimulationError(
            "Expected Modelica Standard Library 4.0.0 for {}, found {!r}. "
            "Inspect {}".format(scenario_id, modelica_version, stdout_path)
        )

    return SimulationArtifacts(
        run_dir=run_dir,
        raw_result=raw_result,
        stdout_log=stdout_path,
        stderr_log=stderr_path,
        raw_validation=raw_validation,
        model_hashes=model_hashes,
        modelica_version=modelica_version,
    )


def check_openmodelica_topologies(
    benchmark: Mapping[str, Mapping[str, Any]],
    config_dir: Path,
    build_root: Path,
    force: bool = False,
) -> Dict[str, Path]:
    """Run OpenModelica's structural check for every configured topology."""

    omc_path = _omc_executable()
    build_root.mkdir(parents=True, exist_ok=True)
    logs: Dict[str, Path] = {}
    for dataset_name, setup in benchmark.items():
        scenario_id = "{}_check".format(dataset_name)
        run_dir = build_root / scenario_id
        if run_dir.exists():
            if not force:
                raise SimulationError(
                    "Model-check directory already exists: {} (use --force)".format(
                        run_dir
                    )
                )
            _safe_remove_directory(run_dir, build_root)

        checked_setup = normal_run(dataset_name, setup).setup
        reusable_models = model_files_for_setup(checked_setup, config_dir)
        model_hashes = snapshot_hashes(reusable_models)
        _, mos_path, _ = write_run_files(
            checked_setup,
            config_dir,
            run_dir,
            include_simulation=False,
        )
        stdout_path = run_dir / "omc.stdout.log"
        stderr_path = run_dir / "omc.stderr.log"
        try:
            completed = subprocess.run(
                [omc_path, mos_path.name],
                cwd=str(run_dir),
                env=_compiler_environment(),
                text=True,
                capture_output=True,
                check=False,
            )
            stdout_path.write_text(completed.stdout, encoding="utf-8")
            stderr_path.write_text(completed.stderr, encoding="utf-8")
            success = "Check of processPlant completed successfully."
            if completed.returncode != 0 or success not in completed.stdout:
                raise SimulationError(
                    "OpenModelica model check failed for {}. Logs: {}, {}".format(
                        dataset_name, stdout_path, stderr_path
                    )
                )
        finally:
            assert_hashes_unchanged(model_hashes, reusable_models)
        logs[dataset_name] = stdout_path
    return logs
