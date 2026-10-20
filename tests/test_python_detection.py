"""Regression tests for Windows Python detection (scripts/windows/common.ps1).

Root cause of the original bug: Windows PowerShell 5.1 passes arguments to
native programs in "legacy" mode, which drops embedded double quotes. The old
check ran `python -c 'import sys; print("%d.%d" % ...)'`, so Python received
`print(%d.%d % ...)`, raised SyntaxError, and the error was hidden by `2>$null`
and an empty catch. PowerShell 7 reproduces legacy behaviour when
$PSNativeCommandArgumentPassing = 'Legacy', which these tests use to emulate 5.1.

Needs PowerShell 7 (pwsh on PATH or $FACESCAN_PWSH); skipped otherwise.
Fake `py` / `python` executables on a controlled PATH stand in for the
launcher, Microsoft Store aliases and old interpreters.
"""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
COMMON = REPO / "scripts" / "windows" / "common.ps1"
PWSH = os.environ.get("FACESCAN_PWSH") or shutil.which("pwsh")
PY37 = os.environ.get("FACESCAN_TEST_PY37")
REAL_PY = os.path.realpath(sys.executable)
needs_pwsh = pytest.mark.skipif(not PWSH, reason="PowerShell 7 not available")

STORE_STUB = ('echo "Python was not found; run without arguments to install from the Microsoft Store, '
              'or disable this shortcut from Settings > Manage App Execution Aliases." >&2\nexit 9009\n')


