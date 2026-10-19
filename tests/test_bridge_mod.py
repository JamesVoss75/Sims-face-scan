"""Runs the bridge mod's logic against stand-ins for the game's modules.

This proves the mod's own logic (guards, test face, comparisons, files) only.
It says nothing about how the real game reacts; that is experiment E2.
"""
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

from tests.test_facial_blob import Blob
from ts4face.facial_blob import FacialData, Modifier
from ts4face.fnv import fnv64

MOD_DIR = Path(__file__).resolve().parents[1] / "mod" / "facescan_bridge"


class FakeSimInfo:
    def __init__(self, last_name="FaceScanTest", age="Age.YOUNGADULT", raw=b""):
        self.first_name, self.last_name, self.sim_id = "Test", last_name, 1234
        self.age, self.gender, self.species = age, "Gender.FEMALE", "SpeciesExtended.HUMAN"
        self.facial_attributes = raw


@pytest.fixture
def mod(tmp_path, monkeypatch):
    state = types.SimpleNamespace(sim=None, output=[])
    commands = {}

    sims4 = types.ModuleType("sims4")
    cmd = types.ModuleType("sims4.commands")
    cmd.CommandType = types.SimpleNamespace(Live=1)
    cmd.CheatOutput = lambda conn: state.output.append

    def command(name, command_type=None):
        def deco(fn):
            commands[name] = fn
            return fn
        return deco
    cmd.Command = command
    sims4.commands = cmd
    services = types.ModuleType("services")

    class Client:
        active_sim_info = property(lambda self: state.sim)
    client = Client()
    services.client_manager = lambda: types.SimpleNamespace(get_first_client=lambda: client)
    pb = types.ModuleType("protocolbuffers")
    pb2 = types.ModuleType("protocolbuffers.PersistenceBlobs_pb2")
    pb2.BlobSimFacialCustomizationData = Blob
    pb.PersistenceBlobs_pb2 = pb2
    for name, m in {"sims4": sims4, "sims4.commands": cmd, "services": services,
                    "protocolbuffers": pb, "protocolbuffers.PersistenceBlobs_pb2": pb2}.items():
        monkeypatch.setitem(sys.modules, name, m)

    # Pretend the mod lives in <tmp>/The Sims 4/Mods/facescan_bridge.ts4script/
    monkeypatch.syspath_prepend(str(MOD_DIR))
    sys.modules.pop("facescan_bridge", None)
    module = importlib.import_module("facescan_bridge")
    fake_file = tmp_path / "The Sims 4" / "Mods" / "facescan_bridge.ts4script" / "facescan_bridge.pyc"
    monkeypatch.setattr(module, "__file__", str(fake_file))
    state.commands, state.module, state.root = commands, module, tmp_path / "The Sims 4" / "facescan"
    return state


def baseline_blob():
    return FacialData(sculpts=[0x8000000000000111],
                      face_modifiers=[Modifier(fnv64("yfheadNose_Narrow"), 0.3), Modifier(999, 0.2)],
                      aged_face_modifiers=[Modifier(77, 0.5)]).encode()


def test_fnv_in_mod_matches_library(mod):
    for name in ("yfheadNose_Wide", "yfheadChin_Wide", "yfheadEyes_Big"):
        assert mod.module.fnv64(name) == fnv64(name)


def test_writes_refused_for_non_test_sim(mod):
    mod.sim = FakeSimInfo(last_name="Goth", raw=baseline_blob())
    mod.commands["facescan.validate_begin"]()
    mod.commands["facescan.set"]("0x10", "0.5")
    assert mod.sim.facial_attributes == baseline_blob()
    assert sum("refused" in line for line in mod.output) == 2


def test_writes_refused_for_child(mod):
    mod.sim = FakeSimInfo(age="Age.CHILD", raw=baseline_blob())
    mod.commands["facescan.validate_begin"]()
    assert mod.sim.facial_attributes == baseline_blob()
    assert "refused" in mod.output[-1]


def test_dump_is_read_only_and_complete(mod):
    mod.sim = FakeSimInfo(last_name="Goth", raw=baseline_blob())
    mod.commands["facescan.dump"]()
    assert mod.sim.facial_attributes == baseline_blob()
    data = json.loads((mod.root / "out" / "1234.json").read_text())
    assert bytes.fromhex(data["blob_hex"]) == baseline_blob()
    assert data["aged_face_modifiers"][0]["key"] == "0x000000000000004D"


def test_validation_flow(mod):
    mod.sim = FakeSimInfo(raw=baseline_blob())
    mod.commands["facescan.validate_begin"]()
    applied = FacialData.decode(mod.sim.facial_attributes)
    faces = applied.face_dict()
    assert faces[fnv64("yfheadNose_Wide")] == pytest.approx(0.613)
    assert fnv64("yfheadNose_Narrow") not in faces          # opposite removed
    assert faces[999] == pytest.approx(0.2)                  # unrelated modifier kept
    assert applied.sculpts == [0x8000000000000111]           # sculpts kept
    assert applied.aged_face_modifiers[0].key == 77          # aged list kept

    mod.commands["facescan.validate_check"]("live_applied")
    assert "PASS" in mod.output[-1]

    # Simulate CAS clamping a probe (observation, still PASS) ...
    clamped = FacialData.decode(mod.sim.facial_attributes)
    clamped.set_face(fnv64("yfheadEyes_Big"), 0.52)
    mod.sim.facial_attributes = clamped.encode()
    mod.commands["facescan.validate_check"]("after_cas")
    assert any("after_cas: PASS (0 problems, 1 probe changes)" in line for line in mod.output)

    # ... and losing a core modifier (FAIL).
    lost = FacialData.decode(mod.sim.facial_attributes)
    lost.set_face(fnv64("yfheadMouth_Wide"), 0.0)
    mod.sim.facial_attributes = lost.encode()
    mod.commands["facescan.validate_check"]("after_reload")
    assert any("after_reload: FAIL" in line for line in mod.output)

    record = json.loads((mod.root / "validation" / "1234.json").read_text())
    assert [c["result"] for c in record["checkpoints"]] == ["PASS", "PASS", "FAIL"]

    mod.commands["facescan.validate_restore"]()
    assert mod.sim.facial_attributes == baseline_blob()


def test_errors_are_reported_not_raised(mod):
    mod.sim = FakeSimInfo(raw=b"\xff\xff")  # not a valid blob
    mod.commands["facescan.dump"]()
    assert mod.output[-1].startswith("facescan error:")
