# FaceScan bridge mod

A small script mod that reads and writes the active Sim's facial data from the cheat console.
It is used for experiment E2. **It has not been run in the game yet.**
How to test it: [../docs/windows-testing.md](../docs/windows-testing.md).

## Commands

| Command | Effect |
|---|---|
| `facescan.step` | Guided test: run it repeatedly; each run does the next checkpoint and says what to do next |
| `facescan.undo` | Restore the test Sim's original face and close the test (record kept) |
| `facescan.info` | Versions, paths, active Sim, write permission; writes `out/api_probe.json` (read-only) |
| `facescan.dump` | Write the active Sim's face data to `out/<sim_id>.json` (read-only) |
| `facescan.set`, `facescan.apply`, `facescan.validate_*` | Developer commands (guarded like `step`) |

## Safety design

- **Writes only to a Sim whose last name is `FaceScanTest`**, and only to human teens through elders.
  Every other Sim is read-only for this mod.
- It acts only when you type a command; there is no background code.
- The original face is stored in the validation record. `facescan.undo` restores it, even after a reload.
- It writes files only to `Documents/Electronic Arts/The Sims 4/facescan/`.
- Errors go to the console and `facescan_log.txt` with a full traceback. They are never raised into the game.

## Diagnostics it leaves behind

- `facescan/mod_loaded.json`: written when the game loads the mod. It records the game's Python version, install
  method, import errors, and whether commands were registered. If it's missing, the mod never loaded.
- `facescan/facescan_log.txt`: every command, its result and any traceback.
- `facescan/out/api_probe.json`: names of the face-related attributes on the live `sim_info` object.
  If the game's API differs from what we expect, this shows the real names.

## Install forms

- Packaged: `py -3.7 mod/build.py` produces `dist/facescan_bridge.ts4script`, with Python 3.7 bytecode plus
  the source and matching timestamps, so the bytecode is used.
- Loose: copy `facescan_bridge/facescan_bridge.py` to `Mods/FaceScanBridge/Scripts/`.
- `E2_install_mod.bat` chooses automatically and removes the other form.

## Verified offline (not in the game)

- The command logic, guided flow, undo, heartbeat, import-failure handling and error logging all run on
  CPython 3.13 and **3.7.17**, with stand-in game modules, loaded both as loose scripts and from a zip.
- `build.py` output: Python 3.7 zipimport loads the `.pyc` (not the `.py`) from the package.
- The full Windows flow (install, simulated play, check, uninstall) runs through the real PowerShell
  scripts on PowerShell 7 against a simulated install (`tests/test_windows_scripts.py`).
