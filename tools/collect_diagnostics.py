"""Collect everything needed to troubleshoot E1/E2 without reading code.

READ-ONLY with respect to the game and saves: it only reads files and
writes into --out.  Every section is collected independently; a failure in
one is recorded and the rest still run.

    python tools/collect_diagnostics.py --stage e2-check --out results/e2/diagnostics

Writes:
    environment.json   machine-readable facts (game version, packs, Python, mod state, ...)
    diagnosis.md       plain-language findings, each with a suggested fix
    copies/            newest lastException files, the mod log, heartbeat and API probe

Privacy: records folder and file NAMES (mods, saves), versions and settings.
It records no personal file contents other than the game's own exception logs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from ts4face.paths import COMMON_INSTALL_DIRS, _registry_install_dirs, looks_like_install, user_data_dir  # noqa: E402

TOOL_VERSION = "diag-1"
MOD_SOURCE = REPO / "mod" / "facescan_bridge" / "facescan_bridge.py"
PACK_RE = re.compile(r"^(EP|GP|SP|FP)\d{2}$", re.IGNORECASE)
VERSION_RE = re.compile(r"\d+\.\d+\.\d+\.\d+")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(cmd: list[str], timeout=20) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout + p.stderr).strip()
    except Exception as e:
        return f"<{type(e).__name__}: {e}>"


def file_version(path: Path) -> str | None:
    """Windows file version of an .exe via the version resource (None elsewhere)."""
    if sys.platform != "win32" or not path.is_file():
        return None
    import ctypes
    from ctypes import wintypes
    size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return None
    buf = ctypes.create_string_buffer(size)
    ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buf)
    ptr, ln = ctypes.c_void_p(), wintypes.UINT()
    if not ctypes.windll.version.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(ln)):
        return None
    ffi = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint32 * 13)).contents
    ms, ls = ffi[2], ffi[3]
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def section_tool() -> dict:
    head = None
    try:
        ref = (REPO / ".git" / "HEAD").read_text().strip()
        head = (REPO / ".git" / ref[5:]).read_text().strip() if ref.startswith("ref: ") else ref
    except OSError:
        pass
    return {"tool_version": TOOL_VERSION, "git_commit": head, "mod_source_sha256": sha256(MOD_SOURCE)[:16],
            "repo_path": str(REPO), "collected_at": time.strftime("%Y-%m-%d %H:%M:%S")}


def section_system() -> dict:
    d = {"platform": platform.platform(), "python": sys.version, "python_executable": sys.executable,
         "python_bits": 64 if sys.maxsize > 2 ** 32 else 32}
    if sys.platform == "win32":
        d["py_launcher_versions"] = _run(["py", "-0p"])
        d["python37"] = _run(["py", "-3.7", "-c", "import sys;print(sys.version)"])
        d["game_running"] = "TS4_x64.exe" in _run(["tasklist", "/FI", "IMAGENAME eq TS4_x64.exe"])
    return d


def section_game(extra: list[str] | None = None) -> dict:
    regs = _registry_install_dirs()
    installs = []
    seen = set()
    for p in (extra or []) + regs + COMMON_INSTALL_DIRS:
        path = Path(p)
        if str(path).lower() in seen or not path.is_dir():
            continue
        seen.add(str(path).lower())
        info = {"path": str(path), "looks_like_install": looks_like_install(path)}
        for exe in ("Game/Bin/TS4_x64.exe", "Game/Bin/TS4_DX9_x64.exe"):
            e = path / exe
            if e.is_file():
                info[exe] = {"file_version": file_version(e), "size": e.stat().st_size,
                             "modified": time.strftime("%Y-%m-%d", time.localtime(e.stat().st_mtime))}
        packs = sorted({d.name.upper() for d in path.iterdir() if d.is_dir() and PACK_RE.match(d.name)})
        delta = path / "Delta"
        info["packs"] = packs
        info["delta_packs"] = sorted(d.name.upper() for d in delta.iterdir() if d.is_dir()) if delta.is_dir() else []
        info["client_packages"] = len(list(path.rglob("Client*Build*.package")))
        installs.append(info)
    return {"registry_install_dirs": regs, "installs": installs}


def parse_options_ini(path: Path) -> dict:
    out = {}
    for line in path.read_text(errors="replace").splitlines():
        if "=" in line and any(k in line.lower() for k in ("mod", "script")):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def section_user(user_dir: Path) -> dict:
    d = {"path": str(user_dir), "exists": user_dir.is_dir(), "onedrive": "onedrive" in str(user_dir).lower()}
    if not user_dir.is_dir():
        return d
    gv = user_dir / "GameVersion.txt"
    if gv.is_file():
        m = VERSION_RE.search(gv.read_bytes().decode("latin-1"))
        d["game_version"] = m.group(0) if m else None
    ini = user_dir / "Options.ini"
    d["options_ini_mod_settings"] = parse_options_ini(ini) if ini.is_file() else None
    mods = user_dir / "Mods"
    m = {"exists": mods.is_dir()}
    if mods.is_dir():
        m["resource_cfg"] = (mods / "Resource.cfg").is_file()
        scripts = []
        for p in mods.rglob("*.ts4script"):
            depth = len(p.relative_to(mods).parts) - 1
            scripts.append({"name": str(p.relative_to(mods)), "depth": depth})
        m["ts4script_files"] = scripts[:300]
        m["ts4script_count"] = len(scripts)
        m["package_count"] = sum(1 for _ in mods.rglob("*.package"))
        loose = [str(p.relative_to(mods)) for p in mods.glob("*/Scripts/*.py")]
        m["loose_script_files"] = loose[:100]
        packed = mods / "facescan_bridge.ts4script"
        m["facescan_ts4script"] = ({"sha256": sha256(packed)[:16], "modified": packed.stat().st_mtime}
                                   if packed.is_file() else None)
        loose_mod = mods / "FaceScanBridge" / "Scripts" / "facescan_bridge.py"
        m["facescan_scripts_folder"] = ({"sha256": sha256(loose_mod)[:16], "modified": loose_mod.stat().st_mtime,
                                         "matches_repo_source": sha256(loose_mod) == sha256(MOD_SOURCE)}
                                        if loose_mod.is_file() else None)
    d["mods"] = m
    saves = sorted((user_dir / "saves").glob("*.save"), key=lambda p: p.stat().st_mtime) if (user_dir / "saves").is_dir() else []
    d["saves"] = {"count": len(saves),
                  "newest": ({"name": saves[-1].name, "modified": saves[-1].stat().st_mtime,
                              "size": saves[-1].stat().st_size} if saves else None)}
    exc = sorted(list(user_dir.glob("lastException*.txt")) + list(user_dir.glob("lastUIException*.txt")),
                 key=lambda p: p.stat().st_mtime)
    d["exception_files"] = [{"name": p.name, "modified": p.stat().st_mtime, "size": p.stat().st_size,
                             "mentions_facescan": "facescan" in p.read_text(errors="replace").lower()}
                            for p in exc[-10:]]
    fs = user_dir / "facescan"
    f = {"exists": fs.is_dir()}
    if fs.is_dir():
        hb = fs / "mod_loaded.json"
        f["heartbeat"] = json.loads(hb.read_text()) if hb.is_file() else None
        log = fs / "facescan_log.txt"
        if log.is_file():
            lines = log.read_text(errors="replace").splitlines()
            f["log_lines"] = len(lines)
            f["log_errors"] = [l for l in lines if "FAILED" in l or "IMPORT ERROR" in l][-10:]
            f["log_tail"] = lines[-40:]
        probe = fs / "out" / "api_probe.json"
        f["api_probe"] = json.loads(probe.read_text()) if probe.is_file() else None
        recs = []
        for p in sorted((fs / "validation").glob("*.json")):
            if p.name.startswith("report"):
                continue
            try:
                r = json.loads(p.read_text())
                recs.append({"file": p.name, "sim": r.get("sim"), "checkpoints": [(c["label"], c["result"])
                             for c in r.get("checkpoints", [])], "readback_identical": r.get("readback_identical"),
                             "install_method": r.get("install_method"), "python": r.get("python")})
            except Exception as e:
                recs.append({"file": p.name, "error": repr(e)})
        f["validation_records"] = recs
    d["facescan"] = f
    return d


def triage(env: dict, stage: str) -> list[dict]:
    """Turn facts into findings: severity, code, message, fix."""
    out = []

    def add(sev, code, msg, fix=""):
        out.append({"severity": sev, "code": code, "message": msg, "fix": fix})
    sysd, game, user = env.get("system", {}), env.get("game", {}), env.get("user", {})
    if not any(i.get("looks_like_install") for i in game.get("installs", [])):
        add("error" if stage == "e1" else "warning", "GAME_NOT_FOUND",
            "The Sims 4 install folder was not found automatically.",
            "Run E1 again and paste the install folder when asked (the folder that contains 'Game' and 'Data').")
    for i in game.get("installs", []):
        exe = i.get("Game/Bin/TS4_x64.exe") or {}
        add("info", "GAME_INSTALL", f"Install: {i['path']}; exe version {exe.get('file_version')}; "
            f"{len(i.get('packs', []))} packs ({', '.join(i.get('packs', [])[:40])})")
    if not user.get("exists"):
        add("error", "NO_USER_FOLDER", f"Game user folder not found at {user.get('path')}.",
            "Start The Sims 4 once so it creates Documents\\Electronic Arts\\The Sims 4, then retry.")
        return out
    add("info", "GAME_VERSION", f"Game version (GameVersion.txt): {user.get('game_version')}")
    if user.get("onedrive"):
        add("info", "ONEDRIVE", "Documents is redirected to OneDrive; paths were resolved through Windows.")
    ini = user.get("options_ini_mod_settings") or {}
    low = {k.lower(): v for k, v in ini.items()}
    if low.get("scriptmodsenabled") == "0" or low.get("modsdisabled") == "1":
        add("error", "MODS_DISABLED", f"Mods or script mods are disabled in Options.ini ({ini}).",
            "In the game: Options > Game Options > Other: tick 'Enable Custom Content and Mods' and "
            "'Script Mods Allowed', then restart the game.")
    elif ini and "scriptmodsenabled" not in low:
        add("info", "MODS_SETTING_UNKNOWN", f"Could not find the script-mod setting in Options.ini ({ini}).")
    if stage.startswith("e2"):
        mods = user.get("mods", {})
        packed, loose = mods.get("facescan_ts4script"), mods.get("facescan_scripts_folder")
        if packed and loose:
            add("error", "MOD_INSTALLED_TWICE", "The mod is installed both as .ts4script and as loose scripts.",
                "Run E2_uninstall_mod.bat, then E2_install_mod.bat once.")
        if not packed and not loose:
            add("error" if stage == "e2-check" else "info", "MOD_NOT_INSTALLED", "The FaceScan mod is not in the Mods folder.",
                "Run E2_install_mod.bat.")
        if loose and not loose.get("matches_repo_source"):
            add("warning", "MOD_OUTDATED", "The installed loose-script mod differs from this repository's version.",
                "Run E2_install_mod.bat again.")
        for s in mods.get("ts4script_files", []):
            if s["depth"] > 1:
                add("warning", "SCRIPT_TOO_DEEP", f"Script mod nested too deep (the game ignores it): {s['name']}")
        others = [s["name"] for s in mods.get("ts4script_files", []) if "facescan" not in s["name"].lower()]
        if others:
            add("info", "OTHER_SCRIPT_MODS", f"{len(others)} other script mods installed (could interfere): "
                + ", ".join(others[:15]))
        fs = user.get("facescan", {})
        hb = fs.get("heartbeat")
        installed_at = max([x["modified"] for x in (packed, loose) if x] or [0])
        if stage == "e2-check":
            if (packed or loose) and not hb:
                add("error", "MOD_NOT_LOADED", "The mod is installed but the game never loaded it (no mod_loaded.json).",
                    "Make sure 'Script Mods Allowed' is ticked and the game was restarted after installing. "
                    "If it was, send the results zip: the fix is to switch install method, which I will tell you how to do.")
            elif hb and hb.get("loaded_epoch", 0) < installed_at:
                add("warning", "MOD_LOAD_STALE", "The last mod load happened before the current install.",
                    "Restart the game after installing, then repeat the test.")
        if hb:
            add("info", "MOD_LOADED", f"Mod {hb.get('mod_version')} loaded by the game at {hb.get('loaded_at')} "
                f"as {hb.get('install_method')}; game Python {str(hb.get('python', '')).split()[0]}")
            if hb.get("import_error"):
                add("error", "MOD_IMPORT_ERROR", "The mod loaded but a game module was missing:\n"
                    + hb["import_error"].strip().splitlines()[-1], "Send the results zip (needs a code fix).")
            if not hb.get("commands_registered"):
                add("error", "MOD_COMMANDS_NOT_REGISTERED", "The mod's cheat commands were not registered.",
                    "Send the results zip (needs a code fix).")
        for e in fs.get("log_errors", []):
            add("error", "MOD_COMMAND_ERROR", f"Mod log reports: {e}", "Send the results zip (needs a code fix).")
        for e in user.get("exception_files", []):
            if e["mentions_facescan"]:
                add("error", "GAME_EXCEPTION_FACESCAN", f"{e['name']} mentions facescan.", "Send the results zip.")
        recs = fs.get("validation_records", [])
        if stage == "e2-check" and hb and not recs:
            add("warning", "TEST_NOT_STARTED", "The mod loaded but no test was started.",
                "In the game, select the FaceScanTest Sim and type: facescan.step")
        for r in recs:
            done = [c for c in r.get("checkpoints", [])]
            if len(done) < 5 and ".done-" not in r.get("file", ""):
                add("warning", "TEST_INCOMPLETE", f"Test for {r.get('sim')} stopped after {len(done)} of 5 checkpoints.",
                    "Continue with facescan.step in the game; it says what to do next.")
    return out


def copy_artifacts(user_dir: Path, out: Path) -> list[str]:
    dst = out / "copies"
    dst.mkdir(parents=True, exist_ok=True)
    copied = []
    exc = sorted(list(user_dir.glob("lastException*.txt")) + list(user_dir.glob("lastUIException*.txt")),
                 key=lambda p: p.stat().st_mtime)[-3:]
    fs = user_dir / "facescan"
    for p in exc + [fs / "mod_loaded.json", fs / "facescan_log.txt", fs / "out" / "api_probe.json"]:
        if p.is_file():
            shutil.copy2(p, dst / p.name)
            copied.append(p.name)
    return copied


def render(env: dict, findings: list[dict], stage: str) -> str:
    icon = {"error": "PROBLEM", "warning": "CHECK", "info": "info"}
    lines = [f"# FaceScan diagnostics ({stage})", "", f"Collected {env['tool']['collected_at']}", ""]
    for sev in ("error", "warning", "info"):
        for f in findings:
            if f["severity"] == sev:
                lines.append(f"- **{icon[sev]}** [{f['code']}] {f['message']}")
                if f["fix"]:
                    lines.append(f"  - What to do: {f['fix']}")
    if env.get("errors"):
        lines += ["", "## Collector errors", ""] + [f"- {k}: {v.splitlines()[-1]}" for k, v in env["errors"].items()]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=["e1", "e2-install", "e2-check"], required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--user-dir", type=Path, default=None)
    ap.add_argument("--game-dir", default=None, help="install folder, if known")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    user_dir = args.user_dir or user_data_dir()
    env, errors = {"stage": args.stage}, {}
    for name, fn in (("tool", section_tool), ("system", section_system), ("game", lambda: section_game([args.game_dir] if args.game_dir else None)),
                     ("user", lambda: section_user(user_dir))):
        try:
            env[name] = fn()
        except Exception:
            errors[name] = traceback.format_exc()
            env[name] = {}
    env["errors"] = errors
    try:
        env["copied"] = copy_artifacts(user_dir, args.out) if user_dir.is_dir() else []
    except Exception:
        errors["copy"] = traceback.format_exc()
    findings = triage(env, args.stage)
    env["findings"] = findings
    (args.out / "environment.json").write_text(json.dumps(env, indent=2, default=str))
    md = render(env, findings, args.stage)
    (args.out / "diagnosis.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
