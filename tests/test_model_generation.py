import tempfile
import unittest
import re
from pathlib import Path

from config import MODULE_SPECS, focused_fault_pair, load_benchmark_config
from model_generation import generate_mos_text, generate_plant_text, write_run_files
from validation import sha256_file


REPOSITORY = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPOSITORY / "code" / "benchmark_setup.json"


class ModelGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_benchmark_config(CONFIG_PATH)

    def test_same_type_instances_receive_independent_fault_modifiers(self):
        _, fault = focused_fault_pair(
            self.config, "ds6", "bottling0", "anom_pump50"
        )
        lines = generate_plant_text(fault.setup).splitlines()
        bottling0 = next(line for line in lines if "bottlingModule bottling0" in line)
        bottling1 = next(line for line in lines if "bottlingModule bottling1" in line)
        self.assertIn("anom_pump50 = true", bottling0)
        self.assertIn("anom_pump50 = false", bottling1)

    def test_ds10_mixer_instances_receive_independent_fault_modifiers(self):
        _, fault = focused_fault_pair(
            self.config, "ds10", "mixer1", "anom_valve_in2"
        )
        lines = generate_plant_text(fault.setup).splitlines()
        mixer0 = next(line for line in lines if "mixerModule mixer0" in line)
        mixer1 = next(line for line in lines if "mixerModule mixer1" in line)
        self.assertIn("anom_valve_in2 = false", mixer0)
        self.assertIn("anom_valve_in2 = true", mixer1)

    def test_ds9_bottling_branches_receive_independent_fault_modifiers(self):
        _, fault = focused_fault_pair(
            self.config, "ds9", "bottling1", "anom_leaking"
        )
        lines = generate_plant_text(fault.setup).splitlines()
        bottling0 = next(line for line in lines if "bottlingModule bottling0" in line)
        bottling1 = next(line for line in lines if "bottlingModule bottling1" in line)
        self.assertIn("anom_leaking = false", bottling0)
        self.assertIn("anom_leaking = true", bottling1)

    def test_generation_is_stable_and_does_not_mutate_models(self):
        _, fault = focused_fault_pair(
            self.config, "ds6", "bottling0", "anom_pump50"
        )
        model_paths = sorted((REPOSITORY / "models").glob("*.mo"))
        before = {path: sha256_file(path) for path in model_paths}
        first = generate_plant_text(fault.setup)
        second = generate_plant_text(fault.setup)
        self.assertEqual(first, second)

        with tempfile.TemporaryDirectory() as temporary:
            write_run_files(
                fault.setup, CONFIG_PATH.parent, Path(temporary) / "run"
            )
        after = {path: sha256_file(path) for path in model_paths}
        self.assertEqual(before, after)

    def test_plant_generation_does_not_depend_on_module_mapping_order(self):
        _, fault = focused_fault_pair(
            self.config, "ds6", "bottling0", "anom_pump50"
        )
        expected = generate_plant_text(fault.setup)
        reordered = dict(reversed(list(fault.setup["model"]["modules"].items())))
        fault.setup["model"]["modules"] = reordered
        self.assertEqual(generate_plant_text(fault.setup), expected)

    def test_generated_plant_binds_fluid_system_and_fixed_noise_seeds(self):
        _, fault = focused_fault_pair(
            self.config, "ds6", "bottling0", "anom_pump50"
        )
        plant = generate_plant_text(fault.setup)
        self.assertIn("inner Modelica.Fluid.System system(", plant)
        seeds = re.findall(r"noiseSeed = (\d+)", plant)
        expected = sum(
            bool(MODULE_SPECS[module["type"]].faults)
            for module in fault.setup["model"]["modules"].values()
        )
        self.assertEqual(len(seeds), expected)
        self.assertEqual(len(set(seeds)), expected)

    def test_simulation_suppresses_extra_event_output_rows(self):
        setup = self.config["ds1"]
        mos = generate_mos_text(setup, [], Path("/tmp/Plant.mo"))
        self.assertIn('loadModel(Modelica, {"4.0.0"});', mos)
        self.assertIn('simflags="-noEventEmit"', mos)
        self.assertIn('variableFilter=".*(', mos)

    def test_modelica_fault_defaults_are_false_and_clogging_is_not_a_fault(self):
        for module_type in ("mixer", "filter", "distill", "bottling"):
            spec = MODULE_SPECS[module_type]
            model = (REPOSITORY / "models" / spec.filename).read_text(
                encoding="utf-8"
            )
            for fault in spec.faults:
                self.assertRegex(
                    model,
                    r"parameter\s+Boolean\s+{}\s*=\s*false\s+annotation\(Evaluate\s*=\s*false\);".format(
                        fault
                    ),
                )
            self.assertNotRegex(model, r"parameter\s+Boolean\s+anom_clogging")
            self.assertIn("useAutomaticLocalSeed = false", model)
            self.assertIn("fault_window_active = time >= anom_start;", model)


if __name__ == "__main__":
    unittest.main()
