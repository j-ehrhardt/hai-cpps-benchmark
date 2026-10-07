import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from actuator_channels import reconstruct_commands, recorded_commands, verify_sources, validate_command_equations, command_specs
from config import load_benchmark_config, normal_run
from dataset_io import load_diagnosis_dataset, load_scenario_dataset
from dataset_metadata import write_release_metadata, update_technical_timing_with_pair
from export import ExportError, export_result_files
from export_v2_1 import (export_v2_1, enrich_release, digest, read_json,
                        validate_diagnosis_release, write_json)
from runner import SimulationArtifacts
from sim import _execute_run, _load_resumable_run

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "code/benchmark_setup.json"


def fixture():
    run = normal_run("ds4", load_benchmark_config(CONFIG)["ds4"])
    run.setup["sim_setup"].update(stopTime=4, numberOfIntervals=4, faultStart=2)
    values = {
        "time": [0., 1., 2., 3., 4.],
        "bottling0.tank_B401.level": [.01] * 5,
        "bottling0.sensor_discrete_tank_B401_high.showActive": [0] * 5,
        "bottling0.state_filling_tank_B401.active": [0] * 5,
        "bottling0.state_emptying_tank_B401.active": [0] * 5,
        "bottling0.state_bottling.active": [1] * 5,
        "bottling0.pump_n_in": [0.] * 5,
        "bottling0.pump_P401.N_in": [0.] * 5,
        "bottling0.valve_in.opening": [.0001] * 5,
        "bottling0.valve_pump_P401.opening": [.0001] * 5,
        "bottling0.valve_out.opening": [1., 1., .0001, .0001, 1.],
        "bottling0.var_pump_n": [1.] * 5,
        "bottling0.var_valve_in": [0.] * 5,
        "bottling0.fault_window_active": [0, 0, 1, 1, 1],
        "bottling0.leaking_valve.opening": [0.] * 5,
        "bottling0.leaking_valve.m_flow": [0.] * 5,
        "bottling0.uniformNoise.y": [1.] * 5,
    }
    return run, pd.DataFrame(values)


