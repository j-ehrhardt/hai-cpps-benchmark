import unittest
from pathlib import Path

from config import generate_single_fault_campaign, load_benchmark_config


REPOSITORY = Path(__file__).resolve().parents[1]


class CampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_benchmark_config(
            REPOSITORY / "code" / "benchmark_setup.json"
        )

    def test_every_fault_run_has_exactly_one_true_boolean(self):
        for run in generate_single_fault_campaign(self.config):
            active = []
            for module_name, module in run.setup["model"]["modules"].items():
                active.extend(
                    (module_name, name)
                    for name, enabled in module["faults"].items()
                    if enabled
                )
            self.assertEqual(active, [(run.target_module, run.target_fault)])

    def test_campaign_inputs_are_not_mutated(self):
        generate_single_fault_campaign(self.config)
        for scenario in self.config.values():
            for module in scenario["model"]["modules"].values():
                self.assertFalse(any(module["faults"].values()))


if __name__ == "__main__":
    unittest.main()
