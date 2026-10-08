from pathlib import Path

from config import load_benchmark_config
from model_generation import generate_plant_text, model_files_for_setup


ROOT = Path(__file__).resolve().parents[1]


def test_example_custom_module_uses_its_declared_class_and_file():
    config = ROOT / "examples" / "custom.json"
    setup = load_benchmark_config(config)["custom1"]
    plant = generate_plant_text(setup)
    files = model_files_for_setup(setup, config.parent)

    assert "passThroughModule pipe0(redeclare package Medium = Medium);" in plant
    assert "connect(source0.port_out0, pipe0.port_in0);" in plant
    assert "connect(pipe0.port_out0, sink0.port_in0);" in plant
    assert files[-1] == ROOT / "examples" / "PassThrough.mo"
