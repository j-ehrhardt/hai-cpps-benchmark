import tempfile
import unittest
from pathlib import Path

import pandas as pd

from export import export_result_csvs


class ExportTests(unittest.TestCase):
    def test_safe_exports_allow_sensors_and_reject_effective_fault_channels(self):
        raw = pd.DataFrame(
            {
                "time": [0.0, 1.0, 2.0],
                "mixer0.tank_B201.level": [0.1, 0.2, 0.3],
                "mixer0.sensor_continuous_pressure_tank_B201.p": [1.0, 1.1, 1.2],
                "mixer0.sensor_continuous_volumeFlowRate.V_flow": [0.0, 0.1, 0.2],
                "mixer0.sensor_discrete_tank_B201_high.showActive": [False, False, True],
                "mixer0.pump_n_in": [0.0, 150.0, 150.0],
                "mixer0.pump_P101.N_in": [0.0, 140.0, 142.0],
                "mixer0.valve_in0.opening": [1.0, 1.0, 0.0],
                "mixer0.leaking_valve.opening": [0.0, 0.0, 0.25],
                "mixer0.clogging_valve.opening": [1.0, 1.0, 1.0],
                "filter0.filter_F101.opening": [1.0, 1.0, 0.5],
                "mixer0.fault_window_active": [False, False, True],
                "mixer0.var_pump_n": [1.0, 1.0, 0.5],
                "mixer0.state_filling_tank_B201.active": [True, True, False],
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw_path = root / "raw.csv"
            raw.to_csv(raw_path, index=False)
            bundle = export_result_csvs(
                raw_path,
                root / "output",
                "test",
                {"startTime": 0, "stopTime": 2, "numberOfIntervals": 2},
            )
            safe = pd.read_csv(bundle.hybrid)
            verification = pd.read_csv(bundle.verification)

        self.assertIn("mixer0.tank_B201.level", safe.columns)
        self.assertIn(
            "mixer0.sensor_discrete_tank_B201_high.showActive", safe.columns
        )
        self.assertNotIn("mixer0.pump_n_in", safe.columns)
        self.assertNotIn("mixer0.valve_in0.opening", safe.columns)
        self.assertIn("mixer0.var_pump_n", verification.columns)
        self.assertIn("mixer0.leaking_valve.opening", verification.columns)
        self.assertIn("filter0.filter_F101.opening", verification.columns)
        self.assertNotIn("filter0.filter_F101.opening", safe.columns)
        self.assertNotIn("mixer0.clogging_valve.opening", verification.columns)
        self.assertNotIn("mixer0.fault_window_active", safe.columns)
        self.assertIn("mixer0.fault_window_active", verification.columns)
        self.assertNotIn("Unnamed: 0", safe.columns)

    def test_event_rows_are_removed_from_canonical_export(self):
        raw = pd.DataFrame(
            {
                "time": [0.0, 0.0, 0.5, 1.0, 1.25, 2.0],
                "mixer0.tank_B201.level": [0.0, 0.1, 9.0, 0.2, 9.0, 0.3],
                "mixer0.sensor_discrete_tank_B201_high.showActive": [
                    False,
                    False,
                    True,
                    False,
                    True,
                    True,
                ],
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw_path = root / "raw.csv"
            raw.to_csv(raw_path, index=False)
            bundle = export_result_csvs(
                raw_path,
                root / "output",
                "test",
                {"startTime": 0, "stopTime": 2, "numberOfIntervals": 2},
            )
            safe = pd.read_csv(bundle.hybrid)

        self.assertEqual(safe["simulation_time"].tolist(), [0.0, 1.0, 2.0])
        self.assertEqual(
            safe["mixer0.tank_B201.level"].tolist(), [0.1, 0.2, 0.3]
        )


if __name__ == "__main__":
    unittest.main()
