import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from campaign import prepare_shards
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

    def test_v22_shard_startup_needs_no_separate_release_readme(self):
        config = REPOSITORY / "code" / "benchmark_setup.json"
        with TemporaryDirectory() as directory:
            output = Path(directory) / "results"
            manifests = {}
            prepare_shards(output, manifests, config, ("ds1",))
            shard = output / "ds1"
            manifest = manifests["ds1"]
            snapshot = shard / "generation"
            self.assertEqual(len(manifest["recordings"]), 28)
            self.assertEqual(manifest["status"], "running")
            self.assertTrue((shard / "campaign.json").is_file())
            self.assertTrue((snapshot / "requirements.txt").is_file())
            self.assertTrue((snapshot / "code" / "campaign.py").is_file())
            self.assertTrue((snapshot / "models" / "Mixer.mo").is_file())
            self.assertEqual(set(manifest["generation_sha256"]), {
                str(path.relative_to(snapshot))
                for path in snapshot.rglob("*") if path.is_file()
            })


if __name__ == "__main__":
    unittest.main()
