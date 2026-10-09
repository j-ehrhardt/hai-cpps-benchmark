"""Event rows must explain valve motion hidden by the one-second export grid."""

import copy
from pathlib import Path
import unittest

import pandas as pd

from actuator_channels import command_specs, reconstruct_commands, validate_command_equations
from config import load_benchmark_config, normal_run
from diagnosis_export import validate_event_audit
from export import ExportError


ROOT = Path(__file__).resolve().parents[1]


class EventAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        setup = copy.deepcopy(load_benchmark_config(ROOT / "code/benchmark_setup.json")["ds1"])
        setup["sim_setup"].update(startTime=0, stopTime=2, numberOfIntervals=2)
        cls.run_spec = normal_run("ds1", setup)

    def _trace(self):
        times = [0.0, 0.95, 0.95, 0.99, 0.99, 1.0, 2.0]
        trace = pd.DataFrame({
            "scenario_id": [self.run_spec.scenario_id] * len(times),
            "simulation_step": range(len(times)),
            "simulation_time": times,
        })
        specs = command_specs(self.run_spec.setup)
        for state in {state for spec in specs for state in spec.states}:
            trace[f"mixer0.{state}.active"] = [0, 0, 0, 0, 0, 0, 0]
        trace["mixer0.state_emptying_tank_B204.active"] = [0, 0, 1, 1, 0, 0, 0]
        for spec in specs:
            if spec.factor:
                trace[f"{spec.module}.{spec.factor}"] = 1.0 if spec.quantity == "speed" else 0.0
        commands = reconstruct_commands(trace, self.run_spec.setup)
        for spec in specs:
            trace[spec.recorded_command] = commands[spec.name]
            target = commands[spec.name]
            if spec.factor:
                factor = trace[f"{spec.module}.{spec.factor}"]
                target = target * factor if spec.quantity == "speed" else target.where(target > factor, factor)
            trace[spec.raw] = target
        trace["mixer0.valve_out.opening"] = [0.0001, 0.0001, 0.0001,
                                               0.4001, 0.4001, 0.3001, 0.0001]
        canonical = trace.iloc[[0, 5, 6]].copy().reset_index(drop=True)
        canonical["simulation_step"] = range(3)
        return trace, canonical

    def test_event_switches_explain_isolated_canonical_ramp_value(self):
        trace, canonical = self._trace()
        commands = reconstruct_commands(canonical, self.run_spec.setup)
        with self.assertRaisesRegex(ExportError, "mixer0.command.valve_out.opening"):
            validate_command_equations(commands, canonical, self.run_spec.setup)
        checked = validate_event_audit(trace, canonical, self.run_spec)
        self.assertIn("mixer0.valve_out.opening", checked)

    def test_unexplained_valve_opening_remains_an_error(self):
        _, canonical = self._trace()
        with self.assertRaisesRegex(ExportError, "mixer0.command.valve_out.opening"):
            validate_event_audit(canonical, canonical, self.run_spec)


if __name__ == "__main__":
    unittest.main()
