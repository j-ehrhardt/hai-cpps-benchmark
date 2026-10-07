import copy
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from config import load_benchmark_config
from diagnosis_campaign import main, plan_campaign, protected_destination
from export_v2_1 import read_json

ROOT = Path(__file__).resolve().parents[1]


class CampaignTests(unittest.TestCase):
    def test_planning_does_not_execute_and_pilot_packages_reproducible_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / 'release'
            args = ['--output', str(output), '--build-root', str(root / 'build'), '--topology', 'ds4']
            with patch('diagnosis_campaign._execute_run') as execute:
                self.assertEqual(main(args), 0)
                execute.assert_not_called()
            manifest = read_json(output / 'campaign.json')
            self.assertEqual(manifest['status'], 'planned')
            self.assertFalse(manifest['completed'])
            report = {'commands': {}, 'missing_command_ranges': [], 'controller_phases_observed': {}, 'unvisited_controller_phases': []}
            result = SimpleNamespace(output_dir=root / 'scenario', hybrid=root / 'measurements.parquet')
            with patch('diagnosis_campaign._execute_run', return_value=result) as execute, \
                 patch('diagnosis_campaign.coverage', return_value=report), \
                 patch('diagnosis_campaign.duplicate_signal_groups', return_value=[]):
                self.assertEqual(main(args + ['--run', '--resume', '--max-runs', '1']), 0)
                self.assertEqual(execute.call_count, 1)
            manifest = read_json(output / 'campaign.json')
            self.assertEqual(manifest['status'], 'incomplete_pilot')
            self.assertEqual(len(manifest['completed']), 1)
            self.assertEqual((output / 'LICENSE').read_bytes(), (ROOT / 'LICENSE').read_bytes())
            frozen = output / 'generation/code/campaign_configuration.json'
            self.assertEqual(set(load_benchmark_config(frozen)), set(load_benchmark_config(ROOT / 'code/benchmark_setup.json')))
            self.assertIn('models/Mixer.mo', manifest['generation_sha256'])

    def test_independent_splits_and_test_only_pairs(self):
        benchmark = load_benchmark_config(ROOT / "code/benchmark_setup.json")
        before = copy.deepcopy(benchmark)
        plans = plan_campaign(benchmark)
        self.assertEqual(benchmark, before)
        self.assertEqual(len(plans), 260)
        healthy = {r.scenario_id: (r, split, group) for r, split, group, paired in plans if paired is None}
        self.assertEqual(len(healthy), 160)
        for topology in benchmark:
            runs = [r for r, _, _ in healthy.values() if r.base_dataset == topology]
            self.assertEqual(len(runs), 16)
            self.assertEqual(len({r.setup['sim_setup']['seed'] for r in runs}), 16)
        self.assertEqual(len({r.scenario_id for r, _, _, _ in plans}), 260)
        faults = [r for r, _, _, paired in plans if paired]
        self.assertEqual(len(faults), 100)
        self.assertEqual(len({(r.base_dataset, r.target_module, r.target_fault) for r in faults}), 100)
        for run, split, group, paired in plans:
            if paired:
                normal, normal_split, normal_group = healthy[paired]
                self.assertEqual((split, group), (normal_split, normal_group))
                self.assertEqual(split, 'test')
                self.assertEqual(run.setup['sim_setup']['seed'], 42)
                self.assertEqual(run.setup['sim_setup'], normal.setup['sim_setup'])
                self.assertEqual(run.setup['model']['edges'], normal.setup['model']['edges'])
                flags = [f for m in run.setup['model']['modules'].values() for f in m['faults'].values()]
                self.assertEqual(sum(flags), 1)

    def test_extra_test_controls_do_not_duplicate_faults_or_reuse_fault_seed(self):
        benchmark = load_benchmark_config(ROOT / 'code/benchmark_setup.json')
        plans = plan_campaign(benchmark, {'train': 10, 'validation': 2, 'calibration': 2, 'test': 2},
                              seed=41, topologies=['ds1'], fault_seed=42)
        healthy = [(r, split) for r, split, _, paired in plans if paired is None]
        self.assertEqual(len(healthy), 16)
        self.assertEqual(len({r.setup['sim_setup']['seed'] for r, _ in healthy}), 16)
        self.assertEqual([split for r, split in healthy if r.setup['sim_setup']['seed'] == 42], ['test'])
        faults = [r for r, _, _, paired in plans if paired]
        self.assertEqual(len(faults), 6)
        self.assertEqual({r.setup['sim_setup']['seed'] for r in faults}, {42})

    def test_invalid_counts_and_protected_paths(self):
        benchmark = load_benchmark_config(ROOT / "code/benchmark_setup.json")
        with self.assertRaises(ValueError):
            plan_campaign(benchmark, {'train': 0})
        for path in ('data', 'data/v2', 'data/v2.1/nested', 'data/backup'):
            with self.assertRaises(ValueError):
                protected_destination(ROOT / path)
        self.assertEqual(protected_destination(ROOT / 'data/v2.1-rerun'), ROOT / 'data/v2.1-rerun')
