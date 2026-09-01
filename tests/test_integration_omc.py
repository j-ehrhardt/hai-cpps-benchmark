import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from config import focused_fault_pair, load_benchmark_config, normal_run
from export import export_result_csvs
from runner import check_openmodelica_topologies, run_openmodelica
from validation import validate_fault_pair


REPOSITORY = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPOSITORY / "code" / "benchmark_setup.json"


@unittest.skipUnless(
    shutil.which("omc") and os.environ.get("RUN_OMC_TESTS") == "1",
    "set RUN_OMC_TESTS=1 to run OpenModelica integration tests",
)
class OpenModelicaIntegrationTests(unittest.TestCase):
    def _run_pair(
        self, benchmark, dataset, module, fault_name, config_dir=CONFIG_PATH.parent
    ):
        normal, fault = focused_fault_pair(
            benchmark, dataset, module, fault_name
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exports = []
            for run in (normal, fault):
                artifacts = run_openmodelica(
                    run.setup,
                    config_dir,
                    root / "build",
                    run.scenario_id,
                )
                exports.append(
                    export_result_csvs(
                        artifacts.raw_result,
                        root / "output" / run.scenario_id,
                        run.scenario_id,
                        run.setup["sim_setup"],
                    )
                )
            return validate_fault_pair(
                exports[0].hybrid,
                exports[1].hybrid,
                exports[0].verification,
                exports[1].verification,
                normal,
                fault,
            )

    def test_short_ds1_simulation_is_complete(self):
        benchmark = load_benchmark_config(CONFIG_PATH)
        setup = copy.deepcopy(benchmark["ds1"])
        setup["sim_setup"].update(
            {"startTime": 0, "stopTime": 20, "numberOfIntervals": 20, "faultStart": 10}
        )
        run = normal_run("ds1", setup)
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = run_openmodelica(
                run.setup,
                CONFIG_PATH.parent,
                Path(temporary) / "build",
                run.scenario_id,
            )
            self.assertEqual(artifacts.raw_validation["canonical_rows"], 21)
            exported = export_result_csvs(
                artifacts.raw_result,
                Path(temporary) / "output",
                run.scenario_id,
                run.setup["sim_setup"],
            )
            with exported.hybrid.open(encoding="utf-8") as handle:
                self.assertEqual(sum(1 for _ in handle), 22)

    def test_repeated_fixed_seed_exports_are_byte_identical(self):
        benchmark = load_benchmark_config(CONFIG_PATH)
        setup = copy.deepcopy(benchmark["ds1"])
        setup["sim_setup"].update(
            {"startTime": 0, "stopTime": 20, "numberOfIntervals": 20, "faultStart": 10}
        )
        run = normal_run("ds1", setup)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exports = []
            for repetition in range(2):
                artifacts = run_openmodelica(
                    run.setup,
                    CONFIG_PATH.parent,
                    root / "build{}".format(repetition),
                    run.scenario_id,
                )
                exports.append(
                    export_result_csvs(
                        artifacts.raw_result,
                        root / "output{}".format(repetition),
                        run.scenario_id,
                        run.setup["sim_setup"],
                    )
                )
            for field in ("continuous", "discrete", "hybrid", "verification"):
                self.assertEqual(
                    getattr(exports[0], field).read_bytes(),
                    getattr(exports[1], field).read_bytes(),
                )

    def test_ds10_mixer_fault_is_instance_specific(self):
        benchmark = load_benchmark_config(CONFIG_PATH)
        benchmark["ds10"]["sim_setup"].update(
            {"startTime": 0, "stopTime": 30, "numberOfIntervals": 30, "faultStart": 10}
        )
        report = self._run_pair(
            benchmark, "ds10", "mixer0", "anom_pump50"
        )
        self.assertTrue(report["injection_observed"], json.dumps(report, indent=2))
        self.assertFalse(
            report["non_target_direct_effects"], json.dumps(report, indent=2)
        )
        self.assertEqual(
            report["category"],
            "component_never_operated_after_onset",
            json.dumps(report, indent=2),
        )

    def test_ds6_bottling_fault_is_instance_specific(self):
        benchmark = load_benchmark_config(CONFIG_PATH)
        benchmark["ds6"]["sim_setup"].update(
            {"startTime": 0, "stopTime": 30, "numberOfIntervals": 30, "faultStart": 10}
        )
        report = self._run_pair(
            benchmark, "ds6", "bottling0", "anom_pump50"
        )
        self.assertTrue(report["injection_observed"], json.dumps(report, indent=2))
        self.assertFalse(
            report["non_target_direct_effects"], json.dumps(report, indent=2)
        )

    def test_filter_pollution_has_safe_effect_when_filter_operates(self):
        benchmark = load_benchmark_config(CONFIG_PATH)
        benchmark["ds3"]["sim_setup"].update(
            {"startTime": 0, "stopTime": 100, "numberOfIntervals": 100, "faultStart": 30}
        )
        with tempfile.TemporaryDirectory() as temporary:
            fixture_dir = Path(temporary) / "models"
            fixture_dir.mkdir()
            filter_source = (REPOSITORY / "models" / "Filter.mo").read_text(
                encoding="utf-8"
            )
            (fixture_dir / "Filter.mo").write_text(
                filter_source.replace(
                    "parameter Real tankMaxVol = 0.95;",
                    "parameter Real tankMaxVol = 0.06;",
                ),
                encoding="utf-8",
            )
            for module in benchmark["ds3"]["model"]["modules"].values():
                model_path = REPOSITORY / "models" / Path(module["files"]).name
                module["files"] = str(model_path.resolve())
            benchmark["ds3"]["model"]["modules"]["filter0"]["files"] = str(
                (fixture_dir / "Filter.mo").resolve()
            )
            report = self._run_pair(
                benchmark,
                "ds3",
                "filter0",
                "anom_pollution",
                config_dir=fixture_dir,
            )
        self.assertTrue(report["injection_observed"], json.dumps(report, indent=2))
        self.assertTrue(
            report["component_operation"]["operated_after_onset"],
            json.dumps(report, indent=2),
        )
        self.assertTrue(report["safe_effect_observed"], json.dumps(report, indent=2))
        self.assertTrue(report["valid"], json.dumps(report, indent=2))


@unittest.skipUnless(
    shutil.which("omc") and os.environ.get("RUN_OMC_EXTENDED_TESTS") == "1",
    "set RUN_OMC_EXTENDED_TESTS=1 to run all topology checks",
)
class ExtendedOpenModelicaTests(unittest.TestCase):
    def test_all_generated_topologies_pass_check_model(self):
        benchmark = load_benchmark_config(CONFIG_PATH)
        with tempfile.TemporaryDirectory() as temporary:
            logs = check_openmodelica_topologies(
                benchmark, CONFIG_PATH.parent, Path(temporary) / "checks"
            )
        self.assertEqual(set(logs), set(benchmark))

    def test_all_topologies_complete_short_normal_simulation(self):
        benchmark = load_benchmark_config(CONFIG_PATH)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for dataset_name, configured_setup in benchmark.items():
                setup = copy.deepcopy(configured_setup)
                setup["sim_setup"].update(
                    {
                        "startTime": 0,
                        "stopTime": 5,
                        "numberOfIntervals": 5,
                        "faultStart": 2,
                    }
                )
                run = normal_run(dataset_name, setup)
                artifacts = run_openmodelica(
                    run.setup,
                    CONFIG_PATH.parent,
                    root / "build",
                    run.scenario_id,
                )
                exported = export_result_csvs(
                    artifacts.raw_result,
                    root / "output" / run.scenario_id,
                    run.scenario_id,
                    run.setup["sim_setup"],
                )
                self.assertEqual(
                    artifacts.raw_validation["canonical_rows"],
                    6,
                    dataset_name,
                )
                self.assertTrue(exported.safe_columns, dataset_name)


if __name__ == "__main__":
    unittest.main()
