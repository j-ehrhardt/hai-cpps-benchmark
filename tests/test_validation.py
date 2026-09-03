import copy
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from config import RunSpec
from validation import ValidationError, _align_pair, validate_fault_pair


def _run_spec():
    return RunSpec(
        scenario_id="ds6_bottling0_anom_pump50",
        base_dataset="ds6",
        target_module="bottling0",
        target_fault="anom_pump50",
        setup={
            "ds_name": "ds6_bottling0_anom_pump50",
            "sim_setup": {"faultStart": 3.0},
            "model": {
                "modules": {
                    "bottling0": {
                        "type": "bottling",
                        "faults": {"anom_pump50": True},
                    },
                    "bottling1": {
                        "type": "bottling",
                        "faults": {"anom_pump50": False},
                    },
                    "sink0": {"type": "sink", "faults": {}},
                    "sink1": {"type": "sink", "faults": {}},
                },
                "edges": {
                    "0": ["bottling0.port_out0", "sink0.port_in0"],
                    "1": ["bottling1.port_out0", "sink1.port_in0"],
                },
            },
        },
    )


def _normal_run_spec():
    fault = _run_spec()
    setup = copy.deepcopy(fault.setup)
    setup["ds_name"] = "ds6_normal"
    setup["model"]["modules"]["bottling0"]["faults"]["anom_pump50"] = False
    return RunSpec("ds6_normal", "ds6", setup)


def _frame(scenario_id, signal):
    return pd.DataFrame(
        {
            "scenario_id": scenario_id,
            "simulation_step": range(7),
            "simulation_time": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "bottling0.tank_B401.level": signal,
        }
    )


def _verification(scenario_id, target, non_target=None):
    if non_target is None:
        non_target = [1.0] * 7
    return pd.DataFrame(
        {
            "scenario_id": scenario_id,
            "simulation_step": range(7),
            "simulation_time": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "bottling0.var_pump_n": target,
            "bottling1.var_pump_n": non_target,
        }
    )


