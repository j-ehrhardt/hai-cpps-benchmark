import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml

from config import RunSpec
from dataset_metadata import fault_events_document, write_release_metadata
from dataset_io import load_scenario_dataset
from export import export_result_files
from validation import validate_release_bundle


def _fault_run() -> RunSpec:
    scenario_id = "ds1_mixer0_anom_pump50"
    return RunSpec(
        scenario_id=scenario_id,
        base_dataset="ds1",
        target_module="mixer0",
        target_fault="anom_pump50",
        setup={
            "ds_name": scenario_id,
            "model": {
                "modules": {
                    "source0": {
                        "type": "source",
                        "files": "../models/Source.mo",
                        "faults": {},
                    },
                    "mixer0": {
                        "type": "mixer",
                        "files": "../models/Mixer.mo",
                        "faults": {
                            "anom_leaking": False,
                            "anom_valve_in0": False,
                            "anom_valve_in1": False,
                            "anom_valve_in2": False,
                            "anom_pump50": True,
                            "anom_pump75": False,
                        },
                    },
                    "sink0": {
                        "type": "sink",
                        "files": "../models/Sink.mo",
                        "faults": {},
                    },
                },
                "edges": {
                    "0": ["source0.port_out0", "mixer0.port_in0"],
                    "1": ["mixer0.port_out0", "sink0.port_in0"],
                },
            },
            "sim_setup": {
                "startTime": 0,
                "stopTime": 2,
                "numberOfIntervals": 2,
                "faultStart": 1,
                "seed": 20260831,
            },
        },
    )


def _raw_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": [0.0, 1.0, 2.0],
            "mixer0.tank_B201.level": [0.1, 0.2, 0.3],
            "mixer0.sensor_continuous_pressure_tank_B201.p": [1.0, 1.1, 1.2],
            "mixer0.sensor_discrete_tank_B201_high.showActive": [False, True, True],
            "mixer0.state_emptying_tank_B201.active": [False, True, True],
            "mixer0.state_emptying_tank_B202.active": [False, False, False],
            "mixer0.state_emptying_tank_B203.active": [False, False, False],
            "mixer0.pump_n_in": [0.0, 150.0, 75.0],
            "mixer0.pump_P101.N_in": [0.0, 50.0, 70.0],
            "mixer0.uniformNoise.y": [1.0, 1.0, 1.0],
            "mixer0.var_pump_n": [1.0, 1.0, 0.5],
            "mixer0.fault_window_active": [False, False, True],
            "mixer0.clogging_valve.opening": [1.0, 1.0, 1.0],
        }
    )


class DatasetMetadataTests(unittest.TestCase):
    def test_release_metadata_and_separation_are_self_consistent(self):
        run = _fault_run()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw_path = root / "raw.csv"
            _raw_frame().to_csv(raw_path, index=False)
            output = root / run.scenario_id
            bundle = export_result_files(
                raw_path, output, run.scenario_id, run.setup["sim_setup"]
            )
            metadata = write_release_metadata(output, run, bundle)
            report = validate_release_bundle(
                bundle,
                run,
                metadata.fault_events,
                metadata.system_knowledge,
                metadata.technical_timing,
            )
            oracle = pd.read_parquet(bundle.oracle_states)
            events = json.loads(metadata.fault_events.read_text(encoding="utf-8"))
            knowledge = yaml.safe_load(
                metadata.system_knowledge.read_text(encoding="utf-8")
            )
            timing = json.loads(
                metadata.technical_timing.read_text(encoding="utf-8")
            )
            online = load_scenario_dataset(output)
            offline = load_scenario_dataset(output, include_oracle=True)

        self.assertTrue(report["valid"])
        self.assertEqual(report["fault_events"], 1)
        self.assertEqual(events["events"][0]["configuration_flag"], "anom_pump50")
        self.assertEqual(events["events"][0]["fault_value"], 0.5)
        self.assertEqual(
            events["events"][0]["intervened_component"], "mixer0.pump_P101"
        )
        self.assertFalse(events["events"][0]["online_feature_allowed"])
        self.assertIn(
            "mixer0.oracle.fault_mechanism.pump.performance_factor",
            oracle.columns,
        )
        self.assertFalse(any("clogging" in column for column in oracle.columns))
        oracle_entries = [
            entry
            for entry in knowledge["variables"]
            if entry.get("oracle_role") == "fault_mechanism_state"
        ]
        self.assertTrue(oracle_entries)
        self.assertTrue(all(not entry["online_feature_allowed"] for entry in oracle_entries))
        threshold_rules = [
            rule
            for rule in knowledge["rules"]
            if rule["name"] == "mixer0.tank_B201.high_threshold"
        ]
        self.assertEqual(len(threshold_rules), 1)
        self.assertEqual(threshold_rules[0]["rule_class"], "K_imp")
        self.assertEqual(timing["time_axis"]["sample_period"], 1.0)
        self.assertEqual(
            {edge["edge_id"] for edge in timing["edges"]}, {"0", "1"}
        )
        self.assertIsNone(online.oracle_states)
        self.assertIsNotNone(offline.oracle_states)
        self.assertFalse(any(".oracle." in column for column in online.measurements))
        self.assertNotIn("scenario_id", online.online_features)
        self.assertFalse(any("anom_" in column for column in online.online_features))

    def test_normal_run_has_no_fault_event(self):
        fault = _fault_run()
        normal = RunSpec(
            scenario_id="ds1_normal",
            base_dataset="ds1",
            setup=fault.setup,
        )
        document = fault_events_document(normal, ())
        self.assertEqual(document["events"], [])

    def test_release_validation_accepts_post_event_boundary_value(self):
        run = _fault_run()
        raw = _raw_frame()
        raw.loc[1, "mixer0.fault_window_active"] = True
        raw.loc[1, "mixer0.var_pump_n"] = 0.5
        raw.loc[1, "mixer0.pump_n_in"] = 75.0

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw_path = root / "raw.csv"
            raw.to_csv(raw_path, index=False)
            output = root / run.scenario_id
            bundle = export_result_files(
                raw_path, output, run.scenario_id, run.setup["sim_setup"]
            )
            metadata = write_release_metadata(output, run, bundle)
            report = validate_release_bundle(
                bundle,
                run,
                metadata.fault_events,
                metadata.system_knowledge,
                metadata.technical_timing,
            )
            timing = json.loads(
                metadata.technical_timing.read_text(encoding="utf-8")
            )

        self.assertTrue(report["valid"])
        self.assertEqual(
            timing["recording"]["event_boundary_value"],
            "pre_or_post_event_value",
        )


if __name__ == "__main__":
    unittest.main()
