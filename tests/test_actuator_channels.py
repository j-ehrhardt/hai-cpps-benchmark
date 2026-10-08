import unittest
from pathlib import Path

import pandas as pd

from actuator_channels import command_specs, recorded_commands, reconstruct_commands
from config import load_benchmark_config
from export import ExportError


CONFIG = Path(__file__).resolve().parents[1] / "code" / "benchmark_setup.json"


class RecordedCommandTests(unittest.TestCase):
    def test_periodic_valve_accepts_pre_event_sample_only_at_boundary(self):
        setup = load_benchmark_config(CONFIG)["ds4"]
        specs = command_specs(setup)
        audit = pd.DataFrame({
            "scenario_id": ["ds4_test"] * 5,
            "simulation_step": list(range(5)),
            "simulation_time": [1.0, 2.0, 3.0, 4.0, 5.0],
        })
        for spec in specs:
            for state in spec.states:
                audit[f"{spec.module}.{state}.active"] = False
        audit["bottling0.state_bottling.active"] = True
        expected = reconstruct_commands(audit, setup)
        for spec in specs:
            audit[spec.recorded_command] = expected[spec.name]

        valve = "bottling0.command_valve_out_opening"
        audit.loc[1, valve] = 1.0  # Pre-event value at time 2.
        commands = recorded_commands(audit, setup)
        self.assertEqual(commands.loc[1, "bottling0.command.valve_out.opening"], 1.0)

        audit.loc[2, valve] = 1.0  # Time 3 is not a switching boundary.
        with self.assertRaisesRegex(ExportError, "at \\[3.0\\]"):
            recorded_commands(audit, setup)


if __name__ == "__main__":
    unittest.main()
