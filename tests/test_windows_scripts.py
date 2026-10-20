"""Runs the real Windows PowerShell scripts end to end against a simulated install.

Needs PowerShell 7 (pwsh on PATH, or $FACESCAN_PWSH); skipped otherwise.  The
"game" is simulated by importing the installed mod with stand-in game modules
and writing a save file, so this checks the scripts, the tools and the files
they exchange, not the real game.
"""
import importlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tests.helpers import sim_data, write_package, write_save
from tests.test_bridge_mod import FakeSimInfo, baseline_blob, install_game_stubs
from tests.test_inventory_tool import TUNING, hotspot, smod
from ts4face.fnv import fnv64

REPO = Path(__file__).resolve().parents[1]
PWSH = os.environ.get("FACESCAN_PWSH") or shutil.which("pwsh")
pytestmark = pytest.mark.skipif(not PWSH, reason="PowerShell 7 not available")


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "repo"
    for d in ("scripts", "tools", "ts4face", "mod"):
        shutil.copytree(REPO / d, root / d, ignore=shutil.ignore_patterns("__pycache__", "dist"))
    user = tmp_path / "Documents" / "Electronic Arts" / "The Sims 4"
    (user / "Mods").mkdir(parents=True)
    (user / "saves").mkdir()
    (user / "GameVersion.txt").write_bytes(b"\x08\x00\x00\x001.120.140.1020")
    (user / "Options.ini").write_text("[options]\nscriptmodsenabled = 1\nmodsdisabled = 0\n")
    write_save(user / "saves" / "Slot_00000001.save", [sim_data(42, "Bella", "Goth", baseline_blob())])
    game = tmp_path / "Program Files" / "The Sims 4"
    wide = fnv64("yfheadNose_Wide")
    write_package(game / "Data" / "Client" / "ClientFullBuild0.package", [
        (0xC5F6763E, 0, wide, smod(), False), (0xDB43E069, 0, 0xD1, b"dmap", True),
        (0x8B18FF6E, 0, 0x6658, hotspot((wide, 0, 0, 0)), False), (0x03B33DDF, 0, 0x99, TUNING, True)])
    (game / "Game" / "Bin").mkdir(parents=True)
    (game / "EP01").mkdir()
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    env = dict(os.environ, FACESCAN_USER_DIR=str(user), FACESCAN_DESKTOP=str(desktop), FACESCAN_ASSUME_YES="1")
    env.pop("FACESCAN_PY37", None)
    return {"root": root, "user": user, "game": game, "desktop": desktop, "env": env}


def ps(world, script, *args, env_extra=None):
    env = dict(world["env"], **(env_extra or {}))
    p = subprocess.run([PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(world["root"] / "scripts" / "windows" / script), *args],
                       capture_output=True, text=True, env=env, timeout=300)
    return p.returncode, p.stdout + p.stderr


def play_test_in_fake_game(world, monkeypatch, entry):
    """What the player does in game: load the mod, run facescan.step six times, save."""
    import types
    state = types.SimpleNamespace(sim=FakeSimInfo(raw=baseline_blob()), output=[])
    state.commands = install_game_stubs(monkeypatch, state)
    monkeypatch.syspath_prepend(str(entry))
    sys.modules.pop("facescan_bridge", None)
    importlib.import_module("facescan_bridge")
    for _ in range(6):
        state.commands["facescan.step"]()
    assert state.output[-1].startswith("TEST COMPLETE"), state.output
    write_save(world["user"] / "saves" / "Slot_00000002.save",
               [sim_data(1234, "Test", "FaceScanTest", state.sim.facial_attributes)])
    return state


def zip_names(path):
    with zipfile.ZipFile(path) as z:
        return set(z.namelist())


def test_e1_end_to_end(world):
    code, out = ps(world, "run_experiment1.ps1", "-GameDir", str(world["game"]))
    assert code == 0, out
    names = zip_names(world["desktop"] / "facescan_e1_results.zip")
    for expected in ("summary.json", "catalog.json", "e1b_codec_report.json", "console_log.txt",
                     "diagnostics/diagnosis.md", "diagnostics/environment.json"):
        assert any(n.replace("\\", "/").endswith(expected) for n in names), (expected, names)
    env = json.loads((world["root"] / "results" / "e1" / "diagnostics" / "environment.json").read_text())
    assert env["user"]["game_version"] == "1.120.140.1020"
    assert env["game"]["installs"][0]["packs"] == ["EP01"]
    summary = json.loads((world["root"] / "results" / "e1" / "summary.json").read_text())
    assert summary["face_counts"]["smods"] == 1


def test_e2_scripts_method_end_to_end(world, monkeypatch):
    code, out = ps(world, "install_bridge_mod.ps1")
    assert code == 0, out
    loose = world["user"] / "Mods" / "FaceScanBridge" / "Scripts"
    assert (loose / "facescan_bridge.py").is_file() and "Method: scripts" in out
    play_test_in_fake_game(world, monkeypatch, loose)
    code, out = ps(world, "check_experiment2.ps1")
    assert code == 0, out
    names = {n.replace("\\", "/") for n in zip_names(world["desktop"] / "facescan_e2_results.zip")}
    for expected in ("diagnostics/diagnosis.md", "install_log.txt", "check_log.txt", "my_notes.txt",
                     "validation/report.md", "validation/1234.json", "diagnostics/copies/mod_loaded.json",
                     "diagnostics/copies/facescan_log.txt"):
        assert any(n.endswith(expected) for n in names), (expected, sorted(names))
    diag = (world["root"] / "results" / "e2" / "diagnostics" / "diagnosis.md").read_text()
    assert "MOD_LOADED" in diag and "MOD_NOT_LOADED" not in diag
    code, out = ps(world, "uninstall_bridge_mod.ps1")
    assert code == 0 and not (world["user"] / "Mods" / "FaceScanBridge").exists()


def test_e2_reinstall_archives_old_data_and_switches_method(world, monkeypatch):
    py37 = os.environ.get("FACESCAN_TEST_PY37")
    if not py37:
        pytest.skip("set FACESCAN_TEST_PY37 to a Python 3.7 interpreter to test the ts4script method")
    assert ps(world, "install_bridge_mod.ps1", "-Method", "scripts")[0] == 0
    (world["user"] / "facescan").mkdir(exist_ok=True)
    (world["user"] / "facescan" / "mod_loaded.json").write_text("{}")
    code, out = ps(world, "install_bridge_mod.ps1", env_extra={"FACESCAN_PY37": py37})
    assert code == 0, out
    assert (world["user"] / "Mods" / "facescan_bridge.ts4script").is_file()
    assert not (world["user"] / "Mods" / "FaceScanBridge").exists()
    assert not (world["user"] / "facescan" / "mod_loaded.json").exists()
    assert list((world["user"] / "facescan" / "archive").glob("*/mod_loaded.json"))
    assert zip_names(world["user"] / "Mods" / "facescan_bridge.ts4script") == {"facescan_bridge.pyc", "facescan_bridge.py"}


def test_e2_check_without_install_explains_problem(world):
    code, out = ps(world, "check_experiment2.ps1")
    assert code != 0
    diag = (world["root"] / "results" / "e2" / "diagnostics" / "diagnosis.md").read_text()
    assert "MOD_NOT_INSTALLED" in diag and "What to do: Run E2_install_mod.bat" in diag
