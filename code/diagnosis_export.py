"""Add recorded commands and diagnosis metadata to benchmark exports."""
from dataclasses import replace
from pathlib import Path
import hashlib
import json

import pandas as pd
import yaml

from actuator_channels import (SCHEMA_VERSION, REGISTRY_VERSION, command_catalogue,
                               reconstruct_commands, recorded_commands, validate_command_equations, verify_sources)
from export import (ExportBundle, ExportError, OracleVariable, IDENTIFIER_COLUMNS,
                    classify_columns)

AUDIT_PATH = "audit_for_verification/internal_verification.csv"
EXTRA_ARTIFACTS = ("commands.parquet", "channel_catalogue.yaml", "permitted_inputs.json")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def read_json(path):
    return json.loads(Path(path).read_text())


def renamed_variables(variables):
    return [replace(v, oracle_column=v.oracle_column.replace(".oracle.actuator_command.pump.speed", ".oracle.fault_adjusted_command.pump.speed"),
                    kind="fault_adjusted_actuator_command") if v.raw_column.endswith(".pump_n_in") else v
            for v in variables]


def derived_cooler_variables(setup):
    """Source-variable names are equation provenance, not recorded raw columns."""
    return [OracleVariable(
        f"{module}.{cooler}.Q_flow",
        f"{module}.oracle.actuator_effective.{cooler}.heat_flow",
        module, cooler, "equation_derived_effective_heat_input", "W", "actuator_state",
    ) for module, config in sorted(setup["model"]["modules"].items())
       if config["type"] == "distill" for cooler in ("cooler_B102", "cooler_B103")]


def add_cooler_references(output_dir, run, bundle, hashes):
    """Add verified constant effective inputs and explicit non-measurement metadata."""
    from actuator_channels import MODELS
    import re
    output_dir = Path(output_dir)
    recorded_raw = {v.raw_column for v in bundle.oracle_variables}
    variables = [v for v in derived_cooler_variables(run.setup) if v.raw_column not in recorded_raw]
    if not variables:
        return bundle
    # This proof is tied to the reviewed model hash, including its constant equations.
    verified = verify_sources(run.setup)
    if verified != hashes:
        raise ExportError("Cooler derivation source identity mismatch")
    source = (MODELS / "Distill.mo").read_text()
    oracle = pd.read_parquet(bundle.oracle_states)
    knowledge_path = output_dir / "system_knowledge.yaml"
    knowledge = yaml.safe_load(knowledge_path.read_text())
    timing_path = output_dir / "technical_timing.json"
    timing = read_json(timing_path)
    period = timing["time_axis"]["sample_period"]
    names = {v.oracle_column for v in variables}
    knowledge["variables"] = [v for v in knowledge["variables"] if v["name"] not in names]
    timing["channels"] = [v for v in timing["channels"] if v["column"] not in names]
    for variable in variables:
        name = variable.oracle_column
        if name in oracle and not oracle[name].eq(0.0).all():
            raise ExportError(f"Nonzero constant cooler reference: {name}")
        oracle[name] = 0.0
        match = re.search(r"^\s*" + re.escape(variable.component) + r"\.Q_flow\s*=.*?;", source, re.M | re.S)
        if not match:
            raise ExportError(f"Missing verified cooler equation: {variable.component}")
        knowledge["variables"].append({
            "name": name, "module": variable.module, "component": variable.component,
            "kind": variable.kind, "unit": "W", "oracle_role": "actuator_state",
            "physical_meaning": "Effective heat input prescribed identically zero by the cooler equation",
            "status": "equation_derived", "availability": "equation_derived_not_recorded",
            "online_observable": False, "online_feature_allowed": False,
            "offline_target_allowed": True, "direct_fault_revealing": False,
            "raw_result_column": None, "oracle_column": name,
            "sign_convention": "positive heat supplied to fluid; negative would remove heat",
            "lower_bound": 0.0, "upper_bound": 0.0,
            "limits": {"constant_value": 0.0, "extra_saturation": "not_modelled"},
            "delay": {"kind": "algebraic", "delay_s": 0.0},
            "provenance": {"modelica_source": "Distill.mo", "source_sha256": hashes["Distill.mo"],
                           "source_variable": variable.raw_column, "raw_result_column": None,
                           "source_equation": match.group(0).strip(), "derivation": "constant_zero_from_verified_equation"},
        })
        timing["channels"].append({
            "column": name, "role": "oracle_state", "sample_period": period,
            "sampling": "canonical_simulator_grid", "derivation": "constant_zero_from_verified_equation",
            "sensor_delay": {"status": "not_applicable"},
            "communication_delay": {"status": "not_applicable"}, "logging_delay": {"status": "not_applicable"},
        })
    original_names = {v.oracle_column for v in bundle.oracle_variables}
    combined = list(bundle.oracle_variables) + [v for v in variables if v.oracle_column not in original_names]
    timing["channel_groups"]["oracle_states"]["columns"] = [v.oracle_column for v in combined]
    oracle.to_parquet(bundle.oracle_states, index=False, engine="pyarrow")
    knowledge_path.write_text(yaml.safe_dump(knowledge, sort_keys=False))
    write_json(timing_path, timing)
    return replace(bundle, oracle_variables=tuple(combined), oracle_columns=tuple(v.oracle_column for v in combined))


