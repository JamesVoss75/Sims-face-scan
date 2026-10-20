"""Diagnostics collector: simulated Windows situations -> expected findings."""
import json
import sys
from pathlib import Path

import pytest

from tests.test_bridge_mod import load_mod

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import collect_diagnostics  # noqa: E402


def fake_install(tmp_path):
    game = tmp_path / "Program Files" / "The Sims 4"
    for d in ("Game/Bin", "Data/Client", "EP01", "GP05", "Delta/EP01"):
        (game / d).mkdir(parents=True)
    (game / "Data/Client/ClientFullBuild0.package").write_bytes(b"DBPF")
    return game


def run(tmp_path, monkeypatch, stage, user_dir, game_dir=None):
    out = tmp_path / "diag"
    argv = ["x", "--stage", stage, "--out", str(out), "--user-dir", str(user_dir)]
    if game_dir:
        argv += ["--game-dir", str(game_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    assert collect_diagnostics.main() == 0
    env = json.loads((out / "environment.json").read_text())
    return env, {f["code"] for f in env["findings"]}, out


def make_user(tmp_path, options="scriptmodsenabled = 1\nmodsdisabled = 0\n"):
    user = tmp_path / "The Sims 4"
    (user / "Mods").mkdir(parents=True, exist_ok=True)
    (user / "saves").mkdir(exist_ok=True)
    (user / "GameVersion.txt").write_bytes(b"\x08\x00\x00\x001.120.140.1020")
    (user / "Options.ini").write_text("[options]\n" + options)
    return user


def test_e1_reports_game_version_and_packs(tmp_path, monkeypatch):
    env, codes, out = run(tmp_path, monkeypatch, "e1", make_user(tmp_path), fake_install(tmp_path))
    assert env["user"]["game_version"] == "1.120.140.1020"
    inst = env["game"]["installs"][0]
    assert inst["packs"] == ["EP01", "GP05"] and inst["client_packages"] == 1
    assert "GAME_NOT_FOUND" not in codes and "GAME_VERSION" in codes
    assert (out / "diagnosis.md").read_text().startswith("# FaceScan diagnostics (e1)")


def test_mods_disabled_detected(tmp_path, monkeypatch):
    _, codes, _ = run(tmp_path, monkeypatch, "e1", make_user(tmp_path, "scriptmodsenabled = 0\n"))
    assert "MODS_DISABLED" in codes


def test_installed_but_never_loaded(tmp_path, monkeypatch):
    user = make_user(tmp_path)
    (user / "Mods" / "facescan_bridge.ts4script").write_bytes(b"PK")
    _, codes, _ = run(tmp_path, monkeypatch, "e2-check", user)
    assert "MOD_NOT_LOADED" in codes


def test_loaded_mod_and_test_progress(tmp_path, monkeypatch):
    m = load_mod(tmp_path, monkeypatch)  # installs into <tmp>/The Sims 4/Mods/FaceScanBridge/Scripts
    user = make_user(tmp_path)
    from tests.test_bridge_mod import FakeSimInfo, baseline_blob
    m.sim = FakeSimInfo(raw=baseline_blob())
    m.commands["facescan.step"]()
    m.commands["facescan.step"]()
    (user / "lastException_1.txt").write_text("Traceback ... facescan_bridge.py line 12")
    env, codes, out = run(tmp_path, monkeypatch, "e2-check", user)
    assert {"MOD_LOADED", "TEST_INCOMPLETE", "GAME_EXCEPTION_FACESCAN"} <= codes
    assert "MOD_NOT_LOADED" not in codes and "MOD_OUTDATED" not in codes
    assert env["user"]["facescan"]["validation_records"][0]["checkpoints"] == [["live_applied", "PASS"]]
    assert {"mod_loaded.json", "facescan_log.txt", "lastException_1.txt", "api_probe.json"} <= set(env["copied"])


def test_command_failure_surfaces(tmp_path, monkeypatch):
    m = load_mod(tmp_path, monkeypatch)
    from tests.test_bridge_mod import FakeSimInfo
    m.sim = FakeSimInfo(raw=b"\xff\xff")
    m.commands["facescan.dump"]()
    _, codes, _ = run(tmp_path, monkeypatch, "e2-check", make_user(tmp_path))
    assert "MOD_COMMAND_ERROR" in codes


def test_collector_survives_broken_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(collect_diagnostics, "section_system", lambda: 1 / 0)
    env, codes, _ = run(tmp_path, monkeypatch, "e1", make_user(tmp_path))
    assert "system" in env["errors"] and "GAME_VERSION" in codes
