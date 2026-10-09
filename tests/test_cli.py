import contextlib
import io
import unittest
from pathlib import Path

from campaign import main


REPOSITORY = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPOSITORY / "code" / "benchmark_setup.json"


class CommandLineTests(unittest.TestCase):
    def test_plan_reports_v22_campaign_size(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = main(["--plan", "--config", str(CONFIG_PATH)])
        self.assertEqual(result, 0)
        self.assertIn("350 recordings", stdout.getvalue())

    def test_invalid_worker_count_fails_before_creating_outputs(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as error:
                main(["--config", str(CONFIG_PATH), "--jobs", "0"])
        self.assertEqual(error.exception.code, 2)
        self.assertIn("--jobs must be at least 1", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