def rename_references(value, mapping):
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [rename_references(v, mapping) for v in value]
    if isinstance(value, dict):
        return {mapping.get(k, k): rename_references(v, mapping) for k, v in value.items()}
    return value


def check_alignment(left, right):
    for frame in (left, right):
        if not set(IDENTIFIER_COLUMNS).issubset(frame):
            raise ExportError("Missing scenario/step/time identifiers")
        if frame[list(IDENTIFIER_COLUMNS)].isna().any().any() or frame.duplicated(list(IDENTIFIER_COLUMNS)).any():
            raise ExportError("Missing or duplicate identifiers")
        if not frame.simulation_time.is_monotonic_increasing or frame.simulation_time.duplicated().any():
            raise ExportError("Non-unique or unordered simulation time")
    if len(left) != len(right):
        raise ExportError("Mismatched table length")
    for key in IDENTIFIER_COLUMNS:
        if not (left[key].to_numpy() == right[key].to_numpy()).all():
            raise ExportError(f"Tables are not aligned on {key}")


def update_diagnosis_pair_timing(normal_dir, fault_dir, run, report):
    from validation import _change_summary
    from dataset_metadata import _first_observed_change
    normal = pd.read_parquet(Path(normal_dir) / "commands.parquet")
    fault = pd.read_parquet(Path(fault_dir) / "commands.parquet")
    summary = _change_summary(normal, fault, list(normal)[3:], run.setup["sim_setup"]["faultStart"], 1e-9, 1e-7, 3)
    path = Path(fault_dir) / "technical_timing.json"
    timing = read_json(path)
    timing["fault_timing"]["diagnosis_observations"] = {
        "commands": _first_observed_change(summary),
        "measurements": _first_observed_change(report["safe_channel_differences"]),
        "offline_references": _first_observed_change(report["verification_channel_differences"]),
        "measured_actuator_responses": {"status": "not_modelled"},
        "method": report["difference_detection"],
        "interpretation": "Sampled same-seed differences, not exact causal onset or independently calibrated detector performance",
    }
    write_json(path, timing)


def enrich_release(output_dir, run, bundle, recorded_hashes=None, require_recorded=False):
    """Add the v2.2 diagnosis contract to a staged simulation release."""
    from dataset_metadata import enrich_diagnosis_metadata
    output_dir = Path(output_dir)
    hashes = verify_sources(run.setup, recorded_hashes)
    audit = pd.read_csv(bundle.verification)
    hybrid = pd.read_parquet(bundle.hybrid)
    check_alignment(hybrid, audit)
    commands = recorded_commands(audit, run.setup)
    recorded = commands is not None
    if require_recorded and not recorded:
        raise ExportError("Fresh simulation is missing recorded nominal commands")
    if not recorded:
        commands = reconstruct_commands(audit, run.setup)
    checked = validate_command_equations(commands, audit, run.setup)
    entries = command_catalogue(run.setup, hashes, recorded=recorded)
    variables = renamed_variables(bundle.oracle_variables)
    mapping = {old.oracle_column: new.oracle_column for old, new in zip(bundle.oracle_variables, variables)
               if old.oracle_column != new.oracle_column}
    oracle = pd.read_parquet(bundle.oracle_states).rename(columns=mapping)
    oracle.to_parquet(bundle.oracle_states, index=False, engine="pyarrow")
    new_audit = output_dir / AUDIT_PATH
    new_audit.parent.mkdir(exist_ok=True)
    if bundle.verification != new_audit:
        bundle.verification.rename(new_audit)
        if not any(bundle.verification.parent.iterdir()):
            bundle.verification.parent.rmdir()
    bundle = replace(bundle, verification=new_audit, oracle_variables=tuple(variables),
                     oracle_columns=tuple(v.oracle_column for v in variables))
    commands.to_parquet(output_dir / "commands.parquet", index=False, engine="pyarrow")
    for name in ("fault_events.json", "technical_timing.json", "system_knowledge.yaml"):
        path = output_dir / name
        document = yaml.safe_load(path.read_text()) if name.endswith("yaml") else read_json(path)
        document = rename_references(document, mapping)
        document["schema_version"] = SCHEMA_VERSION
        if name.endswith("yaml"):
            for entry in document["variables"]:
                if entry["name"].endswith(".oracle.fault_adjusted_command.pump.speed"):
                    entry["kind"] = "fault_adjusted_actuator_command"
                    entry["physical_meaning"] = "Fault-adjusted controller speed before noise and lag; not the nominal command"
            path.write_text(yaml.safe_dump(document, sort_keys=False))
        else:
            write_json(path, document)
    bundle = add_cooler_references(output_dir, run, bundle, hashes)
    enrich_diagnosis_metadata(output_dir, run, bundle, entries, hashes, mapping)
    return bundle, {"valid": True, "schema_version": SCHEMA_VERSION,
                    "command_columns": len(entries), "equations_checked": checked,
                    "measured_actuator_responses": "not_modelled",
                    "source_sha256": hashes}


