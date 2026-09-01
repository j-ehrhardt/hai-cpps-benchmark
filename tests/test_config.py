import copy
import unittest
import warnings
from pathlib import Path

from config import (
    ConfigError,
    MODULE_SPECS,
    generate_single_fault_campaign,
    load_benchmark_config,
    normalize_and_validate,
)


REPOSITORY = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPOSITORY / "code" / "benchmark_setup.json"
CONFIG_DIR = CONFIG_PATH.parent


class ConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_benchmark_config(CONFIG_PATH)

    def test_checked_in_configuration_and_campaign_size(self):
        self.assertEqual(len(self.config), 10)
        self.assertEqual(len(generate_single_fault_campaign(self.config)), 110)

    def test_all_checked_in_faults_are_neutral(self):
        for scenario in self.config.values():
            for module in scenario["model"]["modules"].values():
                self.assertFalse(any(module["faults"].values()))
                self.assertEqual(
                    set(module["faults"]), set(MODULE_SPECS[module["type"]].faults)
                )

    def test_confirmed_topology_fixes(self):
        self.assertEqual(
            self.config["ds2"]["model"]["edges"]["2"],
            ["distill0.port_out1", "sink1.port_in0"],
        )
        self.assertEqual(
            self.config["ds9"]["model"]["edges"]["4"],
            ["bottling0.port_out0", "sink0.port_in0"],
        )
        self.assertEqual(
            self.config["ds9"]["model"]["edges"]["5"],
            ["bottling1.port_out0", "sink1.port_in0"],
        )

    def test_clogging_is_rejected(self):
        invalid = copy.deepcopy(self.config)
        invalid["ds1"]["model"]["modules"]["mixer0"]["faults"][
            "anom_clogging"
        ] = False
        with self.assertRaisesRegex(ConfigError, "does not support faults anom_clogging"):
            normalize_and_validate(invalid, CONFIG_DIR)

    def test_bottling_pollution_is_rejected(self):
        invalid = copy.deepcopy(self.config)
        invalid["ds4"]["model"]["modules"]["bottling0"]["faults"][
            "anom_pollution"
        ] = True
        with self.assertRaisesRegex(ConfigError, "does not support faults anom_pollution"):
            normalize_and_validate(invalid, CONFIG_DIR)

    def test_outlet_fault_is_rejected(self):
        invalid = copy.deepcopy(self.config)
        invalid["ds4"]["model"]["modules"]["bottling0"]["faults"][
            "anom_valve_out0"
        ] = False
        with self.assertRaisesRegex(ConfigError, "does not support faults anom_valve_out0"):
            normalize_and_validate(invalid, CONFIG_DIR)

    def test_input_port_cannot_be_an_edge_source(self):
        invalid = copy.deepcopy(self.config)
        invalid["ds9"]["model"]["edges"]["4"][0] = "bottling0.port_in0"
        with self.assertRaisesRegex(ConfigError, "is not an output port"):
            normalize_and_validate(invalid, CONFIG_DIR)

    def test_fault_severities_are_mutually_exclusive(self):
        invalid = copy.deepcopy(self.config)
        faults = invalid["ds1"]["model"]["modules"]["mixer0"]["faults"]
        faults["anom_pump50"] = True
        faults["anom_pump75"] = True
        with self.assertRaisesRegex(ConfigError, "cannot enable anom_pump50"):
            normalize_and_validate(invalid, CONFIG_DIR)

    def test_legacy_missing_type_is_derived_with_warning(self):
        legacy = copy.deepcopy(self.config)
        del legacy["ds1"]["model"]["modules"]["mixer0"]["type"]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            normalized = normalize_and_validate(legacy, CONFIG_DIR)
        self.assertEqual(
            normalized["ds1"]["model"]["modules"]["mixer0"]["type"], "mixer"
        )
        self.assertTrue(any(item.category is DeprecationWarning for item in caught))

    def test_fault_values_must_be_boolean(self):
        invalid = copy.deepcopy(self.config)
        invalid["ds1"]["model"]["modules"]["mixer0"]["faults"][
            "anom_leaking"
        ] = 1
        with self.assertRaisesRegex(ConfigError, "is not of type 'boolean'"):
            normalize_and_validate(invalid, CONFIG_DIR)

    def test_dataset_name_must_match_mapping_key(self):
        invalid = copy.deepcopy(self.config)
        invalid["ds1"]["ds_name"] = "wrong"
        with self.assertRaisesRegex(ConfigError, "ds_name must match"):
            normalize_and_validate(invalid, CONFIG_DIR)

    def test_dataset_identifier_cannot_escape_run_root(self):
        invalid = {"../outside": copy.deepcopy(self.config["ds1"])}
        invalid["../outside"]["ds_name"] = "../outside"
        with self.assertRaisesRegex(ConfigError, "does not match"):
            normalize_and_validate(invalid, CONFIG_DIR)

    def test_fault_onset_must_precede_simulation_stop(self):
        invalid = copy.deepcopy(self.config)
        invalid["ds1"]["sim_setup"]["faultStart"] = invalid["ds1"]["sim_setup"][
            "stopTime"
        ]
        with self.assertRaisesRegex(ConfigError, "before stopTime"):
            normalize_and_validate(invalid, CONFIG_DIR)


if __name__ == "__main__":
    unittest.main()
