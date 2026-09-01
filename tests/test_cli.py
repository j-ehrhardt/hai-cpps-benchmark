import contextlib
import io
import unittest
from pathlib import Path

from sim import main


REPOSITORY = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPOSITORY / "code" / "benchmark_setup.json"


class CommandLineTests(unittest.TestCase):
    def test_validate_command_reports_campaign_sizes(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = main(["validate", "--config", str(CONFIG_PATH)])
        self.assertEqual(result, 0)
        self.assertIn("10 normal runs, 110 single-fault runs", stdout.getvalue())

    def test_invalid_seed_fails_before_creating_outputs(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = main(
                [
                    "run",
                    "--config",
                    str(CONFIG_PATH),
                    "--seed",
                    "0",
                ]
            )
        self.assertEqual(result, 2)
        self.assertIn("--seed must be between", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