def validate_diagnosis_release(path, run):
    import numpy as np
    path = Path(path)
    policy = read_json(path / "permitted_inputs.json")
    if policy.get("schema_version") != SCHEMA_VERSION:
        raise ExportError("Unsupported diagnostic schema")
    hybrid = pd.read_parquet(path / "hybrid/measurements.parquet")
    commands = pd.read_parquet(path / "commands.parquet")
    audit = pd.read_csv(path / AUDIT_PATH)
    check_alignment(hybrid, commands)
    check_alignment(hybrid, audit)
    expected = recorded_commands(audit, run.setup)
    recorded = expected is not None
    if not recorded:
        expected = reconstruct_commands(audit, run.setup)
    if list(expected) != list(commands) or not np.array_equal(expected.iloc[:, 3:].to_numpy(), commands.iloc[:, 3:].to_numpy()):
        raise ExportError("Commands differ from verified controller reconstruction")
    validate_command_equations(commands, audit, run.setup)
    catalogue = yaml.safe_load((path / "channel_catalogue.yaml").read_text())
    if catalogue.get("schema_version") != SCHEMA_VERSION or catalogue.get("scenario_id") != run.scenario_id:
        raise ExportError("Channel catalogue identity mismatch")
    source_hashes = verify_sources(run.setup)
    expected_catalogue = command_catalogue(run.setup, source_hashes, recorded=recorded)
    if len(catalogue.get("commands", [])) != len(expected_catalogue):
        raise ExportError("Incomplete actuator catalogue")
    for actual, expected_entry in zip(catalogue["commands"], expected_catalogue):
        for key, value in expected_entry.items():
            if actual.get(key) != value:
                raise ExportError(f"Command catalogue mismatch: {expected_entry['name']}:{key}")
    oracle = pd.read_parquet(path / "oracle_states.parquet")
    check_alignment(hybrid, oracle)
    entries = {v["name"]: v for v in catalogue["recorded_channels"]}
    for variable in derived_cooler_variables(run.setup):
        name = variable.oracle_column
        if name not in oracle or not oracle[name].eq(0.0).all():
            raise ExportError(f"Missing/nonzero equation-derived cooler reference: {name}")
        entry = entries.get(name, {})
        if recorded:
            if (variable.raw_column not in audit or not audit[variable.raw_column].eq(0.0).all()
                    or entry.get("raw_result_column") != variable.raw_column
                    or entry.get("online_feature_allowed") is not False):
                raise ExportError(f"Invalid recorded cooler reference: {name}")
            command = next(c for c in catalogue["commands"]
                           if c["component"] == f"{variable.module}.{variable.component}")
            if command.get("effective_reference_column") != name or command.get("effective_reference_status") != "exported_offline":
                raise ExportError(f"Broken recorded cooler command/reference link: {name}")
            continue
        if (entry.get("availability") != "equation_derived_not_recorded"
                or entry.get("online_feature_allowed") is not False
                or entry.get("online_observable") is not False
                or entry.get("raw_result_column", "missing") is not None
                or entry.get("provenance", {}).get("source_sha256") != source_hashes["Distill.mo"]):
            raise ExportError(f"Invalid cooler derivation metadata: {name}")
        command = next(c for c in catalogue["commands"]
                       if c["component"] == f"{variable.module}.{variable.component}")
        if command.get("effective_reference_column") != name or command.get("effective_reference_status") != "equation_derived_offline":
            raise ExportError(f"Broken cooler command/reference link: {name}")
    timing = read_json(path / "technical_timing.json")["fault_timing"]
    if "paired_run_observations" in timing:
        for key in ("first_internal_consequence", "first_measurement_consequence"):
            entry = timing.get(key, {})
            if entry.get("status") not in {"not_observed", "observed_paired_run_difference"} or not entry.get("method"):
                raise ExportError(f"Unresolved paired timing field: {key}")
        validation_path = path / "validation.json"
        if validation_path.exists():
            from dataset_metadata import paired_consequences
            report = read_json(validation_path)
            if "safe_channel_differences" in report:
                for key, expected_entry in paired_consequences(report).items():
                    if timing[key] != expected_entry:
                        raise ExportError(f"Paired timing differs from validation evidence: {key}")
    if policy.get("module_types") != {n: m["type"] for n, m in run.setup["model"]["modules"].items()}:
        raise ExportError("Policy module types differ from configuration")
    continuous, discrete, _ = classify_columns(list(hybrid))
    permitted = sorted(continuous + discrete)
    if sorted(c for c in hybrid if c not in IDENTIFIER_COLUMNS) != permitted:
        raise ExportError("Unknown measurement columns")
    if policy["measurements"] != permitted or policy["commands"] != list(commands)[3:] or policy["actuator_responses"] != []:
        raise ExportError("Diagnostic allowlist mismatch")
    for frame in (hybrid, commands, audit):
        if not np.isfinite(frame.drop(columns=["scenario_id"]).to_numpy(dtype=float)).all():
            raise ExportError("Non-finite diagnostic/verification data")
    return {"valid": True, "rows": len(hybrid), "commands": len(commands.columns) - 3}
