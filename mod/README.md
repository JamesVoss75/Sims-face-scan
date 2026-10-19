# FaceScan bridge mod

A small script mod that reads and writes the active Sim's facial data from the cheat console.
It is used for experiment E2. **It has not been run in the game yet.**

- Step-by-step test instructions: [../docs/windows-testing.md](../docs/windows-testing.md)
- Build: `py -3.7 mod/build.py`, or let `E2_install_mod.bat` do it
- Source: `facescan_bridge/facescan_bridge.py`. It must stay compatible with Python 3.7.

## Safety design

- **Writes only to a Sim whose last name is `FaceScanTest`**, and only to human teens through elders.
  Every other Sim is read-only for this mod.
- Writes happen only when you type a command. The mod runs no background code.
- It backs up the original face before the first change (`facescan.validate_restore` puts it back).
- It writes files only to `Documents/Electronic Arts/The Sims 4/facescan/`.
- Errors are printed to the console and never raised into the game loop.

## Verified offline (in this repo, not in the game)

- The command logic runs under CPython **3.7.17** with protobuf 3.20, using stand-ins for the game modules
  (`tests/test_bridge_mod.py`, `tests/test_validation_e2e.py`).
- `build.py` produces a `.ts4script` with Python 3.7 bytecode (magic `420d0d0a`). zipimport can load it.
- The mod's FNV hash matches the library's, and the library's matches EA modifier IDs.
