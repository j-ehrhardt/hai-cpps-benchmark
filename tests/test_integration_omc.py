import copy
import csv
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from config import focused_fault_pair, load_benchmark_config, normal_run
from dataset_metadata import write_release_metadata
from export import export_result_files
from runner import check_openmodelica_topologies, run_openmodelica
from sim import main
from validation import validate_fault_pair, validate_release_bundle


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
                    export_result_files(
                        artifacts.raw_result,
                        root / "output" / run.scenario_id,
                        run.scenario_id,
                        run.setup["sim_setup"],
                    )
                )
                metadata = write_release_metadata(
                    root / "output" / run.scenario_id, run, exports[-1]
                )
                release_report = validate_release_bundle(
                    exports[-1],
                    run,
                    metadata.fault_events,
                    metadata.system_knowledge,
                    metadata.technical_timing,
                )
                self.assertTrue(release_report["valid"])
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
            exported = export_result_files(
                artifacts.raw_result,
                Path(temporary) / "output",
                run.scenario_id,
                run.setup["sim_setup"],
            )
            metadata = write_release_metadata(Path(temporary) / "output", run, exported)
            release_report = validate_release_bundle(
                exported,
                run,
                metadata.fault_events,
                metadata.system_knowledge,
                metadata.technical_timing,
            )
            self.assertEqual(len(pd.read_parquet(exported.hybrid)), 21)
            self.assertTrue(release_report["valid"])

    def test_short_cli_run_writes_and_resumes_complete_release(self):
        benchmark = load_benchmark_config(CONFIG_PATH)
        setup = copy.deepcopy(benchmark["ds1"])
        setup["sim_setup"].update(
            {"startTime": 0, "stopTime": 5, "numberOfIntervals": 5, "faultStart": 2}
        )
        for module in setup["model"]["modules"].values():
            module["files"] = str(
                (CONFIG_PATH.parent / module["files"]).resolve()
            )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "benchmark.json"
            config_path.write_text(
                json.dumps({"ds1": setup}, indent=2) + "\n", encoding="utf-8"
            )
            arguments = [
                "run",
                "--config",
                str(config_path),
                "--campaign",
                "normal",
                "--output",
                str(root / "output"),
                "--build-root",
                str(root / "build"),
            ]
            self.assertEqual(main(arguments), 0)
            scenario = root / "output" / "ds1_normal"
            expected = (
                scenario / "continuous" / "measurements.parquet",
                scenario / "discrete" / "measurements.parquet",
                scenario / "hybrid" / "measurements.parquet",
                scenario / "oracle_states.parquet",
                scenario / "fault_events.json",
                scenario / "system_knowledge.yaml",
                scenario / "technical_timing.json",
                scenario / "sim_setup.json",
                scenario / "provenance.json",
                scenario / "validation.json",
            )
            self.assertTrue(all(path.is_file() for path in expected))
            self.assertEqual(main(arguments + ["--resume"]), 0)

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
                    export_result_files(
                        artifacts.raw_result,
                        root / "output{}".format(repetition),
                        run.scenario_id,
                        run.setup["sim_setup"],
                    )
                )
            for field in (
                "continuous",
                "discrete",
                "hybrid",
                "oracle_states",
                "verification",
            ):
                self.assertEqual(
                    getattr(exports[0], field).read_bytes(),
                    getattr(exports[1], field).read_bytes(),
                )

    def test_release_metadata_for_every_process_module_type(self):
        benchmark = load_benchmark_config(CONFIG_PATH)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for dataset_name in ("ds1", "ds2", "ds3", "ds4"):
                setup = copy.deepcopy(benchmark[dataset_name])
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
                output = root / "output" / run.scenario_id
                exported = export_result_files(
                    artifacts.raw_result,
                    output,
                    run.scenario_id,
                    run.setup["sim_setup"],
                )
                metadata = write_release_metadata(output, run, exported)
                report = validate_release_bundle(
                    exported,
                    run,
                    metadata.fault_events,
                    metadata.system_knowledge,
                    metadata.technical_timing,
                )
                self.assertTrue(report["valid"], dataset_name)
                self.assertGreater(report["oracle_columns"], 0, dataset_name)

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

    def test_distill_leak_ramp_is_stable_while_pump_operates(self):
        benchmark = load_benchmark_config(CONFIG_PATH)
        benchmark["ds2"]["sim_setup"].update(
            {
                "startTime": 0,
                "stopTime": 300,
                "numberOfIntervals": 300,
                "faultStart": 275,
            }
        )
        _, fault = focused_fault_pair(
            benchmark, "ds2", "distill0", "anom_leaking"
        )
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = run_openmodelica(
                fault.setup,
                CONFIG_PATH.parent,
                Path(temporary) / "build",
                fault.scenario_id,
            )
            with artifacts.raw_result.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            process_log = (artifacts.run_dir / "processPlant.log").read_text(
                encoding="utf-8"
            )
        self.assertEqual(float(rows[-1]["distill0.leaking_valve.opening"]), 0.25)
        self.assertNotIn("Solving non-linear system", process_log)


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
                exported = export_result_files(
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

    def test_ds2_distill_completes_a_full_process_cycle(self):
        benchmark = load_benchmark_config(CONFIG_PATH)
        setup = copy.deepcopy(benchmark["ds2"])
        setup["sim_setup"].update(
            {
                "startTime": 0,
                "stopTime": 500,
                "numberOfIntervals": 500,
                "faultStart": 250,
            }
        )
        run = normal_run("ds2", setup)
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = run_openmodelica(
                run.setup,
                CONFIG_PATH.parent,
                Path(temporary) / "build",
                run.scenario_id,
            )
            process_log = (artifacts.run_dir / "processPlant.log").read_text(
                encoding="utf-8"
            )
        self.assertEqual(artifacts.raw_validation["stop_time"], 500.0)
        self.assertNotIn("While solving non-linear system", process_log)


if __name__ == "__main__":
    unittest.main()
