# FaceScan bridge mod: experiment E2

A small script mod that reads and writes the active Sim's facial data from the
cheat console. It exists to settle the Phase 1 questions that can only be
answered inside the running game. **It has not been run in the game yet.**

## Safety rules

- Use a new, throwaway save with a throwaway household. Do not load a real save
  while the mod is installed.
- Back up `Documents/Electronic Arts/The Sims 4/saves` before you start.
- Remove the `.ts4script` from `Mods` when the experiment is over.
- The mod only changes the active Sim's `facial_attributes`, and only when you
  run a command. It writes files only to `Documents/Electronic Arts/The Sims 4/facescan/`.

## Build and install

1. Install Python 3.7 (the game's embedded version; see below to confirm it).
2. Run `py -3.7 mod/build.py`. This produces `mod/dist/facescan_bridge.ts4script`.
3. Copy it to `Documents/Electronic Arts/The Sims 4/Mods/`.
4. In Game Options → Other, enable **Custom Content and Mods** and **Script
   Mods Allowed**, then restart the game.

## Protocol

Open the cheat console with Ctrl+Shift+C, then do each step and write down the result.

| # | Step | Question it answers |
|---|------|---------------------|
| 1 | In a new household, make a Young Adult Sim. In CAS, drag **one** feature (for example, make the nose wider). Enter live mode and run `facescan.dump`. | Does the dump show that one change as a single face modifier key with an amount in (0, 1]? Does the key match `fnv64("yfheadNose_Wide")`? |
| 2 | Run `facescan.set <key from step 1> 0` | Does the face update **immediately** in live mode, or only after a reload or travel? |
| 3 | Run `facescan.set 0x<key> 1.0` for the opposite-direction modifier (Nose_Narrow). | Does the game accept a value CAS would not produce? Is the visual change sane? |
| 4 | Put a JSON file in `facescan/in/face.json` (copy one from `out/` and edit the amounts), then run `facescan.apply face.json`. | Does a bulk write of sculpts plus modifiers apply correctly? |
| 5 | Shift-click the Sim and choose **Modify in CAS** (requires `testingcheats true`). | Does CAS open with the scripted face? Can you keep editing? Does **Save to Library** export it to the Gallery/Tray? |
| 6 | Save, quit, and reload the save. Run `facescan.dump` again. | Does the change persist, and is it byte-identical? |
| 7 | Open CAS while the mod is installed, then run `facescan.set` from live mode afterwards. | Does anything in CAS react to script changes made while CAS is open? (Expected: no; CAS edits its own copy.) |
| 8 | Check `Documents/Electronic Arts/The Sims 4/lastException*.txt` after each step. | Did anything throw? |

Send back the `out/*.json` files, the console messages, and any `lastException`
files. Steps 2, 5 and 6 decide the automation architecture (see
`docs/02-automation-approaches.md`).

To confirm the embedded Python version, note the `python37.dll` name (or
similar) in the game's `Game/Bin` folder.
