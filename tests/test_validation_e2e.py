"""Offline rehearsal of experiment E2: stub game -> mod records -> save file -> report.

Only the parts outside the game are real here.  Whether the real game keeps
the values is exactly what E2 on Windows has to show.
"""
import json
import sys
from pathlib import Path

from tests.helpers import sim_data, write_save
from tests.test_bridge_mod import FakeSimInfo, baseline_blob, mod  # noqa: F401  (fixture)
from ts4face.facial_blob import FacialData
from ts4face.fnv import fnv64
from ts4face.savegame import load_sims

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import check_validation  # noqa: E402


def run_all_checkpoints(mod):
    mod.sim = FakeSimInfo(raw=baseline_blob())
    mod.commands["facescan.validate_begin"]()
    for label in check_validation.REQUIRED:
        mod.commands["facescan.validate_check"](label)


def test_save_reader(tmp_path):
    face = baseline_blob()
    write_save(tmp_path / "Slot_1.save", [sim_data(1234, "Test", "FaceScanTest", face, genetic=face),
                                          sim_data(5, "Bella", "Goth", b"", age=0x20, gender=0x2000)])
    sims = load_sims(str(tmp_path / "Slot_1.save"))
    assert [(s.sim_id, s.name, s.age, s.gender) for s in sims] == [
        (1234, "Test FaceScanTest", "YOUNGADULT", "FEMALE"), (5, "Bella Goth", "ADULT", "FEMALE")]
    assert sims[0].facial_attr == face and sims[0].genetic_facial_attr == face
    assert sims[1].facial.face_modifiers == []


def test_full_pass(mod, tmp_path, monkeypatch):
    run_all_checkpoints(mod)
    user_dir = mod.root.parent
    write_save(user_dir / "saves" / "Slot_2.save", [sim_data(1234, "Test", "FaceScanTest", mod.sim.facial_attributes)])
    monkeypatch.setattr(sys, "argv", ["check_validation.py", "--user-dir", str(user_dir)])
    assert check_validation.main() == 0
    report = json.loads((mod.root / "validation" / "report.json").read_text())
    labels = [c["label"] for c in report[0]["checks"]]
    assert labels == check_validation.REQUIRED + ["save_file_on_disk"]
    assert report[0]["notes"] == []
    assert report[0]["passed"] is True


def test_detects_loss_on_disk_and_missing_checkpoint(mod, tmp_path, monkeypatch):
    mod.sim = FakeSimInfo(raw=baseline_blob())
    mod.commands["facescan.validate_begin"]()
    mod.commands["facescan.validate_check"]("live_applied")
    stale = FacialData.decode(mod.sim.facial_attributes)
    stale.set_face(fnv64("yfheadNose_Wide"), 0.5)  # the game rounded or reset a core value
    user_dir = mod.root.parent
    write_save(user_dir / "saves" / "Slot_3.save", [sim_data(1234, "Test", "FaceScanTest", stale.encode())])
    monkeypatch.setattr(sys, "argv", ["check_validation.py", "--user-dir", str(user_dir)])
    assert check_validation.main() == 1
    report = json.loads((mod.root / "validation" / "report.json").read_text())[0]
    results = {c["label"]: c["result"] for c in report["checks"]}
    assert results["live_applied"] == "PASS"
    assert results["after_cas"] == "MISSING"
    assert results["save_file_on_disk"] == "FAIL"
    assert "report.md" in {p.name for p in (mod.root / "validation").iterdir()}


def test_verify_blob_codec_tool(tmp_path, monkeypatch):
    import verify_blob_codec
    write_save(tmp_path / "saves" / "a.save", [sim_data(1, "A", "B", baseline_blob(), genetic=baseline_blob()),
                                               sim_data(2, "C", "D", b"")])
    out = tmp_path / "r.json"
    monkeypatch.setattr(sys, "argv", ["x", "--saves", str(tmp_path / "saves"), "--out", str(out)])
    assert verify_blob_codec.main() == 0
    stats = json.loads(out.read_text())["stats"]
    assert stats["blobs"] == 2 and stats["aged_face_modifiers"] == 2 and stats["sims"] == 2


def test_unreadable_save_reported_not_crashed(mod, tmp_path, monkeypatch):
    run_all_checkpoints(mod)
    user_dir = mod.root.parent
    (user_dir / "saves").mkdir(parents=True, exist_ok=True)
    (user_dir / "saves" / "Slot_9.save").write_bytes(b"not a package")
    monkeypatch.setattr(sys, "argv", ["check_validation.py", "--user-dir", str(user_dir)])
    assert check_validation.main() == 1
    report = json.loads((mod.root / "validation" / "report.json").read_text())[0]
    disk = [c for c in report["checks"] if c["label"] == "save_file_on_disk"][0]
    assert disk["result"] == "ERROR" and (mod.root / "validation" / "save_read_error.txt").exists()
