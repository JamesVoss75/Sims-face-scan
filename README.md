# Sims Face Scan

Turn photographs of a real person into a Sims 4 face built only from the game's own CAS sculpts and
facial modifiers. No custom meshes and no photo textures.

> **Status:** Phase 1 (game integration proof). The tools, the in-game test mod and the solver core are
> written and tested **offline** (239 automated tests). **Nothing has been run against the real game
> yet.** The game integration is unproven until experiments E1 and E2 pass on a Windows PC.
> Start here: **[docs/windows-testing.md](docs/windows-testing.md)**.

## Approach (summary)

1. **Write the face directly.** A Sim's face is a small protobuf blob: sculpts plus (SimModifier ID,
   amount 0–1). A tiny script mod sets it on a Sim in live mode. The user then previews it in
   Modify in CAS and uses Save to Library.
2. **Calibrate from game assets.** Each modifier's deformation is stored as BGEO/DMAP/BOND data.
   A local "digital twin" of the head computes it, and in-game captures check the twin (E3).
3. **Solve for real IDs and values.** Photos become a neutral 3D face and measurements. These are
   mapped by deviation from average (this keeps distinctive features and avoids generic "pretty"
   faces), then fitted with bounded least squares to **concrete SMOD IDs, sculpt and preset IDs, and
   amounts**.

## Repository layout

| Path | What | Verified |
|---|---|---|
| `E1_inventory.bat` | **Experiment 1**: read-only inventory of game face data plus codec check on your saves | Logic tested offline |
| `E2_install_mod.bat`, `E2_check_results.bat`, `E2_uninstall_mod.bat` | **Experiment 2**: install the test mod, analyse results, remove it | Scripts parse-checked with PowerShell 7; helpers run-tested |
| `ts4face/dbpf.py` | Read-only `.package` reader | Real EA tuning package read |
| `ts4face/facial_blob.py` | Face blob codec: all fields, aged lists, presence, packed, unknown fields | 200 fuzz cases byte-identical with the protobuf runtime |
| `ts4face/savegame.py` | Read-only save-file reader (Sims → face blobs) | Synthetic saves |
| `ts4face/resources.py` | SMOD, Sculpt, BOND, HOTC, CPRE parsers | Synthetic data; E1 validates on real files |
| `ts4face/catalog.py`, `fnv.py` | Tuning → modifiers → axes; ID hashing | 947/957 EA IDs match |
| `ts4face/linear_model.py` | Linear face model + bounded solver → SMOD IDs and amounts | Synthetic recovery tests |
| `tools/inventory_game_files.py` | E1 slider catalog with self-checks | Synthetic install |
| `tools/verify_blob_codec.py` | E1b codec check on real saves (read-only) | Synthetic saves |
| `tools/check_validation.py` | E2 analysis, including an independent on-disk save check | Offline end-to-end rehearsal |
| `mod/` | In-game bridge mod (Python 3.7) and its build | Logic runs under CPython 3.7.17 with stub game modules; **not run in game** |

## Documents

| | |
|---|---|
| [docs/windows-testing.md](docs/windows-testing.md) | **How to run E1/E2 on your PC** |
| [docs/01-sims4-face-system.md](docs/01-sims4-face-system.md) | How the game stores and deforms faces |
| [docs/02-automation-approaches.md](docs/02-automation-approaches.md) | Script mod vs tray/save writing vs CAS automation |
| [docs/03-calibration.md](docs/03-calibration.md), [docs/09-calibration-and-fidelity.md](docs/09-calibration-and-fidelity.md) | Asset-based calibration; twin-vs-game accuracy plan (E3) |
| [docs/04-face-analysis.md](docs/04-face-analysis.md) | Photo analysis |
| [docs/05-mapping-and-optimization.md](docs/05-mapping-and-optimization.md) | Face → Sims settings |
| [docs/06-architecture.md](docs/06-architecture.md) | Components and communication |
| [docs/07-feasibility-and-risks.md](docs/07-feasibility-and-risks.md) | Status labels, limits, risks |
| [docs/08-roadmap-and-mvp.md](docs/08-roadmap-and-mvp.md) | MVP and roadmap |
| [docs/10-findings-log.md](docs/10-findings-log.md) | What we learned in each round, and how it changed the plan |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | Dependencies, sources, licence obligations |

## Development

```
pip install -r requirements-dev.txt
python -m pytest
```

The project licence has not been chosen yet. See THIRD_PARTY_NOTICES.md.
