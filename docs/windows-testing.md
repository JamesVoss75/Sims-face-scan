# Testing on Windows (E1 and E2)

**What these tests prove:** E1 reads the game's face data (read-only). E2 checks whether a face
written by our mod shows up in the game and survives CAS, saving and reloading. **Neither has been run
on a real game yet.** That is what this is for.

Each test ends with **one zip file on your Desktop**. Send me that zip. It contains everything I need to
troubleshoot, so you don't need to read any code or logs.

## Before you start (once)

1. Download the project: on GitHub, open `JamesVoss75/Sims-face-scan`, select branch
   **`development/face-engine`**, click **Code → Download ZIP**, and extract it (for example to `C:\FaceScan`).
   If Windows warns about the files, right-click the ZIP first → Properties → tick **Unblock**.
2. Install Python if you don't have it. Open *Terminal* and run: `winget install -e --id Python.Python.3.12`
   (or use the installer from python.org with "Add python.exe to PATH" ticked).

## Test 1: E1 (read-only, about 5–15 minutes)

1. Double-click **`E1_inventory.bat`** in the project folder.
2. If it asks for the game folder, paste the folder that contains `Game` and `Data`
   (for example `C:\Program Files\EA Games\The Sims 4`).
3. Send **`Desktop\facescan_e1_results.zip`**.

It changes nothing in the game folder or your saves.

## Test 2: E2 (about 20 minutes)

1. **Quit the game.** Double-click **`E2_install_mod.bat`** and answer **Y** to the questions. It backs up
   your saves to `Documents\FaceScan_backups` first.
2. **Start the game.** Go to *Options → Game Options → Other*, tick **Enable Custom Content and Mods** and
   **Script Mods Allowed**, then restart the game if it asks.
3. Choose **New Game** (don't load your real save). Create one human **Young Adult**, set the **last name** to
   **`FaceScanTest`**, finish CAS, pick any lot, and **save under a new name**.
4. Press **Ctrl+Shift+C** and type **`facescan.step`**, then press Enter.
   **Keep doing what it says and typing `facescan.step` again.** It walks you through six steps (look at the
   face, Modify in CAS, save, reload, CAS again) and says **TEST COMPLETE** at the end.
5. **Quit the game.** Double-click **`E2_check_results.bat`**, answer its three yes/no questions, and send
   **`Desktop\facescan_e2_results.zip`**.
6. Optional cleanup: in the game, `facescan.undo` restores the test Sim's original face. Double-click
   **`E2_uninstall_mod.bat`** to remove the mod.

If `facescan.step` gives no answer at all, the game didn't load the mod. Do step 5 anyway; the zip
will show why.

## Safety

- The mod **only changes a Sim whose last name is FaceScanTest**, and only when you type a command.
  It refuses every other Sim. Nothing runs in the background.
- `facescan.undo` puts the original face back. `E2_uninstall_mod.bat` removes the mod completely.
- Your saves are zipped before installing. Use a new save for the test.
- E1, `E2_check_results.bat` and all analysis are read-only.

## What the zips contain (for troubleshooting)

| Item | Tells me |
|---|---|
| `diagnostics/diagnosis.md` | Plain-language findings with fixes: game version, packs, mods settings, install problems, mod load or command failures |
| `diagnostics/environment.json` | Game install path and exe version, GameVersion.txt, packs, Windows/Python versions, Python 3.7 presence, Options.ini mod settings, other script mods (names only), newest save name, exception files |
| `diagnostics/copies/` | The game's newest `lastException` files, the mod's load record (`mod_loaded.json`: game Python version, install method, import errors), its log (every command plus full error tracebacks), and the live API probe |
| `console_log.txt`, `install_log.txt`, `check_log.txt` | Everything the scripts printed |
| E1: `summary.json`, `catalog.json`, `e1b_codec_report.json` | Every face slider/preset/hotspot in your game, parser self-checks, codec check on your saves |
| E2: `validation/` | Each checkpoint's raw face data plus an independent check against the save file on disk |
| E2: `my_notes.txt` | Your yes/no answers |

Privacy: the zips contain file and folder names (mods, saves) and game settings. They contain no
photos and nothing from your saves except the test Sim's face data.

## If Python is not detected

The `.bat` window prints every Python command it tried and why each was rejected, for example
"not found", "Microsoft Store alias without an installed Python", "version 3.8.10 not accepted",
or the error Python printed. The same text is in `console_log.txt`. Detection tries, in order:

1. the `FACESCAN_PYTHON` override
2. the `py -3` launcher
3. `python` and `python3` on PATH
4. every interpreter that `py -0p` lists
5. `%LOCALAPPDATA%\Programs\Python\Python3*` and `%ProgramFiles%\Python3*`

It accepts the first one that actually runs and is 3.9 or newer.

If Python is installed but still not found, open *Command Prompt* in the project folder and run:

```
set FACESCAN_PYTHON=C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe
E1_inventory.bat
```

## If something goes wrong

Send the zip anyway. The common cases are detected automatically:

| Finding code | Meaning |
|---|---|
| `MODS_DISABLED` | Script mods are off in the game options |
| `MOD_NOT_INSTALLED` / `MOD_INSTALLED_TWICE` | Install problem: rerun `E2_install_mod.bat` |
| `MOD_NOT_LOADED` | Installed, but the game never loaded it. I will switch the install method |
| `MOD_IMPORT_ERROR` / `MOD_COMMANDS_NOT_REGISTERED` / `MOD_COMMAND_ERROR` | The game's scripting API differs from what we expect. The traceback in the zip tells me exactly where |
| `TEST_INCOMPLETE` | The guided test stopped early; continue with `facescan.step` |
| `save_file_on_disk: ERROR` | The save format differs from what we expect; the error file is in the zip |

## Install methods (automatic)

`E2_install_mod.bat` picks the method by itself:

- **Python 3.7 installed** → the standard packaged form: `Mods\facescan_bridge.ts4script`, compiled for
  the game's Python 3.7, with the source included.
- **No Python 3.7** → the loose-script form: `Mods\FaceScanBridge\Scripts\facescan_bridge.py`. This needs no
  extra install. Community guides say the game loads `.py` files from `Mods\<Name>\Scripts`
  (unverified by us).

If the zip shows the mod didn't load, I'll ask you to install Python 3.7
(`winget install -e --id Python.Python.3.7`) and rerun `E2_install_mod.bat`. The installer removes
the previous form automatically.

Advanced overrides, only if I ask: you can set environment variables `FACESCAN_USER_DIR` (Sims 4
documents folder), `FACESCAN_PY37` (path to python 3.7) and `FACESCAN_DESKTOP`.
