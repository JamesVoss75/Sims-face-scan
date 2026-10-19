# Third-party dependencies, sources and licence obligations

The project licence has **not been chosen yet**. This file lists everything the decision depends on.
It will be updated whenever a dependency or source is added.

## 1. Code copied or adapted into this repository

**None.** No source code from another project has been copied, translated or adapted.

The modules below implement *file formats and data layouts*. We learned these by reading
other projects' source code. The Python implementations were written independently:

| Our module | Formats/facts learned from | Their licence | How we used it |
|---|---|---|---|
| `ts4face/dbpf.py` | DBPF 2.1 package index; RefPack/QFS decompression | s4pi (GPL-3.0); RefPack is a long-documented public algorithm | Header and index field layout, compression type codes |
| `ts4face/facial_blob.py`, `ts4face/savegame.py` | protobuf field numbers of `BlobSimFacialCustomizationData`, `SaveGameData`, `SimData`, `GeneticData`; resource type `0x0000000D` | TS4 SimRipper (GPL-3.0); field numbers originate from EA's schema | Field numbers only. Codec and parser are our own |
| `ts4face/resources.py` | Binary layouts of SimModifier, Sculpt, BoneDelta, HotSpotControl, CASPreset | TS4 MorphMaker / TS4 SimRipper (GPL-3.0) | Field order and versions. Our own reader classes |
| `ts4face/fnv.py` | FNV-1 64/32 hashing of lowercased names for instance IDs | Public-domain algorithm; usage seen in MorphMaker | Algorithm constants (public) |
| `mod/facescan_bridge/facescan_bridge.py` | That `sim_info.facial_attributes` and `protocolbuffers.PersistenceBlobs_pb2` can be used from a script mod | Sims4SlowGrowthMod (MIT) | API pattern only |
| `ts4face/catalog.py`, `tools/*` | EA tuning XML structure (`Client_CASModifierTuning`) | Observed in EA data shipped with SimRipper | Element names |

**Assessment, which is not legal advice:** file formats, field numbers and API names are
functional facts. Reimplementing them is generally not considered creating a derivative work. Some
people still take the conservative view that code written after studying GPL code should be GPL.
**If the project is released under GPL-3.0, this question disappears.** If you want a
non-GPL licence, we can document the clean-room boundary more formally before release. We will
**not** copy further GPL code. Mesh/DMAP/BOND evaluation (Phase 2) will also be implemented
independently from format notes. SimRipper's output will be used only as a black-box reference to
compare results.

## 2. Software dependencies

| Package | Used by | Licence | Obligation |
|---|---|---|---|
| Python standard library | all tools (E1, E1b, E2 check need nothing else) | PSF | none for use |
| numpy | `ts4face.linear_model` | BSD-3-Clause | keep notice when redistributing |
| scipy | `ts4face.linear_model` (bounded least squares) | BSD-3-Clause | keep notice when redistributing |
| protobuf (Python) | tests only (reference codec cross-check) | BSD-3-Clause | none (dev only) |
| pytest | tests only | MIT | none (dev only) |
| PowerShell / Windows built-ins | `scripts/windows/*.ps1` | part of Windows | none |
| CPython 3.7 | builds the in-game mod bytecode on the user's PC | PSF | not redistributed |
| MediaPipe (Python) | `faceanalysis.landmarks`: 478 facial landmarks, head pose, blendshapes | Apache-2.0 | keep licence/NOTICE when redistributing |
| MediaPipe Face Landmarker model (`face_landmarker.task`) | model weights, downloaded by `tools/fetch_face_models.py` into the git-ignored `models/` folder, SHA-256 pinned | Apache-2.0 (Google model card) | not committed; attribution if bundled |
| opencv-python-headless | segmentation, colour conversion, image ops | Apache-2.0 (bundles third-party libraries with their own notices) | keep notices |
| Pillow | image I/O and diagnostic drawing | MIT-CMU (HPND) | keep notice |
| matplotlib | comparison chart | Matplotlib licence (PSF-style) | keep notice |

The facial-analysis code (`faceanalysis/`) is original. It uses only the libraries above. No code was adapted
from face-analysis research projects.

Planned (not yet used):

| Package / asset | Purpose | Licence | Note |
|---|---|---|---|
| FLAME **2023 Open** model | statistical 3D head for measuring proportions | CC-BY-4.0 | attribution. **Other FLAME versions are non-commercial and must not be used.** Model files are downloaded by the user and never committed (`.gitignore`) |
| MediaPipe→FLAME landmark embedding | landmark correspondence | to be confirmed | check before use |
| PySide6 | desktop UI | LGPL-3.0 | dynamic linking; ship licence text |

Explicitly **not** used in shipped code: Pixel3DMM, MICA, DECA/EMOCA, SMIRK (non-commercial),
InsightFace model weights (non-commercial), dlib 68-point model (restricted training data).

## 3. Game content

- No EA game files, extracted tuning, meshes, textures, catalog output or save files are in this
  repository. `.gitignore` blocks the usual file types and output folders.
- The tools read the user's own installation locally. Any calibration data derived from EA assets
  stays on the user's machine.
- The in-game mod imports EA's own modules (`services`, `sims4`, `protocolbuffers`) at runtime and
  does not redistribute them.
- Distribution of mods is subject to EA's published modding guidelines (free, non-commercial mods).

## 4. Reference projects (read, not included)

- TS4 SimRipper, https://github.com/CmarNYC-Tools/TS4SimRipper (GPL-3.0)
- TS4 MorphMaker, https://github.com/CmarNYC-Tools/TS4MorphMaker (GPL-3.0)
- Sims4Tools / s4pi / s4pe, https://github.com/s4ptacle/Sims4Tools (GPL-3.0)
- Sims4SlowGrowthMod, https://github.com/TwidWawMon/Sims4SlowGrowthMod (MIT)