class PairValidationTests(unittest.TestCase):
    def test_alignment_accepts_only_timestamp_roundoff(self):
        normal = _frame("normal", [1.0] * 7)
        fault = _frame("fault", [1.0] * 7)
        fault.loc[4, "simulation_time"] += 1e-10

        self.assertEqual(_align_pair(normal, fault), ["bottling0.tank_B401.level"])

    def test_alignment_rejects_material_timestamp_difference(self):
        normal = _frame("normal", [1.0] * 7)
        fault = _frame("fault", [1.0] * 7)
        fault.loc[4, "simulation_time"] += 1e-5

        with self.assertRaisesRegex(ValidationError, "differ at row 4"):
            _align_pair(normal, fault)

    def _validate(self, fault_signal, fault_target, fault_non_target=None):
        run = _run_spec()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            normal_measurements = root / "normal.csv"
            fault_measurements = root / "fault.csv"
            normal_verification = root / "normal_verification.csv"
            fault_verification = root / "fault_verification.csv"
            _frame("ds6_normal", [1.0] * 7).to_csv(
                normal_measurements, index=False
            )
            _frame(run.scenario_id, fault_signal).to_csv(
                fault_measurements, index=False
            )
            _verification("ds6_normal", [1.0] * 7).to_csv(
                normal_verification, index=False
            )
            _verification(
                run.scenario_id, fault_target, fault_non_target
            ).to_csv(fault_verification, index=False)
            return validate_fault_pair(
                normal_measurements,
                fault_measurements,
                normal_verification,
                fault_verification,
                _normal_run_spec(),
                run,
            )

    def test_valid_fault_has_local_and_safe_effect(self):
        report = self._validate(
            [1.0, 1.0, 1.0, 0.9, 0.8, 0.7, 0.6],
            [1.0, 1.0, 1.0, 0.5, 0.5, 0.5, 0.5],
        )
        self.assertTrue(report["valid"])

    def test_undetectable_fault_is_highlighted(self):
        report = self._validate(
            [1.0] * 7,
            [1.0, 1.0, 1.0, 0.5, 0.5, 0.5, 0.5],
        )
        self.assertFalse(report["valid"])
        self.assertEqual(report["category"], "model_equation_not_coupled_to_process")

    def test_cross_instance_injection_is_highlighted(self):
        report = self._validate(
            [1.0, 1.0, 1.0, 0.9, 0.8, 0.7, 0.6],
            [1.0, 1.0, 1.0, 0.5, 0.5, 0.5, 0.5],
            [1.0, 1.0, 1.0, 0.5, 0.5, 0.5, 0.5],
        )
        self.assertFalse(report["valid"])
        self.assertEqual(report["category"], "cross_instance_fault_injection")

    def test_pair_configuration_must_differ_only_at_target_boolean(self):
        run = _run_spec()
        run.setup["sim_setup"]["seed"] = 2
        normal = _normal_run_spec()
        normal.setup["sim_setup"]["seed"] = 1
        with self.assertRaisesRegex(ValidationError, "differ beyond the target"):
            validate_fault_pair(
                Path("unused-normal.csv"),
                Path("unused-fault.csv"),
                Path("unused-normal-verification.csv"),
                Path("unused-fault-verification.csv"),
                normal,
                run,
            )

    def test_downstream_reaction_is_not_cross_instance_injection(self):
        normal_setup = {
            "ds_name": "ds7_normal",
            "sim_setup": {"faultStart": 3.0},
            "model": {
                "modules": {
                    "filter0": {
                        "type": "filter",
                        "faults": {"anom_pollution": False},
                    },
                    "filter1": {
                        "type": "filter",
                        "faults": {"anom_pollution": False},
                    },
                    "sink0": {"type": "sink", "faults": {}},
                },
                "edges": {
                    "0": ["filter0.port_out0", "filter1.port_in0"],
                    "1": ["filter1.port_out0", "sink0.port_in0"],
                },
            },
        }
        fault_setup = copy.deepcopy(normal_setup)
        fault_setup["ds_name"] = "ds7_filter0_anom_pollution"
        fault_setup["model"]["modules"]["filter0"]["faults"][
            "anom_pollution"
        ] = True
        normal_run = RunSpec("ds7_normal", "ds7", normal_setup)
        fault_run = RunSpec(
            "ds7_filter0_anom_pollution",
            "ds7",
            fault_setup,
            "filter0",
            "anom_pollution",
        )
        times = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]

        def measurements(scenario_id, level):
            return pd.DataFrame(
                {
                    "scenario_id": scenario_id,
                    "simulation_step": range(7),
                    "simulation_time": times,
                    "filter0.tank_B101.level": level,
                    "filter0.sensor_continuous_volumeFlowRate.V_flow": [0.1] * 7,
                }
            )

        def verification(scenario_id, direct, local_opening, downstream_opening):
            return pd.DataFrame(
                {
                    "scenario_id": scenario_id,
                    "simulation_step": range(7),
                    "simulation_time": times,
                    "filter0.pollution_value": direct,
                    "filter0.filter_F101.opening": local_opening,
                    "filter1.pollution_value": [0.5] * 7,
                    "filter1.filter_F101.opening": downstream_opening,
                }
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / name for name in ("nm.csv", "fm.csv", "nv.csv", "fv.csv")]
            measurements("ds7_normal", [1.0] * 7).to_csv(paths[0], index=False)
            measurements(
                fault_run.scenario_id,
                [1.0, 1.0, 1.0, 0.9, 0.8, 0.7, 0.6],
            ).to_csv(paths[1], index=False)
            verification("ds7_normal", [0.5] * 7, [1.0] * 7, [1.0] * 7).to_csv(
                paths[2], index=False
            )
            verification(
                fault_run.scenario_id,
                [0.5, 0.5, 0.5, 1.0, 1.0, 1.0, 1.0],
                [1.0, 1.0, 1.0, 0.9, 0.9, 0.9, 0.9],
                [1.0, 1.0, 1.0, 0.8, 0.8, 0.8, 0.8],
            ).to_csv(paths[3], index=False)
            report = validate_fault_pair(
                paths[0], paths[1], paths[2], paths[3], normal_run, fault_run
            )

        self.assertTrue(report["valid"])
        self.assertFalse(report["non_target_direct_effects"])
        self.assertIn(
            "filter1.filter_F101.opening",
            report["changed_internal_channels_beyond_direct_flag"],
        )


if __name__ == "__main__":
    unittest.main()