def fake(bin_dir: Path, name: str, body: str) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    p = bin_dir / name
    p.write_text("#!/bin/bash\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return p


def fake_launcher(bin_dir: Path, py3: str, py37: str | None = None) -> None:
    lines = [f' -V:3.13 *        {py3}']
    if py37:
        lines.append(f' -V:3.7           {py37}')
    listing = "\\n".join(lines)
    fake(bin_dir, "py", f'''case "$1" in
  -0p) printf '{listing}\\n';;
  -3) shift; exec "{py3}" "$@";;
  -3.7) shift; {'exec "' + py37 + '" "$@"' if py37 else 'echo "No suitable Python runtime found" >&2; exit 103'};;
  *) exec "{py3}" "$@";;
esac
''')


def run_ps(script: str, path_dirs, legacy=True, env_extra=None):
    """Dot-source common.ps1 and run `script`; PATH is exactly path_dirs."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("FACESCAN_")}
    env["PATH"] = os.pathsep.join(str(d) for d in path_dirs)
    env.pop("LOCALAPPDATA", None)
    env.pop("ProgramFiles", None)
    env.update(env_extra or {})
    mode = "$PSNativeCommandArgumentPassing = 'Legacy'\n" if legacy else ""
    full = f"{mode}$ErrorActionPreference = 'Stop'\n. '{COMMON}'\n{script}"
    p = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", full],
                       capture_output=True, text=True, env=env, timeout=120)
    return p.returncode, p.stdout + p.stderr


def test_probe_script_output_format():
    out = subprocess.run([sys.executable, str(REPO / "tools" / "python_probe.py")],
                         capture_output=True, text=True, check=True).stdout.strip()
    tag, version, exe, bits = out.split("|")
    assert tag == "FACESCAN_PROBE" and version.count(".") == 2 and bits in ("32", "64")
    assert os.path.samefile(exe, sys.executable)


@pytest.mark.skipif(not PY37, reason="set FACESCAN_TEST_PY37 to a Python 3.7 interpreter")
def test_probe_script_runs_on_python37():
    out = subprocess.run([PY37, str(REPO / "tools" / "python_probe.py")], capture_output=True, text=True,
                         check=True).stdout
    assert out.startswith("FACESCAN_PROBE|3.7.")


@needs_pwsh
def test_root_cause_reproduced_old_inline_check_fails_in_legacy_mode(tmp_path):
    """Documents the bug: the old quoted -c check fails under 5.1-style argument passing."""
    old_check = "$v = & python3 -c 'import sys; print(\"%d.%d\" % sys.version_info[:2])' 2>&1 | % { \"$_\" }; " \
                "\"exit=$LASTEXITCODE out=$v\""
    code, out = run_ps(old_check, [Path(REAL_PY).parent], legacy=True)
    assert "exit=1" in out and "SyntaxError" in out
    code, out = run_ps(old_check, [Path(REAL_PY).parent], legacy=False)
    assert "exit=0" in out


@needs_pwsh
@pytest.mark.parametrize("legacy", [True, False])
def test_detects_python_on_path(tmp_path, legacy):
    bin_dir = tmp_path / "bin"
    fake(bin_dir, "python", f'exec "{REAL_PY}" "$@"\n')
    code, out = run_ps("$p = Find-Python; 'RESULT=' + ($p -join ' ')", [bin_dir], legacy=legacy)
    assert f"RESULT={REAL_PY}" in out, out


@needs_pwsh
def test_prefers_launcher_and_returns_real_interpreter(tmp_path):
    bin_dir = tmp_path / "bin"
    fake_launcher(bin_dir, REAL_PY)
    fake(bin_dir, "python", f'exec "{REAL_PY}" "$@"\n')
    code, out = run_ps("$p = Find-Python; 'RESULT=' + ($p -join ' '); "
                       "'FIRST=' + $script:PythonAttempts[0].Command + ' ' + $script:PythonAttempts[0].Ok",
                       [bin_dir])
    assert f"RESULT={REAL_PY}" in out and "FIRST=py -3 True" in out, out


@needs_pwsh
def test_store_alias_rejected_with_reason_and_next_candidate_used(tmp_path):
    store = tmp_path / "WindowsApps"
    fake(store, "python", STORE_STUB)
    spaced = tmp_path / "Program Files" / "Python 312"
    fake(spaced, "python3", f'exec "{REAL_PY}" "$@"\n')
    code, out = run_ps("$p = Find-Python; 'RESULT=' + ($p -join ' '); Write-PythonReport 'test'",
                       [store, spaced])
    assert f"RESULT={REAL_PY}" in out, out
    # Windows reports exit 9009; Linux truncates exit codes to 8 bits, so only check the reason text.
    assert "Microsoft Store alias without an installed Python (exit" in out, out


@needs_pwsh
def test_override_with_spaces_in_path(tmp_path):
    spaced = tmp_path / "My Programs" / "Python 3.12"
    exe = fake(spaced, "python.exe", f'exec "{REAL_PY}" "$@"\n')
    code, out = run_ps("$p = Find-Python; 'RESULT=' + ($p -join ' ')", [tmp_path / "empty"],
                       env_extra={"FACESCAN_PYTHON": str(exe)})
    assert f"RESULT={REAL_PY}" in out, out


@needs_pwsh
def test_too_old_python_rejected(tmp_path):
    bin_dir = tmp_path / "bin"
    fake(bin_dir, "python", 'echo "FACESCAN_PROBE|3.8.10|/opt/old/python|64"\n')
    fake(bin_dir, "python3", f'exec "{REAL_PY}" "$@"\n')
    code, out = run_ps("$p = Find-Python; 'RESULT=' + ($p -join ' '); Write-PythonReport 'test'", [bin_dir])
    assert f"RESULT={REAL_PY}" in out and "version 3.8.10 not accepted" in out, out


@needs_pwsh
def test_nothing_usable_explains_every_attempt(tmp_path):
    bin_dir = tmp_path / "bin"
    fake(bin_dir, "python", STORE_STUB)
    fake(bin_dir, "python3", 'echo "something broke" >&2\nexit 2\n')
    code, out = run_ps("$p = Require-Python; 'RESULT=' + [string]($p -eq $null)", [bin_dir])
    assert "RESULT=True" in out, out
    for expected in ("No working Python 3.9 or newer", "py -3", "not found", "Microsoft Store",
                     "did not run the probe (exit 2)", "something broke", "FACESCAN_PYTHON"):
        assert expected in out, (expected, out)


@needs_pwsh
@pytest.mark.skipif(not PY37, reason="set FACESCAN_TEST_PY37 to a Python 3.7 interpreter")
def test_multiple_versions_launcher_listing(tmp_path):
    bin_dir = tmp_path / "bin"
    real37 = os.path.realpath(PY37)
    fake_launcher(bin_dir, REAL_PY, real37)
    code, out = run_ps("'P39=' + ((Find-Python) -join ' '); 'P37=' + ((Find-Python37) -join ' ')", [bin_dir])
    assert f"P39={REAL_PY}" in out and f"P37={real37}" in out, out


@needs_pwsh
def test_python37_missing_is_reported(tmp_path):
    bin_dir = tmp_path / "bin"
    fake_launcher(bin_dir, REAL_PY)  # py -3.7 fails like the real launcher does
    code, out = run_ps("$p = Find-Python37; 'P37=' + [string]($p -eq $null); Write-PythonReport '3.7'", [bin_dir])
    assert "P37=True" in out and "py -3.7" in out and "No suitable Python runtime" in out, out


@needs_pwsh
def test_clean_path_and_quote_guard(tmp_path):
    script = r"""
'A=' + (ConvertTo-CleanPath '"C:\Program Files\EA Games\The Sims 4\"')
'B=' + (ConvertTo-CleanPath "  C:\Games\The Sims 4\\  ")
'C=' + (ConvertTo-CleanPath 'C:\')
'D=' + (ConvertTo-CleanPath $null)
try { Invoke-Python @('python3') @('x"y') ; 'GUARD=missing' } catch { 'GUARD=' + $_.Exception.Message }
"""
    code, out = run_ps(script, [Path(REAL_PY).parent])
    assert "A=C:\\Program Files\\EA Games\\The Sims 4\n" in out
    assert "B=C:\\Games\\The Sims 4\n" in out and "C=C:\\\n" in out and "D=\n" in out
    assert "GUARD=internal error: argument contains a double quote" in out


@needs_pwsh
def test_invoke_python_passes_spaces_and_backslashes_intact_in_legacy_mode(tmp_path):
    script = tmp_path / "dir with space" / "echo args.py"
    script.parent.mkdir()
    script.write_text("import sys\nfor a in sys.argv[1:]:\n    print('ARG<' + a + '>')\n")
    ps = (f"$code = Invoke-Python @('{REAL_PY}') @('{script}', 'C:\\Program Files\\EA Games\\The Sims 4', "
          "'--out', 'plain'); 'CODE=' + $code")
    code, out = run_ps(ps, [Path(REAL_PY).parent], legacy=True)
    assert "ARG<C:\\Program Files\\EA Games\\The Sims 4>" in out and "ARG<plain>" in out and "CODE=0" in out, out


def test_bat_launchers_use_full_powershell_path_and_scoped_bypass():
    for bat in REPO.glob("E*.bat"):
        raw = bat.read_bytes()
        text = raw.decode("ascii")
        assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b""), f"{bat.name}: needs CRLF line endings"
        assert r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" in text
        assert "-NoProfile -ExecutionPolicy Bypass -File" in text
        assert "Set-ExecutionPolicy" not in text and "-Scope" not in text  # never changes persistent policy
        assert "exit /b %FACESCAN_RC%" in text


def test_scripts_pass_no_inline_python_code():
    """Inline `-c` code is what broke under 5.1; scripts must call files instead."""
    for ps1 in (REPO / "scripts" / "windows").glob("*.ps1"):
        for n, line in enumerate(ps1.read_text().splitlines(), 1):
            assert " -c " not in line or line.lstrip().startswith("#"), f"{ps1.name}:{n}: {line.strip()}"
