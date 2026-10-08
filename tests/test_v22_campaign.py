import copy
from contextlib import redirect_stdout
from io import StringIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import ConfigError, load_benchmark_config, normalize_and_validate
from campaign_plan import plan_campaign, prepare_manifest, snapshot_campaign
from model_generation import generate_plant_text
from campaign import main, run_pool, work_queue


REPOSITORY = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPOSITORY / "code" / "benchmark_setup.json"


class V22CampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_benchmark_config(CONFIG_PATH)

    def test_full_campaign_has_two_variants_per_released_fault(self):
        plans = plan_campaign(self.config)
        healthy = [run for run, *_ in plans if not run.is_fault]
        faulty = [run for run, *_ in plans if run.is_fault]
        self.assertEqual(len(healthy), 160)
        self.assertEqual(len(faulty), 190)
        self.assertEqual(len({run.scenario_id for run, *_ in plans}), 350)

        example = {
            run.scenario_id: run
            for run in faulty
            if run.base_dataset == "ds1"
            and run.target_module == "mixer0"
            and run.target_fault == "anom_leaking"
        }
        self.assertEqual(
            set(example),
            {
                "ds1_001_mixer0_anom_leaking_persistent",
                "ds1_002_mixer0_anom_leaking_temporal",
            },
        )
        self.assertEqual(
            example["ds1_001_mixer0_anom_leaking_persistent"].fault_variant,
            "persistent",
        )
        self.assertIsNone(
            example["ds1_001_mixer0_anom_leaking_persistent"].setup["sim_setup"]["faultEnd"]
        )
        self.assertEqual(
            example["ds1_002_mixer0_anom_leaking_temporal"].fault_variant,
            "temporal",
        )
        self.assertEqual(
            example["ds1_002_mixer0_anom_leaking_temporal"].setup["sim_setup"]["faultEnd"],
            7500,
        )

    def test_subset_keeps_v21_global_seed_allocation(self):
        ds10 = plan_campaign(self.config, topologies=["ds10"])
        healthy = [run for run, *_ in ds10 if not run.is_fault]
        self.assertEqual(healthy[0].scenario_id, "ds10_001_healthy")
        self.assertEqual(healthy[0].setup["sim_setup"]["seed"], 20261140)
        self.assertEqual(healthy[-1].setup["sim_setup"]["seed"], 42)

    def test_finite_model_passes_anomaly_end_to_every_process_module(self):
        run = next(
            run
            for run, *_ in plan_campaign(self.config, topologies=["ds1"])
            if run.scenario_id == "ds1_002_mixer0_anom_leaking_temporal"
        )
        plant = generate_plant_text(run.setup)
        self.assertIn("anom_start = 2500", plant)
        self.assertIn("anom_end = 7500", plant)

    def test_single_dataset_plan_uses_public_command_without_writing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results"
            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["--dataset", "ds1", "--plan", "--output", str(output)]), 0)
            self.assertIn("28 recordings: 16 healthy, 12 faults", stdout.getvalue())
            self.assertFalse(output.exists())

    def test_single_dataset_manifest_includes_replayable_source(self):
        with tempfile.TemporaryDirectory() as directory:
            shard = Path(directory) / "ds1"
            manifest = prepare_manifest(CONFIG_PATH, "ds1", shard)
            snapshot_campaign(shard, CONFIG_PATH, manifest)
            self.assertEqual(len(manifest["recordings"]), 28)
            self.assertTrue((shard / "generation" / "requirements.txt").is_file())
            self.assertTrue((shard / "generation" / "code" / "campaign.py").is_file())
            self.assertTrue((shard / "generation" / "models" / "Mixer.mo").is_file())

    def test_fault_end_must_define_a_nonempty_bounded_window(self):
        invalid = copy.deepcopy(self.config)
        invalid["ds1"]["sim_setup"]["faultEnd"] = 2500
        with self.assertRaisesRegex(ConfigError, "faultEnd must be after"):
            normalize_and_validate(invalid, CONFIG_PATH.parent)

    def test_pooled_queue_covers_all_topologies_and_waits_for_controls(self):
        plans = plan_campaign(self.config)
        ready, dependents = work_queue(plans)
        self.assertEqual(len(ready), 160)
        self.assertEqual(sum(len(group) for group in dependents.values()), 190)
        self.assertEqual(
            [plan[0].scenario_id for plan in list(ready)[:10]],
            [f"ds{number}_016_healthy" for number in range(1, 11)],
        )
        self.assertEqual(set(dependents),
                         {f"ds{number}_016_healthy" for number in range(1, 11)})
        for control, faults in dependents.items():
            self.assertTrue(all(paired == control for _, _, _, paired in faults))
            self.assertTrue(all(run.base_dataset == control.split("_", 1)[0]
                                for run, _, _, _ in faults))

    def test_pool_dispatches_350_jobs_with_64_slots_and_control_dependencies(self):
        plans = plan_campaign(self.config)
        manifests = {}
        live = set()
        started = []
        maximum_live = 0

        class CompletedProcess:
            def __init__(self, pid):
                self.pid = pid
                self.returncode = 0

            def poll(self):
                live.discard(self.pid)
                return 0

        def prepare(output, result, config, topologies):
            for topology in topologies:
                (output / topology).mkdir()
                result[topology] = {"recordings": [], "completed": [], "coverage": {}}
            manifests.update(result)

        def launch(plan, output, build, logs, config):
            nonlocal maximum_live
            run, _, _, paired = plan
            if paired:
                self.assertIn(paired, manifests[run.base_dataset]["completed"])
            pid = len(started) + 1000
            started.append(run.scenario_id)
            live.add(pid)
            maximum_live = max(maximum_live, len(live))
            return CompletedProcess(pid), StringIO(), logs / f"{run.scenario_id}.log"

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with patch("campaign.prepare_shards", side_effect=prepare), \
                 patch("campaign.start_worker", side_effect=launch), \
                 patch("campaign.coverage", return_value={
                     "missing_command_ranges": [], "unvisited_controller_phases": []}), \
                 patch("campaign.finish_shards"), \
                 patch("campaign.check_campaign", return_value={
                     "valid": True, "recordings": 350, "shards": {}}), \
                 redirect_stdout(StringIO()):
                result = run_pool(base / "output", base / "build", base / "logs", 64)
        self.assertEqual(result, 0)
        self.assertEqual(len(started), 350)
        self.assertEqual(len(set(started)), 350)
        self.assertEqual(maximum_live, 64)


if __name__ == "__main__":
    unittest.main()
