# 6. Application architecture

## 6.1 Components

```
┌──────────────────────── Windows desktop app (Python 3.11+, local only) ─────────────────────────┐
│                                                                                                 │
│  UI (PySide6/Qt)                                                                                │
│   upload photos / sheet → choose age+frame → Generate → preview → refine → Apply to game        │
│        │                                                                                        │
│  ┌─────▼──────────┐   ┌──────────────────┐   ┌──────────────────────┐   ┌───────────────────┐   │
│  │ Face Analyzer  │──▶│ Likeness Mapper  │──▶│ Optimizer            │──▶│ Game Bridge client│   │
│  │ MediaPipe,     │   │ deviation        │   │ BVLS + sculpt search │   │ writes facescan/  │   │
│  │ FLAME fit,     │   │ transfer → target│   │ + polish             │   │ in/*.json, reads  │   │
│  │ quality gate   │   └──────────────────┘   └──────────▲───────────┘   │ out/*.json        │   │
│  └────────────────┘                                     │               └─────────┬─────────┘   │
│                         ┌───────────────────────────────┴──────┐                  │             │
│                         │ Sims Face Model (calibration DB)     │                  │             │
│                         │ built locally from game packages     │◀── Game Data     │             │
│                         │ + twin renderer (preview, validation)│    Extractor     │             │
│                         └──────────────────────────────────────┘    (read-only)   │             │
└───────────────────────────────────────────────────────────────────────────────────┼─────────────┘
                                                                                    │ files
┌───────────────────────── The Sims 4 (unmodified install) ─────────────────────────▼─────────────┐
│  Mods/facescan_bridge.ts4script: polls facescan/in, validates, backs up, sets                    │
│  sim_info.facial_attributes (+ later: skin tone, CAS parts), writes ack to facescan/out          │
│  User: Modify in CAS → tweak hair and clothes → Save to Library (shareable tray Sim)             │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Component | Language | Status in repo |
|---|---|---|
| `ts4face.dbpf`: package reader | Python | Working (zlib, RefPack, uncompressed); tested |
| `ts4face.facial_blob`: blob codec | Python | Working; checked against the protobuf runtime |
| `ts4face.fnv`, `ts4face.catalog`: ID hashing, tuning → axes | Python | Working; pairing is a heuristic until the HOTC parser exists |
| `tools/inventory_game_files.py`: E1 | Python | Done; builds the full slider catalog with self-checks. Run via `E1_inventory.bat` |
| `mod/facescan_bridge`: E2 | Python 3.7 (in game) | v0.2 with a disposable-Sim guard and validation checkpoints; logic verified on CPython 3.7; **untested in game** |
| Resource parsers (GEOM, RIG, SMOD, BGEO, DMAP, BOND, Sculpt, CPRE, HOTC) | Python/NumPy | Phase 2; port from SimRipper/MorphMaker (GPL-3, see §6.4) |
| Twin renderer | Python (pyrender/moderngl) or a minimal software rasterizer | Phase 2 |
| Face Analyzer | Python (MediaPipe, OpenCV, PyTorch-free FLAME fit in NumPy/SciPy) | Phase 3 |
| Mapper/Optimizer | Python (NumPy/SciPy) | Phase 4 |
| UI + packaging | PySide6, PyInstaller or Briefcase | Phase 7 |

Python for everything outside the game keeps one codebase and lets us reuse the vision libraries.
Nothing in the inner loop needs C# or a GPU.

## 6.2 Data flow and files

- `%LOCALAPPDATA%/FaceScan/model/<game-version>/<age>_<frame>.npz`: calibration DB (never shipped)
- `%LOCALAPPDATA%/FaceScan/sessions/<id>/`: fitted parameters, measurements, results. Photos are
  stored only if the user opts in.
- `Documents/Electronic Arts/The Sims 4/facescan/{in,out}/`: bridge mailbox (doc 02 §2.3)

## 6.3 User workflow (target)

1. Launch. On first run, the app finds the game folder, builds the calibration DB (~1–3 minutes), and
   installs the bridge mod after the user confirms. It shows how to enable script mods.
2. Upload photos (front and profile minimum; a six-view sheet plus originals is best). The app
   shows per-view quality and what it detected.
3. Choose age and frame. The default comes from the photos and the user can override it.
4. **Generate.** Analysis and optimization take seconds. The app shows 3 candidates, rendered on the
   twin from the front, 3/4 and profile, next to the photos, with a per-region likeness report.
5. Optional sliders for "distinctiveness" and per-region emphasis. These re-solve instantly.
6. **Apply to game.** The game must be running with a Sim selected in live mode. The bridge applies
   the face and the app confirms.
7. In the game: Modify in CAS → hair, clothes → Save / Save to Library.
8. Fallback if script mods are off: a **manual report** (which preset to pick per region, and which
   features to drag up or down and roughly how much). We should be honest that manual entry is
   approximate.

## 6.4 Licensing

The licence decision is still open. All obligations and sources are listed in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). No GPL code has been copied. Our format readers are
independent implementations, and Phase 2 continues that way.
