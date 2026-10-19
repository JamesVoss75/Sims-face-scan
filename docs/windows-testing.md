# Testing on Windows

Everything here runs on your Windows PC with The Sims 4 installed. The tools were developed in a
Linux container without the game. **None of them has been run against the real game yet.** These
experiments are how we find out.

| Experiment | What it changes | Time |
|---|---|---|
| **E1** inventory + codec check | Nothing (read-only) | ~5–15 min, unattended |
| **E2** live write + persistence validation | One disposable Sim in one disposable save; the mod file in `Mods` | ~30 min |

## 0. One-time setup

1. **Get the code.** On GitHub, open `JamesVoss75/Sims-face-scan`, switch to the branch
   `development/face-engine`, then choose **Code → Download ZIP**. Extract it somewhere, for
   example `C:\FaceScan`. You can also run
   `git clone -b development/face-engine https://github.com/JamesVoss75/Sims-face-scan C:\FaceScan`.
2. **Python 3.9+** (for the tools). Check this in a terminal with `py -3 --version`. If it's missing,
   run `winget install -e --id Python.Python.3.12`, or use the installer from python.org with
   "Add python.exe to PATH" ticked. The tools use only the standard library, so you don't need `pip install`.
3. **Python 3.7** (only for building the E2 mod, because the game runs Python 3.7). The E2
   installer offers to install it with winget (`Python.Python.3.7`). You can also get 3.7.9 from
   https://www.python.org/downloads/release/python-379/. It installs alongside newer versions.

If Windows SmartScreen or "Mark of the Web" blocks a `.bat` file, right-click the ZIP before
extracting, choose **Properties**, and tick **Unblock**.

## 1. Experiment 1: inventory (read-only)

Double-click **`E1_inventory.bat`**.

What it does:
- It finds the game folder (from the registry, then the usual EA app, Origin and Steam paths). If
  it can't, it asks you for the folder.
- It reads every `Client*Build*.package` and `Simulation*Build*.package` and lists every face
  SimModifier, sculpt, CAS preset and drag hotspot. It also extracts EA's CAS modifier tuning
  (names, scales and limits).
- It checks its own parsing. For example, it checks what fraction of hotspot and preset references
  point to modifiers that exist. If a parser misread a field, these rates would collapse.
- **E1b**: it decodes every Sim's face data in your existing saves, re-encodes it, and checks the bytes
  are identical. This proves the codec against real data. It only reads the saves.
- It writes `Desktop\facescan_e1_results.zip`, which contains `summary.json`, `catalog.json` and
  `e1b_codec_report.json`.

**Send back:** `facescan_e1_results.zip`. It contains resource IDs, modifier names and counts.
It does not contain your Sims' names or any game files. The extracted tuning XML stays in
`results\e1\tuning`.

**Expected:** no or few `parse_failures`, and cross-reference rates near 100%. E1b should report
`RESULT: PASS`. Anything else is useful information, not a disaster.

## 2. Experiment 2: does a scripted face survive the game?

### 2a. Install (asks before each change)

1. Quit the game.
2. Double-click **`E2_install_mod.bat`**. It:
   - offers a zip backup of your `saves` folder to `Documents\FaceScan_backups\` (say yes)
   - builds `facescan_bridge.ts4script` with Python 3.7
   - copies it into `Documents\Electronic Arts\The Sims 4\Mods\`
   - checks whether script mods are enabled
3. In the game, go to **Options → Game Options → Other**, enable **Enable Custom Content and Mods**
   and **Script Mods Allowed**, then restart the game. The game shows a mod list on start; check
   that `facescan_bridge.ts4script` is listed.

### 2b. Make the disposable Sim and save

1. Main menu → **New Game**. Create a **new** household (don't load your real save).
2. Make one **human Young Adult** (any frame). Set the **last name to `FaceScanTest`**. The mod
   refuses to change any other Sim.
3. Leave the face at its default or change it; either is fine. Finish CAS, pick any lot, and play.
4. Save it under a new name, for example `FaceScan E2`. Don't overwrite a real save.

### 2c. Run the checkpoints

Open the cheat console with **Ctrl+Shift+C** and type the commands exactly. After each command,
read the line the console prints and write it down (or take a screenshot).

| Step | In the game | Then type |
|---|---|---|
| 1 | Select the FaceScanTest Sim | `facescan.info` (confirm it says `writes: allowed` and shows the Python version) |
| 2 | (nothing) | `facescan.validate_begin` |
| 3 | Look at the face. Did it change visibly (wider nose and mouth, bigger eyes, forward chin)? Note yes/no. | `facescan.validate_check live_applied` |
| 4 | Enter `testingcheats true`, then shift-click the Sim → **Modify in CAS**. **Don't touch anything.** Look at the face, then click the ✓ to leave CAS. | `facescan.validate_check after_cas` |
| 5 | Save the game (same save name). | `facescan.validate_check after_save` |
| 6 | Quit to the main menu, load `FaceScan E2` again, select the Sim. | `facescan.validate_check after_reload` |
| 7 | Open Modify in CAS again, don't change anything, leave with ✓. Save the game again. | `facescan.validate_check after_cas_reopen` |
| 8 | Optional: `facescan.dump` | (writes the full face data to `facescan\out`) |

Each check prints `PASS` or `FAIL` plus the first differences. A "probe" change is expected and
useful. The test face deliberately sets `Eyes_Big` = 0.8, which is above the CAS drag limit, and a
modifier that has no tuning entry. These show how CAS treats such values. Probe changes do not
count as failures.

### 2d. Analyse (read-only)

Quit the game (so the newest save is on disk), then double-click **`E2_check_results.bat`**. It:
- re-checks every checkpoint independently with the project's own codec
- opens the newest save file read-only and checks the Sim's stored face byte by byte against the
  expected face (`save_file_on_disk`)
- writes `report.md`, and zips the records, the report and the newest `lastException*.txt` to
  `Desktop\facescan_e2_results.zip`

**Send back:** `facescan_e2_results.zip`, plus your yes/no notes about whether the face visibly changed
in steps 3, 4 and 6.

### 2e. Clean up

Run **`E2_uninstall_mod.bat`** to remove the mod. You can delete the `FaceScan E2` save and the
`Documents\Electronic Arts\The Sims 4\facescan` folder.

## What each outcome means

| Result | Meaning | Next |
|---|---|---|
| All PASS, and the face changed visibly in step 3 | Live writing works and persists. The planned architecture is confirmed. | Build the calibration pipeline on real assets (E3) |
| PASS, but the face only changed after CAS or reload | Values persist, but live mode needs a refresh | Find the refresh call; the workflow can rely on Modify in CAS |
| `after_cas` FAIL on core modifiers | CAS rewrites or clamps values | Restrict the optimizer to what CAS keeps (the probe results show the rules) |
| `after_reload` / `save_file_on_disk` FAIL | Not persisted (for example, overwritten from genetics) | Also write the genetic copy, or apply through CAS |
| `facescan.info` not recognised | The mod didn't load | Check the script-mod setting, the mod list on start, and `lastException*.txt` |
| `facescan error: …` | A game API differs from what we assumed | Send the message; the mod is small and easy to fix |
