"""Recorded nominal controller outputs and verified command reconstruction."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import math
import re

import numpy as np
import pandas as pd

from export import ExportError, IDENTIFIER_COLUMNS

SCHEMA_VERSION = "2.2.0"
REGISTRY_VERSION = "1.4.0"
# These formulas have been reviewed against exactly these model revisions.
MODEL_HASHES = {
    "Mixer.mo": "510739bac69448fd72bb0cd0f5949436ba18aadc3e688db3df6d969704a9084f",
    "Filter.mo": "87238d89d08a691d8ae7709cd735aa870797bdb3edfd2572564e9685f07926d6",
    "Distill.mo": "f5c5b9cc2ef83b2c0b8b0c0c94ba10e6c101495c75d8c8a0534cbc3fc972ab0c",
    "Bottling.mo": "b025836e0a9f6db15069a4c5d71ff493a2cbde54a26961a644bf871a180bbb2c",
}
MODELS = Path(__file__).resolve().parents[1] / "models"


def verify_sources(setup, recorded_hashes=None):
    result = {}
    for module in setup["model"]["modules"].values():
        filename = Path(module["files"]).name
        path = MODELS / filename
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if filename in MODEL_HASHES and digest != MODEL_HASHES[filename]:
            raise ExportError(f"Unreviewed reconstruction source: {filename}")
        if recorded_hashes is not None:
            matches = [value for name, value in recorded_hashes.items()
                       if Path(name).name == filename]
            if not matches or any(value != digest for value in matches):
                raise ExportError(f"Recorded model hash mismatch: {filename}")
        result[filename] = digest
    return result


@dataclass(frozen=True)
class Command:
    module: str
    component: str
    quantity: str
    states: tuple
    off: float = 0.0
    on: float = 1.0
    periodic: bool = False
    factor: str = ""

    @property
    def name(self):
        return f"{self.module}.command.{self.component}.{self.quantity}"

    @property
    def raw(self):
        if self.quantity == "speed":
            return f"{self.module}.pump_n_in"
        suffix = "Q_flow" if self.quantity == "heat_flow" else "opening"
        return f"{self.module}.{self.component}.{suffix}"

    @property
    def recorded_command(self):
        return f"{self.module}.command_{self.component}_{self.quantity}"

    @property
    def inputs(self):
        values = [f"{self.module}.{state}.active" for state in self.states]
        return values + (["simulation_time"] if self.periodic else [])


def command_specs(setup):
    specs = []
    for name, module in sorted(setup["model"]["modules"].items()):
        kind = module["type"]
        if kind not in {"mixer", "filter", "distill", "bottling"}:
            continue
        def add(component, states, off=0.0001, on=1.0, quantity="opening", factor="", periodic=False):
            specs.append(Command(name, component, quantity, tuple(states), off, on, periodic, factor))
        tanks = ["B201", "B202", "B203"] if kind == "mixer" else ["B401" if kind == "bottling" else "B101"]
        empty = [f"state_emptying_tank_{tank}" for tank in tanks]
        pump = "pump_P401" if kind == "bottling" else "pump_P101"
        add(pump, empty, 0, 150, "speed", "var_pump_n")
        for i, tank in enumerate(tanks):
            valve = f"valve_in{i}" if kind == "mixer" else "valve_in"
            factor = f"var_valve_in{i}" if kind == "mixer" else "var_valve_in0" if kind == "distill" else "var_valve_in"
            add(valve, [f"state_filling_tank_{tank}"], factor=factor)
        if kind == "mixer":
            for tank, state in zip(tanks, empty):
                add(f"valve_pump_tank_{tank}", [state])
            add("valve_pump_tank_B204", empty)
            add("valve_out", ["state_emptying_tank_B204"])
        else:
            add(f"valve_{pump}", empty)
            if kind == "filter":
                add("valve_out", ["state_emptying_tank_B102"], 0)
            elif kind == "bottling":
                add("valve_out", ["state_bottling"], periodic=True)
            else:
                add("valve_distill1", empty, 0)
                add("valve_distill3", ["state_emptying_distill"], 0)
                for outlet in ("valve_out0", "valve_out1"):
                    add(outlet, ["state_emptying_output_tanks"], 0)
                add("heater_distill", ["state_destillation"], 0, 20000, "heat_flow", "var_heat")
                for cooler in ("cooler_B102", "cooler_B103"):
                    add(cooler, [], 0, 0, "heat_flow")
    return specs


def reconstruct_commands(audit, setup):
    """Evaluate healthy control laws using only recorded states and time."""
    result = audit[list(IDENTIFIER_COLUMNS)].copy()
    for spec in command_specs(setup):
        active = pd.Series(False, index=audit.index)
        for state in spec.states:
            key = f"{spec.module}.{state}.active"
            if key not in audit or not audit[key].isin([0, 1, False, True]).all():
                raise ExportError(f"Missing/non-Boolean reconstruction input: {key}")
            active |= audit[key].astype(bool)
        if spec.periodic:
            active &= audit.simulation_time.mod(4) < 2
        result[spec.name] = np.where(active, spec.on, spec.off)
    return result


def _slew_response(value, target, elapsed):
    """Integrate MSL 4.0.0 SlewRateLimiter over one constant-input interval."""
    if elapsed <= 0:
        return value
    rate = 10.0  # 1 / the reviewed built-in valveRampDuration of 0.1 s
    td = 0.001  # valveRampDuration / 100 in the reviewed Modelica sources
    difference = target - value
    direction = 1.0 if difference >= 0 else -1.0
    distance = abs(difference)
    tail = rate * td
    if distance <= tail:
        return target - difference * math.exp(-elapsed / td)
    linear_time = (distance - tail) / rate
    if elapsed <= linear_time:
        return value + direction * rate * elapsed
    return target - direction * tail * math.exp(-(elapsed - linear_time) / td)


def validate_command_equations(commands, audit, setup):
    """Fault references are consulted only here, never during reconstruction."""
    checked = []
    for spec in command_specs(setup):
        if spec.raw not in audit:
            if spec.component.startswith("cooler_"):
                continue  # Constant equation known; effective channel was not recorded.
            raise ExportError(f"Missing effective reference: {spec.raw}")
        expected = commands[spec.name].astype(float)
        if spec.factor:
            key = f"{spec.module}.{spec.factor}"
            if key not in audit:
                raise ExportError(f"Missing verification factor: {key}")
            if spec.quantity == "opening":
                expected = pd.Series(np.maximum(expected, audit[key]), index=audit.index)
            else:
                expected = expected * audit[key]
        effective = audit[spec.raw].astype(float)
        if spec.quantity == "opening":
            # The limiter has a short first-order tail after its linear stroke.
            # Use every simulator event row so intervening command pulses are
            # represented before comparing the effective opening.
            times = audit["simulation_time"].to_numpy(dtype=float)
            targets = expected.to_numpy(dtype=float)
            observed = effective.to_numpy(dtype=float)
            predicted = np.empty(len(observed), dtype=float)
            predicted[0] = observed[0]
            for index in range(1, len(observed)):
                predicted[index] = _slew_response(
                    predicted[index - 1], targets[index - 1],
                    times[index] - times[index - 1],
                )
            # The DASSL run uses a 1e-6 tolerance; allow a small accumulated
            # integration difference without accepting a material valve error.
            valid = np.isclose(predicted, observed, atol=1e-4, rtol=1e-7)
        else:
            valid = np.isclose(expected, effective, atol=1e-9, rtol=1e-7)
        if not valid.all():
            times = audit.loc[~valid, "simulation_time"].head(8).tolist()
            raise ExportError(f"Command/effective equation mismatch {spec.name} at {times}")
        checked.append(spec.raw)
    return checked


def recorded_commands(audit, setup):
    """Require a complete recorded command set; never silently fill missing logs."""
    specs = command_specs(setup)
    present = [spec.recorded_command in audit for spec in specs]
    if not any(present):
        return None
    if not all(present):
        raise ExportError("Incomplete recorded nominal command channels")
    result = audit[list(IDENTIFIER_COLUMNS)].copy()
    expected = reconstruct_commands(audit, setup)
    for spec in specs:
        result[spec.name] = audit[spec.recorded_command]
        valid = np.isclose(result[spec.name], expected[spec.name], atol=1e-9, rtol=1e-7)
        if spec.periodic:
            # With event points suppressed, a grid row at a switching instant
            # may contain the value immediately before or after the event.
            phase = audit["simulation_time"].to_numpy(dtype=float) % 4
            boundary = (np.isclose(phase, 0, atol=1e-8, rtol=0)
                        | np.isclose(phase, 2, atol=1e-8, rtol=0)
                        | np.isclose(phase, 4, atol=1e-8, rtol=0))
            recorded = result[spec.name].to_numpy(dtype=float)
            endpoint = (np.isclose(recorded, spec.off, atol=1e-9, rtol=1e-7)
                        | np.isclose(recorded, spec.on, atol=1e-9, rtol=1e-7))
            valid |= boundary & endpoint
        if not valid.all():
            times = audit.loc[~valid, "simulation_time"].head(8).tolist()
            raise ExportError(f"Recorded nominal command violates controller law: {spec.name} at {times}")
    return result


def command_catalogue(setup, hashes, recorded=False):
    entries = []
    for spec in command_specs(setup):
        filename = Path(setup["model"]["modules"][spec.module]["files"]).name
        source = (MODELS / filename).read_text()
        local_raw = (spec.recorded_command if recorded else spec.raw).split(".", 1)[1]
        equation = re.search(r"^\s*" + re.escape(local_raw) + r"\s*=.*?;", source, re.M | re.S)
        entries.append({
            "name": spec.name, "component": f"{spec.module}.{spec.component}",
            "role": "controller_command", "physical_meaning": f"Nominal requested {spec.quantity} before fault effects",
            "unit": {"speed": "rev/min", "opening": "1", "heat_flow": "W"}[spec.quantity],
            "sign_convention": {"speed": "positive nominal forward shaft rotation", "opening": "0 closed, 1 fully open", "heat_flow": "positive heat supplied to fluid"}[spec.quantity],
            "online_feature_allowed": True, "online_observable": True,
            "availability": "recorded_controller_output" if recorded else "reconstructed_from_recorded_controller_state",
            "observation_assumption": "controller commands can be logged operationally",
            "required_inputs": [spec.recorded_command] if recorded else spec.inputs,
            "nominal_equation": {"any_active_states": list(spec.states), "on": spec.on, "off": spec.off, "additional_condition": "mod(time,4)<2" if spec.periodic else None},
            "source_equation": equation.group(0).strip() if equation else None,
            "source_model": filename, "source_sha256": hashes[filename],
            "limits": {"nominal_support": sorted(set([spec.off, spec.on])), "extra_saturation": "not_modelled"},
            "command_delay": {"status": "not_modelled"},
            "actuator_dynamics": (
                {"kind": "first_order_lag", "time_constant_s": 1.0, "disturbance_multiplier_range": [0.8, 1.2], "disturbance_sample_period_s": 1.0}
                if spec.quantity == "speed" else
                {"kind": "slew_rate_limiter", "full_stroke_time_s": 0.1,
                 "max_opening_rate_per_s": 10.0, "derivative_time_constant_s": 0.001}
                if spec.quantity == "opening" else
                {"kind": "algebraic", "delay_s": 0.0}
            ),
            "measured_response": {"status": "not_modelled", "columns": []},
            "effective_raw_column": (f"{spec.module}.{spec.component}.N_in" if spec.quantity == "speed" else spec.raw) if recorded or not spec.component.startswith("cooler_") else None,
            "effective_source_variable": f"{spec.module}.{spec.component}.N_in" if spec.quantity == "speed" else spec.raw,
        })
    return entries
