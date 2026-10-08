"""Run one user-defined Modelica topology and keep its raw OpenModelica CSV."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from config import ConfigError, load_benchmark_config
from runner import SimulationError, run_openmodelica
from validation import ValidationError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="JSON topology configuration")
    parser.add_argument("--dataset", required=True, help="topology key in the JSON file")
    parser.add_argument("--output", type=Path, default=Path("output/custom"))
    args = parser.parse_args(argv)

    try:
        config = args.config.resolve()
        setups = load_benchmark_config(config)
        if args.dataset not in setups:
            raise ConfigError(f"Unknown dataset {args.dataset!r}; choose from {', '.join(setups)}")
        output = args.output.resolve()
        if (output / args.dataset).exists():
            raise ConfigError(f"Output already exists: {output / args.dataset}; choose a new --output")
        artifacts = run_openmodelica(
            setups[args.dataset], config.parent, output, args.dataset,
            result_filter=".*",
        )
    except (ConfigError, SimulationError, ValidationError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Simulation complete: {artifacts.raw_result}")
    print(f"Modelica source and logs: {artifacts.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