class DiagnosisExportTests(unittest.TestCase):
    def test_direct_commands_are_exported_and_missing_or_corrupt_logs_rejected(self):
        import yaml
        run, raw = fixture()
        audit = raw.rename(columns={"time": "simulation_time"})
        audit.insert(0, "simulation_step", range(len(audit)))
        audit.insert(0, "scenario_id", run.scenario_id)
        expected = reconstruct_commands(audit, run.setup)
        for spec in command_specs(run.setup):
            raw[spec.recorded_command] = expected[spec.name]
            audit[spec.recorded_command] = expected[spec.name]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            raw.to_csv(path / "raw.csv", index=False)
            export_v2_1(path / "raw.csv", path / "release", run)
            catalogue = yaml.safe_load((path / "release/channel_catalogue.yaml").read_text())
            self.assertTrue(all(c['availability'] == 'recorded_controller_output' for c in catalogue['commands']))
            pd.testing.assert_frame_equal(pd.read_parquet(path / 'release/commands.parquet'), expected)
        spec = command_specs(run.setup)[0]
        with self.assertRaisesRegex(ExportError, 'Incomplete recorded'):
            recorded_commands(audit.drop(columns=spec.recorded_command), run.setup)
        audit[spec.recorded_command] = 99.
        with self.assertRaisesRegex(ExportError, 'violates controller law'):
            recorded_commands(audit, run.setup)

    def test_completed_pair_resolves_timing_with_explicit_scope(self):
        report = {
            "target_module": "mixer0", "target_connectivity": {},
            "difference_detection": {"absolute_tolerance": 1e-9, "relative_tolerance": 1e-7, "persistence_samples": 3},
            "verification_channel_differences": {
                "other0.pump_n_in": {"first_persistent_change": 1.0},
                "mixer0.pump_n_in": {"first_persistent_change": 4.0},
            },
            "safe_channel_differences": {
                "other0.tank.level": {"first_persistent_change": 5.0},
                "mixer0.tank.level": {"first_persistent_change": 7.0},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "timing.json"
            write_json(path, {"fault_timing": {"first_internal_consequence": {"status": "pending_paired_run"},
                                               "first_measurement_consequence": {"status": "pending_paired_run"},
                                               "intended_injection_time": 2.0}})
            update_technical_timing_with_pair(path, report)
            timing = read_json(path)["fault_timing"]
            self.assertEqual(timing["first_internal_consequence"]["time"], 4.0)
            self.assertEqual(timing["first_measurement_consequence"]["time"], 5.0)
            self.assertEqual(timing["first_measurement_consequence"]["method"], report["difference_detection"])
            self.assertEqual(timing["intended_injection_time"], 2.0)
            report["verification_channel_differences"] = {}
            report["safe_channel_differences"] = {}
            update_technical_timing_with_pair(path, report)
            for key in ("first_internal_consequence", "first_measurement_consequence"):
                self.assertEqual(read_json(path)["fault_timing"][key]["status"], "not_observed")
                self.assertNotIn("time", read_json(path)["fault_timing"][key])

    def test_cooler_effective_inputs_are_derived_offline_and_validated(self):
        import yaml
        run = normal_run("ds2", load_benchmark_config(CONFIG)["ds2"])
        run.setup["sim_setup"].update(stopTime=4, numberOfIntervals=4, faultStart=2)
        raw = pd.DataFrame({"time": [0., 1., 2., 3., 4.],
                            "distill0.tank_B101.level": [.01]*5,
                            "distill0.sensor_discrete_tank_B101_high.showActive": [0]*5})
        for spec in command_specs(run.setup):
            for state in spec.states:
                raw[f"{spec.module}.{state}.active"] = 0
            if not spec.component.startswith("cooler_"):
                raw[spec.raw] = spec.off
        raw["distill0.var_pump_n"] = 1.
        raw["distill0.var_heat"] = 1.
        raw["distill0.var_valve_in0"] = 0.
        raw["distill0.pump_P101.N_in"] = 0.
        raw["distill0.uniformNoise.y"] = 1.
        raw["distill0.fault_window_active"] = [0, 0, 1, 1, 1]
        raw["distill0.leaking_valve.opening"] = 0.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv = root / "raw.csv"
            raw.to_csv(csv, index=False)
            bundle, _ = export_v2_1(csv, root / "release", run)
            release = root / "release"
            offline = load_diagnosis_dataset(release, include_oracle=True)
            catalogue = yaml.safe_load((release / "channel_catalogue.yaml").read_text())
            for cooler in ("cooler_B102", "cooler_B103"):
                name = f"distill0.oracle.actuator_effective.{cooler}.heat_flow"
                self.assertEqual(offline.oracle_states[name].tolist(), [0.]*5)
                self.assertNotIn(name, offline.online_features)
                entry = next(v for v in catalogue["recorded_channels"] if v["name"] == name)
                self.assertEqual(entry["availability"], "equation_derived_not_recorded")
                self.assertIsNone(entry["raw_result_column"])
                self.assertFalse(entry["online_feature_allowed"])
                self.assertIn(f"{cooler}.Q_flow =", entry["provenance"]["source_equation"])
                link = next(v for v in catalogue["commands"] if v["component"] == f"distill0.{cooler}")
                self.assertEqual(link["effective_reference_column"], name)
            oracle = pd.read_parquet(bundle.oracle_states)
            oracle.loc[0, name] = 1.
            oracle.to_parquet(bundle.oracle_states, index=False)
            with self.assertRaisesRegex(ExportError, "cooler reference"):
                validate_diagnosis_release(release, run)
            oracle.loc[0, name] = 0.
            oracle.to_parquet(bundle.oracle_states, index=False)
            timing = read_json(release / "technical_timing.json")
            timing["fault_timing"]["paired_run_observations"] = {}
            timing["fault_timing"]["first_internal_consequence"] = {"status": "pending_paired_run"}
            write_json(release / "technical_timing.json", timing)
            with self.assertRaisesRegex(ExportError, "Unresolved paired timing"):
                validate_diagnosis_release(release, run)

    def test_control_laws_for_every_module_type(self):
        config = load_benchmark_config(CONFIG)
        cases = [
            ("ds1", "mixer0", "state_emptying_tank_B202", 9, "pump_P101.speed", 150.),
            ("ds2", "distill0", "state_destillation", 10, "heater_distill.heat_flow", 20000.),
            ("ds3", "filter0", "state_emptying_tank_B101", 4, "pump_P101.speed", 150.),
            ("ds4", "bottling0", "state_bottling", 4, "valve_out.opening", 1.),
        ]
        for dataset, module, active, count, channel, value in cases:
            with self.subTest(dataset=dataset):
                setup = config[dataset]
                audit = pd.DataFrame({"scenario_id": [dataset]*2, "simulation_step": [0, 1], "simulation_time": [0., 1.]})
                for spec in command_specs(setup):
                    for state in spec.states:
                        audit[f"{spec.module}.{state}.active"] = [0, int(state == active)]
                commands = reconstruct_commands(audit, setup)
                self.assertEqual(len(commands.columns)-3, count)
                self.assertEqual(commands.loc[1, f"{module}.command.{channel}"], value)
                if dataset == "ds2":
                    self.assertEqual(commands["distill0.command.cooler_B102.heat_flow"].tolist(), [0., 0.])
                if dataset == "ds3":
                    self.assertEqual(commands["filter0.command.valve_out.opening"].tolist(), [0., 0.])

    def test_raw_and_migration_agree_and_preserve_measurements(self):
        run, raw = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv = root / "raw.csv"
            raw.to_csv(csv, index=False)
            legacy = export_result_files(csv, root / "migrated", run.scenario_id, run.setup["sim_setup"])
            write_release_metadata(root / "migrated", run, legacy)
            with self.assertRaisesRegex(ExportError, "missing recorded nominal commands"):
                enrich_release(root / "migrated", run, legacy, require_recorded=True)
            before = {p.name + p.parent.name: digest(p) for p in (legacy.hybrid, legacy.continuous, legacy.discrete, legacy.verification)}
            updated, _ = enrich_release(root / "migrated", run, legacy)
            direct, _ = export_v2_1(csv, root / "direct", run)
            self.assertEqual(before, {p.name + ("audit" if p == updated.verification else p.parent.name): digest(p)
                                      for p in (updated.hybrid, updated.continuous, updated.discrete, updated.verification)})
            pd.testing.assert_frame_equal(pd.read_parquet(root / "migrated/commands.parquet"), pd.read_parquet(root / "direct/commands.parquet"))
            validate_diagnosis_release(root / "migrated", run)
            result = load_diagnosis_dataset(root / "direct")
            self.assertIsNone(result.oracle_states)
            self.assertIsNone(result.annotations)
            self.assertEqual(result.online_features["bottling0.command.valve_out.opening"].tolist(), [1., 1., .0001, .0001, 1.])
            self.assertFalse(any(".oracle." in c for c in result.online_features))
            self.assertNotIn("simulation_time", result.online_features)
            self.assertIn("bottling0.oracle.fault_adjusted_command.pump.speed", pd.read_parquet(direct.oracle_states))
            self.assertIsNone(load_scenario_dataset(root / "direct").oracle_states)
            # Online loading does not need the labels/oracle at all.
            (root / "direct/fault_events.json").unlink()
            direct.oracle_states.unlink()
            load_diagnosis_dataset(root / "direct")
            policy = read_json(root / "direct/permitted_inputs.json")
            policy["commands"].append("bottling0.oracle.fault_mechanism.pump.performance_factor")
            write_json(root / "direct/permitted_inputs.json", policy)
            with self.assertRaisesRegex(ValueError, "invalid controller"):
                load_diagnosis_dataset(root / "direct")

    def test_fault_factors_do_not_construct_commands_and_boundary_mismatch_fails(self):
        run, raw = fixture()
        audit = raw.rename(columns={"time": "simulation_time"})
        audit.insert(0, "simulation_step", range(5))
        audit.insert(0, "scenario_id", run.scenario_id)
        audit["bottling0.state_emptying_tank_B401.active"] = 1
        nominal = reconstruct_commands(audit, run.setup)
        self.assertEqual(nominal["bottling0.command.pump_P401.speed"].tolist(), [150.] * 5)
        audit["bottling0.var_pump_n"] = .5
        audit["bottling0.var_valve_in"] = .2
        pd.testing.assert_frame_equal(nominal, reconstruct_commands(audit, run.setup))
        audit["bottling0.pump_n_in"] = 75.
        audit["bottling0.valve_pump_P401.opening"] = 1.
        audit["bottling0.valve_in.opening"] = .2
        validate_command_equations(nominal, audit, run.setup)
        audit.loc[2, "bottling0.valve_out.opening"] = 1.
        with self.assertRaisesRegex(ExportError, "ambiguous boundaries"):
            validate_command_equations(nominal, audit, run.setup)
        with self.assertRaisesRegex(ExportError, "reconstruction input"):
            reconstruct_commands(audit.drop(columns="bottling0.state_bottling.active"), run.setup)

    def test_verified_source_identity_is_required(self):
        run, _ = fixture()
        with self.assertRaisesRegex(ExportError, "hash mismatch"):
            verify_sources(run.setup, {"Bottling.mo": "incorrect"})

    def test_sim_export_and_resume_v21_without_simulating(self):
        run, raw = fixture()
        audit = raw.rename(columns={"time": "simulation_time"})
        audit.insert(0, "simulation_step", range(len(audit)))
        audit.insert(0, "scenario_id", run.scenario_id)
        commands = reconstruct_commands(audit, run.setup)
        for spec in command_specs(run.setup):
            raw[spec.recorded_command] = commands[spec.name]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv = root / "raw.csv"
            raw.to_csv(csv, index=False)
            hashes = {str(ROOT / "models" / name): value for name, value in verify_sources(run.setup).items()}
            artifacts = SimulationArtifacts(root, csv, root / "stdout", root / "stderr", {"canonical_rows": 5}, hashes, "4.0.0")
            with patch("sim.run_openmodelica", return_value=artifacts), patch("sim._command_output", return_value=None):
                complete = _execute_run(run, CONFIG, root / "out", root / "build", False, False, "v2.1")
            resumed = _load_resumable_run(root / "out", run, CONFIG, "v2.1")
            self.assertEqual(resumed, complete)
            self.assertIsNone(_load_resumable_run(root / "out", run, CONFIG, "v2"))
            data = pd.read_parquet(complete.output_dir / "commands.parquet")
            data.loc[0, "bottling0.command.pump_P401.speed"] = 99.
            data.to_parquet(complete.output_dir / "commands.parquet", index=False)
            with self.assertRaisesRegex(Exception, "stale output"):
                _load_resumable_run(root / "out", run, CONFIG, "v2.1")


if __name__ == "__main__":
    unittest.main()
